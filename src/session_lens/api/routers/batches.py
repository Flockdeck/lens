"""Batch submission and management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from session_lens.api.deps import QueueApi, get_app_settings, get_db, get_queue
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
) -> BatchAccepted | JSONResponse:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_request_bytes:
        raise HTTPException(413, "request too large")
    try:
        form = await request.form(max_files=settings.max_files_per_batch, max_fields=10)
    except MultiPartException as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed multipart request") from exc
    try:
        parts = [p for p in form.getlist("files") if isinstance(p, UploadFile)]
        stored: list[tuple[str, RawRecording]] = []
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
            stored.append((name, await queue.store_raw(db, outcome)))
        if not stored:
            await db.rollback()
            log.info("batch rejected", extra={"rejected": len(rejected)})
            return JSONResponse(
                {
                    "detail": "no acceptable files",
                    "rejected": [r.model_dump() for r in rejected],
                },
                status_code=422,
            )
        batch = await queue.create_batch(db, stored)
        batch_id = batch.id
        await db.commit()
    finally:
        await form.close()
    log.info(
        "batch created",
        extra={"batch_id": batch_id, "accepted": len(stored), "rejected": len(rejected)},
    )
    return BatchAccepted(id=batch_id, accepted=[n for n, _ in stored], rejected=rejected)


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
