# Evaluation

`data/eval/eval_60.json` contains draft generated labels and is not evidence of human
review. Before final metrics are published:

1. Generate a blind worksheet with `python scripts/prepare_manual_eval.py`.
2. Personally label all 60 messages without viewing draft labels.
3. Freeze those labels before prompt tuning.
4. Run `python scripts/run_evaluation.py`.

The final report must include precision, recall, and F1 per category; skip metrics;
spurious rate; exact date/value/company matches; thread-operation accuracy; a confusion
matrix; confidence calibration; and a section named **Failure Cases I Did Not Fix**
containing at least three genuine failures.

## Failure Cases I Did Not Fix

The required human-blind evaluation has not been completed. The following are honest
failures from the **synthetic 250-message regression** run on 9 August 2026 and are not
presented as manually reviewed quality claims:

1. `em_00105`, an award nomination requiring profile approval, was over-suppressed
   instead of routed to Marketing.
2. `em_00160`, an invitation to join a PR roundtable, was over-suppressed instead of
   routed to Marketing.
3. Company-only correction replies such as `em_00207` and `em_00231` were classified
   as acknowledgements/no-ops rather than task updates.

## Live synthetic regression snapshot

Model: `gemini-3.5-flash-lite`  
Corpus: 250 generated messages / 200 threads  
External writes: none; in-memory fake Task API and store only

| Metric | Result |
|---|---:|
| Operation accuracy | 98.00% |
| Owner/category accuracy | 81.87% |
| Priority exact match | 92.75% |
| Due-date exact match | 98.96% |
| Deal-value exact match | 98.45% |
| Company exact/null match | 98.45% |
| Degraded outputs | 0 |

The run initially exposed a model-formatted reply date containing literal quote
characters. The parser now accepts quoted ISO dates/datetimes, and a regression test
covers that failure. These metrics remain a development signal only. They must not be
used as the final hackathon evaluation until the 60 blind labels are personally frozen.
