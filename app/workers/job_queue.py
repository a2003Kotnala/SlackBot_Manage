from __future__ import annotations

from queue import Queue
from threading import Lock, Thread
from uuid import UUID

from app.config import settings
from app.logger import logger


class JobQueue:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._started = False
        self._lock = Lock()

    def enqueue(self, job_id: UUID | str) -> None:
        job_key = str(job_id)
        if settings.followthru_job_execution_mode == "inline":
            self._run_job(job_key)
            return

        self._ensure_worker()
        self._queue.put(job_key)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._started:
                return
            worker = Thread(
                target=self._worker_loop, daemon=True, name="followthru-jobs"
            )
            worker.start()
            self._started = True

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        from app.domain.services.ingestion_job_service import process_ingestion_job

        try:
            process_ingestion_job(job_id)
        except Exception:
            logger.exception(
                "Unhandled exception while processing ingestion job %s", job_id
            )


job_queue = JobQueue()
