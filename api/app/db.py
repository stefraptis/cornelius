"""Database access.

Two ways to talk to Postgres:

* `service_connection()`: full access, used for queue work and for actions the
  API has already authorized itself (bypasses RLS like Supabase's service role).
* `user_connection(user)`: the same connection, but with the Supabase JWT
  claims set and the role switched to `authenticated`, so Postgres row-level
  security filters every query exactly as it would for the browser. This is
  the second line of defence the build guideline requires.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.auth import AuthUser
from app.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        # min_size=0: no connection is opened until the first request, so a
        # wrong password does not make the pool hammer the server (Supabase's
        # pooler blocks a client after repeated authentication failures).
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=0,
            max_size=10,
            timeout=15,
            reconnect_timeout=60,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def service_connection() -> Iterator[psycopg.Connection]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


@contextmanager
def user_connection(user: AuthUser) -> Iterator[psycopg.Connection]:
    """Yield a connection that behaves as the given user under RLS.

    The claims are set for the transaction only (`set_config(..., true)`), and
    the role is reset before the connection returns to the pool.
    """
    pool = get_pool()
    with pool.connection() as conn:
        claims = json.dumps(
            {
                "sub": str(user.id),
                "role": user.role,
                "email": user.email,
                "aal": user.aal,
            }
        )
        try:
            with conn.cursor() as cur:
                cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                cur.execute("set local role authenticated")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            with conn.cursor() as cur:
                cur.execute("reset role")
            conn.commit()


def ping() -> bool:
    """One direct, short-lived connection: fails fast with the server's real message."""
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=10) as conn:
        row = conn.execute("select 1").fetchone()
        return bool(row and row[0] == 1)
