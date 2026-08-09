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
remaining exact-match differences from the **synthetic 250-message regression** run on
9 August 2026 and are not presented as manually reviewed quality claims:

1. `em_00029` returned the explicit current name `NTPC Limited`; the synthetic oracle
   expected `National Thermal Power Corporation Limited`.
2. `em_00169` had the same explicit-name versus expanded-name mismatch.
3. `em_00180` had the same explicit-name versus expanded-name mismatch.

These were not hardcoded away because the product policy prohibits guessing acronym
expansions that are absent from the message. `NTPC Limited` is supported by the email;
the longer expansion is not. The manual evaluation may decide whether this conservative
behavior should remain.

## Live synthetic regression snapshot

Model: `gemini-3.5-flash-lite`  
Corpus: 250 generated messages / 200 threads  
External writes: none; isolated in-memory task repository only

| Metric | Result |
|---|---:|
| Operation accuracy | 99.60% |
| Owner/category accuracy | 100.00% |
| Priority exact match | 98.48% |
| Due-date exact match | 99.49% |
| Deal-value exact match | 100.00% |
| Company exact/null match | 98.48% |
| Degraded outputs | 0 |

That full run produced 155 creates, 50 skips, 42 updates, and 3 no-ops before the final
award-nomination rescue. A focused live-Gemini rerun then verified the corrected award
create, exact 71-hour IST priority, both downstream reply priorities, and the corrected
`tomorrow EOD` date. The corpus oracle now validates the intended 156/49/42/3 lifecycle.
The full percentage table was not silently recomputed after those focused fixes.

These synthetic metrics remain a development signal only. They must not be used as the
final hackathon evaluation until the 60 blind labels are personally frozen.
