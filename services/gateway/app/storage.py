"""MinIO blob storage helper (S3-compatible).

Audio submissions go here, keyed by attempt_id. The DB stores only the
MinIO key; signed playback URLs are minted on demand by `signed_get_url`.
"""

from __future__ import annotations

import os
from uuid import UUID

import boto3
from botocore.client import Config


def _bucket() -> str:
    return os.getenv("MINIO_BUCKET", "interpretit")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
        region_name=os.getenv("MINIO_REGION", "us-east-1"),
    )


def attempt_key(attempt_id: UUID) -> str:
    return f"attempts/{attempt_id}.webm"


def upload_attempt(attempt_id: UUID, audio_bytes: bytes) -> str:
    key = attempt_key(attempt_id)
    _client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=audio_bytes,
        ContentType="audio/webm",
    )
    return key


def signed_get_url(key: str, expires_in_s: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expires_in_s,
    )


def ensure_bucket() -> None:
    """Create the bucket if missing. Idempotent — safe at startup."""
    client = _client()
    bucket = _bucket()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
