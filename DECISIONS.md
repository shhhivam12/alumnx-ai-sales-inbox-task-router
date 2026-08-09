# Engineering Decisions

## 1. Gemini extracts; deterministic code decides

Messy English, Hinglish, HTML, quoted replies, and intent direction benefit from an
LLM. Exact enums, rule precedence, thresholds, dates, idempotency, arithmetic, and
side effects remain deterministic and testable.

## 2. Hosted Supabase Postgres

Exact operational counts, update history, unique constraints, and per-thread locking
fit Postgres. This submission uses one hosted Supabase project, with scoped test IDs
and exact cleanup before grading; no browser database access, Docker, or local Postgres
is required.

The normal test configuration still blocks production by default. The one hosted
concurrency test opts in explicitly, creates UUID-scoped rows, and deletes only those
exact rows. Live semantic corpus tests use an in-memory repository.

## 3. Idempotent ingestion over a deliberately non-deduplicating route

The required public `POST /tasks` intentionally does not deduplicate. `/ingest` avoids
duplicates with unique email records, a thread row lock, a task preflight lookup, and
one Supabase transaction that stores the task and audit state together. Direct grader
POSTs still create a fresh task each time, exactly as specified.

## 4. Gemini free-tier resilience

Calls use small structured batches, conservative rate limiting, transient retries,
schema repair, and a visible degraded mode. No email is silently dropped.
The baseline uses `gemini-3.5-flash-lite`: structured output is available, while its
lower token price is a better fit for batches of up to 100 emails. The model remains
configuration-driven so measured evaluation can justify a temporary stronger model.

## 5. Grounded read-only chat

A deterministic natural-language planner maps supported questions to an allowlisted
intent. Postgres computes every result and the backend first renders deterministic
prose plus `supporting_data`. Gemini may improve wording, but it receives only the
validated plan, supporting data, and grounded draft; any changed number or missing
subject is rejected. Actions and unsupported questions fail closed.

## 6. One task per ingested thread

Multi-owner emails go to triage with all asks stated. Splitting would make reply
reconciliation ambiguous because the required API has no parent-child task model.

## 7. Rejected abstractions

LangChain, LangGraph, LangSmith, RAG, vector databases, MCP, general agents, and
model-generated SQL add failure modes without improving this bounded workflow.

## 8. Free hosting tradeoff

Render can cold-start and Supabase can pause after inactivity. Readiness UI, cold-start
smoke tests, and pre-submission checks mitigate but do not remove this free-tier risk.

## Known shipped limitation

One message with independent asks for several owners becomes a triage task rather
than coordinated subtasks. A later product could add internal sub-intents and human
splitting while retaining one grader-visible thread task.
