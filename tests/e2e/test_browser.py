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
from session_lens.runtime_settings import DynamicEnricher
from session_lens.storage.base import build_store
from session_lens.worker.loop import run_worker
from tests.e2e.conftest import make_settings, recording

sync_api = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser

FOOTER = "Local only · storage: filesystem · enrichment: mock · raw kept 30 days"


@dataclass
class LiveApp:
    url: str
    data_dir: pathlib.Path

    def upload(self, *files: tuple[str, bytes]) -> int:
        parts = [("files", (name, data, "application/x-ndjson")) for name, data in files]
        resp = httpx.post(f"{self.url}/batches", files=parts, timeout=30)
        assert resp.status_code == 202, resp.text
        return int(resp.json()["id"])

    def wait_idle(self, batch_id: int, within: float = 30.0) -> None:
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            body = httpx.get(f"{self.url}/batches/{batch_id}", timeout=10).json()
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
    settings = make_settings(database_url, data_dir, hosts=("127.0.0.1", "localhost"))
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
                DynamicEnricher(make_sessionmaker(engine), settings),
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
                launched = p.chromium.launch(
                    **options, args=["--host-resolver-rules=MAP rebound.example 127.0.0.1"]
                )
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


def open_app(page: sync_api.Page, app: LiveApp) -> None:
    page.goto(app.url + "/")
    page.wait_for_selector("#file-input", state="attached")


def test_the_whole_flow_in_a_browser(
    browser: sync_api.Browser, live_app: LiveApp, tmp_path: pathlib.Path
) -> None:
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.set_default_timeout(20000)
    watched = Watched(page, live_app.url)

    # --- opening it: no sign-in, no key, and the footer says what stays on this machine --------
    page.goto(live_app.url + "/")
    page.wait_for_selector("#file-input", state="attached")
    page.wait_for_function(
        "document.getElementById('status-text').textContent.includes('Local only')"
    )
    assert page.inner_text("#status-text").strip().endswith(FOOTER)
    assert page.locator("#nav a").count() == 4
    assert page.locator("img.brand-mark").count() == 1
    assert page.locator("#token, #signout").count() == 0
    assert "token" not in page.inner_text("body").lower()
    assert page.evaluate("sessionStorage.length + localStorage.length") == 0  # nothing stored

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
    open_app(page, live_app)
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

    open_app(page, live_app)

    # the skip link shows when focused, and Enter moves the focus to the main area
    page.focus(".skip")
    assert page.evaluate("document.querySelector('.skip').getBoundingClientRect().top") >= 0
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"

    # Tab walks the header in order, every stop draws the accent ring, and Enter follows a link
    page.focus(".brand")
    stops = []
    for _ in range(3):
        page.keyboard.press("Tab")
        stops.append(page.evaluate("document.activeElement.textContent.trim()"))
        ring = page.evaluate(
            "(() => { const s = getComputedStyle(document.activeElement);"
            " return [s.outlineStyle, s.outlineWidth, s.outlineColor]; })()"
        )
        assert ring == ["solid", "2px", "rgb(79, 209, 219)"], ring
    assert stops == ["Submit", "Sessions", "Insights"]
    page.focus("#nav a[href='#/sessions']")
    page.keyboard.press("Enter")
    page.wait_for_url("**/#/sessions")


def test_a_page_from_another_origin_cannot_write_and_a_rebound_name_is_refused(
    browser: sync_api.Browser, live_app: LiveApp
) -> None:
    """The two things that stand in for an API key, tried from a real browser."""
    batch_id = live_app.upload(("run.jsonl", recording("claude_full", "victim")))
    live_app.wait_idle(batch_id)
    page = browser.new_context().new_page()
    page.set_default_timeout(20000)

    # another site's page submits a form to the app: the browser sends that origin; it is refused
    page.set_content(
        f'<form id="f" method="post" action="{live_app.url}/batches/{batch_id}/cancel"></form>'
    )
    with page.expect_navigation():
        page.evaluate("document.getElementById('f').submit()")
    assert "cross-origin request refused" in page.inner_text("body")
    body = httpx.get(f"{live_app.url}/batches/{batch_id}", timeout=10).json()
    assert body["status"] != "cancelled"

    # the same for an upload, and nothing is stored (a fresh page, so not on the app's own origin)
    before = len(list(live_app.data_dir.rglob("*.jsonl")))
    page = browser.new_context().new_page()
    page.set_default_timeout(20000)
    page.set_content(
        f'<form id="f" method="post" action="{live_app.url}/batches" enctype="multipart/form-data">'
        '<input type="file" name="files"></form>'
    )
    with page.expect_navigation():
        page.evaluate("document.getElementById('f').submit()")
    assert "cross-origin request refused" in page.inner_text("body")
    assert len(list(live_app.data_dir.rglob("*.jsonl"))) == before

    # a host name that points at this machine but is not one of its own: refused (DNS rebinding)
    port = live_app.url.rsplit(":", 1)[1]
    response = page.goto(f"http://rebound.example:{port}/sessions")
    assert response is not None and response.status == 421
    assert "host not allowed" in page.inner_text("body")
    assert page.goto(live_app.url + "/healthz").status == 200  # its real name still works


def test_settings_change_the_footer_and_the_key_is_never_shown_again(
    browser: sync_api.Browser, live_app: LiveApp
) -> None:
    secret = "sk-ant-browser-test-0123456789"
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.set_default_timeout(20000)
    watched = Watched(page, live_app.url)
    open_app(page, live_app)
    page.wait_for_function(
        "document.getElementById('status-text').textContent.includes('Local only')"
    )

    page.click("#nav >> text=Settings")
    page.wait_for_selector("#s-enricher")
    assert page.locator("#s-warning").is_hidden()
    assert page.locator("#s-key").is_disabled()  # its group is off while Anthropic is not chosen

    # Anthropic with no key is refused, and says why.
    page.select_option("#s-enricher", "anthropic")
    assert page.locator("#s-warning").is_visible()
    page.click("text=Save settings")
    page.wait_for_selector("[role=alert]:has-text('API key')")

    page.fill("#s-key", secret)
    page.click("text=Save settings")
    page.wait_for_function(
        "document.getElementById('status-text').textContent.startsWith('Sends digests to')"
    )
    assert page.locator("#statusbar").get_attribute("data-state") == "remote"
    page.wait_for_selector("#s-key[placeholder^='A key is set']")
    assert page.input_value("#s-key") == ""
    assert secret not in page.content()

    page.reload()
    page.wait_for_selector("#s-key[placeholder^='A key is set']")
    assert page.input_value("#s-enricher") == "anthropic"
    assert secret not in page.content()

    # Back to the mock: the footer is local again, and the saved key can be removed.
    page.select_option("#s-enricher", "mock")
    page.click("text=Save settings")
    page.wait_for_function(
        "document.getElementById('status-text').textContent.startsWith('Local only')"
    )
    page.click("text=Remove saved key")
    page.wait_for_selector("#s-key[placeholder='sk-ant-...']")
    assert watched.foreign == []
    # The one refusal provoked above is the browser's only complaint.
    assert [e for e in watched.errors if "422" not in e] == []
    assert len(watched.errors) <= 1
