"""Health-check route — thin handler, reachability logic kept minimal."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.database import get_engine
from sqlmodel import text
import redis as redis_lib

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()

    # --- DB reachability ---
    db_status = "ok"
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    # --- Redis reachability ---
    redis_status = "ok"
    try:
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
    except Exception:
        redis_status = "unreachable"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(status=overall, db=db_status, redis=redis_status)
