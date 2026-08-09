# Evaluation

I manually reviewed 60 messages before running the final model evaluation. The set has
42 new-task emails, 8 thread updates, 8 messages that should be skipped, and 2 reply
acknowledgements that should not patch a task.

The frozen labels are in `artifacts/manual_eval.json`. The scoring script ignores the
draft suggestions stored beside them and reads only each `human_label`. The current
`gemini-3.5-flash-lite` pipeline was then run once against all 60 messages using the
in-memory repository, so this evaluation made no Supabase or Task API writes.

Reproduce it with:

```bash
python scripts/run_manual_evaluation.py
```

The exact predictions and machine-readable report are saved in
`artifacts/live_eval_predictions.json` and `artifacts/evaluation_report.json`.

## Results

| Metric | Result |
|---|---:|
| Messages processed | 60 |
| Operation accuracy | 100.00% |
| Skip precision | 100.00% |
| Skip recall | 100.00% |
| Missed actionable messages | 0 |
| Spurious tasks | 0 |
| Spurious rate | 0.00% |
| Priority exact match | 100.00% |
| Due-date exact match | 100.00% |
| Deal-value exact match | 100.00% |
| Company exact/null match | 97.62% |
| Degraded outputs | 0 |

Operation accuracy includes all creates, updates, skips, and no-ops. Business-field
exact match is measured on the 42 new tasks because update rows were labelled for
lifecycle behavior rather than duplicating the full existing task state.

## Precision and recall by category

| Category | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `enterprise_rfp` | 7 | 1.00 | 1.00 | 1.00 |
| `smb_enquiry` | 7 | 1.00 | 1.00 | 1.00 |
| `marketing` | 7 | 1.00 | 1.00 | 1.00 |
| `alliances` | 7 | 1.00 | 1.00 | 1.00 |
| `finance` | 7 | 1.00 | 1.00 | 1.00 |
| `triage` | 7 | 1.00 | 1.00 | 1.00 |

## Category confusion matrix

Rows are human labels and columns are model predictions.

| Expected \ Predicted | Enterprise | SMB | Marketing | Alliances | Finance | Triage |
|---|---:|---:|---:|---:|---:|---:|
| Enterprise | 7 | 0 | 0 | 0 | 0 | 0 |
| SMB | 0 | 7 | 0 | 0 | 0 | 0 |
| Marketing | 0 | 0 | 7 | 0 | 0 | 0 |
| Alliances | 0 | 0 | 0 | 7 | 0 | 0 |
| Finance | 0 | 0 | 0 | 0 | 7 | 0 |
| Triage | 0 | 0 | 0 | 0 | 0 | 7 |

## Confidence calibration

For creates, correctness means operation, owner, category, and all scored business
fields matched. For updates, skips, and no-ops, it means the lifecycle operation matched.

| Confidence range | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.00-0.59 | 7 | 44.43% | 100.00% |
| 0.60-0.79 | 0 | - | - |
| 0.80-1.00 | 53 | 92.06% | 98.11% |

The lower-confidence group contains ambiguous items sent to triage. The only exact-field
failure was high confidence, so confidence is directionally useful for ambiguity but is
still overconfident about company-name canonicalisation.

## Failure Cases I Did Not Fix

1. `em_00029` used `NTPC Limited`, the explicit company name in the email, while the
   human label used `National Thermal Power Corporation Limited`. The route, priority,
   date, and value were correct, but company exact match failed.
2. `em_00169` showed the same live-regression issue: the model preserved `NTPC Limited`
   instead of expanding the legal name.
3. `em_00180` showed the same issue again in a separate thread.

I did not hardcode an acronym-expansion table because guessing company legal names from
abbreviations can create worse false data. A production version should use a reviewed
company master or enrichment service and keep the source text beside the canonical name.

## Limits of this evaluation

This is a small, balanced 60-message set created from the challenge corpus, so perfect
category scores do not prove perfect production accuracy. It does include the required
hard cases: PSU routing, the exact Rs. 10 lakh boundary, deadlines within 72 hours,
Hinglish, marketing lookalike spam, ambiguous multi-owner messages, quoted reply chains,
field corrections, thread updates, acknowledgements, and bounces.
