# Item interpretation and long-receipt chains

## Reproduce

Install the vision extra and configure `GROQ_API_KEY` as described in README, then run `python -m docintel serve`. Choose a JPEG/PNG/WebP and click **Read receipt**. To test without an API key, run `python -m unittest discover -s tests -v`: authored fixtures exercise item review, reconciliation, page chains, restart, exports and stale writes. Offline text examples do not perform item recognition.

## Item contract

Each vision row requires description, readable label, printed code, quantity, unit price, printed line amount, source quote, amount quote, category, kind and optional zero-based discount target. Null is allowed for absent text/numbers. Kinds are product, service, discount, tax, payment and fee. Leaf categories are defined in `docintel/items.py`. Codes remain strings to retain leading zeros. Raw descriptions are never replaced by inferred labels.

Limit: 100 proposed rows per image, 300 per combined receipt. Names are bounded; numbers use Decimal and strict formats. Schema or oversized output fails explicitly. Unsupported/ungrounded values carry visible issues. Scores measure uncalibrated evidence support, not correctness probability. A literal OCR/transcription match cannot verify a category, brand, SKU or authenticity.

Accept preserves the proposed normalized item, Reject excludes it and Edit saves an explicit correction. Originals and append-only decision history remain separate. Review writes are transactional, share the document revision with field/group changes and reject stale updates with HTTP 409. Existing older extraction versions retain their reviews; changed prompts/schema create new proposals without copying approvals.

## Reconciliation

Review every line, including taxes, discounts and payments. Printed line amount already represents the line: never multiply it by quantity again. Payments/settlements are excluded from purchases. Discounts reduce the linked purchase category; a basket discount needs an explicitly reviewed category. If the receipt already prints discounted net line amounts, do not deduct the discount a second time: explicitly exclude its duplicate allocation row while retaining the audit evidence, or correct purchase amounts to the printed gross figures and keep the discount. Compare with the photo; the prototype does not automatically infer gross versus net price columns. Tax is not added when net lines already equal the final total. Otherwise, explicit tax lines (or reviewed header tax when no line tax exists) are added once only if the resulting sum exactly equals total.

A missing total is not replaced with BASE or balance. Missing amounts, negative category allocations, unresolved discounts and mismatches block item spending. Currency is separate and cannot be inferred from a bare dollar sign. Total/currency must be human-reviewed before aggregation; dates without review remain outside month groups. Currencies remain separate. Exact reconciliation is a check, not proof of authentic purchases or a complete transcript.

## Chainage workflow

1. Photograph the top of a long receipt, then proceed downward with a small readable overlap.
2. Read the first image. Choose **Add next page**, select the next image and read it. Repeat for up to ten pages.
3. Verify page order; use arrows and **Save page order** to correct it. **Remove** detaches a page, preserving its original reading.
4. Inspect header conflicts and possible overlap rows. Reject a duplicate only after comparing the two photos; identical legitimate purchases must remain.
5. Confirm the printed final total and review every retained item before using spending.

The combined snapshot records ordered page IDs, original image hashes, image/OCR metadata and per-page transcripts. Fields and items retain source-page references; transcription spans are adjusted into the combined text. The chain identity depends on order. Reordering creates a new review snapshot rather than changing previous audit evidence. Restoring the same ordered chain restores its saved decisions.

Repeated identical photo bytes or repeated page IDs are rejected. Nested chains are rejected. Different merchants/identifiers/amounts can produce header conflicts requiring correction; the application does not automatically verify physical continuity or infer missing pages. Exact row matches across pages are only warnings, never automatic deletion. OCR errors or differently cropped descriptions can hide overlaps. Review totals and continuity manually.

## Failure and recovery

Each photo is independently checkpointed. A failed later page leaves completed pages saved. Retry the failed image; successful bytes/configuration reuse checkpoints. If combining fails, use **Save page order** to retry with the saved page readings. SQLite is authoritative; restart restores decisions and atomic JSON exports include provenance and histories. A remote response lost before commit may incur another API call. No exactly-once billing guarantee is claimed.

Original photos are not retained by the server. A restored chain offers **Attach photo** per page. Choose the identical original file: its hash is checked locally before displaying it, without another API call or changing saved review decisions. Keep private photos, transcripts, caches and reviews outside public Git; runtime files under `runs/` are ignored. The CLI batch treats each file as a separate document; page chaining is an explicit local UI/API operation, not filename inference.

## API

`POST /api/pages` accepts only `document_ids`, an ordered list of two to ten saved single-image IDs. `POST /api/item-review` accepts document_id, item_id, action, values and revision. Edited values contain label, category, kind, code, quantity, unit_price, amount and discount_for. Both endpoints enforce origin/body/schema limits. `GET /api/review/<id>` restores the latest reviewed snapshot. `/api/report` remains a developer diagnostic endpoint; it is no longer displayed in the receipt workflow.
