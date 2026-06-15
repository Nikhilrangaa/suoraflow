"""
tasks.py — RQ task definitions.

Phase 0: skeleton only. The full pipeline (probe → extract_audio → vad →
transcribe → diarize → chunk → embed) will be implemented in later phases.
"""
import logging

logger = logging.getLogger(__name__)


def process_asset(asset_id: str) -> None:
    """
    Process a media asset through the full pipeline.

    Statuses: uploaded → probing → extracting_audio → vad → transcribing
              → diarizing → chunking → embedding → ready  (or failed)

    Phase 0 stub — pipeline logic deferred to Phase 2.
    """
    logger.info("process_asset called for asset_id=%s (pipeline not yet implemented)", asset_id)
    # TODO Phase 2: implement the full pipeline here
