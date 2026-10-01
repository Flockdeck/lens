"""Optional S3-compatible store (SeaweedFS, MinIO, ...) over aioboto3. Recordings only leave the
machine if you point this at a remote endpoint; the default store is the local filesystem.
Install with `pip install session-lens[s3]`."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any, Literal

from session_lens.storage.base import RecordingExpired

_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}
_NO_LIFECYCLE_CODES = {"NoSuchLifecycleConfiguration", "NoSuchLifecycle", "404"}


def _error_code(exc: Exception) -> str | None:
    response: dict[str, Any] = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code")
    return code if isinstance(code, str) else None


class S3Store:
    def __init__(
        self,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        addressing_style: Literal["auto", "path", "virtual"] = "auto",
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
    ) -> None:
        try:
            import aioboto3  # type: ignore[import-untyped]
            from botocore.config import Config  # type: ignore[import-untyped]
            from botocore.exceptions import ClientError  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("the s3 store needs aioboto3: install session-lens[s3]") from exc
        self._client_error: type[Exception] = ClientError
        self._bucket = bucket
        self._session = aioboto3.Session()
        self._client_args: dict[str, Any] = {
            "endpoint_url": endpoint_url,
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": addressing_style},
                retries={"mode": "standard", "max_attempts": 3},
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            ),
        }
        self._stack: AsyncExitStack | None = None
        self._client: Any = None
        self._lock: asyncio.Lock | None = None

    async def _s3(self) -> Any:
        """The shared client, opened on first use."""
        if self._client is None:
            self._lock = self._lock or asyncio.Lock()
            async with self._lock:
                if self._client is None:
                    stack = AsyncExitStack()
                    self._client = await stack.enter_async_context(
                        self._session.client("s3", **self._client_args)
                    )
                    self._stack = stack
        return self._client

    async def aclose(self) -> None:
        if self._stack is not None:
            stack, self._stack, self._client = self._stack, None, None
            await stack.aclose()

    async def put(self, key: str, data: bytes) -> None:
        s3 = await self._s3()
        await s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    async def get(self, key: str) -> bytes:
        s3 = await self._s3()
        try:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            async with response["Body"] as body:
                data: bytes = await body.read()
        except self._client_error as exc:
            if _error_code(exc) in _MISSING_CODES:
                raise RecordingExpired(key) from None
            raise
        return data

    async def delete(self, key: str) -> None:
        s3 = await self._s3()
        await s3.delete_object(Bucket=self._bucket, Key=key)

    async def ping(self) -> None:
        s3 = await self._s3()
        await s3.head_bucket(Bucket=self._bucket)

    async def expiry_days(self, prefix: str) -> int | None:
        s3 = await self._s3()
        try:
            response = await s3.get_bucket_lifecycle_configuration(Bucket=self._bucket)
        except self._client_error as exc:
            if _error_code(exc) in _NO_LIFECYCLE_CODES:
                return None
            raise
        days: list[int] = []
        for rule in response.get("Rules", []):
            if rule.get("Status") != "Enabled":
                continue
            expiration_days = rule.get("Expiration", {}).get("Days")
            if expiration_days is None:
                continue
            rule_prefix = rule.get("Filter", {}).get("Prefix", rule.get("Prefix", ""))
            if prefix.startswith(rule_prefix):
                days.append(int(expiration_days))
        return min(days) if days else None
