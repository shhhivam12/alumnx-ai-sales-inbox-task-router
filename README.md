# Alumnx AI Sales inbox task router

- **Candidate ID:** `mahendrushivam123@gmail.com`
- **Backend URL:** https://alumnx-ai-sales-inbox-task-router.onrender.com
- **Frontend URL:** https://alumnx-ai-sales-inbox-task-router.vercel.app
- **Repository URL:** https://github.com/shhhivam12/alumnx-ai-sales-inbox-task-router
- **Video URL:** _add after recording_

The application converts a messy sales inbox into correctly assigned tasks, updates
one task per email thread, records everything it intentionally skips, and exposes a
grounded analytics chat whose numbers come from stored processing data.

## Architecture

```text
Vercel (React preview/results/chat)
                    |
                    v
Render (one FastAPI base URL)
  |-- grader Task API: /tasks, /users
  |-- app API: /ingest, /api/tasks, /api/stats, /api/chat
  |-- Gemini structured extraction
  `-- Supabase Postgres (tasks plus processing/audit history)
```

## Setup

```bash
python scripts/bootstrap.py
python scripts/migrate.py
python scripts/dev.py
```

Database-only verification commands:

```bash
python scripts/verify_database.py
python -m scripts.supabase_smoke_test
```

After bootstrap and before migration, fill `.env` with the hosted Supabase connection
and Gemini key. This project uses one Supabase project; automated tests either stay
in memory or use unique IDs with exact cleanup.

`SUPABASE_DB_URL` means the Postgres connection string from **Supabase Dashboard →
Connect → Session pooler**, not the `https://PROJECT.supabase.co` project URL. Choose
session mode on port `5432` and keep `sslmode=require`. For development,
`SUPABASE_MIGRATION_DB_URL` may be blank; the migration script then uses the same DB
connection string.

Docker and a local database are not required. The backend implements the Task API
itself; its task rows and processing history both persist in hosted Supabase.

## Tests

```bash
python scripts/validate_dataset.py
.venv/Scripts/python -m pytest backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

See `DECISIONS.md` for the required technical tradeoffs and `EVALS.md` for the
honest evaluation protocol and recorded failure cases.

Current verified baseline: 153 backend tests pass (one hosted test is opt-in), all
frontend tests/build checks pass, all 12 official examples pass publicly, and the
eight-group public API matrix passes with exact cleanup. Human-reviewed evaluation and
the submission video are intentionally still marked as user work rather than fabricated.

## Environment and API

Only the backend owns `SUPABASE_DB_URL` and `GEMINI_API_KEY`. Production requires TLS
Postgres, Gemini, the production project reference, and exact non-wildcard CORS origins.

- `POST /ingest`: synchronously routes 1–100 emails.
- `POST /tasks`, `PATCH /tasks/{id}`, `GET /tasks`, `DELETE /tasks/{id}`: exact
  grader-facing persistent Task API.
- `GET /users`: exact team roster.
- `GET /api/tasks`: current persistent tasks plus decision evidence.
- `GET /api/stats`: exact run, batch, or all-history aggregates.
- `POST /api/chat`: allowlisted grounded analytics.
- `GET /api/sample-emails?count=250`: email data without labels.
- `GET /health` and `GET /ready`: liveness and dependency readiness.

## Deployment

Render uses `render.yaml` and serves the FastAPI backend. Vercel builds `frontend/`
with the Vite preset, `frontend` as its root directory, and `dist` as its output.
Set Vercel's public `VITE_API_BASE_URL` to the backend URL above without a trailing
slash. Render's `FRONTEND_ORIGINS` must be the exact Vercel origin above; never use a
wildcard. Apply the tested production migration immediately before deploying the
matching backend revision with `python scripts/migrate.py --production`.

## Known limitation

A multi-owner email produces one triage task rather than coordinated subtasks because
the required Task API has one assignee and no parent-child relationship.
