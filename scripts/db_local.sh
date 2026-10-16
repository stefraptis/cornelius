#!/usr/bin/env bash
# Local PostgreSQL 16 cluster for development and tests.
# Mirrors the Supabase conventions the app relies on: an `auth` schema with
# `auth.users` and `auth.uid()`, and the `anon`, `authenticated`, and
# `service_role` roles. It is not Supabase; it is enough to run migrations and
# prove the RLS policies.
#
# Usage: scripts/db_local.sh start|stop|status|reset|migrate|psql
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# PostgreSQL refuses to run as root. In containers that start as root (CI
# images, sandboxes) re-run as an unprivileged user that owns the data dir.
if [ "$(id -u)" -eq 0 ]; then
  RUN_AS="${LOCAL_PG_RUN_AS:-}"
  if [ -z "${RUN_AS}" ]; then
    for u in postgres claude nobody; do id "$u" >/dev/null 2>&1 && { RUN_AS="$u"; break; }; done
  fi
  if [ -z "${RUN_AS}" ]; then echo "No unprivileged user available to run PostgreSQL" >&2; exit 1; fi
  mkdir -p "${ROOT}/.local"
  chown -R "${RUN_AS}" "${ROOT}/.local"
  exec runuser -u "${RUN_AS}" -- env PGPASSWORD="${PGPASSWORD:-postgres}" LOCAL_PG_PORT="${LOCAL_PG_PORT:-}" LOCAL_PG_DB="${LOCAL_PG_DB:-}" PGBIN="${PGBIN:-}" bash "${BASH_SOURCE[0]}" "$@"
fi
PGBIN="${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"
DATA_DIR="${ROOT}/.local/pg"
PORT="${LOCAL_PG_PORT:-54329}"
DB="${LOCAL_PG_DB:-cornelius}"
SUPERUSER="postgres"
LOG="${ROOT}/.local/pg.log"
export PGPASSWORD="${PGPASSWORD:-postgres}"

psql_super() {
  "${PGBIN}/psql" -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "${PORT}" -U "${SUPERUSER}" "$@"
}

start() {
  mkdir -p "${ROOT}/.local"
  if [ ! -f "${DATA_DIR}/PG_VERSION" ]; then
    echo "Initializing cluster in ${DATA_DIR}"
    PWFILE="$(mktemp)"; echo "${PGPASSWORD}" > "${PWFILE}"
    "${PGBIN}/initdb" -D "${DATA_DIR}" -U "${SUPERUSER}" --auth=scram-sha-256 --pwfile="${PWFILE}" -E UTF8 >/dev/null
    rm -f "${PWFILE}"
    {
      echo "port = ${PORT}"
      echo "listen_addresses = '127.0.0.1'"
      echo "unix_socket_directories = '${ROOT}/.local'"
      echo "log_min_messages = warning"
    } >> "${DATA_DIR}/postgresql.conf"
  fi
  if "${PGBIN}/pg_ctl" -D "${DATA_DIR}" status >/dev/null 2>&1; then
    echo "Cluster already running on port ${PORT}"
  else
    "${PGBIN}/pg_ctl" -D "${DATA_DIR}" -l "${LOG}" -w start >/dev/null
    echo "Cluster started on port ${PORT}"
  fi
  if ! psql_super -d postgres -tAc "select 1 from pg_database where datname='${DB}'" | grep -q 1; then
    psql_super -d postgres -c "create database ${DB}" >/dev/null
    echo "Database ${DB} created"
  fi
}

stop() {
  if "${PGBIN}/pg_ctl" -D "${DATA_DIR}" status >/dev/null 2>&1; then
    "${PGBIN}/pg_ctl" -D "${DATA_DIR}" -w stop >/dev/null && echo "Cluster stopped"
  else
    echo "Cluster not running"
  fi
}

reset() {
  start
  psql_super -d postgres -c "drop database if exists ${DB} with (force)" >/dev/null
  psql_super -d postgres -c "create database ${DB}" >/dev/null
  echo "Database ${DB} recreated"
  migrate
}

migrate() {
  start
  # Bootstrap the Supabase-like auth schema and roles (idempotent), then run
  # every migration not yet recorded in schema_migrations.
  psql_super -d "${DB}" -q -f "${ROOT}/supabase/local/00_supabase_shim.sql"
  psql_super -d "${DB}" -q -c "create table if not exists public.schema_migrations (version text primary key, applied_at timestamptz not null default now())"
  for f in "${ROOT}"/supabase/migrations/*.sql; do
    v="$(basename "${f}" .sql)"
    if psql_super -d "${DB}" -tAc "select 1 from public.schema_migrations where version='${v}'" | grep -q 1; then
      continue
    fi
    echo "Applying ${v}"
    psql_super -d "${DB}" -q --single-transaction -f "${f}"
    psql_super -d "${DB}" -q -c "insert into public.schema_migrations(version) values ('${v}')"
  done
  for f in "${ROOT}"/supabase/seed/*.sql; do
    psql_super -d "${DB}" -q -f "${f}"
  done
  echo "Migrations applied. DATABASE_URL=postgresql://${SUPERUSER}:${PGPASSWORD}@127.0.0.1:${PORT}/${DB}"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) "${PGBIN}/pg_ctl" -D "${DATA_DIR}" status ;;
  reset) reset ;;
  migrate) migrate ;;
  psql) shift; psql_super -d "${DB}" "$@" ;;
  *) echo "Usage: $0 start|stop|status|reset|migrate|psql"; exit 1 ;;
esac
