# Alumnx AI Sales Inbox Task Router

- **Candidate ID:** `mahendrushivam123@gmail.com`
- **Backend URL:** https://alumnx-ai-sales-inbox-task-router.onrender.com
- **Frontend URL:** https://alumnx-ai-sales-inbox-task-router.vercel.app
- **Repository URL:** https://github.com/shhhivam12/alumnx-ai-sales-inbox-task-router
- **Video URL:** _add after recording_

This app reads a mixed sales inbox, ignores noise, creates the right task, and updates
the same task when a thread gets a reply. The frontend shows the raw emails before
routing, every persisted decision after routing, team analytics, and a read-only chat
whose answers are backed by stored data.

## What it handles

- Enterprise RFPs, RFIs, tenders, and deals above Rs. 10 lakh
- SMB enquiries, demos, trials, and deals at or below Rs. 10 lakh
- Marketing, alliances, finance, and genuinely ambiguous triage items
- Deadlines inside 72 hours, including timezone-aware relative dates
- Thread replies as updates instead of duplicate tasks
- Newsletters, out-of-office replies, bounces, and unsolicited vendor spam
- Hinglish, HTML, forwarded messages, quoted history, and degraded LLM calls

## Architecture

```text
React on Vercel
  -> FastAPI on Render
       -> Gemini for structured extraction
       -> deterministic routing and safety rules
       -> Supabase Postgres for tasks, threads, decisions, and chat facts
```

Gemini extracts facts from messy email text. Python owns rule precedence, exact enums,
thresholds, priority, suppression, confidence, idempotency, and thread reconciliation.
The database is the source of truth. Chat queries stored facts and never asks Gemini to
recalculate counts.

## Setup

Python 3.12 and Node.js are required. Copy `.env.example` to `.env`, then add the
Supabase session-pooler connection string and Gemini API key.

```bash
python scripts/bootstrap.py
python scripts/migrate.py
python scripts/dev.py
```

`SUPABASE_DB_URL` must be a Postgres connection string from **Supabase Dashboard ->
Connect -> Session pooler** with TLS enabled. It is not the public Supabase project URL.
Docker and a local database are not required.

## Main API routes

- `POST /ingest` routes 1-100 emails synchronously.
- `POST /tasks`, `PATCH /tasks/{id}`, `GET /tasks`, and `DELETE /tasks/{id}` implement
  the grader-facing Task API.
- `GET /users` returns the exact team roster.
- `GET /api/tasks` and `GET /api/stats` return persisted decisions and analytics.
- `POST /api/chat` answers allowlisted, read-only questions with `supporting_data`.
- `GET /api/sample-emails?count=250` returns sample email data without labels.
- `GET /health` and `GET /ready` expose liveness and dependency readiness.

## Verification

```bash
.venv/Scripts/python -m pytest backend/tests -q
.venv/Scripts/ruff check backend/app backend/tests scripts
npm --prefix frontend test
npm --prefix frontend run build
```

Current local result: **162 passed, 1 skipped** in the backend, Ruff clean, dataset
validation passed, and the frontend test/build checks pass. The skipped test is the
opt-in hosted Supabase concurrency test.

Production checks cover health/readiness, the 12 official examples, request limits,
idempotent replay, thread updates, grounded chat, CORS, and exact cleanup of test rows.

## Deployment

`render.yaml` deploys the backend. Vercel uses `frontend/` as the project root and
publishes `dist/`. Production secrets stay on Render; the browser only receives
`VITE_API_BASE_URL`.

Required production values:

- Render `CANDIDATE_ID`: `mahendrushivam123@gmail.com`
- Render `FRONTEND_ORIGINS`: `https://alumnx-ai-sales-inbox-task-router.vercel.app`
- Vercel `VITE_API_BASE_URL`: `https://alumnx-ai-sales-inbox-task-router.onrender.com`

Run `python scripts/migrate.py --production` before deploying a backend revision that
depends on a new migration.

## Submission notes

See `DECISIONS.md` for the five engineering tradeoffs and `EVALS.md` for the frozen
manual evaluation. The video URL remains intentionally blank until the final recording
is uploaded.

## Known limitation

If one email contains independent asks for several owners, the app creates one triage
task instead of several linked subtasks. The required Task API has one assignee and no
parent-child task model, so this is safer than creating tasks that cannot be reconciled
reliably when replies arrive.
