"""Assets router — thin handlers that delegate to services."""
from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.database import SessionDep
from app.schemas.asset import AssetRead, AssetStatus, TranscriptRead, WaveformRead
from app.services import asset_service

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: str, session: SessionDep) -> AssetRead:
    return asset_service.get_asset(session, asset_id)


@router.get("/{asset_id}/status", response_model=AssetStatus)
def get_asset_status(asset_id: str, session: SessionDep) -> AssetStatus:
    return asset_service.get_asset_status(session, asset_id)


@router.get("/{asset_id}/transcript", response_model=TranscriptRead)
def get_transcript(asset_id: str, session: SessionDep) -> TranscriptRead:
    return asset_service.get_transcript(session, asset_id)


@router.get("/{asset_id}/waveform", response_model=WaveformRead)
def get_waveform(asset_id: str, session: SessionDep) -> WaveformRead:
    return asset_service.get_waveform(session, asset_id)


@router.get("/{asset_id}/media")
def get_media(asset_id: str, session: SessionDep) -> FileResponse:
    """Serve the stored media file. FileResponse handles HTTP Range requests,
    which the browser player needs for seeking."""
    path, content_type = asset_service.get_media_path(session, asset_id)
    return FileResponse(path, media_type=content_type)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str, session: SessionDep) -> None:
    asset_service.delete_asset(session, asset_id)
