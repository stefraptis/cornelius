"""GDPR mechanics for the signed-in user: consent records, data export,
account deletion (Build Guideline, Section 13)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import audit, db
from app.auth import AuthUser, get_current_user
from app.storage import Keys

router = APIRouter(prefix="/me", tags=["privacy"])


# ---------- consent ----------


class ConsentIn(BaseModel):
    terms_version: str = Field(min_length=1, max_length=40)
    privacy_version: str = Field(min_length=1, max_length=40)


class ConsentOut(BaseModel):
    terms_version: str | None
    privacy_version: str | None
    accepted_at: datetime | None


def _latest_consent(cur: Any, user_id: uuid.UUID) -> dict[str, Any] | None:
    cur.execute(
        """
        select terms_version, privacy_version, accepted_at
        from public.consents where user_id = %s
        order by accepted_at desc limit 1
        """,
        (user_id,),
    )
    return cur.fetchone()


@router.get("/consent", response_model=ConsentOut)
def get_consent(user: AuthUser = Depends(get_current_user)) -> ConsentOut:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        row = _latest_consent(cur, user.id)
        if row is None:
            # Sign-up records the accepted versions in the user metadata (the
            # API has no token yet at that moment). Copy them over once.
            meta = (user.claims or {}).get("user_metadata") or {}
            terms = meta.get("accepted_terms_version")
            privacy = meta.get("accepted_privacy_version")
            if terms and privacy:
                cur.execute(
                    """
                    insert into public.consents
                      (user_id, terms_version, privacy_version, accepted_at)
                    values (%s, %s, %s, coalesce(%s::timestamptz, now()))
                    returning terms_version, privacy_version, accepted_at
                    """,
                    (user.id, str(terms)[:40], str(privacy)[:40], meta.get("accepted_at")),
                )
                row = cur.fetchone()
    if row is None:
        return ConsentOut(terms_version=None, privacy_version=None, accepted_at=None)
    return ConsentOut(**row)


@router.post("/consent", response_model=ConsentOut)
def record_consent(
    body: ConsentIn, request: Request, user: AuthUser = Depends(get_current_user)
) -> ConsentOut:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.consents (user_id, terms_version, privacy_version, ip, user_agent)
            values (%s, %s, %s, %s, %s)
            returning terms_version, privacy_version, accepted_at
            """,
            (
                user.id,
                body.terms_version,
                body.privacy_version,
                audit.client_ip(request),
                request.headers.get("user-agent", "")[:512],
            ),
        )
        row = cur.fetchone()
    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action="consent.accept",
            object_type="user",
            object_id=user.id,
            request=request,
            metadata={"terms": body.terms_version, "privacy": body.privacy_version},
        )
    assert row is not None
    return ConsentOut(**row)


# ---------- data export ----------

EXPORT_TABLES: dict[str, str] = {
    "profile": "select * from public.profiles where id = %(uid)s",
    "workspaces": "select * from public.workspaces where owner_user_id = %(uid)s",
    "team_memberships": "select * from public.team_memberships where user_id = %(uid)s",
    "org_memberships": "select * from public.org_memberships where user_id = %(uid)s",
    "videos": "select * from public.videos where owner_user_id = %(uid)s",
    "consents": "select * from public.consents where user_id = %(uid)s",
    "feedback": "select * from public.feedback where user_id = %(uid)s",
    "usage_events": "select * from public.usage_events where user_id = %(uid)s",
    "audit_log": "select * from public.audit_log where actor_id = %(uid)s",
}


@router.get("/export")
def export_my_data(request: Request, user: AuthUser = Depends(get_current_user)) -> Response:
    """Everything we hold about the account, as one JSON file (Article 15 and 20).

    Videos themselves are large and are downloaded from the library; this
    export lists them with their metadata.
    """
    payload: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "user_id": str(user.id),
        "email": user.email,
    }
    with db.user_connection(user) as conn, conn.cursor() as cur:
        for name, sql in EXPORT_TABLES.items():
            cur.execute(sql, {"uid": user.id})
            payload[name] = cur.fetchall()
    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.EXPORT_CREATE,
            object_type="user",
            object_id=user.id,
            request=request,
        )
    body = json.dumps(payload, default=str, indent=2)
    filename = f"cornelius-export-{datetime.now(UTC):%Y%m%d}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- account deletion ----------


class DeleteIn(BaseModel):
    confirm_email: str


@router.post("/delete", status_code=status.HTTP_202_ACCEPTED)
def delete_my_account(
    body: DeleteIn, request: Request, user: AuthUser = Depends(get_current_user)
) -> dict[str, str]:
    """Delete the account now (Article 17).

    The auth user row is removed, which cascades to profile, workspace,
    memberships, videos metadata, consents, feedback, usage and comments.
    Storage objects of the user's videos are removed by a purge job. Audit
    rows keep the actor id but no longer resolve to a person.
    """
    if not user.email or body.confirm_email.strip().lower() != user.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type your account email to confirm")

    with db.service_connection() as conn, conn.cursor() as cur:
        cur.execute("select id from public.videos where owner_user_id = %s", (user.id,))
        prefixes = [Keys.video_prefix(str(r["id"])) for r in cur.fetchall()]
        cur.execute(
            """
            insert into public.account_deletions (user_id, storage_prefixes)
            values (%s, %s) returning id
            """,
            (user.id, prefixes),
        )
        deletion_id = cur.fetchone()["id"]
        if prefixes:
            cur.execute(
                "insert into public.jobs (type, payload) values ('purge', %s::jsonb)",
                (json.dumps({"deletion_id": str(deletion_id), "prefixes": prefixes}),),
            )
        audit.record(
            conn,
            actor_id=user.id,
            action="account.delete",
            object_type="user",
            object_id=user.id,
            request=request,
            metadata={"videos": len(prefixes)},
        )
        cur.execute("delete from auth.users where id = %s", (user.id,))
    return {"status": "deleted"}
