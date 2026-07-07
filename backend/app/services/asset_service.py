"""Asset service — safe upload, list, get, delete, transcript, media."""
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import IO

from fastapi import HTTPException, UploadFile

from sqlmodel import Session, select

from app.config import get_settings
from app.models.asset import Asset
from app.models.project import Project
from app.models.transcript_segment import TranscriptSegment
from app.schemas.asset import (
    AssetRead,
    AssetStatus,
    TranscriptRead,
    TranscriptSegmentRead,
    WaveformRead,
)
from app.utils.ffmpeg import validate_media_type
from app.utils.file_validation import (
    ALLOWED_EXTENSIONS,
    generate_asset_id,
    safe_asset_path,
    validate_extension,
)
from app.workers.queue import get_queue

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB streaming chunk


def _asset_to_read(asset: Asset) -> AssetRead:
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        original_filename=asset.original_filename,
        media_type=asset.media_type,
        ext=asset.ext,
        size_bytes=asset.size_bytes,
        status=asset.status,
        error_message=asset.error_message,
        sample_rate=asset.sample_rate,
        channels=asset.channels,
        audio_codec=asset.audio_codec,
        duration=asset.duration,
        width=asset.width,
        height=asset.height,
        fps=asset.fps,
        speech_ratio=asset.speech_ratio,
        vad_segment_count=asset.vad_segment_count,
        created_at=asset.created_at,
    )


def create_asset_from_upload(
    session: Session,
    project_id: str,
    upload: UploadFile,
) -> AssetRead:
    """Safe upload path — streams to disk, validates, enqueues."""
    settings = get_settings()

    # 1. Confirm project exists
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Validate extension — raises ValueError if disallowed
    filename = upload.filename or ""
    try:
        ext = validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Derive media_type from which set the extension belongs to
    media_type = "video" if ext in ALLOWED_EXTENSIONS["video"] else "audio"

    # 3. Generate safe stored path (UUID-based, never uses uploaded filename)
    asset_id = generate_asset_id()
    stored_path = safe_asset_path(settings.storage_root, project_id, asset_id, ext)

    # 4. Stream upload to disk, enforcing MAX_UPLOAD_MB
    max_bytes = settings.max_upload_mb * 1024 * 1024
    size_bytes = 0
    partial_written = False
    try:
        with open(stored_path, "wb") as f:
            partial_written = True
            while True:
                chunk = upload.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    # Abort: remove partial file
                    f.close()
                    _remove_file_safe(stored_path)
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Upload exceeds the {settings.max_upload_mb} MB limit."
                        ),
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if partial_written:
            _remove_file_safe(stored_path)
        raise HTTPException(
            status_code=500, detail="Failed to write uploaded file."
        ) from exc

    # 5. ffprobe media-type validation — reject files whose bytes don't match extension
    try:
        validate_media_type(stored_path, media_type)
    except (ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        _remove_file_safe(stored_path)
        msg = str(exc) if isinstance(exc, ValueError) else (
            "File content could not be validated as a media file."
        )
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        _remove_file_safe(stored_path)
        raise HTTPException(
            status_code=400,
            detail="File content could not be validated as a media file.",
        ) from exc

    # 6. Persist Asset row
    asset = Asset(
        id=asset_id,
        project_id=project_id,
        original_filename=filename,
        stored_path=str(stored_path),
        media_type=media_type,
        ext=ext,
        size_bytes=size_bytes,
        status="uploaded",
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)

    # 7. Enqueue process_asset — non-fatal if this fails
    # job_timeout must cover CPU transcription of long footage; RQ's 180s
    # default would kill real-world jobs mid-transcription.
    try:
        get_queue().enqueue(
            "app.workers.tasks.process_asset", asset_id, job_timeout=3 * 60 * 60
        )
    except Exception as exc:
        logger.warning(
            "Failed to enqueue process_asset for asset_id=%s: %s", asset_id, exc
        )

    return _asset_to_read(asset)


def list_assets(session: Session, project_id: str) -> list[AssetRead]:
    """Return all assets for a project."""
    # Confirm project exists
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    assets = session.exec(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at.desc())  # type: ignore[arg-type]
    ).all()
    return [_asset_to_read(a) for a in assets]


def get_asset(session: Session, asset_id: str) -> AssetRead:
    """Return a single asset; raises 404 if not found."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_to_read(asset)


def get_asset_status(session: Session, asset_id: str) -> AssetStatus:
    """Return just the status fields for an asset."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetStatus(
        id=asset.id,
        status=asset.status,
        error_message=asset.error_message,
    )


def delete_asset(session: Session, asset_id: str) -> None:
    """Delete asset DB row, its file, and derived artifacts from disk."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    remove_asset_files(asset)
    session.delete(asset)
    session.commit()


def remove_asset_files(asset: Asset) -> None:
    """Remove the stored media file and all derived artifacts for an asset."""
    _remove_file_safe(asset.stored_path)
    if asset.audio_path:
        _remove_file_safe(asset.audio_path)
    if asset.waveform_path:
        _remove_file_safe(asset.waveform_path)
    # Sampled frames directory (visual index artifacts)
    from app.services.pipeline_service import frames_dir

    try:
        d = frames_dir(asset.project_id, asset.id)
        if d.is_dir():
            shutil.rmtree(d)
    except Exception as exc:
        logger.warning("Could not remove frames dir for asset %s: %s", asset.id, exc)


def get_frame_path(session: Session, asset_id: str, frame_index: int) -> Path:
    """Return the JPEG path for a sampled frame; 404 if unknown or missing."""
    from app.models.frame_embedding import FrameEmbedding

    frame = session.exec(
        select(FrameEmbedding)
        .where(FrameEmbedding.asset_id == asset_id)
        .where(FrameEmbedding.frame_index == frame_index)
    ).first()
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    path = Path(frame.frame_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frame file not found on disk")
    return path


def get_transcript(session: Session, asset_id: str) -> TranscriptRead:
    """Return the ordered transcript segments for an asset."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    segments = session.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.asset_id == asset_id)
        .order_by(TranscriptSegment.seg_index)  # type: ignore[arg-type]
    ).all()
    return TranscriptRead(
        asset_id=asset_id,
        status=asset.status,
        segments=[
            TranscriptSegmentRead(
                id=s.id,
                seg_index=s.seg_index,
                start=s.start,
                end=s.end,
                text=s.text,
                speaker=s.speaker,
            )
            for s in segments
        ],
    )


def get_waveform(session: Session, asset_id: str) -> WaveformRead:
    """Return waveform peaks computed by the pipeline."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not asset.waveform_path:
        raise HTTPException(
            status_code=404, detail="Waveform not available for this asset yet"
        )
    try:
        data = json.loads(Path(asset.waveform_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404, detail="Waveform data could not be read"
        ) from exc
    return WaveformRead(
        asset_id=asset_id,
        peaks=data.get("peaks", []),
        duration=data.get("duration", 0.0),
    )


# MIME types for the extension allow-list — used when serving media
_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


def get_media_path(session: Session, asset_id: str) -> tuple[Path, str]:
    """
    Return (path, content_type) for an asset's stored media file.

    The path is server-generated (UUID under STORAGE_ROOT) — never derived
    from user input — and is verified to exist before serving.
    """
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    path = Path(asset.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Media file not found on disk")
    content_type = _CONTENT_TYPES.get(asset.ext, "application/octet-stream")
    return path, content_type


def _remove_file_safe(path: "str | Path") -> None:
    """Remove a file from disk, tolerating missing files."""
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception as exc:
        logger.warning("Could not remove file %s: %s", path, exc)
