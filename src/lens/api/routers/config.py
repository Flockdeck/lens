"""Non-secret runtime facts for the UI."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from lens._version import app_version
from lens.api.deps import get_app_settings
from lens.api.schemas import RuntimeConfig
from lens.config import Settings
from lens.runtime_settings import effective_settings

router = APIRouter(tags=["config"])


@router.get(
    "/config",
    response_model=RuntimeConfig,
    description=(
        "Non-secret settings the UI shows. `raw_retention_days` of 0 means raw recordings are "
        "kept forever. `cleanup_interval_seconds` is null if retention is not run on a timer."
    ),
)
async def runtime_config(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> RuntimeConfig:
    settings = await effective_settings(request.app.state.sessionmaker, settings)
    return RuntimeConfig(
        storage="filesystem",  # recordings are files under data_dir
        enricher=settings.enricher,
        raw_retention_days=settings.raw_retention_days,
        cleanup_interval_seconds=getattr(settings, "cleanup_interval_seconds", None),
        version=app_version(),
    )
