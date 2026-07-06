"""
run_worker.py — In-image RQ worker entrypoint.

Unlike worker/worker.py (which docker-compose bind-mounts from the repo),
this module lives inside the app package so single-container deployments
(e.g. Railway) can start the worker without extra mounts:

  python -m app.workers.run_worker
"""
import logging

from rq import Worker

from app.workers.queue import get_redis_connection
from app.workers.tasks import process_asset  # noqa: F401 — ensure importable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

if __name__ == "__main__":
    worker = Worker(["default"], connection=get_redis_connection())
    worker.work(with_scheduler=True)
