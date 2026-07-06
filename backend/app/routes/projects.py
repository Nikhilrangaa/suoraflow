"""Projects router — thin handlers that delegate to services."""
from fastapi import APIRouter, UploadFile, File

from app.database import SessionDep
from app.schemas.asset import AssetRead
from app.schemas.project import ProjectCreate, ProjectList, ProjectRead
from app.services import asset_service, project_service

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

