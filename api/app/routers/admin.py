"""Platform admin views: usage counts and feedback across accounts.

Only members of public.platform_admins may call these. After the gate, the
queries run with the service connection: an admin must see every account's
name and counts, which the per-user RLS on profiles would hide.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app import db
from app.auth import AuthUser, get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def require_platform_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute("select 1 from public.platform_admins where user_id = %s", (user.id,))
        if cur.fetchone() is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin access required")
    return user


class DailyCount(BaseModel):
    day: date
    events: int
    users: int


class EventCount(BaseModel):
    event: str
    events: int
    users: int


class UserRow(BaseModel):
    user_id: uuid.UUID | None
    full_name: str | None
    events: int
    last_seen: datetime | None


class UsageSummary(BaseModel):
    days: int
    total_users: int
    active_users: int
    total_events: int
    feedback_new: int
    daily: list[DailyCount]
    by_event: list[EventCount]
    top_users: list[UserRow]


@router.get("/usage", response_model=UsageSummary)
def usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    user: AuthUser = Depends(require_platform_admin),
) -> UsageSummary:
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute("select count(*) as n from public.profiles")
        total_users = int(cur.fetchone()["n"])
        cur.execute(
            """
            select count(*) as events, count(distinct user_id) as users
            from public.usage_events where at >= now() - make_interval(days => %s)
            """,
            (days,),
        )
        totals = cur.fetchone()
        cur.execute("select count(*) as n from public.feedback where status = 'new'")
        feedback_new = int(cur.fetchone()["n"])
        cur.execute(
            """
            select date_trunc('day', at)::date as day, count(*) as events,
                   count(distinct user_id) as users
            from public.usage_events
            where at >= now() - make_interval(days => %s)
            group by 1 order by 1
            """,
            (days,),
        )
        daily = cur.fetchall()
        cur.execute(
            """
            select event, count(*) as events, count(distinct user_id) as users
            from public.usage_events
            where at >= now() - make_interval(days => %s)
            group by 1 order by 2 desc limit 50
            """,
            (days,),
        )
        by_event = cur.fetchall()
        cur.execute(
            """
            select u.user_id, p.full_name, count(*) as events, max(u.at) as last_seen
            from public.usage_events u
            left join public.profiles p on p.id = u.user_id
            where u.at >= now() - make_interval(days => %s)
            group by 1, 2 order by 3 desc limit 25
            """,
            (days,),
        )
        top_users = cur.fetchall()

    return UsageSummary(
        days=days,
        total_users=total_users,
        active_users=int(totals["users"]),
        total_events=int(totals["events"]),
        feedback_new=feedback_new,
        daily=[DailyCount(**r) for r in daily],
        by_event=[EventCount(**r) for r in by_event],
        top_users=[UserRow(**r) for r in top_users],
    )


class FeedbackRow(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    full_name: str | None
    category: str
    message: str
    page_url: str | None
    status: str
    admin_note: str | None
    created_at: datetime


@router.get("/feedback", response_model=list[FeedbackRow])
def list_feedback(
    status_filter: str | None = Query(default=None, alias="status"),
    user: AuthUser = Depends(require_platform_admin),
) -> list[FeedbackRow]:
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select f.id, f.user_id, p.full_name, f.category::text as category, f.message,
                   f.page_url,
                   f.status::text as status, f.admin_note, f.created_at
            from public.feedback f
            left join public.profiles p on p.id = f.user_id
            where (%s::text is null or f.status::text = %s)
            order by f.created_at desc limit 200
            """,
            (status_filter, status_filter),
        )
        rows = cur.fetchall()
    return [FeedbackRow(**r) for r in rows]


class FeedbackUpdate(BaseModel):
    status: str | None = None
    admin_note: str | None = None


@router.patch("/feedback/{feedback_id}", response_model=FeedbackRow)
def update_feedback(
    feedback_id: uuid.UUID,
    body: FeedbackUpdate,
    user: AuthUser = Depends(require_platform_admin),
) -> FeedbackRow:
    changes: dict[str, Any] = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")
    sets = ", ".join(f"{k} = %({k})s" for k in changes)
    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"update public.feedback set {sets} where id = %(id)s returning id",  # noqa: S608
            {**changes, "id": feedback_id},
        )
        if cur.fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
        cur.execute(
            """
            select f.id, f.user_id, p.full_name, f.category::text as category, f.message,
                   f.page_url,
                   f.status::text as status, f.admin_note, f.created_at
            from public.feedback f left join public.profiles p on p.id = f.user_id
            where f.id = %s
            """,
            (feedback_id,),
        )
        row = cur.fetchone()
    assert row is not None
    return FeedbackRow(**row)
