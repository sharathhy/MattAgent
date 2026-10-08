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
from app.services import autopilot, model_scout, tasks
from app.trading import service as trading

log = logging.getLogger(__name__)
HOUSEKEEPING_EVERY = timedelta(minutes=10)
AUTOPILOT_EVERY = timedelta(seconds=15)
TRADING_EVERY = 30.0  # seconds between trading-swarm heartbeats


class Worker:
    def __init__(
        self, factory: sessionmaker[Session], router: ModelRouter, poll: float, threads: int = 1
    ) -> None:
        self.factory, self.router, self.poll = factory, router, poll
        self._stop = threading.Event()
        self._threads = [
            threading.Thread(target=self._run, name="matt-worker", daemon=True),
            # Its own thread: market-data calls must never hold up the task queue.
            threading.Thread(target=self._trade, name="matt-trading", daemon=True),
        ]
        with factory() as db:  # SKIP LOCKED makes parallel claiming safe; SQLite has none
            parallel = db.get_bind().dialect.name == "postgresql"
        for i in range(1, threads if parallel else 1):
            self._threads.append(
                threading.Thread(target=self._drain, name=f"matt-worker-{i}", daemon=True)
            )

    def start(self) -> None:
        with self.factory() as db:
            db.execute(
                update(Task)
                .where(Task.status == TaskStatus.RUNNING)
                .values(status=TaskStatus.QUEUED)
            )
            db.commit()
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=10)

    def _drain(self) -> None:
        """Extra workers: only run queued tasks, so several bots think at the same time."""
        while not self._stop.is_set():
            try:
                with self.factory() as db:
                    worked = tasks.process_next(db, self.router) is not None
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._stop.wait(self.poll)

    def _trade(self) -> None:
        """The trading swarm's heartbeat: guard open positions, give bots their turns."""
        while not self._stop.is_set():
            try:
                with self.factory() as db:
                    trading.tick(db, self.router)
            except Exception:
                log.exception("trading loop error")
            self._stop.wait(TRADING_EVERY)

    def _run(self) -> None:
        last_housekeeping = utcnow() - HOUSEKEEPING_EVERY
        last_autopilot = utcnow() - AUTOPILOT_EVERY
        last_scout = utcnow() - model_scout.EVERY  # scout once at start, then every 6 hours
        while not self._stop.is_set():
            try:
                with self.factory() as db:
                    if utcnow() - last_housekeeping >= HOUSEKEEPING_EVERY:
                        db.execute(delete(Knowledge).where(Knowledge.expires_at < utcnow()))
                        db.commit()
                        last_housekeeping = utcnow()
                    if utcnow() - last_scout >= model_scout.EVERY:
                        last_scout = utcnow()  # set first: a failing scan must not loop
                        model_scout.scan(db, self.router)
                    if utcnow() - last_autopilot >= AUTOPILOT_EVERY:
                        autopilot.tick(db, self.router)
                        last_autopilot = utcnow()
                    worked = tasks.process_next(db, self.router) is not None
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._stop.wait(self.poll)
