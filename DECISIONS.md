# Engineering Decisions

## 1. Gemini extracts facts; Python makes the final decision

I use Gemini for the part it is good at: understanding messy English, Hinglish, HTML,
forwarded text, and intent. I did not let it directly choose side effects. Python
applies the routing order, Rs. 10 lakh boundary, PSU exception, 72-hour priority rule,
exact enums, suppression rules, and confidence penalties.

**Why I chose this:** model-only routing was harder to test and a confident wrong enum
would fail the grader. Keeping policy deterministic made the important rules repeatable.

**With two more weeks:** I would add a small adjudicated corpus of real inbox language,
measure where Gemini extraction still drifts, and tune the extractor without weakening
the deterministic policy.

## 2. Supabase Postgres is the source of truth

Tasks, raw emails, decisions, thread state, task events, ingest runs, feedback, and chat
audit rows are stored in Postgres. The chat can answer immediately from these tables;
it does not send old emails back to Gemini to rediscover facts already known.

**Why I chose this:** persistence is required, and relational constraints, transactions,
and row locks fit idempotency and thread reconciliation better than an in-memory cache.

**With two more weeks:** I would add retention rules, database dashboards, point-in-time
recovery checks, and indexes based on production query traces at higher volume.

## 3. Idempotency is enforced inside ingestion

The required public `POST /tasks` route intentionally creates a new task on every valid
request. `/ingest` is different: it records each email identity and content hash, locks
the thread, checks existing task state, and writes the task plus audit state in one
transaction. Replaying the same batch therefore does not create duplicate tasks, while
a later reply updates the existing thread task.

**Why I chose this:** adding deduplication to `POST /tasks` would violate the given API,
but leaving `/ingest` unprotected would fail the replay and reconciliation tests.

**With two more weeks:** I would add a durable worker queue with idempotency keys and
fault-injection tests for crashes between the remote task action and local confirmation.

## 4. Rate limits fail visibly instead of dropping email

Gemini calls use small structured batches, sequential request processing, rate limiting,
exponential retry for transient failures, schema repair, and a deterministic
fallback. The fallback lowers confidence and records degraded mode rather than silently
discarding the email. The model name and limits are environment driven.

**Why I chose this:** the free tier is enough for the challenge but can throttle. A slow
or lower-confidence result is safer than a missing RFP, and the API must not return
before processing finishes.

**With two more weeks:** I would record per-attempt latency and quota headers, adapt
batch size to remaining quota, and load-test the exact production account at 10,000
emails per day.

## 5. Chat is read-only and grounded by a fixed query path

The path is: **question -> deterministic intent plan -> allowlisted Postgres query ->
structured result -> deterministic answer + `supporting_data`**. Gemini may rewrite the
answer for readability, but the backend rejects wording that changes a number or drops
the subject. Zero is a valid result. Unsupported questions and actions such as sending
or deleting email are refused.

**Why I chose this:** free-form SQL or asking Gemini to count raw email text would make
the same question produce different numbers and would create an unnecessary security
risk.

**With two more weeks:** I would expand the allowlist from real ops questions, add a
query preview for reviewers, and test paraphrases and adversarial prompts continuously.

## Failure I knowingly shipped

A message with several independent owners becomes one triage task rather than several
linked tasks. The supplied Task API has one assignee and no parent-child relationship.
Splitting it now would make reply updates ambiguous, so I chose a visible human-review
queue. With two more weeks I would add internal sub-intents and a review screen while
still exposing one grader-compatible task per thread.
