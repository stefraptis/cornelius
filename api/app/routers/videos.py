"""Videos: upload sessions, library, playback, deletion.

Video bytes never pass through this service. The browser uploads parts to
presigned URLs and the worker reads and writes storage directly; the API only
issues URLs and keeps the rows.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app import audit, db
from app.auth import AuthUser, get_current_user, get_current_user_or_query_token
from app.config import get_settings
from app.storage import CompletedPart, Keys, Storage, get_storage

router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi"}
CONTENT_TYPES = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "avi": "video/x-msvideo",
}
VideoStatus = Literal["uploading", "processing", "ready", "analyzing", "analyzed", "failed"]


# ---------- models ----------


class UploadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    procedure_code: str = Field(min_length=1, max_length=40)
    operation_date: date | None = None
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    workspace_id: uuid.UUID | None = None
    consent_confirmed: bool
    request_analysis: bool = True


class UploadSession(BaseModel):
    video_id: uuid.UUID
    upload_id: str
    key: str
    part_size_bytes: int
    part_count: int


class PartUrl(BaseModel):
    part_number: int
    url: str
    expires_in: int


class ListedPart(BaseModel):
    part_number: int
    etag: str


class CompleteIn(BaseModel):
    parts: list[ListedPart] = Field(min_length=1, max_length=10000)


class Video(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    workspace_id: uuid.UUID
    procedure_code: str
    procedure_name: str | None = None
    title: str
    operation_date: date | None
    duration_s: float | None
    status: str
    size_bytes: int | None
    analysis_requested: bool
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    poster_url: str | None = None
    is_owner: bool = True
    permission: str | None = None


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    operation_date: date | None = None


class StorageUsage(BaseModel):
    used_bytes: int
    quota_bytes: int
    videos: int


# ---------- helpers ----------

_SELECT = """
select v.id, v.owner_user_id, v.workspace_id, v.procedure_code, p.name as procedure_name,
       v.title, v.operation_date, v.duration_s, v.status::text as status, v.size_bytes,
       v.analysis_requested, v.last_error, v.created_at, v.updated_at, v.thumbnail_key,
       v.owner_user_id = %(uid)s as is_owner,
       public.video_permission(v.id) as permission
from public.videos v
join public.procedures p on p.code = v.procedure_code
"""


def _to_video(row: dict[str, Any], storage: Storage) -> Video:
    poster = None
    if row.get("thumbnail_key"):
        poster = storage.presign_get(row["thumbnail_key"], ttl_seconds=3600)
    return Video(
        **{k: v for k, v in row.items() if k != "thumbnail_key"},
        poster_url=poster,
    )


def _extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Unsupported file type. Upload MP4, MOV, MKV or AVI.",
        )
    return ext


def _load_owned_uploading(cur: Any, video_id: uuid.UUID, user: AuthUser) -> dict[str, Any]:
    cur.execute(
        """
        select id, original_key, upload_id, status::text as status, size_bytes, analysis_requested,
               procedure_code
        from public.videos
        where id = %s and owner_user_id = %s and deleted_at is null
        """,
        (video_id, user.id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    if row["status"] != "uploading" or not row["upload_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "This video is not being uploaded")
    return row


def _personal_workspace(cur: Any, user: AuthUser) -> uuid.UUID:
    cur.execute("select id from public.workspaces where owner_user_id = %s", (user.id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return row["id"]


# ---------- storage meter ----------


@router.get("/storage", response_model=StorageUsage)
def storage_usage(user: AuthUser = Depends(get_current_user)) -> StorageUsage:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select coalesce(sum(size_bytes), 0) as used, count(*) as n
            from public.videos where owner_user_id = %s and deleted_at is null
            """,
            (user.id,),
        )
        row = cur.fetchone()
        cur.execute(
            "select storage_quota_gb from public.workspaces where owner_user_id = %s", (user.id,)
        )
        ws = cur.fetchone()
    quota_gb = int(ws["storage_quota_gb"]) if ws else 20
    return StorageUsage(
        used_bytes=int(row["used"]), quota_bytes=quota_gb * 1_000_000_000, videos=int(row["n"])
    )


# ---------- upload session ----------


@router.post("", response_model=UploadSession, status_code=status.HTTP_201_CREATED)
def create_upload(
    body: UploadCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> UploadSession:
    settings = get_settings()
    if not body.consent_confirmed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Confirm that the video contains no identifying patient data "
            "and that you may upload it.",
        )
    ext = _extension(body.filename)
    max_bytes = settings.upload_max_gb * 1_000_000_000
    if body.size_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Files are limited to {settings.upload_max_gb} GB"
        )

    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            "select analysis_enabled from public.procedures where code = %s", (body.procedure_code,)
        )
        proc = cur.fetchone()
        if proc is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown procedure")
        workspace_id = body.workspace_id or _personal_workspace(cur, user)

        usage = storage_usage(user)
        if usage.used_bytes + body.size_bytes > usage.quota_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Storage quota exceeded")

        video_id = uuid.uuid4()
        key = Keys.original(str(video_id), ext)
        upload = storage.create_multipart(key, CONTENT_TYPES[ext])
        cur.execute(
            """
            insert into public.videos
              (id, owner_user_id, workspace_id, procedure_code, title, operation_date, status,
               original_key, upload_id, size_bytes, consent_confirmed_at, analysis_requested)
            values (%s, %s, %s, %s, %s, %s, 'uploading', %s, %s, %s, now(), %s)
            """,
            (
                video_id,
                user.id,
                workspace_id,
                body.procedure_code,
                body.title.strip(),
                body.operation_date,
                key,
                upload.upload_id,
                body.size_bytes,
                body.request_analysis and bool(proc["analysis_enabled"]),
            ),
        )

    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.VIDEO_UPLOAD,
            object_type="video",
            object_id=video_id,
            request=request,
            metadata={"size_bytes": body.size_bytes, "procedure": body.procedure_code},
        )

    part_size = upload.part_size_bytes
    part_count = max(1, -(-body.size_bytes // part_size))
    return UploadSession(
        video_id=video_id,
        upload_id=upload.upload_id,
        key=key,
        part_size_bytes=part_size,
        part_count=part_count,
    )


@router.get("/{video_id}/upload/parts", response_model=list[ListedPart])
def list_uploaded_parts(
    video_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> list[ListedPart]:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        row = _load_owned_uploading(cur, video_id, user)
    parts = storage.list_parts(row["original_key"], row["upload_id"])
    return [ListedPart(part_number=p.part_number, etag=p.etag) for p in parts]


@router.get("/{video_id}/upload/part/{part_number}", response_model=PartUrl)
def presign_upload_part(
    video_id: uuid.UUID,
    part_number: int,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> PartUrl:
    if not 1 <= part_number <= 10000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Part number out of range")
    with db.user_connection(user) as conn, conn.cursor() as cur:
        row = _load_owned_uploading(cur, video_id, user)
    ttl = 3600
    url = storage.presign_part(row["original_key"], row["upload_id"], part_number, ttl_seconds=ttl)
    return PartUrl(part_number=part_number, url=url, expires_in=ttl)


@router.post("/{video_id}/upload/complete", response_model=Video)
def complete_upload(
    video_id: uuid.UUID,
    body: CompleteIn,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Video:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        row = _load_owned_uploading(cur, video_id, user)
    info = storage.complete_multipart(
        row["original_key"],
        row["upload_id"],
        [CompletedPart(part_number=p.part_number, etag=p.etag) for p in body.parts],
    )
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update public.videos
            set status = 'processing', size_bytes = %s, upload_id = null
            where id = %s
            """,
            (info.size_bytes, video_id),
        )
        cur.execute(
            "insert into public.jobs (type, video_id, payload) values ('transcode', %s, %s::jsonb)",
            (video_id, json.dumps({"original_key": row["original_key"]})),
        )
    return get_video(video_id, user, storage)


@router.delete("/{video_id}/upload", status_code=status.HTTP_204_NO_CONTENT)
def abort_upload(
    video_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Response:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        row = _load_owned_uploading(cur, video_id, user)
    storage.abort_multipart(row["original_key"], row["upload_id"])
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute("delete from public.videos where id = %s and status = 'uploading'", (video_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- library ----------

SORTS = {
    "created_desc": "v.created_at desc",
    "created_asc": "v.created_at asc",
    "operation_desc": "v.operation_date desc nulls last, v.created_at desc",
    "operation_asc": "v.operation_date asc nulls last, v.created_at asc",
    "duration_desc": "v.duration_s desc nulls last",
    "duration_asc": "v.duration_s asc nulls last",
}


@router.get("", response_model=list[Video])
def list_videos(
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
    scope: Literal["mine", "shared", "all"] = "mine",
    q: str | None = Query(default=None, max_length=200),
    procedure: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "created_desc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Video]:
    clauses = ["v.deleted_at is null"]
    params: dict[str, Any] = {"uid": user.id, "limit": limit, "offset": offset}
    if scope == "mine":
        clauses.append("v.owner_user_id = %(uid)s")
    elif scope == "shared":
        clauses.append("v.owner_user_id <> %(uid)s")
    if q:
        clauses.append("v.title ilike %(q)s")
        params["q"] = f"%{q.strip()}%"
    if procedure:
        clauses.append("v.procedure_code = %(procedure)s")
        params["procedure"] = procedure
    if status_filter:
        if not re.fullmatch(r"[a-z_]+", status_filter):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Bad status")
        clauses.append("v.status::text = %(status)s")
        params["status"] = status_filter
    if date_from:
        clauses.append("v.operation_date >= %(date_from)s")
        params["date_from"] = date_from
    if date_to:
        clauses.append("v.operation_date <= %(date_to)s")
        params["date_to"] = date_to
    order = SORTS.get(sort, SORTS["created_desc"])

    where = " and ".join(clauses)
    sql = f"{_SELECT} where {where} order by {order} limit %(limit)s offset %(offset)s"  # noqa: S608
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_to_video(r, storage) for r in rows]


@router.get("/{video_id}", response_model=Video)
def get_video(
    video_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Video:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            f"{_SELECT} where v.id = %(id)s and v.deleted_at is null",
            {"uid": user.id, "id": video_id},
        )  # noqa: S608
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return _to_video(row, storage)


@router.patch("/{video_id}", response_model=Video)
def update_video(
    video_id: uuid.UUID,
    body: VideoUpdate,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Video:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")
    if "title" in changes:
        changes["title"] = changes["title"].strip()
    sets = ", ".join(f"{k} = %({k})s" for k in changes)
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            f"update public.videos set {sets} "  # noqa: S608
            "where id = %(id)s and deleted_at is null returning id",
            {**changes, "id": video_id},
        )
        if cur.fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return get_video(video_id, user, storage)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: uuid.UUID,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Owner deletes: the row is soft deleted at once (disappears everywhere),
    and a purge job removes every object under the video prefix."""
    # Ownership is checked as the user (RLS); the soft delete itself runs with
    # the service connection because a row with deleted_at set is no longer
    # visible to the user, which makes "update ... returning" fail under RLS.
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select original_key, upload_id from public.videos
            where id = %s and owner_user_id = %s and deleted_at is null
            """,
            (video_id, user.id),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    if row["upload_id"] and row["original_key"]:
        storage.abort_multipart(row["original_key"], row["upload_id"])
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute("update public.videos set deleted_at = now() where id = %s", (video_id,))
        cur.execute(
            "insert into public.jobs (type, video_id, payload) values ('purge', %s, %s::jsonb)",
            (
                video_id,
                json.dumps({"prefixes": [Keys.video_prefix(str(video_id))], "hard_delete": True}),
            ),
        )
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.VIDEO_DELETE,
            object_type="video",
            object_id=video_id,
            request=request,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- playback ----------


@router.get("/{video_id}/stream.m3u8")
def master_playlist(
    video_id: uuid.UUID,
    request: Request,
    user: AuthUser = Depends(get_current_user_or_query_token),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Master playlist with the renditions, each pointing at the API sub-playlist."""
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            "select hls_prefix, status::text as status from public.videos "
            "where id = %s and deleted_at is null",
            (video_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    if not row["hls_prefix"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Video is still processing")
    text = storage.get_bytes(row["hls_prefix"] + "master.m3u8").decode("utf-8")
    base = f"/videos/{video_id}/stream/"
    query_token = request.query_params.get("access_token")
    suffix = f"?access_token={query_token}" if query_token else ""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("http"):
            lines.append(base + s + suffix)
        else:
            lines.append(line)
    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.VIDEO_STREAM,
            object_type="video",
            object_id=video_id,
            request=request,
        )
    return Response(
        "\n".join(lines) + "\n",
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/{video_id}/stream/{rendition}.m3u8")
def rendition_playlist(
    video_id: uuid.UUID,
    rendition: str,
    request: Request,
    user: AuthUser = Depends(get_current_user_or_query_token),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Rendition playlist with every segment line rewritten to a presigned URL."""
    if not re.fullmatch(r"[a-z0-9_]+", rendition):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    settings = get_settings()
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            "select hls_prefix, size_bytes, duration_s from public.videos "
            "where id = %s and deleted_at is null",
            (video_id,),
        )
        row = cur.fetchone()
    if row is None or not row["hls_prefix"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    prefix = row["hls_prefix"] + rendition + "/"
    try:
        text = storage.get_bytes(prefix + "index.m3u8").decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rendition not found") from exc
    out = storage.presign_playlist(text, prefix, ttl_seconds=settings.storage_presign_ttl_seconds)
    # Cost monitor input: a playlist fetch is counted as one full play of the
    # rendition (an upper bound; segments are not individually observed).
    estimate = _rendition_bytes(rendition, row["duration_s"])
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into public.streaming_usage (video_id, user_id, bytes_estimated) "
            "values (%s, %s, %s)",
            (video_id, user.id, estimate),
        )
    return Response(
        out,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/{video_id}/sprite-index")
def sprite_index(
    video_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> dict[str, Any]:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            "select sprite_key from public.videos where id = %s and deleted_at is null", (video_id,)
        )
        row = cur.fetchone()
    if row is None or not row["sprite_key"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    key = row["sprite_key"].rsplit("/", 1)[0] + "/sprite.json"
    try:
        return json.loads(storage.get_bytes(key).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc


RENDITION_BITRATES = {"720p": 2_000_000, "480p": 1_000_000}


def _rendition_bytes(rendition: str, duration_s: float | None) -> int:
    bitrate = RENDITION_BITRATES.get(rendition, 1_500_000)
    return int((float(duration_s or 0) * bitrate) / 8)


@router.get("/{video_id}/assets/{kind}")
def asset_url(
    video_id: uuid.UUID,
    kind: Literal["poster", "sprite", "proxy", "original"],
    user: AuthUser = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> dict[str, str]:
    """A short-lived URL for a non-streaming asset (the owner only for the original)."""
    column = {
        "poster": "thumbnail_key",
        "sprite": "sprite_key",
        "proxy": "proxy_key",
        "original": "original_key",
    }[kind]
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            f"select {column} as key, owner_user_id from public.videos "  # noqa: S608
            "where id = %s and deleted_at is null",
            (video_id,),
        )
        row = cur.fetchone()
    if row is None or not row["key"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if kind == "original" and row["owner_user_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can download the original")
    ttl = 3600
    return {"url": storage.presign_get(row["key"], ttl_seconds=ttl), "expires_in": str(ttl)}
