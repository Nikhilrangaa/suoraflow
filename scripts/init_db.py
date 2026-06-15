"""
init_db.py — Create the pgvector extension and all SQLModel tables.

Normally called automatically on backend startup (app/database.py).
Run manually if you need to reinitialise without restarting the service:
  docker compose run --rm backend python scripts/init_db.py
"""
import sys

# Ensure the app package is importable when run from repo root inside the container
sys.path.insert(0, "/app")

from app.database import init_db  # type: ignore[import]

if __name__ == "__main__":
    print("[init_db] Creating extension + tables…")
    init_db()
    print("[init_db] Done.")
