"""ASR module: faster-whisper integration with word-level timestamps.

The `WordToken` dataclass is the shared interchange between ASR and the
prosody pipeline (for filler detection). Times are stored in **milliseconds**
to match WS contract and avoid float/seconds confusion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

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


def _get_model(model_size: str = "large-v3") -> object:
    if model_size not in _model_cache:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

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


def transcribe(audio_path: str, lang: Literal["ko", "en"]) -> WordTimestampedTranscript:
    """Transcribe audio from MinIO by key, returning word-level timestamps in ms."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _download_from_minio(audio_path, tmp_path)
        model = _get_model()
        segments, info = model.transcribe(  # type: ignore[attr-defined]
            tmp_path,
            language=lang,
            word_timestamps=True,
            vad_filter=True,
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

        return WordTimestampedTranscript(
            text=" ".join(full_text_parts),
            words=words,
            language=info.language,
            duration_s=info.duration,
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
