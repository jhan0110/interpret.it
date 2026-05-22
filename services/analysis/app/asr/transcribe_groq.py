"""Remote ASR via Groq's Whisper-large-v3 endpoint.

Groq exposes an OpenAI-compatible /audio/transcriptions endpoint that runs
Whisper on their LPU silicon (~0.5s for 10s of audio). Removes the largest
local model from the analysis service.

Env vars:
    GROQ_API_KEY        — required when WHISPER_PROVIDER=groq
    GROQ_WHISPER_MODEL  — default "whisper-large-v3"
                          alternatives: "whisper-large-v3-turbo"
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Literal

import httpx

from app.asr.transcribe import (
    WordTimestampedTranscript,
    WordToken,
    _download_from_minio,
)

log = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_DEFAULT_MODEL = "whisper-large-v3"


def transcribe(audio_path: str, lang: Literal["ko", "en"]) -> WordTimestampedTranscript:
    """Transcribe an audio blob stored in MinIO via the Groq API."""
    log.info("[asr.groq.begin] audio_path=%s lang=%s", audio_path, lang)
    t0 = time.monotonic()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set but WHISPER_PROVIDER=groq")
    model = os.environ.get("GROQ_WHISPER_MODEL", _DEFAULT_MODEL)

    with tempfile.NamedTemporaryFile(
        suffix=Path(audio_path).suffix or ".webm", delete=False
    ) as tmp:
        tmp_path = tmp.name

    try:
        log.info("[asr.download.begin] audio_path=%s", audio_path)
        t_dl = time.monotonic()
        _download_from_minio(audio_path, tmp_path)
        dl_ms = int((time.monotonic() - t_dl) * 1000)
        log.info("[asr.download.done] audio_path=%s took=%dms", audio_path, dl_ms)

        with open(tmp_path, "rb") as audio_file:
            files = {"file": (Path(audio_path).name, audio_file, "audio/webm")}
            data = {
                "model": model,
                "language": lang,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            log.info("[asr.groq.request.begin] audio_path=%s model=%s lang=%s", audio_path, model, lang)
            t_req = time.monotonic()
            with httpx.Client(timeout=30.0) as client:
                r = client.post(_GROQ_URL, headers=headers, data=data, files=files)
                r.raise_for_status()
                payload = r.json()
            req_ms = int((time.monotonic() - t_req) * 1000)
            log.info("[asr.groq.request.done] audio_path=%s http_status=%d took=%dms", audio_path, r.status_code, req_ms)

        words = [
            WordToken(
                word=w["word"],
                start_ms=int(float(w["start"]) * 1000),
                end_ms=int(float(w["end"]) * 1000),
                probability=1.0,
            )
            for w in payload.get("words", [])
        ]
        result = WordTimestampedTranscript(
            text=payload.get("text", "").strip(),
            words=words,
            language=payload.get("language", lang),
            duration_s=float(payload.get("duration", 0.0)),
        )
        total_ms = int((time.monotonic() - t0) * 1000)
        log.info("[asr.groq.done] audio_path=%s chars=%d words=%d took=%dms", audio_path, len(result.text), len(result.words), total_ms)
        return result
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
