# Local household Excel ledger

Choose a household member, take/upload a receipt photo, and click **Read receipt**. The saved extraction automatically updates one local workbook. Review and correct the reading in the app. Open **Spending → Download household Excel** when the update finishes.

The workbook contains:

- **Overview**: captured receipt/item counts and confirmed spending, separately for each currency.
- **Receipts**: buyer, purchase date, merchant, receipt number, read total, confirmed total, date review, status and next step.
- **Purchases**: readable item, category, quantity, unit price, current line cost, confirmed line cost, currency, line type, review status, printed description/code and photo number.

Existing receipts use **Unassigned**. Open a saved receipt, enter **Bought by**, and click **Save member**. Names are self-declared metadata, not authenticated accounts. The capture name is remembered only in this browser. Re-uploading the same receipt preserves its existing buyer; change ownership explicitly in the saved receipt.

## Data rules

Pending readings are persisted immediately and labelled. Confirmed spending uses the same conservative reconciliation rules as the app. A reviewed line correction remains visible even while other lines need review. Rejected lines retain their printed description, with no current or confirmed cost. Payment lines do not count as an additional purchase. Discounts stay negative. A printed line amount is never multiplied by quantity again. Do not sum Purchases and Receipts together. Date review is explicit; an unconfirmed date is not a verified purchase date.

The workbook contains no original photos. Receipt and line keys allow tracing each row back to saved reviews. Source-equivalent extraction versions and component images in a receipt chain do not create extra workbook rows. Suspected duplicates photographed separately remain visible with an exclusion status. Photos from a chain inherit the buyer only when all pages have the same assigned member; mixed or unassigned pages require assigning the combined receipt.

The workbook is an app-managed projection. **Make corrections in the app. Manual workbook edits will be replaced on the next update.** Do not use the workbook as a second input database.

## Runtime and replication

The Python extraction, review and spending app still runs with its documented dependencies. Excel export additionally requires **Node.js and a separately available `@oai/artifact-tool` runtime**. This prototype uses the Codex bundled runtime on the development computer. It is not vendored or installed by `pip`, and these instructions do not assume that package is available from the public npm registry. A plain Git clone does not by itself supply the Excel renderer. The app keeps saving receipts if the renderer is absent, and shows **Retry Excel update**.

The app discovers the standard Codex bundle under the current user's `.cache/codex-runtimes/codex-primary-runtime/dependencies/node`. For another available runtime, set:

```powershell
$env:LEDGER_NODE = 'C:\path\to\node.exe'
$env:LEDGER_ARTIFACT_MODULES = 'C:\path\to\node_modules'
python -m docintel serve --port 8767
```

`LEDGER_ARTIFACT_MODULES` is a `node_modules` directory containing `@oai/artifact-tool` (tested with the bundled 2.8.58+ API). The supplied renderer uses its public API. It does not inspect or modify installed package internals.

By default, the live workbook is **`runs/purchase-ledger.xlsx`**, beside `runs/uploads-reviews.sqlite`. A custom `--image-db` puts both files in that database's parent directory. Only one ledger per parent directory is supported; use separate directories for isolated sessions. The **download** is a snapshot; reopen/download again to see later updates.

Rebuild or retry without another model request:

```sh
python -m docintel ledger --reviews runs/uploads-reviews.sqlite
```

All workbook inputs come from local saved reviews. Excel rendering sends no receipts to an external service. Photograph extraction still uses the configured Groq service as described in the image documentation.

## Recovery

SQLite commits the reading before exporting. Database triggers record a dirty generation after capture, review, grouping or member changes. One worker rebuilds the workbook rather than appending rows. It exports to a unique temporary file, verifies totals, flushes file content and records its checksum, then atomically replaces the current workbook. A change arriving during export causes that stale export to be discarded. An OS-held writer lock prevents competing exporters using the same workbook. Unique staging paths isolate a surviving renderer child from a restarted export. Assigning a member does not replace a more thoroughly reviewed extraction version.

After a crash, a restart resumes dirty work. If Excel locks the destination, the previous valid file remains in place and the pending reading stays in SQLite. Close Excel and click **Retry Excel update**. The download control appears only for the current generation. A missing or damaged workbook is detected and rebuilt from the database. Missing runtime/rendering failures use the same retry flow; configure the runtime before retrying. There is no silent conversion of missing values to zero.

Back up the review database and checkpoint database while the server is stopped. Generated Excel can be rebuilt. Treat the workbook and backups as private household purchase data; generated files in `runs/` are excluded from Git.

## Phone and sharing boundary

This release is local to one computer. Household names allow recording different buyers, but there is no sign-in, remote phone endpoint, shared drive or cloud workbook connection. A phone's camera upload becomes useful once an authenticated reachable deployment is added. Do not expose this loopback prototype directly to the internet. Sharing and access controls are a separate next step, as requested.

## Verification

```sh
python -m unittest discover -s tests -v
python -m docintel evaluate
```

Ledger tests cover pending/confirmed costs, negative discounts, payment exclusion, corrected amounts, Unicode member names, re-upload ownership, stale revisions, restart recovery, locked-file retries, stale exports, missing files and download freshness. Cross-platform CI verifies Python logic with an injected test renderer. Actual XLSX generation, typed numbers/dates, formulas, file structure and all three rendered sheet layouts were additionally checked locally with the bundled artifact runtime. CI does not claim to exercise that separately supplied runtime.
