# Evaluation protocol

The initial benchmark is an **authored synthetic regression dataset**, not an independent real-world test set. Sixteen documents cover clean labels, aliases, thousands separators, case/Unicode, missing fields, duplicate fields, invalid dates, locale formats, negative amounts, arithmetic conflicts, instruction-like content, and unsupported prose.

Run `python -m docintel evaluate --output runs/evaluation.json` for the baseline. The committed report is `reports/baseline-evaluation.json`. Gold labels are authored in `data/gold.json` and are not computed at runtime from extraction output.

## Metrics

- **Field exact match:** normalized predicted values equal gold, including expected nulls, across seven fields per document.
- **Decision accuracy:** `validated`/`review` equals the fixture's expected policy decision.
- **Unsafe validations:** gold-review documents incorrectly marked validated.
- **Extraction failures:** documents where the provider/validation could not produce a result. These score zero field matches, never disappear from the denominator.
- **Slices:** field-match numerator and denominator by fixture category.

Baseline result: 112/112 field matches, 16/16 decisions, zero unsafe validations and zero extraction failures. Five cases are expected to validate; eleven are expected to require review. Expected null matches reward abstention; the score must not be described as 100% document extraction coverage.

## Testing versus model evaluation

Unit/integration tests verify source evidence, rejected hallucinations, semantic field swaps, Decimal arithmetic, schema errors, recovery, concurrency, export failures, input faults, and provider request/retry/refusal behavior. Mocked OpenAI transport tests verify the integration contract, not model quality or access. Real process termination and HTTP tests cover executable boundaries.

## Compare AI mode

Set `OPENAI_API_KEY`, choose a compatible model, then run:

```sh
python -m docintel evaluate --provider openai --model YOUR_MODEL --output runs/ai-evaluation.json
```

The synthetic evaluation gate is intentionally strict and may return exit code 2 even when AI extracts more prose fields than the baseline's expected nulls. Review case-level differences; this fixture gate encodes current conservative policy, not a universal AI-quality ranking. Use a separate broader gold set with provider-independent value labels for comparative research. Retain raw provider output securely if needed for analysis, not in public commits.

## Next credible evaluation

1. Obtain consented, de-identified supplier invoices with independently annotated text spans and field labels.
2. Split by supplier/layout, not random pages, to reduce template leakage.
3. Add separate slices for OCR corruption, multi-page text, credit notes, multilingual text, mixed currencies, and adversarial instructions.
4. Measure field precision/recall, abstention coverage, unsafe acceptance, document completeness, latency, and per-document cost. Do not infer calibrated confidence from a model's self-reported score.
5. Freeze prompt/policy/model configuration before evaluating a held-out set; publish uncertainty and failures alongside averages.

Version 0.2 adds a separately recorded live Groq image smoke test in `reports/groq-vision-smoke.json`. Run `python -m docintel evaluate --images --dataset data/images --provider groq` with the vision extra and a key. The clean render, simulated shadow/angle and blank-image results are scored against independently authored values. They are not real camera photos. The checkpointed batch output records failures and the summary never removes them from the denominator. No production accuracy, latency, cost or confidence-calibration result is claimed.

## Document-role and proposed-field comparison (0.4)

`data/documents/gold.json` specifies ten proposed fields and document type for three independently authored layouts. `scripts/benchmark_documents.py` runs Groq-only or PaddleOCR+Groq with separate checkpoints. Score printed proposals and expected absences separately, and include extraction failures. Proposed century dates can match this benchmark while still remaining unusable machine values until a human confirms them. The latest comparison reports document all cases, elapsed run times and limitations; they do not measure calibrated probability, merchant-disjoint real-photo generalisation, OCR superiority or repeated-run latency.

The next quality gate requires independently labelled camera images from many merchants, invoice/retail/payment-slip types, day/month/year conventions, currencies, missing fields, lighting and orientations. Keep private photos local and use consented/anonymized data for public benchmarks. Measure field correctness and amount-role errors, confidence precision versus coverage, and review workload. Split by merchant/layout and reserve a separate calibration set. No trained calibration model or universal threshold exists in this release.

## Number-format regression update (v2)

The current authored benchmark contains 17 documents. European `1.200,00` is now supported and its expected subtotal is 1200.00. The new `17_ambiguous_separator.txt` case uses `1.234`, which remains unsupported rather than guessing a decimal or thousands separator. This changes an explicit format policy, not a real-world accuracy estimate.
