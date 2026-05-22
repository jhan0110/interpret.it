"""ElevenLabs TTS integration with content-hash caching in MinIO.

Two callers:
- `generate_feedback_audio` — short TTS for mid-session feedback playback.
- `generate_segment_audio` — full-sentence training segments, voice
  selected by source language.

Both cache by content hash so identical inputs reuse the same MinIO
object. In `USE_MOCKS=1` mode (the dev default), real ElevenLabs is
skipped; instead a silent mp3 of the target duration is generated via
pydub so the browser sees playable, correctly-sized audio.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import time

import boto3

log = logging.getLogger(__name__)

_s3_client = None

# Default placeholder voice IDs (override with env vars). The real
# voice catalogue lives at https://api.elevenlabs.io/v1/voices.
_DEFAULT_EN_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah — generic neutral en
_DEFAULT_KO_VOICE = "AZnzlk1XvdvUeBnXmlld"  # placeholder until a real ko voice is chosen
_FEEDBACK_DEFAULT_VOICE = _DEFAULT_EN_VOICE


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


def _use_mocks() -> bool:
    return os.environ.get("USE_MOCKS", "1") == "1"


def voice_id_for_lang(lang: str) -> str:
    """Resolve the ElevenLabs voice ID for the given source language."""
    env_key = f"ELEVENLABS_VOICE_{lang.upper()}"
    override = os.environ.get(env_key)
    if override:
        return override
    return _DEFAULT_EN_VOICE if lang == "en" else _DEFAULT_KO_VOICE


def _minio_key(text: str, voice_id: str, prefix: str = "tts") -> str:
    h = hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()[:16]
    return f"{prefix}/{h}.mp3"


def _object_exists(bucket: str, key: str) -> bool:
    try:
        _get_s3().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _silent_mp3(seconds: int) -> bytes:
    """Generate a playable silent mp3 of the given duration for mock mode."""
    from pydub import AudioSegment  # type: ignore[import-untyped]

    silent = AudioSegment.silent(duration=max(1, seconds) * 1000)
    buf = io.BytesIO()
    silent.export(buf, format="mp3")
    return buf.getvalue()


def _real_tts(text: str, voice_id: str) -> bytes:
    from elevenlabs import ElevenLabs  # type: ignore[import-untyped]

    api_key = os.environ["ELEVENLABS_API_KEY"]
    client = ElevenLabs(api_key=api_key)
    log.info("[tts.request.begin] voice=%s text_len=%d", voice_id, len(text))
    t0 = time.monotonic()
    audio = b"".join(
        client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            output_format="mp3_44100_128",
        )
    )
    req_ms = int((time.monotonic() - t0) * 1000)
    log.info("[tts.request.done] voice=%s http_status=200 took=%dms bytes=%d", voice_id, req_ms, len(audio))
    return audio


def _generate_and_store(
    text: str, voice_id: str, *, prefix: str, mock_duration_s: int
) -> str:
    log.info("[tts.begin] voice=%s text_len=%d mock=%s", voice_id, len(text), _use_mocks())
    t0 = time.monotonic()
    bucket = os.environ.get("MINIO_BUCKET", "interpretit")
    key = _minio_key(text, voice_id, prefix=prefix)
    if _object_exists(bucket, key):
        log.info("[tts.cache_hit] key=%s", key)
        return key
    audio_bytes = (
        _silent_mp3(mock_duration_s) if _use_mocks() else _real_tts(text, voice_id)
    )
    log.info("[tts.upload.begin] key=%s bytes=%d", key, len(audio_bytes))
    t_up = time.monotonic()
    _get_s3().put_object(
        Bucket=bucket, Key=key, Body=audio_bytes, ContentType="audio/mpeg"
    )
    up_ms = int((time.monotonic() - t_up) * 1000)
    log.info("[tts.upload.done] key=%s took=%dms", key, up_ms)
    total_ms = int((time.monotonic() - t0) * 1000)
    log.info("[tts.done] key=%s total_took=%dms", key, total_ms)
    return key


def generate_feedback_audio(text: str, voice_id: str | None = None) -> str:
    """Generate TTS audio for in-session feedback playback. Returns MinIO key."""
    return _generate_and_store(
        text,
        voice_id or _FEEDBACK_DEFAULT_VOICE,
        prefix="tts",
        mock_duration_s=3,
    )


def generate_segment_audio(
    text: str, source_lang: str, *, target_seconds: int = 10
) -> str:
    """Generate the playback audio for a training segment.

    Voice is selected by `source_lang` (override via `ELEVENLABS_VOICE_EN`
    / `ELEVENLABS_VOICE_KO`). In `USE_MOCKS=1` mode a silent mp3 of length
    `target_seconds` is produced — playable, correctly-sized, no API key.
    Returns the MinIO object key.
    """
    voice = voice_id_for_lang(source_lang)
    return _generate_and_store(
        text,
        voice,
        prefix="tts",
        mock_duration_s=target_seconds,
    )
