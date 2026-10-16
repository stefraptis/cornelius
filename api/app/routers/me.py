"""The signed-in user: profile, workspaces, memberships."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import audit, db
from app.auth import AuthUser, get_current_user

router = APIRouter(prefix="/me", tags=["me"])


class Profile(BaseModel):
    id: uuid.UUID
    full_name: str
    title: str | None = None
    specialty: str | None = None
    locale: str = "en"
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=100)
    specialty: str | None = Field(default=None, max_length=100)
    locale: str | None = Field(default=None, pattern="^[a-z]{2}(-[A-Z]{2})?$")


class Workspace(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    team_id: uuid.UUID | None = None
    storage_quota_gb: int


class TeamMembership(BaseModel):
    team_id: uuid.UUID
    team_name: str
    org_id: uuid.UUID | None = None
    role: str


class OrgMembership(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str


class Me(BaseModel):
    user_id: uuid.UUID
    email: str | None
    second_factor: bool
    profile: Profile
    workspaces: list[Workspace]
    teams: list[TeamMembership]
    organizations: list[OrgMembership]
    platform_admin: bool = False


@router.get("", response_model=Me)
def get_me(request: Request, user: AuthUser = Depends(get_current_user)) -> Me:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute("select * from public.profiles where id = %s", (user.id,))
        profile = cur.fetchone()
        if profile is None:
            # The auth trigger creates the profile; if it has not run yet
            # (first request right after sign up) create it now.
            cur.execute(
                "insert into public.profiles (id) values (%s) "
                "on conflict (id) do nothing returning *",
                (user.id,),
            )
            profile = cur.fetchone()
            if profile is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

        cur.execute(
            """
            select id, kind::text as kind, name, team_id, storage_quota_gb
            from public.workspaces
            order by kind, name
            """
        )
        workspaces = cur.fetchall()

        cur.execute(
            """
            select m.team_id, t.name as team_name, t.org_id, m.role::text as role
            from public.team_memberships m
            join public.teams t on t.id = m.team_id
            where m.user_id = %s and t.deleted_at is null
            order by t.name
            """,
            (user.id,),
        )
        teams = cur.fetchall()

        cur.execute("select 1 from public.platform_admins where user_id = %s", (user.id,))
        platform_admin = cur.fetchone() is not None

        cur.execute(
            """
            select m.org_id, o.name as org_name, m.role::text as role
            from public.org_memberships m
            join public.organizations o on o.id = m.org_id
            where m.user_id = %s and o.deleted_at is null
            order by o.name
            """,
            (user.id,),
        )
        orgs = cur.fetchall()

    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.PROFILE_VIEW,
            object_type="user",
            object_id=user.id,
            request=request,
        )
        conn.commit()

    return Me(
        user_id=user.id,
        email=user.email,
        second_factor=user.has_second_factor,
        profile=Profile(**profile),
        workspaces=[Workspace(**w) for w in workspaces],
        teams=[TeamMembership(**t) for t in teams],
        organizations=[OrgMembership(**o) for o in orgs],
        platform_admin=platform_admin,
    )


@router.patch("/profile", response_model=Profile)
def update_profile(
    body: ProfileUpdate, request: Request, user: AuthUser = Depends(get_current_user)
) -> Profile:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")

    assignments = ", ".join(f"{column} = %({column})s" for column in changes)
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(
            f"update public.profiles set {assignments} where id = %(id)s returning *",  # noqa: S608
            {**changes, "id": user.id},
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

    with db.service_connection() as conn:
        audit.record(
            conn,
            actor_id=user.id,
            action=audit.PROFILE_UPDATE,
            object_type="user",
            object_id=user.id,
            request=request,
            metadata={"fields": sorted(changes)},
        )
        conn.commit()
    return Profile(**row)
