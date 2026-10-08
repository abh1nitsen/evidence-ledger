# Operations and recovery

## Interrupted batch

Reissue the same `run` command using the same `--db`. Completed jobs are reused; pending jobs are reclaimed. The OS releases the lock on process death. Leave the `.lock` file in place: the file's presence does not mean the lock is held. Deleting a lock file while a process owns it can undermine serialization on some platforms.

## Provider failures

Check credentials/account access, model compatibility, connectivity, and rate limits without pasting keys or document text into logs. Failed jobs stay failed until explicitly retried:

```sh
python -m docintel run --provider openai --model YOUR_MODEL --db runs/ai.sqlite --output runs/ai-report.json --retry-failed
```

Retries may incur additional remote cost. Authentication and malformed/refused responses stop at the provider boundary. The report stores `provider_failure`, not raw API errors. For a controlled diagnosis, run a synthetic fixture using a temporary input directory and fresh database.

## Corrupt, empty, binary, or oversized input

The file gets `failed / invalid_input`, and other documents continue. Fix the file, then rerun. Input failures are not cached. Groq mode supports JPEG/PNG/WebP directly when the vision extra is installed. PDFs/HEIC/TIFF require a separate conversion stage; changing an extension is insufficient.

For Groq `provider_http_429`, wait for the quota window to recover, then retry failed jobs. Requests already use bounded Retry-After delays. Image upload retries failed jobs when the user clicks Read receipt again. Cached successful image results are reused.

## Export failure or missing report

Fix output directory permissions/free disk space and rerun with the same database. Already committed results are reused. The UI shows an empty ledger if no report exists; run a batch first. Restarting the page reloads the current export.

## Concurrent process message

Only one batch owns a database. Stop the other writer or give the second process distinct database **and output** paths. The lock is nonblocking, so a competing writer fails early rather than claiming pending work.

## New model or policy

Different provider/model/prompt/schema identities create new jobs automatically. For code changes to baseline extraction or validation, bump the baseline revision or `VERSION`. Model aliases may change upstream without the name changing: choose fixed snapshots for audited experiments and use a fresh database after known alias changes.

## Manual review

`review` is a durable output decision. Inspect issues and source spans, compare against the original invoice, and save Accept/Reject/Edit decisions in the local review UI. The app persists human corrections separately from immutable machine proposals and has no payment integration. Use the JSON download as an extraction record, not as an authorization record.

## Reset and backups

For a fresh experiment, select a new database path instead of deleting working state. For archival backups, stop the writer and copy the database plus its companion WAL/SHM files if present, or use SQLite's backup API. Never copy only the main file from an active WAL database and assume it contains every committed result. Store private documents/checkpoints/reports outside the public repository; encrypt and protect them according to your environment.

## OCR and review recovery

Use `--ocr paddle` only after installing the optional OCR extra. Initial recognition downloads official model weights into `runs/ocr`; failures are explicit. For `ocr_timeout`, retry after checking CPU load; the worker deadline is 180 seconds. For `ocr_process_failed`, check the pinned runtime/model installation; choose Groq-only mode explicitly with no OCR flag if needed. OCR caches are keyed by content/configuration and verified against weight hashes.

Preserve both the image checkpoint database and its sibling `<stem>-reviews.sqlite` when keeping human review history. Re-upload identical bytes or select **Resume a saved reading** after restart. Re-extraction under a changed schema/provider configuration creates a distinct review identity. HTTP 409 means another decision changed the revision; reload and retry rather than overwriting it. Machine evidence and original suggestions are immutable; corrections live in the decision history. Exports flag effective arithmetic mismatches.

## Long receipts and item review

Each photo has its own checkpoint; a failed later photo does not erase earlier pages. Retry a failed photo when provider quota allows. If combination fails, use **Save page order** with the saved page readings. Resuming an unchanged ordered chain restores its decisions; changing order creates another combined snapshot. Original photo bytes are not retained server-side: **Attach photo** checks the matching original locally before showing it.

Do not auto-delete flagged overlaps: repeated purchases may be valid. Reject only confirmed duplicates. Item mismatches, unresolved discounts or a rejected discount target block item allocations. For prices already discounted, exclude a duplicate discount allocation or correct the purchase to the printed gross amount; compare the photo before deciding. A payment slip without a printed final total stays outside spending. See [item and chain rules](ITEMS_AND_PAGES.md).

Groq HTTP 429 is checkpointed with a sanitized error code. The UI retries failed uploads explicitly; batch retries require `--retry-failed`. A daily allowance may need much longer than the bounded Retry-After cap. New credentials are supplied through `GROQ_API_KEY`; keys are never part of cache identity, so successful source/configuration checkpoints remain reusable. No automatic credential rotation is implemented.
