# Validation record

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

OpenAI transport was mocked to verify the documented Responses request schema, timeout, retries, authentication-failure handling, refusal, incomplete output and cache identity. **No live paid model call was made**, and no AI quality result is implied by the offline score.

The CI workflow independently runs tests, offline evaluation and resume commands on Ubuntu/Windows with Python 3.11/3.12. Its GitHub status is separate from this local record. Clean-clone and CI outcomes are verified after publication and reported in the delivery message.

These checks exercise the implementation under specified faults; they do not guarantee survival of all hardware/filesystem failures, complete injection resistance, authentic invoices, or correctness across real supplier layouts.
