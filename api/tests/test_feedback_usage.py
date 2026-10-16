"""Feedback, usage events, and the platform admin gate."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.main import create_app
from tests.conftest import make_token
from tests.dbtest import as_service, as_user, create_auth_user, recreate_database, server_reachable

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client(settings: Settings) -> Iterator[TestClient]:
    if not server_reachable(settings.database_url):
        pytest.skip("PostgreSQL not reachable at DATABASE_URL; run `make db-local`")
    recreate_database(settings.database_url)
    db.close_pool()
    with TestClient(create_app()) as test_client:
        yield test_client
    db.close_pool()


@pytest.fixture(scope="module")
def users(settings: Settings, client: TestClient) -> dict[str, uuid.UUID]:
    with psycopg.connect(settings.database_url) as conn:
        admin = create_auth_user(conn, "admin@example.org", "Platform Admin")
        alice = create_auth_user(conn, "alice@example.org", "Alice")
        bob = create_auth_user(conn, "bob@example.org", "Bob")
        conn.execute(
            "insert into public.platform_admins (user_id, note) values (%s, 'owner')", (admin,)
        )
        conn.commit()
    return {"admin": admin, "alice": alice, "bob": bob}


def auth(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


def test_feedback_round_trip(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    r = client.post(
        "/feedback",
        json={
            "category": "bug",
            "message": "The timeline jumps",
            "page_url": "/library",
            "app_version": "0.1.0",
        },
        headers=auth(users["alice"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "new"
    mine = client.get("/feedback/mine", headers=auth(users["alice"])).json()
    assert [m["message"] for m in mine] == ["The timeline jumps"]
    assert client.get("/feedback/mine", headers=auth(users["bob"])).json() == []


def test_feedback_validation(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    assert (
        client.post("/feedback", json={"message": ""}, headers=auth(users["alice"])).status_code
        == 422
    )
    assert (
        client.post(
            "/feedback", json={"message": "x", "category": "rant"}, headers=auth(users["alice"])
        ).status_code
        == 422
    )


def test_usage_events_batch(
    client: TestClient, users: dict[str, uuid.UUID], settings: Settings
) -> None:
    r = client.post(
        "/usage/events",
        json={
            "events": [
                {"event": "page.view", "page": "/library", "session_id": "s1"},
                {
                    "event": "video.play",
                    "page": "/videos/1",
                    "properties": {"speed": 1.5, "nested": {"x": 1}, "long": "a" * 500},
                    "duration_ms": 1200,
                },
            ]
        },
        headers=auth(users["alice"]),
    )
    assert r.status_code == 202 and r.json() == {"accepted": 2}
    assert (
        client.post(
            "/usage/events",
            json={"events": [{"event": "Bad Event!"}]},
            headers=auth(users["alice"]),
        ).status_code
        == 422
    )
    with as_service(settings.database_url) as conn:
        props = conn.execute(
            "select properties from public.usage_events where event = 'video.play'"
        ).fetchone()["properties"]
    assert props["speed"] == 1.5 and "nested" not in props and len(props["long"]) == 200


def test_users_cannot_write_events_for_others(
    settings: Settings, users: dict[str, uuid.UUID]
) -> None:
    with (
        as_user(settings.database_url, users["bob"]) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.usage_events (user_id, event) values (%s, 'page.view')",
            (users["alice"],),
        )
    with (
        as_user(settings.database_url, users["bob"]) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into public.feedback (user_id, message) values (%s, 'forged')",
            (users["alice"],),
        )


def test_admin_gate_and_summary(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    assert client.get("/admin/usage", headers=auth(users["alice"])).status_code == 403
    assert client.get("/admin/feedback", headers=auth(users["bob"])).status_code == 403
    assert client.get("/me", headers=auth(users["alice"])).json()["platform_admin"] is False
    assert client.get("/me", headers=auth(users["admin"])).json()["platform_admin"] is True

    summary = client.get("/admin/usage?days=7", headers=auth(users["admin"])).json()
    assert summary["total_users"] == 3
    assert summary["active_users"] == 1
    assert summary["total_events"] == 2
    assert summary["feedback_new"] == 1
    assert {e["event"]: e["events"] for e in summary["by_event"]} == {
        "page.view": 1,
        "video.play": 1,
    }
    assert summary["top_users"][0]["full_name"] == "Alice"
    assert len(summary["daily"]) == 1


def test_admin_feedback_list_and_update(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    rows = client.get("/admin/feedback", headers=auth(users["admin"])).json()
    assert len(rows) == 1 and rows[0]["full_name"] == "Alice"
    fid = rows[0]["id"]
    r = client.patch(
        f"/admin/feedback/{fid}",
        json={"status": "planned", "admin_note": "M1"},
        headers=auth(users["admin"]),
    )
    assert r.status_code == 200 and r.json()["status"] == "planned"
    assert (
        client.patch(
            f"/admin/feedback/{fid}", json={"status": "done"}, headers=auth(users["alice"])
        ).status_code
        == 403
    )
    assert (
        client.get("/admin/feedback?status=planned", headers=auth(users["admin"])).json()[0]["id"]
        == fid
    )
    assert client.get("/admin/feedback?status=new", headers=auth(users["admin"])).json() == []
    # Users cannot change their own feedback status (RLS), even directly.
    assert (
        client.get("/feedback/mine", headers=auth(users["alice"])).json()[0]["status"] == "planned"
    )
