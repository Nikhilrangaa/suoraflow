"""
seed_demo.py — Seed a demo project with the committed fixture clip and
run it through the full pipeline.

Usage:
  docker compose run --rm backend python scripts/seed_demo.py

Idempotent: re-running when the demo project already exists is a no-op.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlmodel import Session, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.utils.file_validation import generate_asset_id, safe_asset_path  # noqa: E402
from app.workers.queue import get_queue  # noqa: E402

DEMO_PROJECT_NAME = "Demo — Mountain Documentary"
FIXTURE = Path("/app/fixtures/demo_interview.wav")


def main() -> int:
    if not FIXTURE.exists():
        print(f"[seed_demo] Fixture not found: {FIXTURE}", file=sys.stderr)
        return 1

    init_db()
    settings = get_settings()

    with Session(get_engine()) as session:
        existing = session.exec(
            select(Project).where(Project.name == DEMO_PROJECT_NAME)
        ).first()
        if existing is not None:
            print(f"[seed_demo] Demo project already exists (id={existing.id}); nothing to do.")
            return 0

        project = Project(
            name=DEMO_PROJECT_NAME,
            description="Seeded demo: a two-voice narration about a mountain "
            "expedition. Try searching for “drone footage of the sunrise” or "
            "“discussion about the budget”.",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        asset_id = generate_asset_id()
        dest = safe_asset_path(settings.storage_root, project.id, asset_id, ".wav")
        shutil.copyfile(FIXTURE, dest)

        asset = Asset(
            id=asset_id,
            project_id=project.id,
            original_filename="demo_interview.wav",
            stored_path=str(dest),
            media_type="audio",
            ext=".wav",
            size_bytes=dest.stat().st_size,
            status="uploaded",
        )
        session.add(asset)
        session.commit()

        get_queue().enqueue(
            "app.workers.tasks.process_asset", asset_id, job_timeout=3 * 60 * 60
        )
        print(f"[seed_demo] Created project '{DEMO_PROJECT_NAME}' (id={project.id})")
        print(f"[seed_demo] Enqueued pipeline for asset {asset_id}.")
        print("[seed_demo] Open http://localhost:5173 and watch it process.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
