# Validation record

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
