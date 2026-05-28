"""TTS integration with content-hash caching in MinIO.

Two callers:
- `generate_feedback_audio` — short TTS for mid-session feedback playback.
- `generate_segment_audio` — full-sentence training segments, voice
  selected by source language.

Provider is chosen by the ``TTS_PROVIDER`` env var: ``openai`` (default,
gpt-4o-mini-tts via OpenRouter) or ``elevenlabs`` (legacy fallback).
Both cache by content hash so identical inputs reuse the same MinIO
object. In `USE_MOCKS=1` mode (the dev default), the real TTS request
is skipped; instead a silent mp3 of the target duration is generated
via pydub so the browser sees playable, correctly-sized audio.

The module filename is historical — kept to avoid churn in importers.
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

# OpenAI gpt-4o-mini-tts voices are multilingual; one voice per learner
# is fine — language is inferred from input text.
_OPENAI_DEFAULT_VOICE = "alloy"


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
    if os.environ.get("USE_MOCKS", "1") == "1":
        return True
    try:
        from app.spend import is_over_ceiling

        if is_over_ceiling():
            log.warning("[spend.ceiling] reached — TTS falling back to mock for the rest of the day")
            return True
    except Exception:  # noqa: BLE001 — spend module must never crash a caller
        log.exception("spend.is_over_ceiling check failed; proceeding with real TTS")
    return False


def _provider() -> str:
    return os.environ.get("TTS_PROVIDER", "openai").lower()


def voice_id_for_lang(lang: str) -> str:
    """Resolve the voice identifier for the given source language.

    For OpenAI TTS, voices are multilingual and we use a single configured
    voice (``OPENAI_TTS_VOICE``) regardless of language. For ElevenLabs,
    a per-language voice ID is selected.
    """
    if _provider() == "openai":
        return os.environ.get("OPENAI_TTS_VOICE", _OPENAI_DEFAULT_VOICE)
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


def _real_tts_elevenlabs(text: str, voice_id: str) -> bytes:
    from elevenlabs import ElevenLabs  # type: ignore[import-untyped]

    api_key = os.environ["ELEVENLABS_API_KEY"]
    client = ElevenLabs(api_key=api_key)
    log.info("[tts.elevenlabs.begin] voice=%s text_len=%d", voice_id, len(text))
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
    log.info("[tts.elevenlabs.done] voice=%s http_status=200 took=%dms bytes=%d", voice_id, req_ms, len(audio))
    return audio


def _real_tts_openai(text: str, voice: str) -> bytes:
    """Synthesize via OpenAI audio-out chat completions through OpenRouter.

    OpenRouter does not proxy the standalone ``/v1/audio/speech`` endpoint,
    but exposes ``openai/gpt-audio*`` chat models with ``audio`` output
    modality. The audio data is returned base64-encoded inside the
    assistant message; we decode and return the raw bytes.
    """
    import base64

    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY (or OPENAI_API_KEY) required for openai TTS")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    model = os.environ.get("OPENAI_TTS_MODEL", "openai/gpt-audio-mini")
    log.info("[tts.openai.begin] model=%s voice=%s text_len=%d", model, voice, len(text))
    t0 = time.monotonic()
    stream = client.chat.completions.create(
        model=model,
        modalities=["text", "audio"],
        audio={"voice": voice, "format": "pcm16"},
        stream=True,
        messages=[
            {
                "role": "system",
                "content": "Read the user's text aloud exactly as written, with no preamble.",
            },
            {"role": "user", "content": text},
        ],
    )
    audio_b64_parts: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        audio_delta = getattr(delta, "audio", None)
        if audio_delta is None:
            continue
        data = audio_delta.get("data") if isinstance(audio_delta, dict) else getattr(audio_delta, "data", None)
        if data:
            audio_b64_parts.append(data)
    if not audio_b64_parts:
        raise RuntimeError("audio output missing from chat completion stream")
    pcm_bytes = base64.b64decode("".join(audio_b64_parts))

    from pydub import AudioSegment  # type: ignore[import-untyped]

    segment = AudioSegment(
        data=pcm_bytes,
        sample_width=2,
        frame_rate=24000,
        channels=1,
    )
    mp3_buf = io.BytesIO()
    segment.export(mp3_buf, format="mp3")
    audio = mp3_buf.getvalue()
    req_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "[tts.openai.done] voice=%s took=%dms pcm_bytes=%d mp3_bytes=%d",
        voice, req_ms, len(pcm_bytes), len(audio),
    )
    return audio


def _real_tts(text: str, voice: str) -> bytes:
    if _provider() == "openai":
        return _real_tts_openai(text, voice)
    return _real_tts_elevenlabs(text, voice)


def _record_tts_spend(prefix: str, mock_duration_s: int) -> None:
    """Bump the daily spend counter for a TTS call.

    `prefix` and `mock_duration_s` together disambiguate the call kind:
    segments are typically 10-40s; feedback clips are ~3s. We classify
    short clips as 'feedback' for the spend bucket regardless of caller.
    """
    try:
        from app.spend import record_spend

        provider = _provider()
        kind_suffix = "feedback" if mock_duration_s <= 5 else "segment"
        record_spend(f"tts_{provider}_{kind_suffix}")
    except Exception:  # noqa: BLE001
        log.exception("spend.record_spend failed; continuing")


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
    if _use_mocks():
        audio_bytes = _silent_mp3(mock_duration_s)
    else:
        _record_tts_spend(prefix, mock_duration_s)
        audio_bytes = _real_tts(text, voice_id)
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


def _feedback_default_voice() -> str:
    if _provider() == "openai":
        return os.environ.get("OPENAI_TTS_VOICE", _OPENAI_DEFAULT_VOICE)
    return os.environ.get("ELEVENLABS_FEEDBACK_VOICE", _FEEDBACK_DEFAULT_VOICE)


def generate_feedback_audio(text: str, voice_id: str | None = None) -> str:
    """Generate TTS audio for in-session feedback playback. Returns MinIO key."""
    return _generate_and_store(
        text,
        voice_id or _feedback_default_voice(),
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
