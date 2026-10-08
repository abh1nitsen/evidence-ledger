# Model and system card

**System:** Evidence Ledger v0.4.0. **Domain:** invoice intake. **Owner:** Abhinit Sen. **Task:** document-aware structured extraction from text/photos with evidence and review routing.

## Methods

The default baseline uses anchored case-insensitive label rules. It is not ML and has no trained weights. Optional providers use OpenAI structured Responses for text or Groq JSON-mode completions for text/images. No model is fine-tuned here; the project supplies prompts and schemas, then independently validates output.

AI batch mode requires explicit provider selection and the matching environment key. Groq photo extraction is also available from the upload UI when the server has `GROQ_API_KEY` and Pillow. Inputs are sent to the selected provider. Model choice is recorded in the configuration fingerprint, not presented as a benchmark winner. Fixed model snapshots are preferred for experiments when accessible.

## Intended use

Portfolio demonstrations, regression testing of extraction contracts, and experimentation with text invoices. Useful outputs are normalized values, source quotes/spans, content fingerprints, and review issues.

## Decision semantics

`validated` means implemented schema/evidence/policy checks passed. `review` means a human must inspect missing or conflicting information. Neither verifies supplier identity, authenticity, bank details, tax legality, or suitability for payment. There is no automated payment or approval action.

## Limitations

Groq vision supports JPEG/PNG/WebP transcription and extraction. No PDF/HEIC ingestion, line items, multi-invoice splitting, tax-rate reasoning, discount handling, multi-currency conversion, credit-note support, authenticated multi-user approval, calibrated confidence, or distributed processing. Image quotes ground to model transcription in Groq-only mode or independent OCR text in hybrid mode. OCR boxes locate image regions but do not prove recognition correctness; every photo requires review. Quote occurrence and label binding cannot prove semantic correctness in every layout. Exact repeated evidence keeps the supported value and triggers review. AI prompt injection is not solved by instruction-like text matching or schema output.

The baseline only supports declared labels and constrained date/amount formats. The AI provider may interpret broader prose, but unlabelled source binding requires review. The schema and policy favor abstention over inferred values.

## Evidence

See synthetic-only results in `EVALUATION.md` and verification in `VALIDATION.md`. OpenAI text behavior remains mock-tested. Groq vision is exercised with a real key on a small synthetic smoke set; this does not establish accuracy on natural-light camera photos. There is no trained-model artifact, no real invoice data, and no claim of production readiness.

Version 0.4 adds optional independently grounded PaddleOCR, ten proposed fields, document roles and human decisions. Scores are transparent heuristics with a provisional threshold, not calibrated probabilities. Human acceptance is not machine validation or payment approval. No evaluated replacement model superiority is claimed from a three-layout synthetic regression.
