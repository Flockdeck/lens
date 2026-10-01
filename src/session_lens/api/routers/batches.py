"""Batch submission and management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from session_lens.api.deps import (
    QueueApi,
    StoreProvider,
    get_app_settings,
    get_db,
    get_queue,
    get_store_provider,
    provide_or_503,
)
from session_lens.api.schemas import BatchAccepted, BatchItemOut, BatchOut, RejectedFile
from session_lens.api.uploads import check_file
from session_lens.config import Settings
from session_lens.db.models import Batch, ItemStatus, RawRecording

router = APIRouter(prefix="/batches", tags=["batches"])
log = logging.getLogger("session_lens.api.batches")


async def load_batch(db: AsyncSession, batch_id: int) -> BatchOut:
    batch = (
        await db.execute(
            select(Batch)
            .where(Batch.id == batch_id)
            .options(selectinload(Batch.items))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "batch not found")
    items = sorted(batch.items, key=lambda i: i.id)
    counts = {s.value: 0 for s in ItemStatus}
    for item in items:
        counts[item.status.value] += 1
    return BatchOut(
        id=batch.id,
        status=batch.status.value,
        counts=counts,
        items=[
            BatchItemOut(
                id=i.id,
                filename=i.filename,
                status=i.status.value,
                attempts=i.attempts,
                error=i.error,
                session_id=i.session_id,
            )
            for i in items
        ],
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=BatchAccepted)
async def submit_batch(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store_provider: Annotated[StoreProvider, Depends(get_store_provider)],
) -> BatchAccepted | JSONResponse:
    # The request-wide size cap (declared or streamed) is enforced by BodySizeLimit.
    store = provide_or_503(store_provider, "object store")
    try:
        form = await request.form(max_files=settings.max_files_per_batch, max_fields=10)
    except MultiPartException as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed multipart request") from exc
    try:
        parts = [p for p in form.getlist("files") if isinstance(p, UploadFile)]
        accepted: list[tuple[str, RawRecording]] = []
        rejected: list[RejectedFile] = []
        total = 0
        for part in parts:
            name, outcome = await check_file(part, settings)
            if isinstance(outcome, RejectedFile):
                rejected.append(outcome)
                continue
            total += len(outcome)
            if total > settings.max_request_bytes:
                rejected.append(RejectedFile(filename=name, reason="request size limit exceeded"))
                continue
            # One file in memory at a time: put it in the store, then drop the bytes. If a later
            # step fails (or the transaction rolls back) after some puts, those objects are left
            # orphaned in the bucket; the bucket lifecycle rule expires them, and no raw_recordings
            # row points at them because the rows roll back with the transaction.
            try:
                raw = await queue.store_raw(db, store, outcome)
            except SQLAlchemyError:
                raise
            except Exception as exc:
                await db.rollback()
                log.error("object store put failed", extra={"exc_type": type(exc).__name__})
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, "object store unavailable"
                ) from exc
            accepted.append((name, raw))
        if not accepted:
            await db.rollback()
            log.info("batch rejected", extra={"rejected": len(rejected)})
            return JSONResponse(
                {
                    "detail": "no acceptable files",
                    "rejected": [r.model_dump() for r in rejected],
                },
                status_code=422,
            )
        batch = await queue.create_batch(db, store, accepted)
        batch_id = batch.id
        await db.commit()
    finally:
        await form.close()
    log.info(
        "batch created",
        extra={"batch_id": batch_id, "accepted": len(accepted), "rejected": len(rejected)},
    )
    return BatchAccepted(id=batch_id, accepted=[n for n, _ in accepted], rejected=rejected)


@router.get("/{batch_id}", response_model=BatchOut)
async def get_batch(batch_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> BatchOut:
    return await load_batch(db, batch_id)


@router.post("/{batch_id}/retry", response_model=BatchOut)
async def retry_batch(
    batch_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[QueueApi, Depends(get_queue)],
) -> BatchOut:
    await load_batch(db, batch_id)  # 404 if missing
    await queue.retry_failed(db, batch_id)
    await db.commit()
    log.info("batch retry", extra={"batch_id": batch_id})
    return await load_batch(db, batch_id)


@router.post("/{batch_id}/cancel", response_model=BatchOut)
async def cancel_batch(
    batch_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[QueueApi, Depends(get_queue)],
) -> BatchOut:
    await load_batch(db, batch_id)
    await queue.cancel_batch(db, batch_id)
    await db.commit()
    log.info("batch cancel", extra={"batch_id": batch_id})
    return await load_batch(db, batch_id)
