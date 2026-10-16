"""Row-level security: the negative tests the build guideline requires.

Every test here answers one question: can a user see or change something
that is not theirs? The answer must be no, at the database layer, with no
API in between.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import psycopg
import pytest

from app.config import Settings
from tests.dbtest import (
    as_service,
    as_user,
    create_auth_user,
    personal_workspace,
    recreate_database,
    server_reachable,
)

pytestmark = pytest.mark.db


@dataclass
class World:
    """Two hospitals, two teams, and users in various roles."""

    url: str
    # Hospital A: admin, mentor, trainee; team "A surgery"
    a_admin: uuid.UUID
    a_mentor: uuid.UUID
    a_trainee: uuid.UUID
    a_org: uuid.UUID
    a_team: uuid.UUID
    # Hospital B: admin, surgeon; team "B surgery"
    b_admin: uuid.UUID
    b_surgeon: uuid.UUID
    b_org: uuid.UUID
    b_team: uuid.UUID
    # Solo surgeon with no memberships
    solo: uuid.UUID
    # Videos
    a_trainee_video: uuid.UUID  # owned by trainee, shared to team A (view)
    a_mentor_video: uuid.UUID  # owned by mentor, not shared
    b_video: uuid.UUID  # owned by B surgeon, shared to org B
    solo_video: uuid.UUID
    # An analysis on the trainee video
    a_analysis: uuid.UUID


@pytest.fixture(scope="module")
def world(settings: Settings) -> World:
    url = settings.database_url
    if not server_reachable(url):
        pytest.skip("PostgreSQL not reachable at DATABASE_URL; run `make db-local`")
    recreate_database(url)

    with psycopg.connect(url) as conn:
        a_admin = create_auth_user(conn, "a.admin@hospital-a.example", "Admin A")
        a_mentor = create_auth_user(conn, "a.mentor@hospital-a.example", "Mentor A")
        a_trainee = create_auth_user(conn, "a.trainee@hospital-a.example", "Trainee A")
        b_admin = create_auth_user(conn, "b.admin@hospital-b.example", "Admin B")
        b_surgeon = create_auth_user(conn, "b.surgeon@hospital-b.example", "Surgeon B")
        solo = create_auth_user(conn, "solo@example.org", "Solo Surgeon")

        a_org = conn.execute(
            "insert into public.organizations (name, country, created_by) values ('Hospital A','GR',%s) returning id",
            (a_admin,),
        ).fetchone()[0]
        b_org = conn.execute(
            "insert into public.organizations (name, country, created_by) values ('Hospital B','GR',%s) returning id",
            (b_admin,),
        ).fetchone()[0]
        conn.execute(
            "insert into public.org_memberships (org_id, user_id, role) values (%s,%s,'member'),(%s,%s,'member')",
            (a_org, a_mentor, a_org, a_trainee),
        )
        conn.execute(
            "insert into public.org_memberships (org_id, user_id, role) values (%s,%s,'member')",
            (b_org, b_surgeon),
        )
        a_team = conn.execute(
            "insert into public.teams (org_id, name, created_by) values (%s,'A surgery',%s) returning id",
            (a_org, a_mentor),
        ).fetchone()[0]
        conn.execute(
            "update public.team_memberships set role='mentor' where team_id=%s and user_id=%s",
            (a_team, a_mentor),
        )
        conn.execute(
            "insert into public.team_memberships (team_id, user_id, role) values (%s,%s,'trainee')",
            (a_team, a_trainee),
        )
        b_team = conn.execute(
            "insert into public.teams (org_id, name, created_by) values (%s,'B surgery',%s) returning id",
            (b_org, b_surgeon),
        ).fetchone()[0]

        def video(owner: uuid.UUID, title: str) -> uuid.UUID:
            ws = personal_workspace(conn, owner)
            return conn.execute(
                "insert into public.videos (owner_user_id, workspace_id, procedure_code, title, status) "
                "values (%s,%s,'lc',%s,'ready') returning id",
                (owner, ws, title),
            ).fetchone()[0]

        a_trainee_video = video(a_trainee, "Trainee case 1")
        a_mentor_video = video(a_mentor, "Mentor private case")
        b_video = video(b_surgeon, "B case")
        solo_video = video(solo, "Solo case")

        conn.execute(
            "insert into public.video_shares (video_id, team_id, permission, created_by) values (%s,%s,'view',%s)",
            (a_trainee_video, a_team, a_trainee),
        )
        conn.execute(
            "insert into public.video_shares (video_id, org_id, permission, created_by) values (%s,%s,'view',%s)",
            (b_video, b_org, b_surgeon),
        )

        mv = conn.execute(
            "select id from public.model_versions where is_active limit 1"
        ).fetchone()[0]
        a_analysis = conn.execute(
            "insert into public.analyses (video_id, model_version_id, status, mean_confidence, sampled_frames) "
            "values (%s,%s,'completed',0.925,1800) returning id",
            (a_trainee_video, mv),
        ).fetchone()[0]
        conn.execute(
            "insert into public.phase_segments (analysis_id, version, phase, start_s, end_s, mean_confidence) "
            "values (%s,0,'Preparation',0,120,0.97),(%s,0,'CalotTriangleDissection',120,900,0.93)",
            (a_analysis, a_analysis),
        )
        conn.commit()

    return World(
        url=url,
        a_admin=a_admin, a_mentor=a_mentor, a_trainee=a_trainee, a_org=a_org, a_team=a_team,
        b_admin=b_admin, b_surgeon=b_surgeon, b_org=b_org, b_team=b_team,
        solo=solo,
        a_trainee_video=a_trainee_video, a_mentor_video=a_mentor_video, b_video=b_video,
        solo_video=solo_video, a_analysis=a_analysis,
    )  # fmt: skip


def visible_videos(w: World, user: uuid.UUID) -> set[str]:
    with as_user(w.url, user) as conn:
        rows = conn.execute("select title from public.videos order by title").fetchall()
    return {r["title"] for r in rows}


# ---------- bootstrap ----------


def test_new_user_gets_profile_and_personal_workspace(world: World) -> None:
    with as_user(world.url, world.solo) as conn:
        profile = conn.execute(
            "select full_name from public.profiles where id = %s", (world.solo,)
        ).fetchone()
        ws = conn.execute("select kind::text as kind, name from public.workspaces").fetchall()
    assert profile == {"full_name": "Solo Surgeon"}
    assert ws == [{"kind": "personal", "name": "Personal"}]


def test_team_creator_becomes_owner_and_team_workspace_exists(world: World) -> None:
    with as_service(world.url) as conn:
        row = conn.execute(
            "select role::text as role from public.team_memberships where team_id=%s and user_id=%s",
            (world.b_team, world.b_surgeon),
        ).fetchone()
        ws = conn.execute(
            "select 1 from public.workspaces where team_id=%s", (world.b_team,)
        ).fetchone()
    assert row == {"role": "team_owner"}
    assert ws is not None


# ---------- videos: who sees what ----------


def test_solo_surgeon_sees_only_own_video(world: World) -> None:
    assert visible_videos(world, world.solo) == {"Solo case"}


def test_trainee_sees_own_video_but_not_mentors_private_video(world: World) -> None:
    assert visible_videos(world, world.a_trainee) == {"Trainee case 1"}


def test_mentor_sees_own_and_team_shared_video(world: World) -> None:
    assert visible_videos(world, world.a_mentor) == {"Mentor private case", "Trainee case 1"}


def test_org_admin_sees_team_shared_video_not_private_ones(world: World) -> None:
    assert visible_videos(world, world.a_admin) == {"Trainee case 1"}


def test_hospital_b_gets_nothing_from_hospital_a(world: World) -> None:
    assert visible_videos(world, world.b_admin) == {"B case"}
    assert visible_videos(world, world.b_surgeon) == {"B case"}


def test_org_share_is_visible_to_org_members_only(world: World) -> None:
    assert "B case" in visible_videos(world, world.b_admin)
    assert "B case" not in visible_videos(world, world.a_admin)
    assert "B case" not in visible_videos(world, world.solo)


def test_direct_select_by_id_of_foreign_video_returns_nothing(world: World) -> None:
    with as_user(world.url, world.b_surgeon) as conn:
        row = conn.execute(
            "select id from public.videos where id = %s", (world.a_trainee_video,)
        ).fetchone()
        count = conn.execute("select count(*) as n from public.videos").fetchone()
    assert row is None
    assert count == {"n": 1}


def test_soft_deleted_video_disappears(world: World) -> None:
    with as_service(world.url) as conn:
        vid = conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title, status, deleted_at) "
            "values (%s,%s,'lc','Deleted case','ready', now()) returning id",
            (world.solo, personal_workspace(conn, world.solo)),
        ).fetchone()["id"]
        conn.commit()
    assert "Deleted case" not in visible_videos(world, world.solo)
    with as_service(world.url) as conn:
        conn.execute("delete from public.videos where id = %s", (vid,))
        conn.commit()


# ---------- videos: who can write what ----------


def test_user_cannot_insert_video_owned_by_someone_else(world: World) -> None:
    with (
        as_user(world.url, world.b_surgeon) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) values (%s,%s,'lc','x')",
            (world.a_trainee, personal_workspace(conn, world.b_surgeon)),
        )


def test_user_cannot_insert_video_into_foreign_workspace(world: World) -> None:
    with as_service(world.url) as conn:
        a_ws = personal_workspace(conn, world.a_trainee)
    with (
        as_user(world.url, world.b_surgeon) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) values (%s,%s,'lc','x')",
            (world.b_surgeon, a_ws),
        )


def test_owner_can_insert_into_own_workspace(world: World) -> None:
    with as_user(world.url, world.solo) as conn:
        ws = conn.execute("select id from public.workspaces").fetchone()["id"]
        row = conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) "
            "values (%s,%s,'lc','New solo case') returning id",
            (world.solo, ws),
        ).fetchone()
        assert row is not None
        conn.rollback()


def test_viewer_cannot_update_shared_video(world: World) -> None:
    with as_user(world.url, world.a_mentor) as conn:
        result = conn.execute(
            "update public.videos set title = 'hijacked' where id = %s", (world.a_trainee_video,)
        )
        assert result.rowcount == 0


def test_only_owner_can_share(world: World) -> None:
    with (
        as_user(world.url, world.a_mentor) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.video_shares (video_id, team_id, permission, created_by) values (%s,%s,'view',%s)",
            (world.a_trainee_video, world.b_team, world.a_mentor),
        )


def test_users_cannot_hard_delete_videos(world: World) -> None:
    with (
        as_user(world.url, world.solo) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("delete from public.videos where id = %s", (world.solo_video,))


# ---------- analysis outputs follow the video ----------


def test_analysis_rows_visible_to_video_viewers_only(world: World) -> None:
    for user, expected in (
        (world.a_trainee, 2),
        (world.a_mentor, 2),
        (world.a_admin, 2),
        (world.b_surgeon, 0),
        (world.solo, 0),
    ):
        with as_user(world.url, user) as conn:
            n = conn.execute("select count(*) as n from public.phase_segments").fetchone()["n"]
            m = conn.execute("select count(*) as n from public.analyses").fetchone()["n"]
        assert (n, m) == (expected, 1 if expected else 0), f"user {user}"


def test_phase_correction_allowed_for_owner_and_mentor_only_as_new_version(world: World) -> None:
    insert = (
        "insert into public.phase_segments (analysis_id, version, phase, start_s, end_s, verified_by) "
        "values (%s,%s,'Preparation',0,110,%s)"
    )
    # owner: ok
    with as_user(world.url, world.a_trainee) as conn:
        conn.execute(insert, (world.a_analysis, 1, world.a_trainee))
        conn.rollback()
    # mentor of the team the video is shared to: ok
    with as_user(world.url, world.a_mentor) as conn:
        conn.execute(insert, (world.a_analysis, 1, world.a_mentor))
        conn.rollback()
    # org admin (not a mentor): no
    with (
        as_user(world.url, world.a_admin) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (world.a_analysis, 1, world.a_admin))
    # another hospital: no
    with (
        as_user(world.url, world.b_surgeon) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (world.a_analysis, 1, world.b_surgeon))
    # owner trying to overwrite the raw model output (version 0): no
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (world.a_analysis, 0, world.a_trainee))
    # claiming someone else verified it: no
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (world.a_analysis, 1, world.a_mentor))


def test_raw_model_output_cannot_be_updated_or_deleted_by_users(world: World) -> None:
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "update public.phase_segments set phase='x' where analysis_id=%s", (world.a_analysis,)
        )
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("delete from public.phase_segments where analysis_id=%s", (world.a_analysis,))


# ---------- profiles, teams, organizations ----------


def test_profiles_visible_only_inside_shared_context(world: World) -> None:
    with as_user(world.url, world.a_trainee) as conn:
        names = {
            r["full_name"] for r in conn.execute("select full_name from public.profiles").fetchall()
        }
    assert names == {"Admin A", "Mentor A", "Trainee A"}
    with as_user(world.url, world.solo) as conn:
        names = {
            r["full_name"] for r in conn.execute("select full_name from public.profiles").fetchall()
        }
    assert names == {"Solo Surgeon"}


def test_user_cannot_update_another_users_profile(world: World) -> None:
    with as_user(world.url, world.a_trainee) as conn:
        result = conn.execute(
            "update public.profiles set full_name='x' where id=%s", (world.a_mentor,)
        )
        assert result.rowcount == 0


def test_organizations_and_teams_isolated_between_hospitals(world: World) -> None:
    with as_user(world.url, world.a_admin) as conn:
        orgs = {r["name"] for r in conn.execute("select name from public.organizations").fetchall()}
        teams = {r["name"] for r in conn.execute("select name from public.teams").fetchall()}
        members = conn.execute("select count(*) as n from public.team_memberships").fetchone()["n"]
    assert orgs == {"Hospital A"}
    assert teams == {"A surgery"}
    assert members == 2
    with as_user(world.url, world.b_surgeon) as conn:
        orgs = {r["name"] for r in conn.execute("select name from public.organizations").fetchall()}
        teams = {r["name"] for r in conn.execute("select name from public.teams").fetchall()}
    assert orgs == {"Hospital B"}
    assert teams == {"B surgery"}


def test_trainee_cannot_add_members_or_promote_self(world: World) -> None:
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.team_memberships (team_id, user_id, role) values (%s,%s,'mentor')",
            (world.a_team, world.solo),
        )
    with as_user(world.url, world.a_trainee) as conn:
        result = conn.execute(
            "update public.team_memberships set role='team_owner' where team_id=%s and user_id=%s",
            (world.a_team, world.a_trainee),
        )
        assert result.rowcount == 0


def test_non_admin_cannot_create_team_inside_organization(world: World) -> None:
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.teams (org_id, name, created_by) values (%s,'Rogue team',%s)",
            (world.a_org, world.a_trainee),
        )


def test_anyone_can_create_independent_team(world: World) -> None:
    with as_user(world.url, world.solo) as conn:
        row = conn.execute(
            "insert into public.teams (name, created_by) values ('Research group',%s) returning id",
            (world.solo,),
        ).fetchone()
        assert row is not None
        conn.rollback()


def test_member_can_leave_team_but_not_remove_others(world: World) -> None:
    with as_user(world.url, world.a_trainee) as conn:
        result = conn.execute(
            "delete from public.team_memberships where team_id=%s and user_id=%s",
            (world.a_team, world.a_mentor),
        )
        assert result.rowcount == 0
        result = conn.execute(
            "delete from public.team_memberships where team_id=%s and user_id=%s",
            (world.a_team, world.a_trainee),
        )
        assert result.rowcount == 1
        conn.rollback()


# ---------- jobs, registry, audit ----------


def test_jobs_visible_only_for_viewable_videos_and_not_claimable_by_users(world: World) -> None:
    with as_service(world.url) as conn:
        conn.execute(
            "insert into public.jobs (type, video_id) values ('transcode', %s)",
            (world.a_trainee_video,),
        )
        conn.commit()
    with as_user(world.url, world.a_mentor) as conn:
        assert conn.execute("select count(*) as n from public.jobs").fetchone()["n"] == 1
    with as_user(world.url, world.b_surgeon) as conn:
        assert conn.execute("select count(*) as n from public.jobs").fetchone()["n"] == 0
    with (
        as_user(world.url, world.a_trainee) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "select * from public.claim_next_job(array['transcode']::public.job_type[], 'me')"
        )
    with as_service(world.url) as conn:
        job = conn.execute(
            "select * from public.claim_next_job(array['transcode']::public.job_type[], 'worker-1')"
        ).fetchone()
        assert (
            job["status"] == "running" and job["locked_by"] == "worker-1" and job["attempts"] == 1
        )
        nothing = conn.execute(
            "select * from public.claim_next_job(array['transcode']::public.job_type[], 'worker-2')"
        ).fetchone()
        assert nothing is None
        conn.rollback()


def test_procedure_registry_readable_lc_enabled_others_coming_soon(world: World) -> None:
    with as_user(world.url, world.solo) as conn:
        rows = conn.execute(
            "select code, analysis_enabled, model_version_id is not null as has_model "
            "from public.procedures order by display_order"
        ).fetchall()
    assert rows[0] == {"code": "lc", "analysis_enabled": True, "has_model": True}
    assert all(not r["analysis_enabled"] for r in rows[1:])
    with (
        as_user(world.url, world.solo) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "update public.procedures set analysis_enabled = true where code = 'robotic_chole'"
        )


def test_login_is_audited_by_trigger(world: World) -> None:
    with as_service(world.url) as conn:
        conn.execute("update auth.users set last_sign_in_at = now() where id = %s", (world.solo,))
        conn.commit()
        rows = conn.execute(
            "select action, object_type from public.audit_log where actor_id = %s", (world.solo,)
        ).fetchall()
    assert {"action": "auth.login", "object_type": "user"} in rows


def test_audit_log_private_to_actor_and_not_forgeable(world: World) -> None:
    with as_user(world.url, world.solo) as conn:
        conn.execute(
            "insert into public.audit_log (actor_id, action, object_type, object_id) values (%s,'video.view','video',%s)",
            (world.solo, str(world.solo_video)),
        )
        conn.commit()
    with (
        as_user(world.url, world.solo) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.audit_log (actor_id, action) values (%s,'video.view')",
            (world.a_trainee,),
        )
    with as_user(world.url, world.a_trainee) as conn:
        assert conn.execute("select count(*) as n from public.audit_log").fetchone()["n"] == 0
    with as_user(world.url, world.solo) as conn:
        assert conn.execute("select count(*) as n from public.audit_log").fetchone()["n"] >= 2
