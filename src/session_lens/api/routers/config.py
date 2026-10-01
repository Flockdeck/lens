"""Non-secret runtime facts for the UI."""

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends

from session_lens.api.deps import get_app_settings
from session_lens.api.schemas import RuntimeConfig
from session_lens.config import Settings

router = APIRouter(tags=["config"])


def _version() -> str:
    try:
        return version("session-lens")
    except PackageNotFoundError:
        return "unknown"


@router.get(
    "/config",
    response_model=RuntimeConfig,
    description=(
        "Non-secret settings the UI shows. `raw_retention_days` of 0 means raw recordings are "
        "kept forever. `cleanup_interval_seconds` is null if retention is not run on a timer."
    ),
)
async def runtime_config(settings: Annotated[Settings, Depends(get_app_settings)]) -> RuntimeConfig:
    # Read through getattr so the endpoint keeps working while these settings are added.
    return RuntimeConfig(
        storage=getattr(settings, "storage", "filesystem"),
        enricher=settings.enricher,
        raw_retention_days=settings.raw_retention_days,
        cleanup_interval_seconds=getattr(settings, "cleanup_interval_seconds", None),
        version=_version(),
    )
