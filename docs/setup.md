# Setup: Supabase, storage, local run

About 20 minutes, once. Windows, macOS and Linux.

## 1. Supabase (database and sign-in)

The project is created in an EU region (Frankfurt). In the Supabase dashboard:

1. **Project Settings > API keys**: copy the project URL, the publishable key and a secret key.
2. **Project Settings > Database** (or the Connect button): copy the **Session pooler** URI. This is `DATABASE_URL` for the API and workers. Add `?sslmode=require` if it is not there.
3. **Authentication > Sign In / Providers > Email**: keep Email enabled, with "Confirm email" on. Password sign-in and magic links both use this provider.
4. **Authentication > Multi-Factor**: enable TOTP (authenticator app).
5. **Authentication > URL Configuration**: Site URL `http://localhost:3100` for now; add `http://localhost:3100/auth/callback` to Redirect URLs. Repeat with the real domain later.
6. **Migrations**: after `.env` is filled (next step), run from the `api` folder:
   ```
   python scripts/migrate.py
   ```
   It applies every pending file in `supabase/migrations/` in order, records them in `public.schema_migrations`, and re-runs the seeds. Run it again after every update that adds a migration. (Alternative: paste the files into the SQL Editor in order.)

Then at the repository root:

```bash
cp .env.example .env
```

Fill `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `DATABASE_URL`. Leave `SUPABASE_JWT_SECRET` empty (new projects sign tokens with asymmetric keys; the API verifies them through the project's JWKS).

For the frontend, create `web/.env.local` with the three `NEXT_PUBLIC_*` lines from `web/.env.example`.

## 2. Backblaze B2 (video storage, M1)

1. Create a **private** bucket in **EU Central** named for example `cornelius-videos`.
2. Create an application key restricted to that bucket with read and write.
3. Fill `STORAGE_ENDPOINT_URL` (shown on the bucket page, `https://s3.eu-central-003.backblazeb2.com`), `STORAGE_REGION`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY_ID` (keyID), `STORAGE_SECRET_ACCESS_KEY` (applicationKey).
4. Bucket CORS (needed for browser uploads in M1): allow `PUT`, `GET`, `HEAD` from the web app origin with the `ETag` header exposed.

## 3. Run

Three processes in development: the API, the web app, and the transcode worker (needs ffmpeg on PATH; on Windows: `winget install Gyan.FFmpeg`, then open a new terminal).

```bash
# API
cd api
python -m venv .venv
.venv\Scripts\activate          # Windows; on macOS/Linux: . .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8100

# Web (second terminal)
cd web
pnpm install
pnpm dev                        # http://localhost:3100

# Transcode worker (third terminal, from the repository root)
pip install -e "api[workers]"
python -m workers.transcode.main
```

The worker reads `DATABASE_URL` and the `STORAGE_*` values from `.env` and `local.env` like the API.

Sign up at http://localhost:3100/signup, confirm the email, sign in. Settings > Security sets up two-factor authentication.

## 4. Platform admin

The usage page (`/admin/usage`) and the feedback inbox are visible only to accounts listed in `public.platform_admins`. After signing up, add yourself once from the `api` folder:

```
python scripts/migrate.py --admin you@example.org
```

## 5. Tests

```bash
cd api && pytest -q -m "not db"          # unit tests, no database needed
make db-local && cd api && pytest -q     # all tests, local PostgreSQL 16 (macOS/Linux; on Windows use WSL or point DATABASE_URL at any Postgres 16 with the postgres superuser)
cd web && pnpm lint && pnpm typecheck && pnpm test
```

The RLS tests create and drop a database named `cornelius_test`, so point `DATABASE_URL` at a server you own, never at the Supabase project.
