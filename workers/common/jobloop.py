"""Shared job loop for workers (M1 fills in the handlers).

A worker claims one job at a time with `public.claim_next_job`, runs the
handler for its type, and marks the job succeeded or failed. Failed jobs are
retried with exponential backoff until `max_attempts`, then left failed for
the retry button in the library.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import time
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger("worker")

Handler = Callable[[dict[str, Any], psycopg.Connection], None]


class JobLoop:
    def __init__(self, database_url: str, job_types: list[str], handlers: dict[str, Handler]):
        self.database_url = database_url
        self.job_types = job_types
        self.handlers = handlers
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.poll_interval = float(os.environ.get("JOBS_POLL_INTERVAL_S", "5"))
        self._stop = False
        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)

    def _request_stop(self, *_: object) -> None:
        self._stop = True

    def run_forever(self) -> None:
        log.info("worker.start types=%s id=%s", self.job_types, self.worker_id)
        with psycopg.connect(self.database_url, row_factory=dict_row, autocommit=True) as conn:
            while not self._stop:
                job = self.claim(conn)
                if job is None:
                    time.sleep(self.poll_interval)
                    continue
                self.process(conn, job)
        log.info("worker.stop")

    def claim(self, conn: psycopg.Connection) -> dict[str, Any] | None:
        row = conn.execute(
            "select * from public.claim_next_job(%s::public.job_type[], %s)",
            (self.job_types, self.worker_id),
        ).fetchone()
        return dict(row) if row else None

    def process(self, conn: psycopg.Connection, job: dict[str, Any]) -> None:
        handler = self.handlers.get(job["type"])
        job_id = job["id"]
        log.info("job.start id=%s type=%s attempt=%s", job_id, job["type"], job["attempts"])
        try:
            if handler is None:
                raise RuntimeError(f"No handler for job type {job['type']}")
            handler(job, conn)
        except Exception as exc:  # noqa: BLE001
            log.exception("job.failed id=%s", job_id)
            retry = job["attempts"] < job["max_attempts"]
            backoff_s = min(3600, 60 * (2 ** (job["attempts"] - 1)))
            conn.execute(
                """
                update public.jobs
                set status = %s, error = %s, locked_by = null, locked_at = null,
                    run_after = case when %s then now() + make_interval(secs => %s)
                                else run_after end,
                    finished_at = case when %s then null else now() end
                where id = %s
                """,
                ("queued" if retry else "failed", str(exc)[:2000], retry, backoff_s, retry, job_id),
            )
            return
        conn.execute(
            "update public.jobs set status = 'succeeded', finished_at = now(), locked_by = null "
            "where id = %s",
            (job_id,),
        )
        log.info("job.done id=%s", job_id)


def configure_logging() -> None:
    class Json(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return json.dumps(
                {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
            )

    handler = logging.StreamHandler()
    handler.setFormatter(Json())
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), handlers=[handler])
