# Master Implementation Contract

## Alumnx AI Sales inbox task router

- Candidate ID: `mahendrushivam123@gmail.com`
- Backend: Python 3.12, FastAPI, Pydantic v2, HTTPX
- Database: hosted Supabase Postgres through the session pooler with TLS
- Frontend: React, TypeScript, Vite
- Deployment: Render backend and Cloudflare Pages frontend
- LLM: official Google GenAI SDK with schema-constrained extraction; the configurable
  default is the lower-cost `gemini-3.5-flash-lite`

This file is the locked implementation contract. The challenge statement in
`PROBLEM_STATEMENT.md` remains authoritative if an external contract changes.

## Non-negotiable behavior

1. Normalize and validate the candidate ID on every grader Task API and ingestion request.
2. `/ingest` accepts 1-100 emails and returns only after all required Task API writes
   have succeeded or definitively failed.
3. One candidate/thread maps to at most one task created by `/ingest`. Replies patch that task;
   repeated deliveries never create duplicates.
4. Suppress out-of-office messages, delivery failures, newsletters, and high-confidence
   unsolicited vendor spam. Triage is only for actionable ambiguity.
5. Gemini extracts facts. Deterministic code owns routing precedence, exact enums,
   amount/date roles, confidence, POST/PATCH decisions, and all arithmetic.
6. Missing or unsupported company, due date, or deal value remains `null`.
7. Chat uses allowlisted database queries and always returns `supporting_data`.
8. Browser code never receives Gemini or database credentials. It calls only our
   FastAPI backend, which also implements the grader-facing Task API.

## Routing precedence

1. Confirmed non-actionable: skip.
2. Multiple material asks with different owners: triage.
3. Government/PSU tender: Aarti / `enterprise_rfp`.
4. Formal RFP/RFI/tender: Aarti / `enterprise_rfp`.
5. Invoice, PO, payment, tax, credit-note, or vendor billing: Divya / `finance`.
6. Webinar, sponsorship, content, PR, media, or awards: Meera / `marketing`.
7. Reseller, channel, referral, OEM, marketplace, white-label, or integration:
   Karan / `alliances`.
8. Direct purchase above INR 10,00,000: Aarti.
9. Direct purchase at or below INR 10,00,000: Rohit / `smb_enquiry`.
10. Clear small-company demo/trial/product enquiry with no value: Rohit.
11. Remaining actionable ambiguity: triage.

An actionable deadline that is overdue or no more than 72 hours from `received_at`
is high priority. A stated no-rush request is low; otherwise priority is medium.

## Persistence

Alembic creates the private Postgres schema and these tables:

- `ingest_groups`
- `ingest_runs`
- `emails`
- `decisions`
- `threads`
- `task_events`
- `tasks`
- `quality_feedback`
- `chat_audit`

The public `POST /tasks` deliberately permits duplicates, exactly as the grader spec
requires. `/ingest` provides idempotency through unique email records, per-thread row
locks, a task preflight lookup, and an atomic task-plus-audit transaction.

## Gemini contract

Gemini extracts actionability, skip reason, intents, owner candidates, direction,
organization, procurement type, typed amounts, typed deadlines, urgency, subtypes,
topics, evidence, and explicit reply field changes. Outputs are Pydantic-validated.
Calls are rate-limited, retried for transient failures, and split when a structured
batch is incomplete. Persistent failure activates a conservative deterministic mode.

The project intentionally excludes LangChain, LangGraph, LangSmith, RAG, vector
databases, MCP, general agents, model-generated SQL, queues, Docker, local Postgres,
browser Supabase access, and email sending.

## Delivery phases

1. Repository/configuration/contracts/migration.
2. Normalization, suppression, routing, confidence, and oracle tests.
3. Task API reconciliation and synchronous ingestion.
4. Gemini structured extraction and degraded mode.
5. Stats, feedback, and grounded chat.
6. Preview-first React UI with sequential 100/100/50 batching.
7. Manual evaluation, edge hardening, deployment, documentation, and video.

Every phase must report changed files, commands, test results, remaining failures,
external side effects, and prerequisites for the next phase. Generated labels never
count as the required hand-labelled evaluation.

## Phase-by-phase agent contract

Every agent first reads `PROBLEM_STATEMENT.md`, this contract, `DATASET.md`, existing
tests, and the latest handoff. Every phase reports files changed, commands, results,
known failures, external side effects, and exact next prerequisites.

### Phase 0 — repository normalization

Create the locked layout, preserve fixtures/ground truth, install safe placeholders,
and remove active legacy-stack guidance. Gate: dataset validator, backend import,
frontend build, no secrets, and no Docker.

### Phase 1 — contracts, configuration, and Supabase

Implement strict models/enums, startup guards, TLS pool, Alembic schema/index/RLS,
repository adapters, liveness, readiness, and public config. Gate: migration
apply/reapply on the single hosted project, production safety tests, and
stable OpenAPI. Tests use explicit UUID scope and exact cleanup.

### Phase 2 — deterministic domain engine

Implement normalization, current-reply extraction, suppression, typed amount/date/
company policy, precedence, confidence, explicit reply changes, and task payloads.
Gate: worked examples, invalid fixtures, boundary tests, and exact oracle replay.

### Phase 3 — Task API and ingestion

Implement the persistent grader routes (`/tasks` and `/users`), synchronous ingestion,
candidate/thread locking, durable events, task adoption, smallest PATCH, immutable
source identity, enriched `/api/tasks`, and batch decisions. Gate: exact direct API
contract plus replay/concurrency/reply behavior and counters.

### Phase 4 — Gemini extraction

Implement email-ID-keyed schema output, micro-batches, rate limiting, Retry-After,
jittered retries, repair, missing-item retry, split fallback, focused verification,
injection boundaries, and conservative degradation. Gate: failure simulations and a
live sample using in-memory task persistence during prompt tuning.

### Phase 5 — statistics and grounded chat

Implement run/batch/all scopes, unique-delivery semantics, ten question families,
allowlisted execution, deterministic answers, numeric/ID validation, audit, and human
feedback. Gate: stable answers, exact zero/refusal behavior, and no raw email bodies or
executable queries reaching Gemini.

### Phase 6 — frontend

Implement wake state, JSON/file/sample input, safe raw preview, explicit route action,
sequential 100/100/50 requests, progress/results/feedback, grounded chat/supporting
data, responsive tables, and accessible errors. Gate: preview-before-ingest, read-only
identity, and no service secret or Supabase client in the bundle.

### Phase 7 — evaluation and hardening

Freeze personally reviewed blind labels before tuning; report category and suppression
precision/recall/F1, field exact matches, lifecycle accuracy, confusion matrix, and
confidence calibration. Exercise all edge families and preserve three honest failures.

### Phase 8 — deployment and submission

Migrate production, deploy Render/Cloudflare, set exact CORS, test cold readiness,
one/full/replay/reply ingests and grounded/refusal chat, audit persistent task counts, finalize
URLs/docs/video, and verify candidate identity byte-for-byte.

## Edge-case invariant registry

- Identity/input: normalized/wrong IDs, empty/oversized batches, malformed fields,
  timezone enforcement, duplicates/conflicts, out-of-order/later/orphan replies, HTML,
  Unicode, large bodies, unknown fields, and request limits.
- Suppression: English/Hinglish OOO, quoted bounce decoys, newsletters versus invites,
  vendor directionality, weak spam, prompt injection, and harmless thread replies.
- Ownership: formal/public procurement overrides, exact INR thresholds, small demos,
  all department subtypes, negation, multi-owner triage, cross-threshold ranges, and
  non-INR values without conversion.
- Facts: Indian units, relative dates from `received_at`, 71/72/73 hours, end-of-day,
  meeting/event/OOO decoys, superseded quotes, amount roles, conflicts, and clearing.
- Consistency/failure: replay, concurrency, missing/conflicting task mappings,
  transaction rollback, enum rejection, immutable source, malformed/partial/rate-
  limited Gemini, outage, stable scoped chat, null sums, zeroes, and refusal.
