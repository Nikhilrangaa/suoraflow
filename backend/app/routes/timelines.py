"""Timelines router — thin handlers that delegate to timeline_service."""
from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.database import SessionDep
from app.schemas.rough_cut import RoughCutRequest, RoughCutResponse
from app.schemas.timeline import (
    TimelineItemCreate,
    TimelineItemMove,
    TimelineRead,
)
from app.services import rough_cut_service, timeline_service

router = APIRouter(prefix="/api/timelines", tags=["timelines"])

# Rough-cut generation is project-scoped (POST /api/projects/{id}/rough-cut),
# so it lives on its own router with the projects prefix. Registered in main.py.
rough_cut_router = APIRouter(prefix="/api/projects", tags=["timelines"])


@rough_cut_router.post(
    "/{project_id}/rough-cut", response_model=RoughCutResponse, status_code=201
)
def generate_rough_cut(
    project_id: str, data: RoughCutRequest, session: SessionDep
) -> RoughCutResponse:
    return rough_cut_service.generate_rough_cut(session, project_id, data)


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
