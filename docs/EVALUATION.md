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

No live AI accuracy, latency, cost, confidence calibration, or production performance is claimed in this release.
