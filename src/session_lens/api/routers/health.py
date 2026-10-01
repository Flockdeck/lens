"""Unauthenticated probes and Prometheus metrics."""

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.deps import get_db, get_store
from session_lens.db.models import BatchItem

if TYPE_CHECKING:
    from session_lens.storage.base import RecordingStore

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    db: Annotated[AsyncSession, Depends(get_db)],
    store: Annotated["RecordingStore", Depends(get_store)],
) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
        await store.ping()
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


@router.get("/metrics")
async def metrics(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    registry: CollectorRegistry = request.app.state.registry
    gauge: Gauge = request.app.state.queue_depth
    try:
        rows = (
            await db.execute(select(BatchItem.status, func.count()).group_by(BatchItem.status))
        ).all()
        seen = {status.value: n for status, n in rows}
        for name in ("queued", "running", "done", "failed", "cancelled"):
            gauge.labels(status=name).set(seen.get(name, 0))
    except Exception:
        pass  # DB down: still serve process-level metrics
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
