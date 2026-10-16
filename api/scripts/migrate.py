"""Apply pending SQL migrations to the database in DATABASE_URL.

    python scripts/migrate.py            # apply pending migrations and seeds
    python scripts/migrate.py --status   # show what is applied and what is pending

Works against Supabase (session pooler URL) and against the local cluster.
Applied versions are recorded in public.schema_migrations. If that table does
not exist yet but the schema does (migrations pasted into the SQL editor by
hand), the versions whose objects already exist are marked as applied first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"
SEEDS = REPO_ROOT / "supabase" / "seed"

# A representative object per hand-applied migration, used once to bootstrap
# schema_migrations on a database that predates this script.
BOOTSTRAP_MARKERS = {
    "0001_accounts": ("table", "public.workspaces"),
    "0002_videos_analysis": ("table", "public.videos"),
    "0003_rls": ("function", "public.can_view_video"),
}


def object_exists(conn: psycopg.Connection, kind: str, name: str) -> bool:
    if kind == "table":
        row = conn.execute("select to_regclass(%s)", (name,)).fetchone()
        return bool(row and row[0])
    row = conn.execute("select to_regproc(%s)", (name,)).fetchone()
    return bool(row and row[0])


def main(argv: list[str]) -> int:
    settings = get_settings()
    url = settings.database_url
    status_only = "--status" in argv

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "create table if not exists public.schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        applied = {
            r[0] for r in conn.execute("select version from public.schema_migrations").fetchall()
        }
        if not applied:
            for version, (kind, name) in BOOTSTRAP_MARKERS.items():
                if object_exists(conn, kind, name):
                    conn.execute(
                        "insert into public.schema_migrations (version) values (%s) "
                        "on conflict do nothing",
                        (version,),
                    )
                    applied.add(version)
                    print(f"bootstrap: {version} already present")

        files = sorted(MIGRATIONS.glob("*.sql"))
        pending = [f for f in files if f.stem not in applied]
        for f in files:
            print(f"{'applied' if f.stem in applied else 'pending'}  {f.stem}")
        if status_only:
            return 0
        if not pending:
            print("Nothing to apply.")
        for f in pending:
            print(f"Applying {f.stem} ...", end=" ", flush=True)
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute(
                    "insert into public.schema_migrations (version) values (%s)", (f.stem,)
                )
            print("done")
        for f in sorted(SEEDS.glob("*.sql")):
            print(f"Seeding {f.stem} ...", end=" ", flush=True)
            conn.execute(f.read_text(encoding="utf-8"))
            print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
