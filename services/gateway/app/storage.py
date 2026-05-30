"""MinIO blob storage helper (S3-compatible).

Audio submissions go here, keyed by attempt_id. The DB stores only the
MinIO key; signed playback URLs are minted on demand by `signed_get_url`.

boto3's client is sync and uses urllib3 under the hood. We:
- Cache a module-level client so each call doesn't rebuild the boto
  session (~5ms each).
- Provide `upload_attempt_async` which runs `put_object` in a thread
  pool so async handlers don't stall the event loop on every audio
  submit. `signed_get_url` stays sync because boto's URL-signing is
  CPU-only and faster than the wrap overhead.
"""

from __future__ import annotations

import asyncio
import os
import threading
from uuid import UUID

import boto3
from botocore.client import Config


_bucket_name: str | None = None
_client_singleton = None
_client_lock = threading.Lock()


def _bucket() -> str:
    global _bucket_name
    if _bucket_name is None:
        _bucket_name = os.getenv("MINIO_BUCKET", "interpretit")
    return _bucket_name


def _client():
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    with _client_lock:
        if _client_singleton is None:
            _client_singleton = boto3.client(
                "s3",
                endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
                aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                config=Config(signature_version="s3v4"),
                region_name=os.getenv("MINIO_REGION", "us-east-1"),
            )
    return _client_singleton


# WebM remains the only browser-emitted container we accept; if a future
# codec change needs `.mp4`, route through this helper rather than
# hardcoding a string at call sites.
def attempt_key(attempt_id: UUID, ext: str = "webm") -> str:
    return f"attempts/{attempt_id}.{ext}"


def upload_attempt(attempt_id: UUID, audio_bytes: bytes) -> str:
    """Synchronous put. Prefer `upload_attempt_async` from async paths."""
    key = attempt_key(attempt_id)
    _client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=audio_bytes,
        ContentType="audio/webm",
    )
    return key


async def upload_attempt_async(attempt_id: UUID, audio_bytes: bytes) -> str:
    """Async wrapper — runs the blocking S3 put in a thread pool.

    boto3 itself is synchronous; without the threadpool the FastAPI
    event loop is blocked for the duration of the network write
    (tens to hundreds of ms per blob under load).
    """
    return await asyncio.to_thread(upload_attempt, attempt_id, audio_bytes)


def signed_get_url(key: str, expires_in_s: int = 3600) -> str:
    """Mint a presigned GET URL for `key`.

    The SigV4 signature is computed against the **internal** MinIO endpoint
    (the host MinIO actually sees), then we rewrite just the URL's scheme
    + netloc to `MINIO_PUBLIC_ENDPOINT` for the browser. This way Caddy can
    use its default Host-rewriting behavior (proxy → upstream sends
    Host: minio:9000) and the signature still validates because MinIO
    receives the same host it was signed against.

    Signing against the public host instead would require Caddy to
    preserve the original Host header end-to-end, which proved brittle.
    """
    signed = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expires_in_s,
    )
    public_endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT")
    if not public_endpoint:
        return signed
    from urllib.parse import urlsplit, urlunsplit

    src = urlsplit(signed)
    pub = urlsplit(public_endpoint)
    return urlunsplit((pub.scheme, pub.netloc, src.path, src.query, src.fragment))


def ensure_bucket() -> None:
    """Create the bucket if missing. Idempotent — safe at startup."""
    client = _client()
    bucket = _bucket()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
