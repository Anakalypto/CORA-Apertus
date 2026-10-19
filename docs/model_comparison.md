# Apertus v1.5 70B vs 8B on every AI feature of CORA

**Question.** Can CORA run on Apertus 8B instead of 70B? The smaller model is about 3× faster per call and runs on a single GPU, so an archive could host it itself. The question is what that costs in quality, feature by feature.

**Method.** Each feature was run on both models with identical inputs, the pipeline's own prompts and post-processing, and the same scoring. Where a reference exists we score against it; where none exists we only compare the models with each other, and say so. Raw outputs of both models are kept for audit.

```
python src/eval_models.py --config src/config_eval200.toml   # parsing (200 new records)
python src/eval_features.py                                  # the other features
```

Results: `data/eval200/model_comparison.json` (parsing) and `data/model_eval/<feature>.json` (outputs + metrics). Run on 19 Oct 2026 through the Keera gateway (CSCS).

## Summary

| Feature | Reference | 70B | 8B | Verdict |
|---|---|---:|---:|---|
| **Parsing** (classification pass), 200 new records | automatic checks | 98.5 % pass | **100 %** pass | 8B as good |
| | creator = record's author field | 86.6 % | **95.1 %** | 8B better ¹ |
| **Stapfer extraction**, 100 sheets of 1799 | Bern hand coding (ground truth) | **84.5 %** | 80.8 % | 70B better |
| | sheets with unusable output | **0 %** | 8 % ² | 70B better |
| **Source level** (pass 3) | 29 levels adjudicated by hand | **62 %** | 55 % | 70B better (small n) |
| | secondary sources recognised (keyword labels, n = 120) | **70 %** | 28 % | 70B much better |
| **Audit, mechanical checks** | rule detectors (exact) | F1 0.20–0.98 | F1 0–0.88 | 70B better, **but rules decide** ³ |
| **Audit, judgement checks** (persons, places, sensitivity) | none | — | — | 93–99 % agreement |
| **Ask the archive**, 24 questions | known answer record | 100 % right record cited | 100 % right record cited | equal ⁴ |
| | unanswerable questions refused | 8 / 8 | 8 / 8 in substance, 1 flag missing | equal ⁴ |
| **Imagination** (trust card, since removed), 100 records | citation/support checks | 0 % unsourced, 22 % weak | 0 % unsourced, 24 % weak | equal |
| **What-if** party positions, 40 real votes (backtest) | real recommendations | 65.0 % | 61.4 % | **both below the naive baseline (71.7 %)** ⁵ |
| **See more**, 30 records | citation check | 44 % unsourced | 53 % unsourced | 70B better; both high |
| **Consultations tagging**, 100 procedures | none (agreement 74 %) | 3 off-list topics | 18 off-list topics | 70B better; rule-fixable ⁶ |
| **Subject panel**, 20 records | none | — | — | same Wikipedia article in only 14 % |

**Speed, mean seconds per call.** Parsing 16.5 vs 5.7; audit 6.9 vs 2.4; source level 3.3 vs 0.9; Q&A 2.4 vs 0.8; what-if 10.1 vs 3.9; consultations 12.2 vs 4.7. Stapfer is the exception: 6.6 vs 13.8, because 8B writes long outputs.

## Notes

1. **Creator.** Where the two disagree, 70B often names the publisher (*SRG SSR*) as creator although the record says *Produktion: DRS*. That is the error prompt v2 was meant to remove (quality report §9), and 8B follows the rule more literally.
2. **Stapfer failures.** At the pipeline's limit of 1,500 output tokens, 8B failed on 27 of 100 sheets.
   - **Cause 1:** it copies the long transcriptions into its evidence field.
   - **Cause 2:** on some sheets it degenerates into blank lines.
   - **Effect of a larger limit:** at 4,000 tokens, 19 of the 27 recover and 8 still fail. The accuracy figures above compare the 92 sheets both models parsed.
   - Concrete fixes: shorter evidence quotes, a repetition penalty, or constrained JSON decoding.
3. **Mechanical checks.** 8B misses most non-ISO dates (recall 0.18 vs 1.00) and packed role fields. The pipeline's final flags are *Apertus OR rule detector* (classify.py), so this does not change the published flags.
4. **Ask the archive.**
   - 70B set `insufficient` on 2 answerable questions. In both it gave a careful partial answer; for example, the Argentina record is an index of press articles, not the articles.
   - 8B wrote "the sources do not contain the number of visitors" for an unanswerable question but did not set the flag, so the page would present that refusal as an answer.
5. **What-if.** Given each party's recommendations on related votes, the naive baseline is "each party repeats its most frequent recommendation". Neither model beats it, so the what-if imagination should stay labelled as generated and not be presented as a forecast.
   - The models often answer with the evidence labels ("yes", "free vote") instead of the codes the prompt asks for.
   - `referendum.whatif` currently drops such answers. The evaluation maps them to codes.
6. **Off-list topics.** 8B's off-list topics are near-synonyms: *labor* for *labour*, *tax* for *public finance & tax*, *public health* for *health*. A synonym map would fix most of them.

## What this means for deployment

- **8B is enough** for the core parsing pass and Ask the archive. These are the features a reader uses on every record, and 8B is 2–3× faster on all of them.
- **70B is still worth it** for:
  - the source-level pass, where 8B misses most secondary sources;
  - long, messy transcriptions like the Stapfer sheets.
- **Rules close several gaps cheaply:**
  - mechanical detectors (already in place);
  - a topic synonym map;
  - setting `insufficient` when no sentence makes a claim;
  - mapping "yes/no/free vote" to codes in what-if.
- **Fine-tuning targets.** If 8B is fine-tuned later, there are two measurable targets with ready-made references:
  - source level, with the adjudicated set as the test;
  - compact JSON on long inputs, with Stapfer as the test.

## Limits

- Several references are small: 29 adjudicated levels, 24 questions and 20 subject panels. Differences of a few points on them are within noise.
- Parsing has no human gold standard on the 200 new records. The automatic checks verify form and consistency with the record, not full correctness. The 25-record manual review (quality report §3, §9) remains the only human judgement and was done on 70B output.
- Temperature is low but not zero for some features (0.1–0.3), so single runs vary slightly.
