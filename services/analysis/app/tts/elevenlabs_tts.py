"""ElevenLabs TTS integration with content-hash caching in MinIO."""

from __future__ import annotations

import hashlib
import os

import boto3

_s3_client = None


def _get_s3() -> boto3.client:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
            aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        )
    return _s3_client


def _minio_key(text: str, voice_id: str) -> str:
    h = hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()[:16]
    return f"tts/{h}.mp3"


def _object_exists(bucket: str, key: str) -> bool:
    try:
        _get_s3().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def generate_feedback_audio(text: str, voice_id: str) -> str:
    """Generate TTS audio via ElevenLabs, cache by content hash, return MinIO key.

    If identical (text, voice_id) was already generated, returns the cached path
    without re-calling ElevenLabs.
    """
    from elevenlabs import ElevenLabs  # type: ignore[import-untyped]

    bucket = os.environ.get("MINIO_BUCKET", "interpretit")
    key = _minio_key(text, voice_id)

    if _object_exists(bucket, key):
        return key

    api_key = os.environ["ELEVENLABS_API_KEY"]
    client = ElevenLabs(api_key=api_key)

    audio_bytes = b"".join(
        client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            output_format="mp3_44100_128",
        )
    )

    _get_s3().put_object(Bucket=bucket, Key=key, Body=audio_bytes, ContentType="audio/mpeg")
    return key


def generate_segment_audio(text: str, voice_id: str, segment_id: str) -> str:
    """Generate and store scenario playback audio for a segment.

    Returns the MinIO key for the stored audio. Uses content-hash dedup.
    """
    return generate_feedback_audio(text, voice_id)
