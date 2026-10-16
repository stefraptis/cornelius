"""Transcode worker entry point. Handlers are implemented in M1."""

from __future__ import annotations

import os
from typing import Any

import psycopg

from workers.common.jobloop import JobLoop, configure_logging


def handle_transcode(job: dict[str, Any], conn: psycopg.Connection) -> None:
    # M1: download original, strip metadata, blur out-of-body frames, HLS 720p/480p,
    # poster, sprite sheet, proxy, SHA-256, upload, mark video ready.
    raise NotImplementedError("transcode handler arrives in M1")


def handle_purge(job: dict[str, Any], conn: psycopg.Connection) -> None:
    # M1: delete originals past original_purge_at, or every object of a deleted video.
    raise NotImplementedError("purge handler arrives in M1")


if __name__ == "__main__":
    configure_logging()
    JobLoop(
        database_url=os.environ["DATABASE_URL"],
        job_types=["transcode", "purge"],
        handlers={"transcode": handle_transcode, "purge": handle_purge},
    ).run_forever()
