# Cornelius

Cornelius is a web platform where surgeons upload laparoscopic cholecystectomy (LC) videos, receive AI phase and instrument analysis, and learn from their own cases. "Cornelius" is a placeholder name.

The platform is for retrospective review, education, and research. It never gives real-time or patient-specific clinical guidance.

## Repository layout

| Path | What it is |
| --- | --- |
| `web/` | Next.js (React, TypeScript, Tailwind) frontend |
| `api/` | FastAPI service: metadata, permissions, presigned storage access, job queue |
| `workers/transcode/` | CPU worker: anonymization, HLS renditions, thumbnails (M1) |
| `workers/analysis/` | GPU worker wrapping the published LC pipeline (M2) |
| `supabase/` | Database migrations, seeds, and row-level security policies |
| `docs/` | Milestone notes and runbooks |

The build brief lives in the Claude project as "Surgical Video Platform: Build Guideline". Decisions recorded there are fixed unless the owner changes them.

## Quick start (development)

Prerequisites: Node 22, pnpm 10, Python 3.11+, PostgreSQL 16 client and server (for local tests), ffmpeg.

```bash
cp .env.example .env            # fill in Supabase and B2 values
make web-dev                    # Next.js on http://localhost:3000
make api-dev                    # FastAPI on http://localhost:8000
make db-local                   # local Postgres with migrations applied (for tests)
make test                       # api tests, RLS tests, web lint and unit tests
```

Each package also has its own README with details.

## Milestones

Build order is M0 (foundations) to M6 (education expansion and pilot). The current milestone and its acceptance checklist are in `docs/M0.md`.
