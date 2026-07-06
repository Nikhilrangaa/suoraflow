"""
conftest.py — Isolate the test run from the development database and storage.

Executed before any test module imports the app, so the environment overrides
below are what app.config.Settings picks up:

- DATABASE_URL is pointed at a dedicated `suoraflow_test` database (created
  here if missing) so pytest runs never pollute dev data.
- STORAGE_ROOT is pointed at a throwaway directory.
"""
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg

_dev_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://suoraflow:suoraflow_secret@db:5432/suoraflow",
)

_TEST_DB = "suoraflow_test"


def _swap_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{dbname}"))


def _ensure_test_db() -> None:
    # psycopg needs a plain postgresql:// DSN (no +psycopg driver marker)
    admin_dsn = _dev_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{_TEST_DB}"')


_ensure_test_db()

os.environ["DATABASE_URL"] = _swap_db(_dev_url, _TEST_DB)
os.environ["STORAGE_ROOT"] = "/tmp/suoraflow_test_storage"
os.makedirs("/tmp/suoraflow_test_storage", exist_ok=True)

# Initialise the schema once per test session (imports settings AFTER the
# overrides above, so everything binds to the test database). Models must be
# imported first so SQLModel.metadata knows the tables.
import app.models  # noqa: E402, F401
from app.database import init_db  # noqa: E402

init_db()
