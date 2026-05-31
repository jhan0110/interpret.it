"""ASR module: faster-whisper integration with word-level timestamps.

The `WordToken` dataclass is the shared interchange between ASR and the
prosody pipeline (for filler detection). Times are stored in **milliseconds**
to match WS contract and avoid float/seconds confusion.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

_model_cache: dict[str, object] = {}


@dataclass
class WordToken:
    word: str
    start_ms: int
    end_ms: int
    probability: float


@dataclass
class WordTimestampedTranscript:
    text: str
    words: list[WordToken]
    language: str
    duration_s: float


def _get_model(model_size: str | None = None) -> object:
    if model_size is None:
        model_size = os.environ.get("WHISPER_MODEL", "small")
    if model_size not in _model_cache:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "Local Whisper fallback requested but faster-whisper is not installed. "
                "Set WHISPER_PROVIDER=groq or reinstall the package."
            ) from exc

        device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _model_cache[model_size] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _model_cache[model_size]


def _download_from_minio(audio_path: str, local_path: str) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
    )
    bucket = os.environ.get("MINIO_BUCKET", "interpretit")
    client.download_file(bucket, audio_path, local_path)


def transcribe(audio_path: str, lang: Literal["ko", "en", "es"], prompt: str | None = None) -> WordTimestampedTranscript:
    """Dispatch to local faster-whisper or a remote provider per WHISPER_PROVIDER."""
    provider = os.environ.get("WHISPER_PROVIDER", "local")
    log.info("[asr.transcribe.dispatch] provider=%s audio_path=%s lang=%s", provider, audio_path, lang)
    if provider == "groq":
        from app.asr.transcribe_groq import transcribe as _remote_transcribe

        return _remote_transcribe(audio_path, lang, prompt)
    return _transcribe_local(audio_path, lang, prompt)


def _transcribe_local(audio_path: str, lang: Literal["ko", "en", "es"], prompt: str | None = None) -> WordTimestampedTranscript:
    """Local faster-whisper transcription (fallback / offline mode)."""
    import tempfile

    log.info("[asr.local.begin] audio_path=%s lang=%s", audio_path, lang)
    t0 = time.monotonic()

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        log.info("[asr.download.begin] audio_path=%s", audio_path)
        t_dl = time.monotonic()
        _download_from_minio(audio_path, tmp_path)
        dl_ms = int((time.monotonic() - t_dl) * 1000)
        log.info("[asr.download.done] audio_path=%s took=%dms", audio_path, dl_ms)
        model = _get_model()
        segments, info = model.transcribe(  # type: ignore[attr-defined]
            tmp_path,
            language=lang,
            word_timestamps=True,
            vad_filter=True,
            initial_prompt=prompt,
        )

        words: list[WordToken] = []
        full_text_parts: list[str] = []
        for segment in segments:
            full_text_parts.append(segment.text.strip())
            if segment.words:
                for w in segment.words:
                    words.append(
                        WordToken(
                            word=w.word,
                            start_ms=int(w.start * 1000),
                            end_ms=int(w.end * 1000),
                            probability=float(w.probability),
                        )
                    )

        result = WordTimestampedTranscript(
            text=" ".join(full_text_parts),
            words=words,
            language=info.language,
            duration_s=info.duration,
        )
        total_ms = int((time.monotonic() - t0) * 1000)
        log.info("[asr.local.done] audio_path=%s chars=%d words=%d took=%dms", audio_path, len(result.text), len(result.words), total_ms)
        return result
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
