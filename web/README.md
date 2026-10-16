# Cornelius web

Next.js (App Router, TypeScript, Tailwind CSS v4) frontend.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_* values
pnpm install
pnpm dev                     # http://localhost:3100
pnpm lint && pnpm typecheck && pnpm test
pnpm build
```

## Where things are

| Path | Purpose |
| --- | --- |
| `src/app/(auth)/` | Sign in (password or email link), sign up, 2FA challenge, password reset |
| `src/app/(app)/` | Everything behind sign-in: library, analytics, quizzes, annotation, teams, settings, about the model |
| `src/app/auth/` | Route handlers: link callback, sign out |
| `src/app/dev/shell` | Development-only component review page with sample data (404 in production) |
| `src/proxy.ts` | Session refresh, sign-in redirect, and second-factor enforcement on every request |
| `src/components/ui/` | Buttons, inputs, tabs, dialogs, menus, chips, stat tiles, empty states, skeletons |
| `src/components/shell/` | Sidebar, workspace switcher, theme toggle, user menu |
| `src/lib/api.ts` | Typed client for the FastAPI service |
| `src/lib/supabase/` | Browser and server Supabase clients |
| `src/lib/i18n.ts` + `src/messages/en.json` | All UI strings; add `el.json` for Greek |
| `src/app/globals.css` | Design tokens from the build guideline (Section 14) |

## Design rules in code

- Colors come from CSS variables (`--bg`, `--surface`, `--border`, `--text`, `--text-muted`, `--accent`, `--danger`, `--warning`). No blue, no gradients, no shadows.
- IBM Plex Sans for text, IBM Plex Mono with tabular figures for timestamps and numbers (`.font-mono` or `.tabular`).
- Phase and instrument colors are data: they arrive from the API (`model_versions`) and are never hardcoded in components.
- Every string the user sees goes through `t("key")`.
- No em dashes in UI copy (a unit test checks `en.json`).
