"""Assets router — thin handlers that delegate to services."""
from fastapi import APIRouter

from app.database import SessionDep
from app.schemas.asset import AssetRead, AssetStatus
from app.services import asset_service

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: str, session: SessionDep) -> AssetRead:
    return asset_service.get_asset(session, asset_id)


@router.get("/{asset_id}/status", response_model=AssetStatus)
def get_asset_status(asset_id: str, session: SessionDep) -> AssetStatus:
    return asset_service.get_asset_status(session, asset_id)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str, session: SessionDep) -> None:
    asset_service.delete_asset(session, asset_id)
