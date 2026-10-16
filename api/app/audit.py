"""Audit log writer (Build Guideline, Section 13).

Records who viewed, shared, exported, or deleted what. Logins are recorded by
a database trigger on auth.users; everything the API does is recorded here
with the service connection so the write cannot be blocked by RLS.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import uuid
from typing import Any

import psycopg
from fastapi import Request

log = logging.getLogger(__name__)

# Action names, kept in one place so reports can rely on them.
LOGIN = "auth.login"
PROFILE_VIEW = "profile.view"
PROFILE_UPDATE = "profile.update"
VIDEO_VIEW = "video.view"
VIDEO_UPLOAD = "video.upload"
VIDEO_SHARE = "video.share"
VIDEO_UNSHARE = "video.unshare"
VIDEO_DELETE = "video.delete"
VIDEO_STREAM = "video.stream"
REPORT_VIEW = "report.view"
EXPORT_CREATE = "export.create"
PERMISSION_CHANGE = "permission.change"


def client_ip(request: Request | None) -> str | None:
    """Best-effort client address; None when it is not a valid IP (test clients, sockets)."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    candidate = forwarded.split(",")[0].strip() if forwarded else None
    if not candidate and request.client:
        candidate = request.client.host
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def record(
    conn: psycopg.Connection,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    object_type: str | None = None,
    object_id: str | uuid.UUID | None = None,
    request: Request | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert one audit row. Never raises: a logging failure must not break the request."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.audit_log
                  (actor_id, action, object_type, object_id, ip, user_agent, metadata)
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    actor_id,
                    action,
                    object_type,
                    str(object_id) if object_id is not None else None,
                    client_ip(request),
                    request.headers.get("user-agent", "")[:512] if request else None,
                    json.dumps(metadata or {}),
                ),
            )
    except Exception:  # noqa: BLE001
        log.exception("audit.write_failed", extra={"ctx_action": action})
