"""The whole flow in a real browser, against a real server: the real app on a real port, the real
worker, real MySQL and the real filesystem store. Nothing is faked between click and database.

These need a browser. They use Microsoft Edge if it is installed, else Playwright's Chromium
(`uv run playwright install chromium`), and are skipped when neither can be launched.
"""

from __future__ import annotations

import asyncio
import pathlib
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
import uvicorn
from sqlalchemy import text

from session_lens.api.app import create_app
from session_lens.db.models import Base
from session_lens.db.session import make_engine, make_sessionmaker
from session_lens.enrich.base import build_enricher
from session_lens.storage.base import build_store
from session_lens.worker.loop import run_worker
from tests.e2e.conftest import AUTH, TOKEN, make_settings, recording

sync_api = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser

FOOTER = "Local only · storage: filesystem · enrichment: mock · raw kept 30 days"


@dataclass
class LiveApp:
    url: str
    data_dir: pathlib.Path

    def upload(self, *files: tuple[str, bytes]) -> int:
        parts = [("files", (name, data, "application/x-ndjson")) for name, data in files]
        resp = httpx.post(f"{self.url}/batches", files=parts, headers=AUTH, timeout=30)
        assert resp.status_code == 202, resp.text
        return int(resp.json()["id"])

    def wait_idle(self, batch_id: int, within: float = 30.0) -> None:
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            body = httpx.get(f"{self.url}/batches/{batch_id}", headers=AUTH, timeout=10).json()
            if body["counts"]["queued"] == 0 and body["counts"]["running"] == 0:
                return
            time.sleep(0.1)
        raise AssertionError("the batch did not finish")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_app(database_url: str, tmp_path: pathlib.Path) -> Iterator[LiveApp]:
    """uvicorn and the worker on one event loop in a thread, with an empty database."""
    port = _free_port()
    data_dir = tmp_path / "data"
    settings = make_settings(database_url, data_dir)
    leave = threading.Event()
    failure: list[BaseException] = []

    async def main() -> None:
        engine = make_engine(settings)
        async with engine.begin() as conn:
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        server = uvicorn.Server(
            uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
        )
        stop = asyncio.Event()
        worker = asyncio.create_task(
            run_worker(
                make_sessionmaker(engine),
                build_store(settings),
                build_enricher(settings),
                settings,
                stop,
            )
        )
        serving = asyncio.create_task(server.serve())
        await asyncio.to_thread(leave.wait)  # until the test is over
        stop.set()
        server.should_exit = True
        await asyncio.gather(worker, serving)
        await engine.dispose()

    def run() -> None:
        try:
            asyncio.run(main())
        except BaseException as exc:  # surfaced to the test below
            failure.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise AssertionError(f"the server did not start: {failure}")
    try:
        yield LiveApp(url=url, data_dir=data_dir)
    finally:
        leave.set()
        thread.join(timeout=30)
    assert not failure, failure


@pytest.fixture(scope="module")
def browser() -> Iterator[sync_api.Browser]:
    with sync_api.sync_playwright() as p:
        launched = None
        for options in ({"channel": "msedge"}, {}):
            try:
                launched = p.chromium.launch(**options)
                break
            except Exception:
                continue
        if launched is None:
            pytest.skip("no browser could be launched (uv run playwright install chromium)")
        yield launched
        launched.close()


class Watched:
    """What the page asked for and complained about while a test ran."""

    def __init__(self, page: sync_api.Page, base: str) -> None:
        self.foreign: list[str] = []
        self.errors: list[str] = []
        page.on(
            "request",
            lambda r: (
                None
                if r.url.startswith(base) or r.url.startswith("data:")
                else self.foreign.append(r.url)
            ),
        )
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)


def sign_in(page: sync_api.Page, app: LiveApp) -> None:
    page.goto(app.url + "/")
    page.fill("#token", TOKEN)
    page.click("button[type=submit]")
    page.wait_for_selector("#file-input", state="attached")


def test_the_whole_flow_in_a_browser(
    browser: sync_api.Browser, live_app: LiveApp, tmp_path: pathlib.Path
) -> None:
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.set_default_timeout(20000)
    watched = Watched(page, live_app.url)

    # --- sign in: a wrong token is refused, the right one is accepted -------------------------
    page.goto(live_app.url + "/")
    page.get_by_role("heading", name="API token").wait_for()
    assert "Status unavailable" in page.inner_text("#status-text")
    page.fill("#token", "not-the-token")
    page.click("button[type=submit]")
    page.wait_for_selector("text=That token was not accepted")
    # the one console error this flow is allowed: the browser logging the 401 it provoked on purpose
    assert watched.errors and all("401" in e for e in watched.errors), watched.errors
    watched.errors.clear()
    page.fill("#token", TOKEN)
    page.click("button[type=submit]")
    page.wait_for_selector("#file-input", state="attached")
    page.wait_for_function(
        "document.getElementById('status-text').textContent.includes('Local only')"
    )
    assert page.inner_text("#status-text").strip().endswith(FOOTER)
    assert page.locator("#nav a").count() == 3
    assert page.locator("img.brand-mark").count() == 1

    # --- submit: several files at once, an empty one flagged before anything is sent ----------
    files = {
        "claude_full.jsonl": recording("claude_full", "ui1"),
        "truncated.jsonl": recording("truncated", "ui2"),
        "cut_off.jsonl": recording("cut_off_last_line", "ui3"),
        "wrong_version.jsonl": recording("wrong_version"),
        "empty.jsonl": recording("empty"),
    }
    paths = []
    for name, data in files.items():
        path = tmp_path / name
        path.write_bytes(data)
        paths.append(str(path))
    page.set_input_files("#file-input", paths)
    page.wait_for_selector("text=Submit batch")
    assert "File is empty" in page.inner_text("body")
    assert "4 ready" in page.inner_text("body") and "1 will be skipped" in page.inner_text("body")
    page.click("text=Submit batch")
    page.wait_for_url("**/#/batches/*")

    # --- the batch runs and the page shows it, glyph and word --------------------------------
    page.wait_for_selector("button:has-text('Retry failed (1)')")
    page.wait_for_selector(".badge-failed")
    assert page.locator("tbody .badge-done").count() == 3
    assert page.locator("tbody .badge-failed").count() == 1
    assert "UnsupportedVersion" in page.inner_text("tbody")
    assert "empty.jsonl" in page.inner_text(".error-box")
    for badge in page.locator("tbody .badge").all():
        assert badge.locator(".glyph").count() == 1  # never colour alone

    # --- browse and filter -------------------------------------------------------------------
    page.click("text=View sessions")
    page.wait_for_selector("tbody tr")
    assert page.locator("tbody tr").count() == 3
    page.locator("select").filter(has=page.locator("option[value=stuck]")).select_option("stuck")
    page.click("button:has-text('Apply')")
    page.wait_for_function("document.querySelectorAll('tbody tr').length === 1")
    assert "stuck" in page.inner_text("tbody")

    # --- inspect: metrics, risky actions, raw events -----------------------------------------
    page.click("tbody a")
    page.wait_for_selector("text=Metrics")
    assert page.get_by_role("heading", name="Risky actions (3)").count() == 1
    assert "git_force_push" in page.inner_text("body")
    assert page.locator(".badge-stuck").count() >= 1
    page.click("text=Show raw events")
    page.wait_for_selector(".event")
    assert page.locator(".event").count() >= 5

    # --- re-enrich, then delete it ------------------------------------------------------------
    page.click("button:has-text('Re-enrich')")
    page.wait_for_selector(".toast:has-text('Re-enriched')")
    assert len(list(live_app.data_dir.rglob("*.jsonl"))) == 4  # every accepted upload is on disk
    page.click("button:has-text('Delete session')")
    page.wait_for_selector("dialog[open]")
    page.click("dialog[open] button:has-text('Delete')")
    page.wait_for_url("**/#/sessions")
    page.wait_for_function("document.querySelectorAll('tbody tr').length === 2")
    assert len(list(live_app.data_dir.rglob("*.jsonl"))) == 3  # its file went with it

    # --- insights --------------------------------------------------------------------------------
    page.click("#nav >> text=Insights")
    page.wait_for_selector("svg.chart")
    assert page.locator("svg.chart").count() >= 2
    assert page.get_by_role("heading", name="Compare").count() == 1

    # --- signing out returns to the prompt -------------------------------------------------------
    page.click("#signout")
    page.get_by_role("heading", name="API token").wait_for()

    # nothing left the machine, and the page never complained
    assert watched.foreign == []
    assert watched.errors == []


def test_a_phone_sized_screen_keeps_its_nav_and_does_not_scroll_sideways(
    browser: sync_api.Browser, live_app: LiveApp
) -> None:
    live_app.wait_idle(live_app.upload(("run.jsonl", recording("claude_full", "phone"))))
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    page.set_default_timeout(20000)
    watched = Watched(page, live_app.url)
    sign_in(page, live_app)
    assert page.locator("#nav a").first.is_visible()

    for route in ("sessions", "insights"):
        page.click(f"#nav >> text={route.capitalize()}")
        page.wait_for_selector("table" if route == "sessions" else "svg.chart")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0, f"{route} scrolls sideways by {overflow}px"
    assert watched.foreign == [] and watched.errors == []


def test_the_keyboard_reaches_everything_and_the_focus_is_visible(
    browser: sync_api.Browser, live_app: LiveApp
) -> None:
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.set_default_timeout(20000)

    # the token form works from the keyboard alone
    page.goto(live_app.url + "/")
    page.keyboard.type(TOKEN)  # the field has the focus when the prompt appears
    page.keyboard.press("Enter")
    page.wait_for_selector("#file-input", state="attached")

    # the skip link shows when focused, and Enter moves the focus to the main area
    page.focus(".skip")
    assert page.evaluate("document.querySelector('.skip').getBoundingClientRect().top") >= 0
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"

    # Tab walks the header in order, every stop draws the accent ring, and Enter follows a link
    page.focus(".brand")
    stops = []
    for _ in range(4):
        page.keyboard.press("Tab")
        stops.append(page.evaluate("document.activeElement.textContent.trim()"))
        ring = page.evaluate(
            "(() => { const s = getComputedStyle(document.activeElement);"
            " return [s.outlineStyle, s.outlineWidth, s.outlineColor]; })()"
        )
        assert ring == ["solid", "2px", "rgb(79, 209, 219)"], ring
    assert stops == ["Submit", "Sessions", "Insights", "Change token"]
    page.focus("#nav a[href='#/sessions']")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/sessions")
