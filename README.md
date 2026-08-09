# Alumnx AI Sales Inbox Task Router

- **Candidate ID:** `mahendrushivam123@gmail.com`
- **Backend URL:** https://alumnx-ai-sales-inbox-task-router.onrender.com
- **Frontend URL:** https://alumnx-ai-sales-inbox-task-router.vercel.app
- **Repository URL:** https://github.com/shhhivam12/alumnx-ai-sales-inbox-task-router
- **Video URL:** https://www.youtube.com/watch?v=ohda2csxqCY

Alumnx AI Sales Inbox Task Router converts a mixed sales inbox into persistent,
auditable tasks. It suppresses newsletters, out-of-office replies, bounces, and vendor
spam; routes actionable messages to the correct team member; and updates the existing
task when a later message arrives in the same thread.

The dashboard lets an operations manager inspect the original emails before routing,
watch decisions appear, review team workload and deadlines, and ask questions whose
numbers come from stored database records.

## How the application works

```text
Browser (React/Vite)
  -> FastAPI backend
       -> normalizes email and removes quoted reply history
       -> applies high-precision deterministic suppression
       -> asks Gemini for structured facts from ambiguous language
       -> applies deterministic routing, priority, amount, and confidence rules
       -> creates or updates one persistent task per email thread
       -> stores tasks, decisions, evidence, events, and chat audit in Supabase Postgres
```

Gemini interprets messy language, but it cannot write tasks or generate SQL. Python
owns routing precedence, allowed enums, the Rs. 10 lakh boundary, priority rules,
idempotency, and reply reconciliation. Chat uses allowlisted database queries and
deterministic answer templates, so a zero-result question returns zero rather than an
invented answer.

The Task API is implemented by this backend. There is no external organizer-hosted
Task API and no Task API key to configure.

## Prerequisites

Install these before cloning the repository:

- Git
- Python 3.12
- Node.js 20 or newer with npm
- A hosted Supabase project
- A Google Gemini API key

Docker and local PostgreSQL are not required.

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/shhhivam12/alumnx-ai-sales-inbox-task-router.git
cd alumnx-ai-sales-inbox-task-router
```

### 2. Bootstrap dependencies

Windows PowerShell:

```bash
py -3.12 scripts/bootstrap.py
```

macOS or Linux:

```bash
python3.12 scripts/bootstrap.py
```

This creates `.venv`, installs the backend and frontend dependencies, and copies
`.env.example` to `.env` when `.env` does not already exist. It never overwrites an
existing `.env`.

### 3. Configure `.env`

Open the generated `.env` and fill at least:

```dotenv
APP_ENV=development
CANDIDATE_ID=mahendrushivam123@gmail.com
FRONTEND_ORIGINS=http://localhost:5173

SUPABASE_DB_URL=postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require
SUPABASE_MIGRATION_DB_URL=

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Get `SUPABASE_DB_URL` from **Supabase Dashboard -> Connect -> Session pooler**. Use
the PostgreSQL connection string, not the public `https://...supabase.co` project URL.
If the password contains special URL characters, percent-encode them.

`SUPABASE_MIGRATION_DB_URL` is optional. When it is empty, the migration script uses
`SUPABASE_DB_URL`. A separate migration URL is only useful when an environment has a
different administrative connection for schema changes.

The candidate ID is intentionally locked to this submission identity and must not be
changed.

### 4. Create the database schema

Windows PowerShell:

```bash
py -3.12 scripts/migrate.py
```

macOS or Linux:

```bash
python3.12 scripts/migrate.py
```

This applies the Alembic migrations to the configured Supabase project. The database
can be empty before this command; the command creates the private schema, tables, and
indexes used by the app.

For a database deliberately configured as production, also set
`PRODUCTION_SUPABASE_PROJECT_REF`, set `APP_ENV=production`, and run:

```bash
py -3.12 scripts/migrate.py --production
```

Use `python3.12` instead of `py -3.12` on macOS or Linux.

The production guard prevents accidentally migrating a production project without an
explicit flag.

### 5. Start backend and frontend

Windows PowerShell:

```bash
py -3.12 scripts/dev.py
```

macOS or Linux:

```bash
python3.12 scripts/dev.py
```

Open http://localhost:5173. FastAPI runs at http://localhost:8000 and Vite proxies the
local `/api`, `/ingest`, `/health`, `/ready`, and `/users` requests to it. Press
`Ctrl+C` once to stop both processes.

In short, after cloning, the Windows workflow has three operational commands:

```bash
py -3.12 scripts/bootstrap.py
py -3.12 scripts/migrate.py
py -3.12 scripts/dev.py
```

The required manual step between the first and second commands is filling `.env` with
the Supabase connection string and Gemini key.

On macOS or Linux, use the same three commands with `python3.12` in place of
`py -3.12`.

## Verify a local installation

With the application running, these URLs should respond:

- http://localhost:8000/health — process liveness
- http://localhost:8000/ready — database, migration, and configuration readiness
- http://localhost:8000/users — fixed sales-team roster
- http://localhost:5173 — dashboard

Run the automated checks from another terminal:

```bash
.venv/Scripts/python -m pytest backend/tests -q
.venv/Scripts/ruff check backend/app backend/tests scripts
.venv/Scripts/python scripts/validate_dataset.py
npm --prefix frontend test
npm --prefix frontend run build
```

On macOS or Linux, replace `.venv/Scripts/python` with `.venv/bin/python`.
The hosted-Supabase concurrency test is opt-in because it creates and then removes
test-scoped rows.

## Main API routes

### Grader-facing Task API

- `POST /tasks` creates a task.
- `PATCH /tasks/{id}` updates mutable task fields.
- `GET /tasks?candidate_id=...` lists and filters tasks.
- `DELETE /tasks/{id}` deletes one task.
- `GET /users` returns the exact team roster.

### Dashboard API

- `POST /ingest` synchronously routes 1-100 emails.
- `GET /api/tasks` joins current tasks with stored classification metadata.
- `GET /api/stats` returns persisted run, category, assignee, and priority analytics.
- `POST /api/chat` answers allowlisted read-only questions with `supporting_data`.
- `GET /api/batches/{id}/decisions` returns one routing decision per email.
- `POST /api/decisions/{email_id}/feedback` records explicit quality feedback.
- `GET /api/sample-emails?count=250` returns sample emails without labels.
- `GET /health` and `GET /ready` expose liveness and readiness separately.

Interactive API documentation is available at `/docs` when FastAPI is running.

## Repository structure

```text
.
|-- backend/              FastAPI application, migrations, and backend tests
|   |-- alembic/          Versioned Supabase/Postgres schema migrations
|   |-- app/
|   |   |-- api/          HTTP route handlers
|   |   |-- db/           Connection pool and transaction helpers
|   |   |-- domain/       Validated models, enums, routing, and confidence policy
|   |   |-- repositories/ Database access and in-memory test implementation
|   |   `-- services/     Normalization, Gemini extraction, ingestion, chat, stats
|   `-- tests/            Unit, integration, and exact API contract tests
|-- frontend/             React, TypeScript, Vite dashboard and browser tests
|   |-- src/components/   Inbox, results, chat, analytics, and help views
|   |-- src/api/          Typed backend client
|   `-- tests/            Vitest/RTL and Playwright workflow tests
|-- data/                 Safe synthetic development and regression corpus
|   |-- inbox.json        250 sample emails used by the dashboard sample button
|   |-- team_roster.json  Required fixed users and assignment IDs
|   |-- batches/          The 250-email corpus split into ingest-sized batches
|   |-- fixtures/         Invalid payloads used to test API validation
|   |-- ground_truth/     Expected synthetic decisions and final tasks
|   `-- eval/             Frozen 60-email evaluation input/worksheet source
|-- artifacts/            Committed evidence supporting EVALS.md; other outputs ignored
|-- scripts/              Setup, migration, validation, evaluation, and smoke-test tools
|-- .github/workflows/    GitHub Actions backend and frontend checks
|-- .env.example          Safe configuration template with no credentials
|-- render.yaml           Render backend deployment definition
|-- PROBLEM_STATEMENT.md  Original hackathon requirements used for verification
|-- DECISIONS.md          Five required engineering trade-offs and limitation
|-- EVALS.md              Manual evaluation method, metrics, and unfixed failures
`-- DATASET.md            Synthetic corpus composition and validation notes
```

### Why `data/` remains committed

The files under `data/` are synthetic and contain no secrets. They are not unused
build output:

- The frontend sample button reads `data/inbox.json` through the backend.
- The grader roster endpoint reads `data/team_roster.json`.
- Unit and regression tests use the invalid fixtures and ground truth.
- The batch files reproduce the sequential 100/100/50 ingestion workflow.
- Evaluation scripts use the frozen evaluation source.

Removing this directory would break the sample workflow and weaken reproducibility.

### Why selected `artifacts/` files remain committed

Only three evaluation-evidence files are intentionally tracked:

- `manual_eval.json` — the frozen reviewed labels behind `EVALS.md`.
- `evaluation_report.json` — calculated metrics and confusion data.
- `live_eval_predictions.json` — model outputs used for comparison.

Temporary regression reports, logs, Playwright output, coverage, credentials, and
other generated files are ignored by `.gitignore`. The selected artifacts let judges
verify that the evaluation numbers were calculated rather than invented.

## Deployment configuration

`render.yaml` deploys the FastAPI backend. Configure these secrets in Render:

- `SUPABASE_DB_URL`
- `SUPABASE_MIGRATION_DB_URL` (optional at runtime)
- `PRODUCTION_SUPABASE_HOST`
- `PRODUCTION_SUPABASE_PROJECT_REF`
- `GEMINI_API_KEY`
- `FRONTEND_ORIGINS=https://alumnx-ai-sales-inbox-task-router.vercel.app`

Deploy `frontend/` as the Vercel project root, use `npm run build`, and publish
`dist/`. Configure:

```dotenv
VITE_API_BASE_URL=https://alumnx-ai-sales-inbox-task-router.onrender.com
```

Database and Gemini credentials belong only on Render. They must never use the
`VITE_` prefix or be exposed to the browser.

## Evaluation and engineering notes

[`EVALS.md`](EVALS.md) contains the frozen 60-email manual evaluation, metrics,
confidence analysis, and the required “Failure Cases I Did Not Fix” section.
[`DECISIONS.md`](DECISIONS.md) explains Gemini versus deterministic policy, Supabase,
idempotency, rate-limit handling, grounded chat, and the deliberately shipped
multi-owner limitation.

## Known limitation

When one email contains independent asks belonging to several owners, the baseline
creates one transparent triage task rather than multiple linked tasks. The specified
Task API supports one assignee and has no parent-child task relationship, so one task
per thread remains safer for reply reconciliation.
