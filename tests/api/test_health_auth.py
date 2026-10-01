import httpx
import pytest

from tests.api.standins import InMemoryStore


async def test_probes_need_no_token(client: httpx.AsyncClient) -> None:
    anon = {"Authorization": ""}
    assert (await client.get("/healthz", headers=anon)).json() == {"status": "ok"}
    assert (await client.get("/readyz", headers=anon)).status_code == 200
    metrics = await client.get("/metrics", headers=anon)
    assert metrics.status_code == 200
    assert "session_lens_queue_items" in metrics.text


@pytest.mark.parametrize(
    "path", ["/batches/1", "/sessions", "/sessions/1", "/stats/usage", "/stats/trends"]
)
@pytest.mark.parametrize("header", ["", "Bearer wrong", "Basic dGVzdC10b2tlbg=="])
async def test_auth_required(client: httpx.AsyncClient, path: str, header: str) -> None:
    resp = await client.get(path, headers={"Authorization": header})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_request_metrics_recorded(client: httpx.AsyncClient) -> None:
    await client.get("/stats/usage")
    text = (await client.get("/metrics")).text
    assert 'route="/stats/usage"' in text


async def test_static_ui_hides_python_sources(client: httpx.AsyncClient) -> None:
    anon = {"Authorization": ""}
    assert (await client.get("/__init__.py", headers=anon)).status_code == 404


async def test_readyz_503_when_store_down(client: httpx.AsyncClient, store: InMemoryStore) -> None:
    store.healthy = False
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/healthz")).status_code == 200


async def test_readyz_503_when_db_unreachable(database_url: str, store: InMemoryStore) -> None:
    from session_lens.api.app import create_app
    from session_lens.api.deps import get_store
    from session_lens.config import Settings

    bad = database_url.rsplit("@", 1)[0] + "@127.0.0.1:1/none"
    app = create_app(Settings(database_url=bad, api_token="t"))
    app.dependency_overrides[get_store] = lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/healthz")).status_code == 200
            assert (await c.get("/readyz")).status_code == 503
            assert (await c.get("/metrics")).status_code == 200
