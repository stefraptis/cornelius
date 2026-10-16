"""Worker job loop against the real jobs table: claim, success, retry with backoff, final failure."""

from __future__ import annotations

import pytest
from workers.common.jobloop import JobLoop

from app.config import Settings
from tests.dbtest import (
    as_service,
    create_auth_user,
    personal_workspace,
    recreate_database,
    server_reachable,
)

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def video_id(settings: Settings) -> str:
    if not server_reachable(settings.database_url):
        pytest.skip("PostgreSQL not reachable at DATABASE_URL; run `make db-local`")
    recreate_database(settings.database_url)
    with as_service(settings.database_url) as conn:
        user = create_auth_user(conn, "worker-owner@example.org", "Owner")
        ws = personal_workspace(conn, user)
        vid = conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) values (%s,%s,'lc','Job test') returning id",
            (user, ws),
        ).fetchone()["id"]
        conn.commit()
    return str(vid)


def make_loop(url: str, handler) -> JobLoop:  # type: ignore[no-untyped-def]
    loop = JobLoop.__new__(JobLoop)
    loop.database_url = url
    loop.job_types = ["transcode"]
    loop.handlers = {"transcode": handler}
    loop.worker_id = "test-worker"
    loop.poll_interval = 0
    loop._stop = False
    return loop


def test_success_marks_job_succeeded(settings: Settings, video_id: str) -> None:
    seen = []
    loop = make_loop(settings.database_url, lambda job, conn: seen.append(job["id"]))
    with as_service(settings.database_url) as conn:
        conn.autocommit = True
        job_id = conn.execute(
            "insert into public.jobs (type, video_id) values ('transcode', %s) returning id",
            (video_id,),
        ).fetchone()["id"]
        job = loop.claim(conn)
        assert job is not None and job["id"] == job_id and job["status"] == "running"
        loop.process(conn, job)
        row = conn.execute(
            "select status, finished_at, locked_by from public.jobs where id = %s", (job_id,)
        ).fetchone()
    assert seen == [job_id]
    assert (
        row["status"] == "succeeded" and row["finished_at"] is not None and row["locked_by"] is None
    )


def test_failure_requeues_with_backoff_then_fails_for_good(
    settings: Settings, video_id: str
) -> None:
    def boom(job, conn):  # type: ignore[no-untyped-def]
        raise RuntimeError("ffmpeg exploded")

    loop = make_loop(settings.database_url, boom)
    with as_service(settings.database_url) as conn:
        conn.autocommit = True
        job_id = conn.execute(
            "insert into public.jobs (type, video_id, max_attempts) values ('transcode', %s, 2) returning id",
            (video_id,),
        ).fetchone()["id"]

        job = loop.claim(conn)
        loop.process(conn, job)
        row = conn.execute(
            "select status, attempts, error, run_after > now() as deferred from public.jobs where id = %s",
            (job_id,),
        ).fetchone()
        assert row["status"] == "queued" and row["attempts"] == 1 and row["deferred"] is True
        assert "ffmpeg exploded" in row["error"]

        # Not claimable while deferred.
        assert loop.claim(conn) is None
        conn.execute("update public.jobs set run_after = now() where id = %s", (job_id,))

        job = loop.claim(conn)
        assert job is not None and job["attempts"] == 2
        loop.process(conn, job)
        row = conn.execute(
            "select status, attempts, finished_at from public.jobs where id = %s", (job_id,)
        ).fetchone()
        assert row["status"] == "failed" and row["attempts"] == 2 and row["finished_at"] is not None
        assert loop.claim(conn) is None
