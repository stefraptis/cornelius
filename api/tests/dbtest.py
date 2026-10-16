"""Helpers for tests that need a real PostgreSQL.

The test database is dropped and recreated on every run, then the Supabase
shim, every migration, and every seed are applied, so the tests always run
against exactly what is in `supabase/`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row, tuple_row

from tests.conftest import REPO_ROOT

SUPABASE_DIR = REPO_ROOT / "supabase"


def _split_db(url: str) -> tuple[str, str]:
    base, _, dbname = url.rpartition("/")
    return base, dbname


def server_reachable(url: str) -> bool:
    base, _ = _split_db(url)
    try:
        with psycopg.connect(base + "/postgres", connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


def recreate_database(url: str) -> None:
    base, dbname = _split_db(url)
    with psycopg.connect(base + "/postgres", autocommit=True) as conn:
        conn.execute(
            sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(dbname))
        )
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(dbname)))

    files: list[Path] = [SUPABASE_DIR / "local" / "00_supabase_shim.sql"]
    files += sorted((SUPABASE_DIR / "migrations").glob("*.sql"))
    files += sorted((SUPABASE_DIR / "seed").glob("*.sql"))
    with psycopg.connect(url, autocommit=True) as conn:
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))


def create_auth_user(conn: psycopg.Connection, email: str, full_name: str = "") -> uuid.UUID:
    with conn.cursor(row_factory=tuple_row) as cur:
        row = cur.execute(
            "insert into auth.users (email, raw_user_meta_data) values (%s, %s::jsonb) returning id",
            (email, json.dumps({"full_name": full_name})),
        ).fetchone()
    assert row is not None
    conn.commit()
    return row[0]


def personal_workspace(conn: psycopg.Connection, user_id: uuid.UUID) -> uuid.UUID:
    with conn.cursor(row_factory=tuple_row) as cur:
        row = cur.execute(
            "select id from public.workspaces where owner_user_id = %s", (user_id,)
        ).fetchone()
    assert row is not None
    return row[0]


@contextmanager
def as_user(url: str, user_id: uuid.UUID, email: str = "") -> Iterator[psycopg.Connection]:
    """A connection acting as `authenticated` with the given JWT claims.

    Mirrors exactly how PostgREST / Supabase execute a browser query, so what
    these tests prove is what the browser gets.
    """
    claims = json.dumps({"sub": str(user_id), "role": "authenticated", "email": email})
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.execute("select set_config('request.jwt.claims', %s, false)", (claims,))
        conn.execute("set role authenticated")
        try:
            yield conn
        finally:
            conn.rollback()
            conn.execute("reset role")


@contextmanager
def as_service(url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        yield conn
