# OCR, field scores and durable review

## Pipeline

1. Bound and normalize the upload (original limit 8 MB/20 MP; normalized longest edge 2000).
2. Optionally run pinned PP-OCRv5 mobile detection and recognition on CPU. The worker is terminated on a 180-second timeout; no Groq/OpenAI key is passed to it. First-run weight downloads require network. Orientation follows EXIF; arbitrary perspective/rotation correction and document unwarping are not enabled in this small CPU configuration.
3. Validate OCR text/scores/rectangles, cache it atomically, and provide it with the image to Groq for field-role interpretation. Validation grounds hybrid output in the independent OCR text. It does not replace missing OCR text with a model transcription.
4. Classify invoice, retail receipt, payment slip or unknown. Preserve optional transaction time, base amount and tip, and distinguish absence from an uncertain candidate. Tax and final total can be absent on a payment slip.
5. Show proposals, evidence and image crops. Source quotes that cannot be located in OCR stay unverified; no fabricated crop is drawn for them.
6. Record review events in SQLite and export effective human decisions alongside the immutable machine result.

## Scores

The score is deliberately called an **uncalibrated evidence score**. It is not the probability that the field is correct and not the OCR recognition score alone.

| Component | Contribution |
|---|---:|
| Literal quote exists in grounding text | 0.45 |
| Candidate can be normalized to a supported format | 0.15 |
| Label checks support the field role | 0.15 |
| Independent OCR supports the quote | 0.20 × minimum recognition score of matching regions |

Missing candidates score zero. Conflicting/missing evidence, label conflicts, duplicate labels, arithmetic mismatch and two-digit-century assumptions cap the score at 0.49 and force review. Repeated evidence remains inspectable. Exact text recognition does not establish semantic field correctness. Whole-line recognition scores and heuristics can be wrong; a high score still requires image verification. Groq-only extraction has no independent OCR component.

The provisional default threshold is 0.85, configurable with `--review-threshold` between 0 and 1. It highlights fields; it never auto-approves photos. Every supported candidate has Accept/Reject/Edit, including high-scoring fields. Absent candidates have Reject/Edit, with no meaningless Accept button. A calibrated threshold requires an independently labelled corpus, merchant/layout-disjoint holdouts and per-field precision/coverage measurements. This release does not claim calibration.

## Decisions and recovery

Accept takes the displayed normalized proposal. Reject explicitly leaves the effective field null. Edit validates a user correction; edited dates require a four-digit ISO year. Two-digit-date acceptance explicitly confirms the proposed 20xx century. No timezone is inferred.

Machine values, raw candidates, quotes, OCR regions and scores remain unchanged. Events record action, corrected value, timestamp and revision. `effective_fields` reflects the most recent event per field; `fields[].human_review` and `review.history` identify its origin. A reviewed document is not payment-approved. This local prototype has no authenticated reviewer identity and is not a multi-user approval service.

A review belongs to the document/configuration checkpoint identity. A new extraction revision does not silently inherit approvals from an older configuration. Server restarts preserve decisions. The UI's saved-reading selector restores the latest reading per source image; originals are not stored, so re-upload to inspect crops. Image checkpoints, review records, OCR caches and exports are private ignored runtime files. Keep SQLite/WAL data when preserving history. Download attachment links expire on server restart; restoring a reading creates a new link.

The API requires same-origin POSTs, checks input shape and uses optimistic revisions. Stale updates return 409 and reload the current review. Failed updates do not erase prior decisions. OCR failures produce explicit codes (`ocr_not_installed`, `ocr_timeout`, `ocr_process_failed`, `ocr_invalid_output`); choose Groq-only mode explicitly rather than relying on a hidden fallback.

## Reusable models

The current optional OCR implementation uses PaddleOCR 3.7.0, PaddlePaddle 3.3.1 and PaddleX 3.7.2 with explicit PP-OCRv5 mobile checkpoints, recorded weight hashes and CPU settings. [Official pipeline documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md) documents text locations and recognition scores. [PP-StructureV3](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md) is a future layout/table comparison, not part of the current runtime.

[Donut CORD](https://huggingface.co/naver-clova-ix/donut-base-finetuned-cord-v2) is a receipt-trained alternative; it was researched but not benchmarked in this release. [LayoutLMv3](https://huggingface.co/microsoft/layoutlmv3-base) needs task fine-tuning and its listed noncommercial license makes it unsuitable as the default unrestricted reusable extractor. No universal-format accuracy claim follows from using pretrained weights.
