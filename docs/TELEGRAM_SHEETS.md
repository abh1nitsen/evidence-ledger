# Household photo → AI → shared Google Sheet

Version 0.9 adds a standalone Telegram worker. It is built and covered by mocked integration tests; live operation requires your own bot token, Google authorization and target spreadsheet. It does not require this chat to remain open. Google Drive in Codex can help manage the shared document, but its connection does not provide credentials to your separately running Python worker.

## What you need

1. Create a dedicated bot using `/newbot` in [@BotFather](https://t.me/BotFather). Save its token in a private `telegram_bot_token.txt` outside the repository. Never commit credentials.
2. Choose a new native Google Sheet in your Drive, named Household Purchases. The creation command below initializes it after Google authorization. Alternatively use an existing Sheet ID from `https://docs.google.com/spreadsheets/d/ID/edit`. Excel `.xlsx` in Drive is not a live Sheets API target; download the app's Excel export when needed.
3. For unattended Python access, enable Google Sheets API in your Google Cloud project and create an OAuth **Desktop app** client. Save the downloaded client JSON privately as `google_client_secret.json`. Set up the consent screen/test users following [Google's Python quickstart](https://developers.google.com/workspace/sheets/api/quickstart/python). Testing-mode authorizations may expire and require login again; choose an appropriate consent configuration for long-term use.
4. Install the optional runtime and authorize interactively:

```powershell
python -m pip install -e ".[vision,cloud]"
python -m docintel google-login --client C:/private/.secrets/google_client_secret.json --token C:/private/.secrets/google_token.json
```

Google's authorization grants the Sheets scope, which can access your spreadsheets. The worker only uses the configured spreadsheet ID. Review Google's consent screen yourself. OAuth tokens and client files remain outside the repo.

## Prepare and create the ledger without Telegram

Copy `config/telegram.example.json` to a private configuration file and set your absolute credential paths. An empty `spreadsheet_id` requests a new sheet. You can check setup offline and create the new sheet after Google sign-in, even before creating your Telegram bot:

```powershell
python -m docintel household-status --config C:/private/.secrets/telegram.private.json
python -m docintel google-create --config C:/private/.secrets/telegram.private.json
```

The status command prints presence/readiness states, never credential values, and does not claim to verify account access. The create command makes Household Purchases with three owned tabs and saves the new ID atomically in your private config. It creates an empty ledger; historical receipt records are populated when the worker synchronizes. Running it again with a saved ID reuses that ID without creating another Sheet.

If the request times out or the process crashes before saving the returned ID, the config records a pending/uncertain creation. A repeat command refuses to create another sheet blindly. Check Drive for Household Purchases; if it exists, copy its ID into `spreadsheet_id` and set `sheet_creation_state` to `created`. Only after verifying that nothing was created should you clear the state and retry. This guard prevents accidental duplicates; it cannot make Google's create request exactly-once. Share the created Sheet with household members using Drive's normal sharing controls.

## Enrol household members

Copy `config/telegram.example.json` to a private configuration file, such as `C:/private/.secrets/telegram.json`. Set absolute credential paths and the spreadsheet ID. Leave `members` empty initially. Run from the repository root:

```powershell
python -m docintel telegram --config C:/private/.secrets/telegram.json
```

Each member opens the bot and sends `/start`. The bot replies with their numeric Telegram user ID. Stop the worker with Ctrl+C, add those IDs to the private config, and restart:

```json
"members": {"123456789": "Household member A", "987654321": "Household member B"}
```

Names are display labels; access is checked against numeric Telegram IDs. Unknown users' photos are not downloaded or sent to Groq. Only private chats are supported. Use a dedicated bot with no webhook configured; the worker refuses to replace an existing webhook. Each bot must have its own state directory.

## Daily use and review

Send one receipt photo, or send it as a JPEG/PNG/WebP file under 8 MB. The worker saves the reading locally, assigns the registered buyer, and sends a summary with review buttons. It then synchronizes three generated tabs in your shared Sheet:

Send `/status` to check whether the shared Sheet matches the current local reviews, is waiting for an update, or needs a retry.

- **EL Receipts:** when, who, merchant, proposed total, confirmed total, status, reason and the specific fields still needing review.
- **EL Purchases:** what was bought, quantity, price, grouping, review state and original printed description.
- **EL Overview:** confirmed spending, separately by currency.

Every image reading starts with **Needs review**. The current scores are uncalibrated evidence scores; they do not justify auto-approval. Accept or Reject individual fields and items using the bot buttons. `/review RECEIPT_ID` restores the current reading; `/edit RECEIPT_ID total 12.34` corrects a field. Date edits use `YYYY-MM-DD`. The laptop app still provides complete item edits, spending groups, source-photo comparison and page chaining. Keep its server on the same reviews database specified in the config.

Only reviewed, reconciled purchases contribute to confirmed totals. A confirmed amount with an unconfirmed date remains explicitly marked, and is not silently assigned to a month. There is no currency conversion. For a receipt without item detail, use the browser to save its spending group.

Generated tabs are app-owned snapshots: edits inside them are overwritten on the next sync. Review receipts through the bot or app. Other tabs remain yours; use a Notes tab for household notes. The worker refuses to overwrite an existing tab with the same name unless its A1 ownership marker matches. All three generated tables update in a single [atomic Sheets batch](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate), including clearing obsolete rows. Strings are literal values, so printed text cannot become spreadsheet formulas.

## Graceful failures and resumption

- An unrelated image, unknown document or unreadable photo gets an explanation and creates no purchase rows. Model classification can be wrong; retake/reupload a false rejection. This gate is conservative, not a guarantee of perfect image recognition.
- A blurry but still recognized receipt may be saved for review; missing values are not invented.
- Exact duplicate image bytes do not create another receipt or reveal someone else's reading through Telegram. Different photographs of the same bill still need the existing possible-duplicate review.
- Telegram albums are explicitly declined in this version. For long receipts, use the browser's Add next page and saved page order. This avoids treating album pages as separate purchases.
- Download/model failures remain in a durable SQLite inbox with capped retry backoff. After the first failure, the bot sends a delayed-reading notice. Restarting resumes requests without reacknowledging lost work. Original downloads and model checkpoints are private under `runs/telegram`.
- Google failures leave the local receipt intact and the cloud sync dirty. Sync retries after at least 60 seconds; a failed sync does not claim that the shared Sheet is current.
- Notifications are at-least-once: a crash after Telegram delivered a reply but before the local commit can repeat that reply. Purchase storage remains deduplicated.
- The laptop, internet connection and worker must run for processing. Telegram retains undelivered updates for no longer than 24 hours; do not rely on it as indefinite storage while the laptop is off. Once received locally, the durable queue survives longer outages.
- Rejected/invalid originals are kept in the private intake directory for audit/retry; apply your own retention policy. Photos travel through Telegram and recognized receipt photos are sent to Groq. They are not stored in the public repository or Google Sheet.

The Telegram worker also maintains `purchase-ledger.xlsx` beside the configured reviews database, even with no Google Sheet and no browser server running. `/status` reports local Excel readiness as well as cloud status. If Excel is holding the workbook open and blocks replacement, close it and send `/retry_excel`; the last good file stays intact and saved receipts remain available. The export requires the same Node/artifact-tool runtime as the browser's Excel export. Once Google is configured, local Excel and Google Sheets remain projections of the same saved reviews; cloud failures do not stop local export.

## Reproduce the checks

```powershell
python -m unittest discover -s tests -v
python -m docintel evaluate
python -m docintel telegram --config C:/private/.secrets/telegram.json --once
```

The last command performs one live polling/processing/sync pass using your configured accounts. Offline tests use authored receipt data and fake transports, covering admission, restart/deduplication, ownership, stale buttons, retry notices, cloud retry, literal cells and refusal to overwrite unowned tabs. They do not establish live account permissions or real-world document-classification accuracy.
