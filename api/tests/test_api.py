"""API endpoint tests against the real database (RLS applied through the API)."""

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
from tests.dbtest import as_service, create_auth_user, recreate_database, server_reachable

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
        alice = create_auth_user(conn, "alice@example.org", "Alice Surgeon")
        bob = create_auth_user(conn, "bob@example.org", "Bob Surgeon")
    return {"alice": alice, "bob": bob}


def auth(user_id: uuid.UUID, email: str = "x@example.org") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id, email)}"}


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/db").json()["status"] == "ok"


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_me_returns_profile_and_personal_workspace(
    client: TestClient, users: dict[str, uuid.UUID]
) -> None:
    response = client.get("/me", headers=auth(users["alice"], "alice@example.org"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == str(users["alice"])
    assert body["email"] == "alice@example.org"
    assert body["second_factor"] is False
    assert body["profile"]["full_name"] == "Alice Surgeon"
    assert [w["kind"] for w in body["workspaces"]] == ["personal"]
    assert body["teams"] == [] and body["organizations"] == []


def test_me_writes_audit_row(
    client: TestClient, users: dict[str, uuid.UUID], settings: Settings
) -> None:
    client.get(
        "/me", headers={**auth(users["bob"]), "User-Agent": "pytest", "X-Forwarded-For": "10.1.2.3"}
    )
    with as_service(settings.database_url) as conn:
        row = conn.execute(
            "select action, object_type, object_id, host(ip) as ip, user_agent from public.audit_log "
            "where actor_id = %s and action = 'profile.view' order by at desc limit 1",
            (users["bob"],),
        ).fetchone()
    assert row == {
        "action": "profile.view",
        "object_type": "user",
        "object_id": str(users["bob"]),
        "ip": "10.1.2.3",
        "user_agent": "pytest",
    }


def test_update_profile_only_touches_own_row(
    client: TestClient, users: dict[str, uuid.UUID], settings: Settings
) -> None:
    response = client.patch(
        "/me/profile",
        json={"title": "Consultant", "specialty": "General surgery", "locale": "el"},
        headers=auth(users["alice"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Consultant"
    assert response.json()["locale"] == "el"

    bob = client.get("/me", headers=auth(users["bob"])).json()
    assert bob["profile"]["title"] is None

    with as_service(settings.database_url) as conn:
        row = conn.execute(
            "select metadata from public.audit_log where actor_id = %s and action = 'profile.update'",
            (users["alice"],),
        ).fetchone()
    assert row["metadata"] == {"fields": ["locale", "specialty", "title"]}


def test_update_profile_validates_input(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    assert client.patch("/me/profile", json={}, headers=auth(users["alice"])).status_code == 400
    assert (
        client.patch(
            "/me/profile", json={"locale": "greek"}, headers=auth(users["alice"])
        ).status_code
        == 422
    )


def test_procedures_registry(client: TestClient, users: dict[str, uuid.UUID]) -> None:
    response = client.get("/procedures", headers=auth(users["alice"]))
    assert response.status_code == 200
    procedures = response.json()
    lc = procedures[0]
    assert lc["code"] == "lc" and lc["analysis_enabled"] is True
    assert [p["name"] for p in lc["model_version"]["phase_labels"]] == [
        "Preparation",
        "Calot's Triangle Dissection",
        "Clipping and Cutting",
        "Gallbladder Dissection",
        "Gallbladder Packaging",
        "Cleaning and Coagulation",
        "Gallbladder Retraction",
    ]
    tools = {t["code"]: t["name"] for t in lc["model_version"]["tool_labels"]}
    assert tools["Clipper"] == "Clip Applier"
    assert tools["Irrigator"] == "Suction-Irrigation"
    assert lc["model_version"]["metrics"]["dataset"] == "Cholec80"
    assert all(
        p["analysis_enabled"] is False and p["model_version"] is None for p in procedures[1:]
    )

    assert (
        client.get("/procedures/robotic_chole", headers=auth(users["alice"])).json()[
            "analysis_enabled"
        ]
        is False
    )
    assert client.get("/procedures/nope", headers=auth(users["alice"])).status_code == 404
