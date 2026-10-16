"""Feedback from users and usage events (first-party, EU only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app import db
from app.auth import AuthUser, get_current_user

router = APIRouter(tags=["feedback"])

Category = Literal["bug", "idea", "question", "other"]


class FeedbackIn(BaseModel):
    category: Category = "other"
    message: str = Field(min_length=1, max_length=4000)
    page_url: str | None = Field(default=None, max_length=1000)
    app_version: str | None = Field(default=None, max_length=50)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    category: str
    message: str
    page_url: str | None
    status: str
    created_at: datetime


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    body: FeedbackIn, request: Request, user: AuthUser = Depends(get_current_user)
) -> FeedbackOut:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.feedback
              (user_id, category, message, page_url, app_version, user_agent)
            values (%s, %s, %s, %s, %s, %s)
            returning id, category::text as category, message, page_url,
                      status::text as status, created_at
            """,
            (
                user.id,
                body.category,
                body.message.strip(),
                body.page_url,
                body.app_version,
                request.headers.get("user-agent", "")[:512],
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return FeedbackOut(**row)


@router.get("/feedback/mine", response_model=list[FeedbackOut])
def my_feedback(user: AuthUser = Depends(get_current_user)) -> list[FeedbackOut]:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id, category::text as category, message, page_url,
                   status::text as status, created_at
            from public.feedback where user_id = %s order by created_at desc limit 100
            """,
            (user.id,),
        )
        rows = cur.fetchall()
    return [FeedbackOut(**r) for r in rows]


# ---------- usage events ----------

EVENT_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,3}$"


class UsageEventIn(BaseModel):
    event: str = Field(pattern=EVENT_PATTERN, max_length=80)
    page: str | None = Field(default=None, max_length=300)
    properties: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    session_id: str | None = Field(default=None, max_length=64)
    at: datetime | None = None


class UsageBatchIn(BaseModel):
    events: list[UsageEventIn] = Field(min_length=1, max_length=100)


@router.post("/usage/events", status_code=status.HTTP_202_ACCEPTED)
def record_usage(body: UsageBatchIn, user: AuthUser = Depends(get_current_user)) -> dict[str, int]:
    import json

    rows = [
        (
            user.id,
            e.event,
            e.page,
            json.dumps(_compact(e.properties)),
            e.duration_ms,
            e.session_id,
            e.at,
        )
        for e in body.events
    ]
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.usage_events
              (user_id, event, page, properties, duration_ms, session_id, at)
            values (%s, %s, %s, %s::jsonb, %s, %s, coalesce(%s, now()))
            """,
            rows,
        )
    return {"accepted": len(rows)}


def _compact(properties: dict[str, Any]) -> dict[str, Any]:
    """Keep properties small: at most 20 keys, scalar values, short strings."""
    out: dict[str, Any] = {}
    for key, value in list(properties.items())[:20]:
        if isinstance(value, bool | int | float) or value is None:
            out[str(key)[:40]] = value
        elif isinstance(value, str):
            out[str(key)[:40]] = value[:200]
    return out
