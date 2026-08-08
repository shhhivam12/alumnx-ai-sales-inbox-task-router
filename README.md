# Alumnx AI Sales inbox task router

**Candidate ID:** `mahendrushivam123@gmail.com`  
**Backend URL:** _add after deployment_  
**Frontend URL:** _add after deployment_  
**Repository URL:** https://github.com/shhhivam12/alumnx-ai-sales-inbox-task-router  
**Video URL:** _add after recording_

The application converts a messy sales inbox into correctly assigned tasks, updates
one task per email thread, records everything it intentionally skips, and exposes a
grounded analytics chat whose numbers come from stored processing data.

## Architecture

```text
Cloudflare Pages (React preview/results/chat)
                    |
                    v
Render (FastAPI validation, routing, reconciliation, chat)
              |                         |
              v                         v
     Supabase Postgres            Shared Task API
              ^
              |
       Gemini structured extraction
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

After bootstrap and before migration, fill `.env` with the hosted development
Supabase URL and Gemini key.

`SUPABASE_DB_URL` means the Postgres connection string from **Supabase Dashboard →
Connect → Session pooler**, not the `https://PROJECT.supabase.co` project URL. Choose
session mode on port `5432` and keep `sslmode=require`. For development,
`SUPABASE_MIGRATION_DB_URL` may be blank; the migration script then uses the same DB
connection string.

Docker and a local database are not required. Local task writes use the fake Task API
unless `TASK_API_MODE=live` is explicitly configured.

## Tests

```bash
python scripts/validate_dataset.py
.venv/Scripts/python -m pytest backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

See `HACKATHON_PLAN.md` for locked behavior, `DECISIONS.md` for tradeoffs, and
`EVALS.md` for the honest evaluation protocol. `CODE_WALKTHROUGH.md` explains the
implementation in beginner language; `REQUIREMENTS_REVIEW.md` maps every major
hackathon requirement to evidence and remaining external work.

## Environment and API

Only the backend owns `SUPABASE_DB_URL`, `GEMINI_API_KEY`, and `TASK_API_BASE_URL`.
Development defaults to fake Task API mode. Production requires live mode, TLS
Postgres, Gemini, and exact non-wildcard CORS origins.

- `POST /ingest`: synchronously routes 1–100 emails.
- `GET /api/tasks`: current remote tasks plus decision evidence.
- `GET /api/stats`: exact run, batch, or all-history aggregates.
- `POST /api/chat`: allowlisted grounded analytics.
- `GET /api/sample-emails?count=250`: email data without labels.
- `GET /health` and `GET /ready`: liveness and dependency readiness.

## Deployment

Render uses `render.yaml`. Cloudflare Pages builds `frontend/`; replace the placeholder
Render host in `frontend/public/_redirects`. Rehearse the migration on development,
then apply it to production with `python scripts/migrate.py --production`.

## Known limitation

A multi-owner email produces one triage task rather than coordinated subtasks because
the shared API has one assignee and no parent-child relationship.
