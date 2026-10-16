"""Analysis (GPU) worker entry point. Wraps the published LC pipeline in M2.

Inputs needed from the owner at the start of M2: inference code (stage 1,
stage 2, heuristics, narration, report rendering), model weights, thresholds
config, and Video_05.mp4 with its reference report.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg

from workers.common.jobloop import JobLoop, configure_logging


def handle_analyze(job: dict[str, Any], conn: psycopg.Connection) -> None:
    raise NotImplementedError("analysis handler arrives in M2")


def handle_narrate(job: dict[str, Any], conn: psycopg.Connection) -> None:
    raise NotImplementedError("narration handler arrives in M3")


if __name__ == "__main__":
    configure_logging()
    JobLoop(
        database_url=os.environ["DATABASE_URL"],
        job_types=["analyze", "narrate"],
        handlers={"analyze": handle_analyze, "narrate": handle_narrate},
    ).run_forever()
