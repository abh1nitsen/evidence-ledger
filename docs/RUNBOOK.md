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

`review` is a durable output decision. Inspect issues and source spans, compare against the original invoice, and resolve outside this prototype. The app does not persist human edits or approvals and has no payment integration. Use the JSON download as an extraction record, not as an authorization record.

## Reset and backups

For a fresh experiment, select a new database path instead of deleting working state. For archival backups, stop the writer and copy the database plus its companion WAL/SHM files if present, or use SQLite's backup API. Never copy only the main file from an active WAL database and assume it contains every committed result. Store private documents/checkpoints/reports outside the public repository; encrypt and protect them according to your environment.
