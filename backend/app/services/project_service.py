"""Project service — all business logic for project CRUD."""
import logging

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models.asset import Asset
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead

logger = logging.getLogger(__name__)


def create_project(session: Session, data: ProjectCreate) -> ProjectRead:
    """Create a new project and persist it."""
    project = Project(name=data.name.strip(), description=data.description)
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        asset_count=0,
    )


def list_projects(session: Session) -> list[ProjectRead]:
    """Return all projects with their asset counts (single grouped query)."""
    rows = session.exec(
        select(Project, func.count(Asset.id))
        .join(Asset, Asset.project_id == Project.id, isouter=True)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())  # type: ignore[arg-type]
    ).all()
    return [
        ProjectRead(
            id=p.id,
            name=p.name,
            description=p.description,
            created_at=p.created_at,
            asset_count=count,
        )
        for p, count in rows
    ]


def get_project(session: Session, project_id: str) -> ProjectRead:
    """Return a project by id; raises 404 if not found."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    count = session.exec(
        select(func.count(Asset.id)).where(Asset.project_id == project_id)
    ).one()
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        asset_count=count,
    )


def delete_project(session: Session, project_id: str) -> None:
    """Delete project and all its assets (files + DB rows)."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete each asset's files (media + derived artifacts), then the DB row
    from app.services.asset_service import remove_asset_files

    assets = session.exec(select(Asset).where(Asset.project_id == project_id)).all()
    for asset in assets:
        remove_asset_files(asset)
        session.delete(asset)

    session.delete(project)
    session.commit()
