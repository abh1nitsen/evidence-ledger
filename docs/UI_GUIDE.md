# Document reader walkthrough

1. Choose a JPEG, PNG or WebP image under 8 MB. Previewing stays local. In OCR mode, the photo is read locally and a normalized copy plus OCR text is sent to Groq when you click **Read receipt**.
2. Inspect document type and the ten common/optional fields. A payment slip can lack tax or final total. A BASE amount is kept separate; missing print stays absent rather than being inferred.
3. Low-scoring candidates remain visible. Scores are uncalibrated evidence support, not correctness probabilities; the configurable default threshold is 85/100. Conflicts and century assumptions always need review.
4. **Evidence & checks** shows the quote, reasons and independent OCR photo crops where available. **Locate in reading** highlights source characters. **Enlarge photo** opens the whole original for comparison. OCR and AI can both misread print.
5. **Accept** takes the normalized proposal; **Reject** leaves the effective value blank; **Edit** saves a correction. Two-digit years require explicit confirmation, and edited dates use a four-digit ISO year. Missing candidates have no Accept button.
6. Decisions save automatically. **Resume a saved reading** restores them after restart; re-upload the original to inspect photo crops. Original suggestions remain unchanged. Concurrent stale decisions reload the latest revision and ask you to retry.
7. Download JSON with original machine fields, scores, `effective_fields` and review history. Human-reviewed arithmetic mismatches remain flagged. Review does not authorize payment.

A bare $ does not confirm currency; S$ is an explicit SGD marker, although OCR may misread it. Such cases remain visible suggestions requiring photo inspection. Failed reading or failed saving shows an error; existing decisions remain stored.

The offline text demo and developer sample batch ledger are secondary views. The ledger is separate from your uploaded image. Original private photos, transcripts, OCR caches and review histories do not belong in public Git fixtures or screenshots.

![Synthetic review controls with original evidence and correction](images/review-controls.jpg)
