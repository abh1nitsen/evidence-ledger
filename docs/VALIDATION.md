# Validation record

## Version 0.5 layout and receipt-level spend

Verified 8 October 2026: **86 automated tests passed**. Added transactional grouping/restoration/export, shared-revision conflicts, invalid tags/categories, reviewed-only totals, currency separation, date-review grouping, arithmetic exclusion and duplicate suppression tests. Browser verification saved a synthetic receipt category/tags, accepted its currency and total, observed the correct spending total, and restored the metadata. Responsive checks found no horizontal overflow in the panels/fields/selectors at 320, 390 and 1024 pixels, including a 192-character unbroken merchant name and expanded saved-reading controls. These browser viewport checks do not replace physical-phone tests. The rear-camera input is present; physical Android/iOS capture and external phone access remain untested. Synthetic-only desktop/mobile previews are in `docs/images/spending-layout.jpg` and `docs/images/spending-mobile.jpg`.


## Version 0.4 independent OCR and saved review

Verified on 8 October 2026 with Python 3.12.10, Pillow 12.3.0, PaddleOCR 3.7.0, PaddlePaddle 3.3.1 and PaddleX 3.7.2 on Windows CPU. **78 automated tests passed**, including labelled identifiers/currency markers, century confirmation, split date/time OCR lines, blank total versus base roles, OCR coordinate/score validation and timeout/no-fallback behavior, cache reuse, immutable originals, human arithmetic checks, optimistic review revisions, HTTP review/export and restoration. Core offline evaluation remains 112/112 fields and 16/16 expected decisions.

Both live Groq-only and PaddleOCR+Groq runs matched **22/22 printed-field proposals**, **8/8 absent fields**, and **3/3 document types** on the independently authored invoice, retail and payment-slip layouts. Reports are `reports/groq-document-diversity.json` and `reports/hybrid-document-diversity.json`, with synthetic-only batch details. Observed single-run elapsed time was 46.078 seconds and 50.516 seconds respectively, including preprocessing/provider time. The hybrid run reused independently cached OCR results; these are warm-cache observations, not a cold-start latency comparison. Both reports use the final `invoice-v2.0.2` rules and prompt. This small benchmark shows no accuracy advantage for either path and does not estimate production accuracy or latency. Confidence remains uncalibrated with a provisional threshold.

A private natural-light payment slip produced six proposed fields, including identifier, proposed century/date, transaction time, currency and base amount. Its blank TOTAL and absent tax remain unfilled. Independent OCR detected 54 regions; currency still needed review because the OCR did not preserve the literal S$ marker reliably. A second private retail photo produced seven proposals, including a previously discarded pre-tax amount and a separately normalized time; its bare dollar currency remains unconfirmed. These two cases are qualitative debugging, not a real-photo accuracy dataset. No private photo, identifiers, transcript, crops or screenshot is committed.

Browser verification exercised independent OCR crops, Accept/Reject/Edit on synthetic data, download of effective fields and original suggestions, and saved-reading recovery. The public screenshot uses synthetic data. Review status does not imply payment approval.


## Version 0.3 receipt usability

Verified 8 October 2026: **59 automated tests passed**. Added coverage for currency-prefixed receipt amounts, unambiguous numeric dates, repeated evidence with retained values, and separation of rejected suggestions. Offline evaluation remains 112/112 field matches and 16/16 expected decisions. A fresh live Groq run of all four synthetic image fixtures matched 28/28 fields and 4/4 review decisions with zero extraction failures. The published smoke reports now correspond to schema `invoice-v1.2`.

Browser checks covered the explicit choose/read/check workflow, request progress, enlarged photo, repeated total evidence highlighting, JSON attachment download and saved-result reuse. One privately supplied natural-light retail receipt yielded five accepted fields; the currency abstained and the pre-tax suggestion was rejected because it was missing from the model transcription. The model also flagged multiple documents despite the single receipt: quality diagnostics are model suggestions requiring human inspection. This single case is qualitative debugging, not an accuracy benchmark. Its photo, transcript, identifiers and screenshots are excluded from the repository. The public UI screenshot uses an authored synthetic fixture.


## Version 0.2 image extension

Verified on 8 October 2026 with Python 3.12.10 and Pillow 12.3.0. The full suite now includes **56 automated tests**, covering image limits/format, EXIF orientation/metadata removal, mandatory image review, output schema, upload checkpoint reuse, provider failure handling, HTTP JSON attachments and bounded Retry-After delays alongside the original recovery tests.

Browser verification exercised local image preview, live Groq extraction, exact tax selection in the model transcript (`96.00`), checkpoint reuse after a server restart, and a successful HTTP attachment download to `extraction.json`. The saved image in `docs/images/photo-prototype.jpg` shows the photo and resulting human-review decision. Download response routes hold at most 16 opaque-token exports in server memory and expire on eviction/restart; regenerate extraction to obtain a new download link.

The Groq key and default model were verified through a live model-list request. Live Groq image extraction matched **28/28 expected field values**, **4/4 review decisions**, and produced **zero extraction failures or unsafe validations** on the final synthetic smoke run. This included a clean render, simulated shadow, simulated angle and blank image. See `reports/groq-vision-smoke.json` and its synthetic-only batch detail. An initial smoke run hit HTTP 429; bounded Retry-After handling was added and tested before the final run. These fixtures are generated images, not actual natural-light photos; no real-photo accuracy claim follows.

Image extraction uses JSON object mode with local schema checks. Source quotes refer to generated transcription; all image results require human review. The earlier offline baseline remains at 112/112 field matches and 16/16 expected decisions. OpenAI remains mock-tested.

## Initial version 0.1 verification

Development verification date: **8 October 2026**. Local environment: Windows, Python 3.12.10, Git 2.53.0.

## Verified locally

- **40 automated tests passed** using `python -m unittest discover -s tests -v`.
- Offline synthetic evaluation: **112/112 fields**, **16/16 policy decisions**, **0 unsafe validations**, **0 extraction failures**.
- Fresh batch demo: processed 2 documents with 14 remaining; resume processed 14 and skipped 2; repeated run processed 0 and skipped 16.
- Abrupt child-process death with `os._exit(73)` after extraction left a pending checkpoint. The next run acquired the released OS lock, reclaimed the job, and completed it on attempt 2.
- Export failure preserved committed extraction; rerun reconstructed the report without repeating extraction.
- HTTP integration tests exercised valid extraction, rejected cross-origin writes, invalid input, known-only file serving, and security headers.
- Browser checks verified complete extraction, exact tax highlighting (`96.00`), missing currency abstention, arithmetic review, and instruction-containing source review.
- The saved UI image in `docs/images/prototype.jpg` shows the arithmetic-mismatch result and the synthetic batch ledger.

## Scope of evidence

OpenAI transport was mocked to verify the documented Responses request schema, timeout, retries, authentication-failure handling, refusal, incomplete output and cache identity. No live model call was made for the initial version 0.1, and no AI quality result is implied by the offline score. Version 0.2 Groq verification is recorded separately above.

The CI workflow independently runs tests, offline evaluation and resume commands on Ubuntu/Windows with Python 3.11/3.12. Its GitHub status is separate from this local record. Clean-clone and CI outcomes are verified after publication and reported in the delivery message.

These checks exercise the implementation under specified faults; they do not guarantee survival of all hardware/filesystem failures, complete injection resistance, authentic invoices, or correctness across real supplier layouts.
