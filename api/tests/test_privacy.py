"""Consent records, data export, account deletion."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.main import create_app
from tests.conftest import TEST_JWT_SECRET, make_token
from tests.dbtest import (
    as_service,
    create_auth_user,
    personal_workspace,
    recreate_database,
    server_reachable,
)

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


def auth(user_id: uuid.UUID, email: str, metadata: dict | None = None) -> dict[str, str]:
    if metadata is None:
        return {"Authorization": f"Bearer {make_token(user_id, email)}"}
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "exp": now + 3600,
            "user_metadata": metadata,
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_consent_from_signup_metadata_then_reconsent(
    client: TestClient, settings: Settings
) -> None:
    with psycopg.connect(settings.database_url) as conn:
        uid = create_auth_user(conn, "consent@example.org", "C")
    headers = auth(
        uid,
        "consent@example.org",
        {"accepted_terms_version": "v1", "accepted_privacy_version": "v1"},
    )
    first = client.get("/me/consent", headers=headers).json()
    assert first["terms_version"] == "v1" and first["privacy_version"] == "v1"

    r = client.post(
        "/me/consent", json={"terms_version": "v2", "privacy_version": "v1"}, headers=headers
    )
    assert r.status_code == 200 and r.json()["terms_version"] == "v2"
    assert client.get("/me/consent", headers=headers).json()["terms_version"] == "v2"
    with as_service(settings.database_url) as conn:
        n = conn.execute(
            "select count(*) as n from public.consents where user_id = %s", (uid,)
        ).fetchone()["n"]
        audited = conn.execute(
            "select count(*) as n from public.audit_log where actor_id = %s and action = 'consent.accept'",
            (uid,),
        ).fetchone()["n"]
    assert n == 2 and audited == 1


def test_no_consent_without_metadata(client: TestClient, settings: Settings) -> None:
    with psycopg.connect(settings.database_url) as conn:
        uid = create_auth_user(conn, "noconsent@example.org", "N")
    body = client.get("/me/consent", headers=auth(uid, "noconsent@example.org")).json()
    assert body == {"terms_version": None, "privacy_version": None, "accepted_at": None}


def test_export_contains_own_rows_only(client: TestClient, settings: Settings) -> None:
    with psycopg.connect(settings.database_url) as conn:
        a = create_auth_user(conn, "a-export@example.org", "A")
        b = create_auth_user(conn, "b-export@example.org", "B")
        for owner, title in ((a, "A video"), (b, "B video")):
            conn.execute(
                "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) values (%s,%s,'lc',%s)",
                (owner, personal_workspace(conn, owner), title),
            )
        conn.commit()
    r = client.get("/me/export", headers=auth(a, "a-export@example.org"))
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment;")
    data = json.loads(r.content)
    assert data["email"] == "a-export@example.org"
    assert [v["title"] for v in data["videos"]] == ["A video"]
    assert data["profile"][0]["full_name"] == "A"
    assert any(
        row["action"] == "export.create"
        for row in client.get("/me/export", headers=auth(a, "a-export@example.org")).json()[
            "audit_log"
        ]
    )


def test_delete_requires_email_confirmation_and_cascades(
    client: TestClient, settings: Settings
) -> None:
    with psycopg.connect(settings.database_url) as conn:
        uid = create_auth_user(conn, "gone@example.org", "Gone")
        vid = conn.execute(
            "insert into public.videos (owner_user_id, workspace_id, procedure_code, title) values (%s,%s,'lc','x') returning id",
            (uid, personal_workspace(conn, uid)),
        ).fetchone()[0]
        conn.commit()
    headers = auth(uid, "gone@example.org")
    assert (
        client.post(
            "/me/delete", json={"confirm_email": "wrong@example.org"}, headers=headers
        ).status_code
        == 400
    )
    r = client.post("/me/delete", json={"confirm_email": "GONE@example.org"}, headers=headers)
    assert r.status_code == 202
    with as_service(settings.database_url) as conn:
        assert (
            conn.execute("select count(*) as n from auth.users where id = %s", (uid,)).fetchone()[
                "n"
            ]
            == 0
        )
        assert (
            conn.execute(
                "select count(*) as n from public.profiles where id = %s", (uid,)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "select count(*) as n from public.videos where id = %s", (vid,)
            ).fetchone()["n"]
            == 0
        )
        deletion = conn.execute(
            "select storage_prefixes from public.account_deletions where user_id = %s", (uid,)
        ).fetchone()
        assert deletion["storage_prefixes"] == [f"videos/{vid}/"]
        job = conn.execute(
            "select payload from public.jobs where type = 'purge' order by created_at desc limit 1"
        ).fetchone()
        assert job["payload"]["prefixes"] == [f"videos/{vid}/"]
        assert (
            conn.execute(
                "select count(*) as n from public.audit_log where object_id = %s and action = 'account.delete'",
                (str(uid),),
            ).fetchone()["n"]
            == 1
        )
