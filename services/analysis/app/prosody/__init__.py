"""Prosody analysis subpackage.

`run_prosody_pipeline` requires pydub/librosa/torch — heavy deps that are
not always available at import time (unit tests for cognitive_load and
filler_lexicon should not pull them). Import the pipeline directly from
`app.prosody.pipeline` when you need it.
"""

from app.prosody.filler_lexicon import FILLER_LEXICON

__all__ = ["FILLER_LEXICON"]
