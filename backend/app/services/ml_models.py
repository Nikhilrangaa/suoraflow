"""
ml_models.py — Lazy singletons for heavyweight ML models.

Models load on first use and are cached for the process lifetime:
- the worker loads Whisper (+ embedder during the embedding step),
- the backend only ever loads the embedder, lazily, for query embedding.

Nothing here downloads at import time; weights come from the shared
model_cache volume (pre-warmable via scripts/warm_models.py).
"""
import logging
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_whisper_model: Optional[Any] = None
_embedding_model: Optional[Any] = None
_diarization_pipeline: Optional[Any] = None
_diarization_failed = False


def get_whisper_model():
    """Return the cached faster-whisper model, loading it on first call."""
    global _whisper_model
    if _whisper_model is None:
        settings = get_settings()
        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model=%s device=%s compute=%s",
            settings.whisper_model, settings.whisper_device, settings.whisper_compute_type,
        )
        _whisper_model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _whisper_model


def get_embedding_model():
    """Return the cached sentence-transformers model, loading it on first call."""
    global _embedding_model
    if _embedding_model is None:
        settings = get_settings()
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model=%s", settings.embedding_model)
        _embedding_model = SentenceTransformer(settings.embedding_model, device="cpu")
    return _embedding_model


def get_diarization_pipeline():
    """
    Return the pyannote diarization pipeline, or None when unavailable.

    Unavailable means any of: no HF_TOKEN, pyannote not installed, or the
    pipeline failed to load. All are non-fatal by design — the caller falls
    back to single-speaker labelling and the pipeline continues.
    """
    global _diarization_pipeline, _diarization_failed
    if _diarization_pipeline is not None:
        return _diarization_pipeline
    if _diarization_failed:
        return None

    settings = get_settings()
    if not settings.hf_token:
        return None

    try:
        from pyannote.audio import Pipeline  # optional dependency

        logger.info("Loading pyannote speaker-diarization pipeline")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=settings.hf_token,
        )
        return _diarization_pipeline
    except Exception as exc:
        # Never fail the audio pipeline because diarization is unavailable.
        logger.warning("Diarization unavailable, falling back to single speaker: %s", exc)
        _diarization_failed = True
        return None
