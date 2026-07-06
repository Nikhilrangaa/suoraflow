"""Timelines router — thin handlers that delegate to timeline_service."""
from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.database import SessionDep
from app.schemas.timeline import (
    TimelineItemCreate,
    TimelineItemMove,
    TimelineRead,
)
from app.services import timeline_service

router = APIRouter(prefix="/api/timelines", tags=["timelines"])


@router.get("/{timeline_id}", response_model=TimelineRead)
def get_timeline(timeline_id: str, session: SessionDep) -> TimelineRead:
    return timeline_service.get_timeline(session, timeline_id)


@router.post("/{timeline_id}/items", response_model=TimelineRead, status_code=201)
def add_item(
    timeline_id: str, data: TimelineItemCreate, session: SessionDep
) -> TimelineRead:
    return timeline_service.add_item(session, timeline_id, data)


@router.patch("/{timeline_id}/items/{item_id}", response_model=TimelineRead)
def move_item(
    timeline_id: str, item_id: str, data: TimelineItemMove, session: SessionDep
) -> TimelineRead:
    return timeline_service.move_item(session, timeline_id, item_id, data)


@router.delete("/{timeline_id}/items/{item_id}", status_code=204)
def remove_item(timeline_id: str, item_id: str, session: SessionDep) -> None:
    timeline_service.remove_item(session, timeline_id, item_id)


@router.get("/{timeline_id}/export")
def export_timeline(
    timeline_id: str,
    session: SessionDep,
    format: str = Query(default="json", pattern="^(json|csv)$"),
) -> Response:
    content, media_type, filename = timeline_service.export_timeline(
        session, timeline_id, format
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
