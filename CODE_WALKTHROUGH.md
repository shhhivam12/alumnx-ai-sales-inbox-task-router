# Alumnx AI Sales inbox task router — Beginner Code Walkthrough

This document explains the project as if you are preparing to present it to a reviewer.
It avoids framework jargon where possible and tells you where each important behavior
lives. Read `PROBLEM_STATEMENT.md` first for the business problem, then use this file to
explain the implementation.

## 1. The whole product in one sentence

The browser sends a batch of emails to FastAPI; the backend safely reads the current
message, asks Gemini for structured facts when needed, applies exact Python routing
rules, creates or updates one persistent task per thread, records the evidence in Postgres,
and answers analytics questions only from stored facts.

```text
React browser
    -> POST /ingest
    -> validation and normalization
    -> deterministic suppression
    -> Gemini fact extraction
    -> deterministic routing policy
    -> per-thread database lock
    -> Task API POST/PATCH
    -> Supabase audit records
    -> results and grounded chat
```

## 2. Important vocabulary

- **Email ID:** identifies one immutable delivered message.
- **Thread ID:** groups the original message and all replies.
- **Candidate ID:** the submission namespace. It is always
  `mahendrushivam123@gmail.com`.
- **Decision:** our stored explanation of what one email meant.
- **Task:** the grader-visible work item stored by our own backend Task API.
- **Ingest run:** one HTTP call to `/ingest`, containing at most 100 emails.
- **Ingest group:** one logical browser batch. A 250-email batch contains three runs.
- **Reconciliation:** checking stored email, thread, and task state before insert or
  update so retries do not make duplicate tasks.
- **Degraded mode:** safe deterministic extraction used when Gemini is unavailable.
- **Grounded answer:** an answer whose numbers and IDs come from stored query results.

## 3. Repository map

### Root files

- `.env.example` lists safe configuration names. Real secrets stay in ignored `.env`.
- `README.md` is the public setup and submission page.
- `HACKATHON_PLAN.md` locks architecture and implementation phases.
- `DECISIONS.md` explains engineering tradeoffs.
- `EVALS.md` explains honest evaluation and why generated labels are not human review.
- `PROBLEM_STATEMENT.md` is the original challenge contract.
- `render.yaml` declares the future Render backend service.
- `pyproject.toml` configures Python linting.

### `backend/app`

- `main.py`: creates FastAPI, CORS, request-size protection, routes, and error handlers.
- `config.py`: loads environment variables and fails early on unsafe configuration.
- `errors.py`: converts application and validation errors into one JSON shape.
- `dependencies.py`: creates the configured repository, Gemini extractor, reconciler,
  and ingestion service once per process.
- `logging_config.py`: formats application logs as JSON without email bodies or secrets.

### `backend/app/domain`

Domain files contain business data and rules, not HTTP or database code.

- `enums.py`: exact Task API values such as `u_aarti` and `enterprise_rfp`.
- `email_models.py`: validates incoming emails and batches.
- `extraction_models.py`: the only structured shape Gemini may return.
- `task_models.py`: exact create and patch payloads for the Task API.
- `chat_models.py`: allowlisted chat plans and scopes.
- `routing_policy.py`: exact routing precedence, priority, task text, and reply merging.
- `confidence.py`: application-owned confidence calculation.

### `backend/app/services`

- `email_normalizer.py`: makes text safe and consistent.
- `quote_parser.py`: removes old quoted history from a reply prompt.
- `suppression.py`: high-precision OOO, bounce, newsletter, spam, and acknowledgement
  detection before normal routing.
- `gemini_extractor.py`: prompt, structured schema call, batching, retry, repair/split,
  and degraded extraction.
- `gemini_rate_limiter.py`: ensures calls respect the configured requests per minute.
- `reconciler.py`: decides create, adopt, update, no-op, or conflict under a thread lock.
- `ingestion_service.py`: orchestrates a complete synchronous batch.
- `stats_service.py`: calculates exact operational counts.
- `chat_planner.py`: maps supported questions to a small typed intent.
- `chat_executor.py`: runs only allowlisted stored-data operations.
- `answer_renderer.py`: turns supporting data into deterministic prose.

### `backend/app/repositories` and `backend/app/db`

- `store.py`: thread-safe in-memory adapter for credential-free unit tests.
- `postgres_store.py`: persistent hosted Supabase adapter.
- `pool.py`: small TLS Psycopg connection pool with health and migration checks.
- `transaction.py`: rollback-safe transaction helper.
- The small repository-named modules document ownership; both real adapters implement
  the same operations used by services.

### `backend/app/api`

Each file owns one public API area:

- `config.py`: read-only public app name, identity, and batch limit.
- `ingest.py`: required synchronous ingestion endpoint.
- `grader_tasks.py`: exact persistent `/tasks` CRUD and `/users` grader contract.
- `tasks.py`: current tasks plus local evidence.
- `stats.py`: scoped exact aggregates.
- `decisions.py`: per-email results and human feedback.
- `samples.py`: email-only sample data.
- `chat.py`: grounded analytics chat.
- `health.py`: cheap liveness and dependency-aware readiness.

### `frontend/src`

- `App.tsx`: page state and the complete user journey.
- `api/client.ts`: browser calls to our backend only.
- `features/input/validation.ts`: safe local parsing and 100-email chunk creation.
- `components/JsonInput.tsx`: paste, upload, and sample controls.
- `components/EmailPreviewTable.tsx`: raw plain-text preview before ingestion.
- `components/RoutingProgress.tsx`: readiness lock and sequential progress.
- `components/ProcessingSummary.tsx`: result counters.
- `components/DecisionTable.tsx`: route, confidence, evidence, and feedback.
- `components/ChatPanel.tsx`: scoped questions plus collapsible supporting data.
- `styles.css` and `mobile.css`: desktop, table overflow, and mobile layout.

## 4. Startup and configuration

`Settings` in `backend/app/config.py` reads `.env`. Pydantic validates types such as
integers and URLs before the server accepts traffic.

Important safety checks:

1. Candidate ID is trimmed and lowercased.
2. It must equal the locked email exactly.
3. A Supabase value must be a `postgresql://...` connection string. A public
   `https://PROJECT.supabase.co` URL is rejected.
4. TLS is added when `sslmode` is missing.
5. Production requires Gemini, Supabase, non-wildcard CORS, and the expected
   production project reference.
6. Tests reject the configured production project reference.

`dependencies.py` checks whether `SUPABASE_DB_URL` is present. With a valid value it
creates `PostgresStore`; credential-free tests use `MemoryStore`. Production cannot
start without Postgres because production configuration requires the URL.

## 5. What happens inside `POST /ingest`

### Step 1 — HTTP and schema validation

FastAPI parses JSON into `IngestRequest`. Pydantic verifies required fields, string
lengths, valid email addresses, timezone-aware timestamps, array limits, batch size,
duplicate email IDs, and duplicate thread/index pairs. Unknown email fields remain in
the raw JSON but do not influence routing.

### Step 2 — create the run

`IngestionService.ingest()` hashes the request and creates one `ingest_runs` record.
The optional `client_batch_id` links three frontend chunks to one `ingest_groups` row.

### Step 3 — preserve thread ordering and batch Gemini work

Messages are sorted within each thread by message index, received time, and email ID.
The service makes a “wave” containing at most one email from each thread. Up to five
independent emails in that wave can share one Gemini request. A second reply from the
same thread cannot enter a wave until its predecessor has finished.

### Step 4 — normalize the email

`normalize_email()`:

- converts line endings and HTML entities;
- turns simple HTML into readable text;
- strips script/style content;
- finds the current unquoted reply;
- retains attachment filenames only as filenames;
- preserves the full validated input as raw JSON;
- creates a stable SHA-256 content hash;
- truncates only prompt content when required.

React also renders bodies as text, never as HTML.

### Step 5 — detect duplicates and conflicts

The store looks up candidate/email and candidate/thread/index keys.

- Same email ID and same content hash: `unchanged`.
- Same email ID but different content: HTTP 409.
- Same thread/index but a different email ID: HTTP 409.
- A new email ID with duplicate text is still a new message, as required.

### Step 6 — deterministic suppression

`deterministic_suppression()` runs before Gemini routing. It requires strong signal
combinations, which reduces expensive calls and avoids spurious tasks.

- OOO needs an automatic/away subject and an away/return body signal.
- Bounce needs a mailer-daemon/postmaster sender and delivery-failure language.
- Newsletter needs broadcast language and an unsubscribe/preferences signal.
- Vendor spam needs selling-to-us direction, not merely words like marketing or SEO.
- A pure acknowledgement on an existing thread becomes a no-op.

Weak spam is not confidently suppressed; Gemini may clarify it, and unresolved
actionable text goes to triage.

### Step 7 — Gemini extracts facts, not policy

Gemini receives delimited untrusted data, the current message, metadata, attachment
names, and a short prior task state. It has no tools and cannot call the database or
Task API.

The schema allows only facts such as intent, direction, organization, typed amounts,
typed deadlines, urgency, evidence, and explicit reply changes. Pydantic rejects any
unsupported enum.

The current default is `gemini-3.5-flash-lite`, chosen for lower batch cost. Calls are
rate-limited, transient failures retry with jitter and Retry-After where available,
missing IDs retry individually, malformed batches split into individual calls, and a
final failure uses conservative deterministic extraction.

### Step 8 — Python applies routing precedence

`route_email()` owns the final decision. The key order is:

1. Non-actionable -> skip.
2. Multiple independent owners -> triage.
3. Government/PSU tender -> Aarti.
4. Formal RFP/RFI/tender -> Aarti.
5. Finance -> Divya.
6. Marketing collaboration -> Meera.
7. Alliances -> Karan.
8. Direct purchase above INR 10,00,000 -> Aarti.
9. Direct purchase at or below INR 10,00,000 -> Rohit.
10. Clear demo/trial/product enquiry -> Rohit.
11. Remaining actionable uncertainty -> triage.

Finance, payment, invoice, and alliance pipeline amounts are not deal values.
Non-INR values are not converted. Exactly 72 hours is high priority; relative time is
resolved from the email’s `received_at`, not the server clock.

### Step 9 — confidence is calculated

Gemini does not choose its own confidence. `confidence.py` starts from a rule-specific
base, adds supported agreement signals, subtracts ambiguity/noise/failure penalties,
and clamps the result. Low-confidence ambiguity remains triage.

### Step 10 — reconcile under one thread lock

`Reconciler.reconcile()` enters `store.thread_lock(thread_id)`. In Postgres this creates
the placeholder when needed and executes `SELECT ... FOR UPDATE` inside one transaction.
All reads and writes in that reconciliation use the same bound connection.

Then it queries our persistent `tasks` table through the repository:

- Zero matching tasks and no mapping -> insert one task.
- One matching task and no mapping -> adopt it.
- More than one matching task -> conflict and stop writes.
- Existing task plus changed fields -> smallest allowed PATCH.
- Existing task plus no changes -> no-op.
- Previously mapped task disappears -> error; never silently recreate it.

Because the task insert and all audit rows share the same bound Postgres transaction,
they commit or roll back together. There is no second organizer service or network gap.

### Step 11 — commit audit state

The same successful transaction stores the task, immutable email, decision, current
thread snapshot, and operation event. A failed transaction leaves no half-created task.

## 6. Reply behavior

A task’s `source_email_id` always remains the first email that created it. A reply may
change category, owner, priority, due date, deal value, company, confidence, and factual
description. Explicit `clear` is different from “no new value”:

- `clear`: set the field to null.
- `set`: use the supported new value.
- `unchanged`: keep prior state when the current reply gives no replacement.

Descriptions append only genuinely new reasoning and stay below 2,000 characters.
OOO, newsletter, bounce, or spam replies do not mutate an existing task.

## 7. Database tables in easy language

- `ingest_groups`: one browser batch ID.
- `ingest_runs`: one `/ingest` delivery and its counters/errors.
- `emails`: immutable received messages and safe normalized text.
- `decisions`: one final classification per email.
- `threads`: the current task snapshot and task ID mapping per thread. The internal
  `remote_task_id` column name is legacy wording; it now points to our own `tasks` row.
- `task_events`: create/update/adopt/no-op history and before/after snapshots.
- `tasks`: the exact grader-visible task records returned by `GET /tasks`.
- `quality_feedback`: explicit human correctness/spurious labels.
- `chat_audit`: question, validated plan, supporting data, and answer; never raw body.

Tables live in `app_private`, RLS is enabled, and no browser policy is created. Only the
trusted backend receives the Postgres password.

## 8. Grounded chat

The chat path is intentionally not a general agent:

```text
question -> refusal guard -> typed intent -> validation -> allowlisted query
         -> supporting_data -> deterministic sentence -> audit
```

`chat_planner.py` recognizes the ten grading families. It never returns SQL, table
names, arbitrary operators, or actions. `chat_executor.py` uses decision history for
email-count questions and current thread snapshots for current task/value questions.
`answer_renderer.py` can only mention values passed in `supporting_data`.

“Send an email” is refused. Zero is stated explicitly. Spurious rate means confirmed
human flags divided by unique processed emails; zero flags is never called perfect
accuracy. “Open RFP” includes a caveat in review material because the required API has no
open/closed status.

## 9. Frontend journey

1. `App` fetches `/api/config`; the candidate ID is display-only.
2. It polls `/ready` during a cold start.
3. Paste, upload, or sample loading parses locally.
4. A raw table appears before any `/ingest` call.
5. The user explicitly clicks Route.
6. `chunkEmails()` makes `100/100/50`; a normal `for` loop awaits each request, so
   chunks are never concurrent.
7. Counters and decision evidence render after confirmation.
8. Chat defaults to the current logical batch and exposes supporting JSON.

Tables use horizontal scrolling on small screens. Email text is escaped by React.

## 10. How to explain idempotency in an interview

Say:

> The grader-facing POST route intentionally does not deduplicate, but ingestion must.
> The email hash catches exact replays and a Postgres thread row lock serializes
> concurrent writers. Under that lock I query our tasks table, then insert or update the
> task and audit records in one transaction. Replies always update the adopted task ID.

## 11. How to explain Gemini versus deterministic rules

Say:

> Gemini handles messy language and returns supported facts in a strict schema. Python
> owns exact rule order, INR thresholds, due-date roles, confidence, enums, arithmetic,
> and side effects. This gives language understanding without giving the model authority
> to write tasks or invent analytics.

## 12. Tests and what they prove

- Unit tests: input, configuration, suppression, threshold/date boundaries, clearing,
  confidence/routing, chat intents, and Gemini failures.
- Contract tests: exact Task API create/list/filter/patch/delete/users behavior,
  candidate identity, enum errors, and deliberate direct-POST duplicates.
- Dataset validator: frozen 250-message corpus and expected lifecycle.
- Frontend tests: invalid input, raw/full payloads, duplicates, and 100/100/50 chunks.
- Local API smoke: health, readiness, samples, full 250 ingestion, replay, tasks,
  decisions, stats, feedback, and all ten chat questions.
- Browser pass: visible preview, explicit routing, result/evidence table, grounded chat,
  and responsive layout.

## 13. Common debugging path

- Startup says Supabase URL is invalid: copy the Session pooler Postgres string, not the
  project HTTPS URL.
- `/ready` says migration missing: run `python scripts/migrate.py`.
- Gemini is degraded: verify key/model/quota; logs contain event types, never bodies.
- Duplicate task rows: stop ingestion writes, inspect the thread conflict, and clean up
  only exact development task IDs.
- A replay shows `unchanged`: correct; it is processed but creates no new decision/task.
- Chat number looks unexpected: open supporting data, then inspect decision history or
  current thread snapshot depending on question semantics.

## 14. Presentation order

1. State the outcome and locked identity.
2. Preview sample emails before routing.
3. Route and explain sequential chunks.
4. Show created, updated, skipped, no-op, and evidence.
5. Ask an RFP count or deal-value question and open supporting data.
6. Explain Gemini facts versus deterministic policy.
7. Explain the thread lock and POST-timeout reconciliation.
8. End with the honest one-task multi-owner limitation.
