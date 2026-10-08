# Model and system card

**System:** Evidence Ledger v0.1.0. **Domain:** invoice intake. **Owner:** Abhinit Sen. **Task:** seven-field structured extraction with evidence and review routing.

## Methods

The default baseline uses anchored case-insensitive label rules. It is not ML and has no trained weights. The optional AI provider calls a user-selected OpenAI model through structured Responses output. The model is not fine-tuned here; the project supplies a prompt and schema, then independently validates the response.

AI mode requires explicit CLI selection and `OPENAI_API_KEY`. It sends full input text to the provider. Model choice is recorded in the configuration fingerprint, not presented as a benchmark winner. Fixed model snapshots are preferred for experiments when accessible.

## Intended use

Portfolio demonstrations, regression testing of extraction contracts, and experimentation with text invoices. Useful outputs are normalized values, source quotes/spans, content fingerprints, and review issues.

## Decision semantics

`validated` means implemented schema/evidence/policy checks passed. `review` means a human must inspect missing or conflicting information. Neither verifies supplier identity, authenticity, bank details, tax legality, or suitability for payment. There is no automated payment or approval action.

## Limitations

No OCR/PDF/image ingestion, line items, multi-invoice splitting, tax-rate reasoning, discount handling, multi-currency conversion, credit-note support, reviewer persistence, calibrated confidence, or distributed processing. Quote occurrence and label binding cannot prove semantic correctness in every layout. Exact repeated values intentionally reduce coverage. AI prompt injection is not solved by instruction-like text matching or schema output.

The baseline only supports declared labels and constrained date/amount formats. The AI provider may interpret broader prose, but unlabelled source binding requires review. The schema and policy favor abstention over inferred values.

## Evidence

See the synthetic-only results in `EVALUATION.md` and actual verification in `VALIDATION.md`. Live AI behavior was not tested using a real API key during initial development. There is no trained-model artifact, no real invoice data, and no claim of production readiness.
