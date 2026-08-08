# Hackathon Requirement Review

Use this as a reviewer checklist beside `PROBLEM_STATEMENT.md`. Status meanings:

- **PASS:** implemented and locally verified.
- **READY, EXTERNAL CHECK PENDING:** code exists; needs a real service connection.
- **USER INPUT REQUIRED:** cannot be completed without a value or human judgment.
- **DEPLOYMENT LATER:** intentionally reserved for final production testing.

## Submission identity

| Requirement | Status | Evidence |
|---|---|---|
| Candidate ID is lowercase and byte-identical | PASS | Config, grader Task routes, app API, UI, and README use `mahendrushivam123@gmail.com` |
| Wrong candidate rejected | PASS | Common error returns `candidate_id_mismatch` |
| Frontend has no editable candidate copy | PASS | It reads `/api/config` and displays the value |

## Required product workflow

| Requirement | Status | Evidence |
|---|---|---|
| Paste JSON | PASS | `JsonInput` plus local validation |
| Upload `.json` | PASS | Browser file input reads text locally |
| Generate/load sample | PASS | `/api/sample-emails`; 250 visible in browser |
| Show raw table before routing | PASS | Browser and component test |
| Explicit route click | PASS | No ingest during preview |
| Batch maximum 100 | PASS | Pydantic request limit and frontend chunk helper |
| 250 sends 100/100/50 sequentially | PASS | Unit test and visible local routing pass |
| Synchronous confirmed response | PASS | Service waits for every reconciliation |
| Result/evidence display | PASS | Decision table includes required routing fields |
| Grounded chat | PASS | Typed plans, allowlisted executor, supporting JSON |

## Routing and suppression

| Requirement | Status | Evidence |
|---|---|---|
| OOO, newsletter, bounce, vendor spam skipped | PASS | Deterministic suppression and tests |
| Marketing collaboration versus vendor direction | PASS | Direction-aware deterministic/Gemini contract |
| RFP/RFI/tender and PSU override | PASS | Routing precedence |
| Finance owner/category | PASS | Typed finance intent set |
| Marketing owner/category | PASS | Typed marketing intent set |
| Alliances owner/category | PASS | Typed alliance intent set |
| INR 10,00,000 boundary | PASS | 10,00,000 Rohit; 10,00,001 Aarti tests |
| Multi-owner ambiguity | PASS | One low-confidence triage task |
| Weak unresolved actionability | PASS | Triage rather than confident spam/task guess |
| Deal-value role exclusions | PASS | Finance/pipeline roles do not become deal value |
| Non-INR conversion prohibited | PASS | No exchange-rate conversion exists |

## Dates, company, confidence, and task text

| Requirement | Status | Evidence |
|---|---|---|
| Relative dates use `received_at` | PASS | Extractor receives and resolves from email time |
| Exactly 72 hours is high | PASS | Boundary unit test |
| Meeting/event/OOO date is not due date | PASS | Allowlisted actionable deadline roles |
| Company remains null when unsupported | PASS | Conservative extraction and prior-state merge |
| Confidence is application-calculated | PASS | `confidence.py`; Gemini has no confidence field |
| Titles/descriptions respect limits | PASS | Pydantic and routing truncation |
| Attachment content is never claimed read | PASS | Only filenames enter extraction evidence |

## Threading, replies, and idempotency

| Requirement | Status | Evidence |
|---|---|---|
| One task per ingested thread | PASS | Thread row lock plus local task reconciliation |
| Same email replay creates nothing | PASS | Unit and 250-email API replay smoke |
| Same ID/different content conflicts | PASS | Store conflict check |
| Reply uses PATCH | PASS | Reconciler and Task API contract |
| Source email remains original | PASS | Lifecycle test |
| Explicit clear/set/unchanged | PASS | Reply models and clear-field tests |
| Acknowledgement is no-op | PASS | Suppression and unit test |
| Orphan reply rejected | PASS | 409 unit test |
| Concurrent thread serialization | PASS | Hosted two-writer test produced one `created`, one `unchanged`, and one task row |
| Direct POST does not deduplicate | PASS | Contract test creates two IDs for the same payload |
| Task and audit write are atomic | PASS | Both use the connection bound by the thread transaction |
| Multiple task rows for one ingested thread stop writes | PASS | Reconciler returns 409 conflict |

## Persistence and Supabase

| Requirement | Status | Evidence |
|---|---|---|
| Private Postgres schema | PASS | Applied and catalog-verified on development Supabase |
| Required tables and indexes | PASS | Nine tables and 30 total explicit/constraint indexes verified |
| Persistent grader Task API table | PASS | `app_private.tasks`; live create/read/cleanup smoke passed |
| RLS enabled and no browser policies | PASS | RLS verified on all nine private tables |
| TLS session pooler | PASS | Client-side TLS and Session pooler port 5432 verified |
| Current development migration | PASS | `0002_local_task_api` applied and reverified |
| Production and test project guard | PASS | Project-reference checks in settings |
| No Supabase secret/client in frontend | PASS | No `supabase-js` dependency or Vite secret |

## Gemini

| Requirement | Status | Evidence |
|---|---|---|
| Official Google GenAI SDK | PASS | Locked dependency and extractor |
| Lower-cost structured model | PASS | Live key/model call succeeded with `gemini-3.5-flash-lite` |
| Schema-constrained output | PASS | Live two-email structured extraction succeeded |
| Up to five independent emails per call | PASS | Wave orchestration plus extractor chunking |
| Same thread sequential | PASS | One message per thread per wave |
| Rate limit/retry/jitter/Retry-After | PASS | Extractor and resilience tests |
| Missing item repair and malformed split | PASS | Unit failure simulations |
| Total outage degradation | PASS | Unit failure simulation |
| Full live 250 synthetic regression | PASS | Completed in isolated in-memory persistence; results and limitations are in `EVALS.md` |
| Full live 60 human-reviewed evaluation | USER INPUT REQUIRED | Requires personally frozen blind labels |

## Stats and chat

| Requirement | Status | Evidence |
|---|---|---|
| Unique processed denominator | PASS | Decision IDs, not delivery attempts |
| Delivery attempts separate | PASS | Run received counts |
| Current task questions use current snapshots | PASS | Chat executor fix and local browser query |
| History questions use confirmed events | PASS | Task-event grouping |
| Confirmed spurious feedback/rate | PASS | Feedback endpoint and stats |
| Ten required question families | PASS | Parameterized tests and local API smoke |
| Marketing separated from spam | PASS | Category versus skip-reason executor |
| Null-aware RFP sum | PASS | Current snapshots, null count, Indian formatting |
| Action request refused | PASS | Deterministic refusal test |
| No model SQL/actions/raw bodies | PASS | Typed plan contract and request shape |

## Security and observability

| Requirement | Status | Evidence |
|---|---|---|
| Request and field-size limits | PASS | FastAPI middleware and Pydantic |
| Raw HTML never rendered | PASS | Text conversion plus React escaping |
| Prompt injection treated as data | PASS | System boundary, no tools, typed schema |
| Parameterized SQL | PASS | Psycopg placeholders throughout repository |
| Structured logs without bodies/secrets | PASS | JSON formatter and safe event fields |
| Exact production CORS | PASS | Production startup validation |
| No Docker/local Postgres | PASS | Scripts and docs use hosted Supabase |
| No LangChain/LangGraph/LangSmith/RAG/MCP | PASS | No dependencies or runtime code |

## Tests and evaluation

| Requirement | Status | Evidence |
|---|---|---|
| Dataset validator | PASS | 250 messages, 200 threads, frozen expected lifecycle |
| Backend unit tests | PASS | Configuration, routing, edge, chat, Gemini, lifecycle |
| Task API contract tests | PASS | Exact create/list/filter/patch/delete/users, enum error, candidate, and direct duplicate behavior |
| Frontend build/tests | PASS | Vite production build and Vitest |
| Local 250 API smoke and replay | PASS | `scripts/local_api_smoke_test.py` |
| Visible browser workflow | PASS | Preview, route, decisions, chat, responsive pass |
| Hosted Supabase repository smoke | PASS | Insert/lock/decision/event/feedback/audit/read/targeted cleanup passed |
| Frozen manual 60 labels | USER INPUT REQUIRED | Must be personally labelled, not generated |
| Honest metrics/confusion/calibration | USER INPUT REQUIRED | Run only after labels are frozen |
| Three real unfixed failures | USER INPUT REQUIRED | Populate from live reviewed evaluation |

## GitHub readiness

| Requirement | Status | Evidence |
|---|---|---|
| No committed `.env` | PASS | `.gitignore` ignores `.env` |
| No detected keys/DB passwords | PASS | Secret-pattern scan |
| Dependency lock for frontend | PASS | `package-lock.json` |
| CI for backend/frontend/dataset | PASS | `.github/workflows/ci.yml` |
| README setup within three commands | PASS | Bootstrap, migrate, dev |
| Public URLs and video | DEPLOYMENT LATER | Placeholders remain intentionally |

## What is needed from the user now

The Supabase development connection and persistent Task API are complete. No organizer
Task API URL or key is needed. The 60-message blind worksheet still requires personal
labels before final evaluation claims.

## Intentionally postponed until deployment

- Production Supabase migration.
- Render and Cloudflare deployment.
- Exact deployed CORS verification.
- Cold-start-after-idle tests.
- Public grader Task API contract smoke on the deployed Render URL.
- Public URLs, repository URL, and video URL.
