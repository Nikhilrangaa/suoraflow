"""
worker.py — RQ worker entrypoint.

Shares the backend image and imports tasks from app.workers.tasks.
Run via:
  python worker/worker.py
"""
import logging
import sys

# Ensure /app is on the path when run from repo root inside the container
sys.path.insert(0, "/app")

from rq import Worker
from app.workers.queue import get_redis_connection
from app.workers.tasks import process_asset  # noqa: F401 — ensure importable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

if __name__ == "__main__":
    conn = get_redis_connection()
    queues = ["default"]
    worker = Worker(queues, connection=conn)
    worker.work(with_scheduler=True)
