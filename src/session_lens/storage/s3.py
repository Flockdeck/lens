"""S3-compatible store (DigitalOcean Spaces, MinIO) over aioboto3."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aioboto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from session_lens.storage.base import RecordingExpired

_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


class S3Store:
    def __init__(
        self, endpoint_url: str, region: str, bucket: str, access_key: str, secret_key: str
    ) -> None:
        self._bucket = bucket
        self._session = aioboto3.Session()
        self._client_args = {
            "endpoint_url": endpoint_url,
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        async with self._session.client("s3", **self._client_args) as client:
            yield client

    async def put(self, key: str, data: bytes) -> None:
        async with self._client() as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body: bytes = await response["Body"].read()
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in _MISSING_CODES:
                    raise RecordingExpired(key) from None
                raise
            return body

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def ping(self) -> None:
        async with self._client() as s3:
            await s3.head_bucket(Bucket=self._bucket)
