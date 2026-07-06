"""Projects router — thin handlers that delegate to services."""
from fastapi import APIRouter, UploadFile, File

from app.database import SessionDep
from app.schemas.asset import AssetRead
from app.schemas.project import ProjectCreate, ProjectList, ProjectRead
from app.schemas.search import SearchRequest, SearchResponse
from app.schemas.timeline import ClipCreate, ClipRead, TimelineCreate, TimelineRead
from app.services import asset_service, project_service, search_service, timeline_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectRead:
    return project_service.create_project(session, data)


@router.get("", response_model=ProjectList)
def list_projects(session: SessionDep) -> ProjectList:
    projects = project_service.list_projects(session)
    return ProjectList(projects=projects, total=len(projects))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: SessionDep) -> ProjectRead:
    return project_service.get_project(session, project_id)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: SessionDep) -> None:
    project_service.delete_project(session, project_id)


@router.post("/{project_id}/assets/upload", response_model=AssetRead, status_code=201)
async def upload_asset(
    project_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
) -> AssetRead:
    return asset_service.create_asset_from_upload(session, project_id, file)


@router.get("/{project_id}/assets", response_model=list[AssetRead])
def list_assets(project_id: str, session: SessionDep) -> list[AssetRead]:
    return asset_service.list_assets(session, project_id)


@router.post("/{project_id}/search", response_model=SearchResponse)
def search(project_id: str, data: SearchRequest, session: SessionDep) -> SearchResponse:
    return search_service.search_project(session, project_id, data)


@router.post("/{project_id}/clips", response_model=ClipRead, status_code=201)
def create_clip(project_id: str, data: ClipCreate, session: SessionDep) -> ClipRead:
    return timeline_service.create_clip(session, project_id, data)


@router.get("/{project_id}/clips", response_model=list[ClipRead])
def list_clips(project_id: str, session: SessionDep) -> list[ClipRead]:
    return timeline_service.list_clips(session, project_id)


@router.post("/{project_id}/timelines", response_model=TimelineRead, status_code=201)
def create_timeline(
    project_id: str, data: TimelineCreate, session: SessionDep
) -> TimelineRead:
    return timeline_service.create_timeline(session, project_id, data)


@router.get("/{project_id}/timelines", response_model=list[TimelineRead])
def list_timelines(project_id: str, session: SessionDep) -> list[TimelineRead]:
    return timeline_service.list_timelines(session, project_id)
