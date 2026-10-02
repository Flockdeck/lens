import httpx

from session_lens.storage.memory import InMemoryStore


async def test_probes_answer(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).status_code == 200
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "session_lens_queue_items" in metrics.text


async def test_request_metrics_recorded(client: httpx.AsyncClient) -> None:
    await client.get("/stats/usage")
    text = (await client.get("/metrics")).text
    assert 'route="/stats/usage"' in text


async def test_static_ui_hides_python_sources(client: httpx.AsyncClient) -> None:
    assert (await client.get("/__init__.py")).status_code == 404


async def test_readyz_503_when_store_down(client: httpx.AsyncClient, store: InMemoryStore) -> None:
    async def down() -> None:
        raise ConnectionError("store down")

    store.ping = down  # type: ignore[method-assign]
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/healthz")).status_code == 200


async def test_readyz_503_when_db_unreachable(database_url: str, store: InMemoryStore) -> None:
    from session_lens.api.app import create_app
    from session_lens.api.deps import get_store_provider
    from session_lens.config import Settings

    bad = database_url.rsplit("@", 1)[0] + "@127.0.0.1:1/none"
    app = create_app(Settings(database_url=bad, allowed_hosts=["test"]))
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/healthz")).status_code == 200
            assert (await c.get("/readyz")).status_code == 503
            assert (await c.get("/metrics")).status_code == 200
