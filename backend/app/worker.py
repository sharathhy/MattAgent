"""Background worker thread that drains the task queue.

Render's free tier has no Redis, so the queue is the database and the worker runs inside the
web process. Running tasks left over from a crash are re-queued on start.
"""

import logging
import threading
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.domain import TaskStatus
from app.db.base import utcnow
from app.llm.router import ModelRouter
from app.models import Knowledge, Task
from app.services import autopilot, tasks

log = logging.getLogger(__name__)
HOUSEKEEPING_EVERY = timedelta(minutes=10)
AUTOPILOT_EVERY = timedelta(seconds=15)


class Worker:
    def __init__(self, factory: sessionmaker[Session], router: ModelRouter, poll: float) -> None:
        self.factory, self.router, self.poll = factory, router, poll
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="matt-worker", daemon=True)

    def start(self) -> None:
        with self.factory() as db:
            db.execute(
                update(Task)
                .where(Task.status == TaskStatus.RUNNING)
                .values(status=TaskStatus.QUEUED)
            )
            db.commit()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _run(self) -> None:
        last_housekeeping = utcnow() - HOUSEKEEPING_EVERY
        last_autopilot = utcnow() - AUTOPILOT_EVERY
        while not self._stop.is_set():
            try:
                with self.factory() as db:
                    if utcnow() - last_housekeeping >= HOUSEKEEPING_EVERY:
                        db.execute(delete(Knowledge).where(Knowledge.expires_at < utcnow()))
                        db.commit()
                        last_housekeeping = utcnow()
                    if utcnow() - last_autopilot >= AUTOPILOT_EVERY:
                        autopilot.tick(db, self.router)
                        last_autopilot = utcnow()
                    worked = tasks.process_next(db, self.router) is not None
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._stop.wait(self.poll)
