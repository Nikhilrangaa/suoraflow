"""
tasks.py — RQ task definitions.

process_asset drives an asset through the pipeline:
  uploaded → probing → extracting_audio → vad → transcribing → diarizing
           → chunking → embedding → ready   (or failed)

Status is persisted after every step so the UI can poll live progress.
Failures set status=failed with a short, safe error_message — never a stack
trace, never transcript content — and never crash the worker process.
"""
import logging
from pathlib import Path

from sqlmodel import Session, delete

from app.database import get_engine
from app.models.asset import Asset
from app.models.text_embedding import TextEmbedding
from app.models.transcript_segment import TranscriptSegment
from app.services import pipeline_service

logger = logging.getLogger(__name__)

# Human-readable step names for safe error messages
_STEP_LABEL = {
    "probing": "media probing",
    "extracting_audio": "audio extraction",
    "vad": "voice activity detection",
    "transcribing": "transcription",
    "diarizing": "speaker diarization",
    "chunking": "transcript chunking",
    "embedding": "semantic embedding",
}


def _set_status(session: Session, asset: Asset, status: str) -> None:
    asset.status = status
    session.add(asset)
    session.commit()
    session.refresh(asset)


def process_asset(asset_id: str) -> None:
    """Run the full processing pipeline for one asset. Idempotent per asset."""
    engine = get_engine()
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            logger.warning("process_asset: asset %s not found; skipping", asset_id)
            return

        current_step = "probing"
        try:
            stored_path = Path(asset.stored_path)
            if not stored_path.exists():
                raise FileNotFoundError("Stored media file is missing")

            # --- probe -------------------------------------------------
            _set_status(session, asset, "probing")
            probe = pipeline_service.probe_asset(stored_path)
            asset.duration = probe.duration
            asset.width = probe.width
            asset.height = probe.height
            asset.fps = probe.fps
            asset.sample_rate = probe.sample_rate
            asset.channels = probe.channels
            asset.audio_codec = probe.audio_codec
            session.add(asset)
            session.commit()

            if not probe.has_audio:
                # B-roll without audio is valid footage: finish gracefully
                # with an empty transcript rather than failing the asset.
                asset.speech_ratio = 0.0
                asset.vad_segment_count = 0
                _set_status(session, asset, "ready")
                logger.info("Asset %s has no audio stream; marked ready", asset_id)
                return

            # --- extract audio + waveform peaks ------------------------
            current_step = "extracting_audio"
            _set_status(session, asset, "extracting_audio")
            wav_path, waveform_path = pipeline_service.audio_artifact_paths(
                asset.project_id, asset.id
            )
            pipeline_service.extract_audio(stored_path, wav_path, waveform_path)
            asset.audio_path = str(wav_path)
            asset.waveform_path = str(waveform_path)
            session.add(asset)
            session.commit()

            # --- VAD ----------------------------------------------------
            current_step = "vad"
            _set_status(session, asset, "vad")
            vad = pipeline_service.run_vad(wav_path)
            asset.speech_ratio = vad.speech_ratio
            asset.vad_segment_count = vad.segment_count
            session.add(asset)
            session.commit()

            # --- transcribe ----------------------------------------------
            current_step = "transcribing"
            _set_status(session, asset, "transcribing")
            result = pipeline_service.transcribe(wav_path)

            # --- diarize (optional, never fails) -------------------------
            current_step = "diarizing"
            _set_status(session, asset, "diarizing")
            segments = pipeline_service.diarize(wav_path, result.segments)

            # Replace any existing segments (idempotent re-processing)
            session.exec(
                delete(TranscriptSegment).where(TranscriptSegment.asset_id == asset.id)
            )
            for i, seg in enumerate(segments):
                session.add(
                    TranscriptSegment(
                        asset_id=asset.id,
                        seg_index=i,
                        start=seg.start,
                        end=seg.end,
                        text=seg.text,
                        speaker=seg.speaker,
                    )
                )
            session.commit()

            # --- chunk ----------------------------------------------------
            current_step = "chunking"
            _set_status(session, asset, "chunking")
            chunks = pipeline_service.chunk_segments(segments)

            # --- embed ----------------------------------------------------
            current_step = "embedding"
            _set_status(session, asset, "embedding")
            vectors = pipeline_service.embed_texts([c.text for c in chunks])

            # Replace any existing embeddings (idempotent re-processing)
            session.exec(
                delete(TextEmbedding).where(TextEmbedding.asset_id == asset.id)
            )
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                session.add(
                    TextEmbedding(
                        asset_id=asset.id,
                        chunk_index=i,
                        start=chunk.start,
                        end=chunk.end,
                        text=chunk.text,
                        embedding=vec,
                    )
                )
            session.commit()

            _set_status(session, asset, "ready")
            logger.info(
                "Asset %s ready: %d transcript segments, %d chunks, speech_ratio=%s",
                asset_id, len(segments), len(chunks), asset.speech_ratio,
            )
        except Exception as exc:
            # Short, safe message only — no stack traces, no transcript text.
            label = _STEP_LABEL.get(current_step, current_step)
            logger.error(
                "process_asset failed for %s during %s: %s",
                asset_id, label, type(exc).__name__,
            )
            try:
                asset.status = "failed"
                asset.error_message = f"Processing failed during {label}."
                session.add(asset)
                session.commit()
            except Exception:
                logger.error("Could not persist failed status for asset %s", asset_id)
