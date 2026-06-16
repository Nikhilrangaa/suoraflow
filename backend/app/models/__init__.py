"""Models package — import all tables so SQLModel.metadata registers them."""
from app.models.project import Project
from app.models.asset import Asset

__all__ = ["Project", "Asset"]
