"""Transcode worker: downloads the original, runs the ffmpeg pipeline, uploads
the results, and marks the video ready. Also runs purge jobs.

    python -m workers.transcode.main

Job payloads:
  transcode: {"original_key": "videos/<id>/original/source.mp4"}
  purge:     {"prefixes": ["videos/<id>/"], "hard_delete": true?, "deletion_id": "<uuid>"?}
             or {"video_id": ..., "original_only": true} for the retention purge.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import psycopg
from app.storage import Keys, Storage, get_storage

from workers.common.jobloop import JobLoop, configure_logging
from workers.transcode.pipeline import OutOfBodyConfig, TranscodeResult, transcode_video

log = logging.getLogger("worker.transcode")

CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".mp4": "video/mp4",
}


def _upload_dir(storage: Storage, local_dir: Path, prefix: str) -> int:
    count = 0
    for path in sorted(local_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(local_dir).as_posix()
            storage.upload_file(str(path), prefix + rel, CONTENT_TYPES.get(path.suffix, None))
            count += 1
    return count


def _load_video(conn: psycopg.Connection, video_id: str) -> dict[str, Any]:
    row = conn.execute(
        "select id, original_key, status::text as status, analysis_requested, procedure_code, "
        "deleted_at from public.videos where id = %s",
        (video_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"video {video_id} not found")
    return dict(row)


def handle_transcode(job: dict[str, Any], conn: psycopg.Connection) -> None:
    storage = get_storage()
    video_id = str(job["video_id"])
    video = _load_video(conn, video_id)
    if video["deleted_at"] is not None:
        log.info("transcode.skip_deleted video=%s", video_id)
        return
    original_key = job["payload"].get("original_key") or video["original_key"]
    if not original_key:
        raise RuntimeError("video has no original_key")

    conn.execute(
        "update public.videos set status = 'processing', last_error = null where id = %s",
        (video_id,),
    )

    work = Path(tempfile.mkdtemp(prefix=f"cornelius-{video_id[:8]}-"))
    try:
        src = work / ("source" + Path(original_key).suffix)
        log.info("transcode.download video=%s key=%s", video_id, original_key)
        storage.download_file(original_key, str(src))

        result: TranscodeResult = transcode_video(src, work / "out", _config_from_env())

        # Duplicate detection: same content already in this owner's library.
        dup = conn.execute(
            """
            select v2.id from public.videos v1
            join public.videos v2 on v2.owner_user_id = v1.owner_user_id
            where v1.id = %s and v2.id <> v1.id and v2.sha256 = %s and v2.deleted_at is null
            limit 1
            """,
            (video_id, result.sha256),
        ).fetchone()

        hls_prefix = Keys.hls_prefix(video_id)
        thumbs_prefix = Keys.thumbs_prefix(video_id)
        n = _upload_dir(storage, result.hls_dir, hls_prefix)
        storage.upload_file(str(result.poster), Keys.poster(video_id), "image/jpeg")
        storage.upload_file(str(result.sprite), Keys.sprite(video_id), "image/jpeg")
        storage.upload_file(
            str(result.sprite_index), thumbs_prefix + "sprite.json", "application/json"
        )
        storage.upload_file(str(result.proxy), Keys.proxy(video_id), "video/mp4")
        log.info("transcode.uploaded video=%s hls_files=%s", video_id, n)

        retention_days = int(os.environ.get("ORIGINAL_RETENTION_DAYS", "90"))
        conn.execute(
            """
            update public.videos
            set status = 'ready',
                duration_s = %s,
                hls_prefix = %s,
                thumbnail_key = %s,
                sprite_key = %s,
                proxy_key = %s,
                sha256 = %s,
                extra_streams = extra_streams || %s::jsonb,
                original_purge_at = now() + make_interval(days => %s),
                last_error = case when %s::uuid is not null
                                  then 'Duplicate of an existing video in your library'
                                  else null end
            where id = %s
            """,
            (
                result.probe.duration_s,
                hls_prefix,
                Keys.poster(video_id),
                Keys.sprite(video_id),
                Keys.proxy(video_id),
                result.sha256,
                json.dumps(
                    [
                        {
                            "kind": "transcode_info",
                            "width": result.probe.width,
                            "height": result.probe.height,
                            "fps": result.probe.fps,
                            "out_of_body_runs": result.out_of_body,
                            "duplicate_of": str(dup["id"]) if dup else None,
                        }
                    ]
                ),
                retention_days,
                dup["id"] if dup else None,
                video_id,
            ),
        )

        if video["analysis_requested"]:
            enabled = conn.execute(
                "select analysis_enabled from public.procedures where code = %s",
                (video["procedure_code"],),
            ).fetchone()
            if enabled and enabled["analysis_enabled"]:
                conn.execute(
                    "insert into public.jobs (type, video_id, payload) "
                    "values ('analyze', %s, '{}'::jsonb)",
                    (video_id,),
                )
                conn.execute(
                    "update public.videos set status = 'analyzing' where id = %s", (video_id,)
                )
    except Exception as exc:
        conn.execute(
            "update public.videos set status = 'failed', last_error = %s where id = %s",
            (str(exc)[:500], video_id),
        )
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def handle_purge(job: dict[str, Any], conn: psycopg.Connection) -> None:
    storage = get_storage()
    payload = job["payload"]
    deleted = 0
    if payload.get("original_only") and job.get("video_id"):
        row = conn.execute(
            "select original_key from public.videos where id = %s", (job["video_id"],)
        ).fetchone()
        if row and row["original_key"]:
            storage.delete_key(row["original_key"])
            conn.execute(
                "update public.videos set original_key = null where id = %s", (job["video_id"],)
            )
            deleted = 1
    else:
        for prefix in payload.get("prefixes", []):
            deleted += storage.delete_prefix(prefix)
        if payload.get("hard_delete") and job.get("video_id"):
            conn.execute("delete from public.videos where id = %s", (job["video_id"],))
        if payload.get("deletion_id"):
            conn.execute(
                "update public.account_deletions set purged_at = now() where id = %s",
                (payload["deletion_id"],),
            )
    log.info("purge.done job=%s objects=%s", job["id"], deleted)


def _config_from_env() -> OutOfBodyConfig:
    cfg = OutOfBodyConfig()
    for field_name in ("min_red_dominance", "max_brightness", "min_saturation"):
        value = os.environ.get("OOB_" + field_name.upper())
        if value:
            setattr(cfg, field_name, float(value))
    for field_name in ("min_run_s", "pad_s"):
        value = os.environ.get("OOB_" + field_name.upper())
        if value:
            setattr(cfg, field_name, int(value))
    return cfg


if __name__ == "__main__":
    from app.config import get_settings

    configure_logging()
    JobLoop(
        database_url=get_settings().database_url,
        job_types=["transcode", "purge"],
        handlers={"transcode": handle_transcode, "purge": handle_purge},
    ).run_forever()
