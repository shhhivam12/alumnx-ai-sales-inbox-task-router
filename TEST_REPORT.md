# Verification Report

Date: 9 August 2026 (IST)

Application: `Alumnx AI Sales inbox task router`

Candidate ID: `mahendrushivam123@gmail.com`

This report separates exact contract/lifecycle results from probabilistic semantic
quality. It does not claim that unseen natural language can be perfect.

## Final baseline result

- The backend implements both required API groups under one base URL.
- The production-configured local backend reports ready with Supabase, migration,
  persistent Task API, and Gemini configured.
- All 12 problem-statement worked examples pass live.
- The 24-case live adversarial matrix passes with no errors or degraded outputs.
- The production HTTP API matrix passes every group and verifies exact cleanup.
- The frozen 250-message lifecycle is exact: 156 creates, 49 skips, 42 updates,
  and 3 no-ops.
- Production Supabase has the current schema and zero application rows, ready for the
  grader's fresh batch.

## Official worked examples: 12/12 live

These were sent through the running FastAPI backend using
`gemini-3.5-flash-lite` and the production Supabase project. The runner removed only
its unique test records and verified cleanup.

| # | Expected outcome | Verified result |
|---:|---|---|
| 1 | Aarti / enterprise RFP / Rs. 25 lakh / 12 Aug | PASS, exact |
| 2 | Rohit / SMB / low / no invented value or date | PASS, exact |
| 3 | PSU override to Aarti / Rs. 6.5 lakh / high | PASS, exact |
| 4 | Meera sponsorship / Rs. 4 lakh / tomorrow EOD | PASS, exact |
| 5 | Divya finance / overdue / invoice value excluded | PASS, exact |
| 6 | Karan alliances / no sales value | PASS, exact |
| 7 | Out-of-office | PASS, no task |
| 8 | SEO/PR/webinar vendor pitch | PASS, no task |
| 9 | Newsletter | PASS, no task |
| 10 | Reply correction | PASS, PATCH semantics, one task, original source ID |
| 11 | Two-owner ambiguity | PASS, triage with confidence `0.42` |
| 12 | Hinglish `1.2 cr`, board review, unknown company | PASS, exact |

Artifact command: `python scripts/run_official_examples_live.py`

## Public HTTP API matrix

`scripts/run_production_api_matrix.py` exercises the real HTTP process and production
database with a unique marker. All eight groups passed:

1. `/health`, `/ready`, `/api/config`, and `/users`.
2. `POST/GET/PATCH/DELETE /tasks`, filters, exact enum error, required fields, missing
   task behavior, and the required direct-POST non-deduplication.
3. `/ingest` create, suppression, reply update, replay idempotency, `/api/tasks`, batch
   decisions, and scoped stats.
4. Feedback creation/correction and confirmed-spurious semantics.
5. All ten required grounded chat question families, explicit zero, action refusal,
   and repeat-answer stability.
6. 250 sample emails with no labels or ground truth.
7. Wrong identity, empty/duplicate/invalid fields, strict booleans, timezone errors,
   same-ID content conflict, thread-index conflict, orphan reply, malformed JSON,
   real 25 MiB rejection, missing scope, invalid UUID, 404, and 405.
8. Exact allowed CORS origin and rejection of a foreign origin.

The final cleanup removed only the matrix marker's records and verified zero matching
emails, threads, tasks, groups, and chat audits remained.

## Adversarial semantic matrix: 24/24 live

The live, no-database adversarial run covers:

- RFI and PSU/formal precedence;
- Rs. 10,00,000 and Rs. 10,00,001 boundaries;
- high-value sponsorship versus sales;
- overdue invoice and GST with invoice amount excluded;
- reseller/integration and alliance pipeline values;
- legitimate SEO product buyers versus SEO vendor spam;
- newsletter sponsorship versus broadcast suppression;
- forwarded actionable RFP evidence;
- prompt-injection text with multiple owners;
- event/meeting date decoys;
- Hinglish and unknown company;
- foreign currency without conversion;
- different-owner versus same-owner multi-intent;
- company-only replies, OOO replies, and acknowledgement no-ops.

Result: 24 passed, 0 errors, 0 degraded outputs.

Artifact command: `python scripts/run_hackathon_adversarial_live.py`

## Frozen 250-message regression

The dataset validator confirms 250 messages, 200 threads, 156 final tasks, 14 generated
edge assertions, 11 invalid fixtures, and the exact lifecycle below.

| Operation | Expected | Live result |
|---|---:|---:|
| Create | 156 | 156 |
| Skip | 49 | 49 |
| Update | 42 | 42 |
| No-op | 3 | 3 |

The latest full live-Gemini measurement before the final narrow hardening rules was:

| Metric | Result |
|---|---:|
| Operation accuracy | 100.00% |
| Owner/category accuracy | 94.44% |
| Priority exact match | 94.95% |
| Due-date exact match | 98.48% |
| Deal-value exact match | 97.98% |
| Company exact/null match | 98.48% |
| Dropped/degraded | 0 / 0 |

These synthetic metrics are not substituted for the required personally reviewed
60-message evaluation. See `EVALS.md` for the honest limitation and unfixed cases.

## Automated suites

| Suite | Result |
|---|---|
| Backend unit/integration/contract | PASS; 137 tests |
| Hosted Supabase concurrency | PASS; one `created`, one `unchanged`, one task |
| Ruff | PASS |
| Dataset validator | PASS |
| Frontend Vitest | PASS; 2 files / 4 tests |
| TypeScript + Vite production build | PASS |
| Playwright desktop workflow | PASS; 250 preview and sequential 100/100/50 |

## Production Supabase state

- Alembic revision: `0002_local_task_api`.
- Required private tables: 9/9.
- Index count: 30.
- RLS: enabled on 9/9 tables.
- TLS: required through the session pooler.
- Application rows after test cleanup: zero in all nine tables.

An empty application dataset is intentional at handoff: the schema is initialized,
but old demo tasks cannot contaminate grader counts.

## Deliberately not completed yet

- Render/Cloudflare deployment and public cold-start tests.
- Final Cloudflare-origin CORS replacement.
- Personally reviewed 60-email labels and final precision/recall/F1.
- Mobile-specific browser test, skipped by user for the baseline.
- Submission video and public URLs.
