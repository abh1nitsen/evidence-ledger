# Receipt reader walkthrough

1. Choose a JPEG, PNG or WebP photo under 8 MB. Previewing does not send it externally.
2. Click **Read receipt**. The photo is normalized and sent to Groq. The button and status indicate that reading is in progress; input changes are disabled during the request.
3. Read the merchant, date and total summary, then inspect the seven fields. Missing fields show **Not confirmed**, and reasons use plain language. Review is mandatory for photos because evidence is grounded in a model transcription rather than independently verified image pixels.
4. Open **Enlarge photo** to compare print. **Show supporting text** reveals the exact quote. **Locate in reading** opens the full transcription and highlights its characters; repeated matches cycle with each click.
5. Download the extraction JSON. A reused checkpoint is clearly identified and does not make a new model call. Failed requests show a retry message, not an empty success.

Amounts with supported leading currency markers are normalized separately from currency. A bare dollar symbol does not establish USD or SGD. Numeric dates are normalized only when their day/month ordering is unambiguous. Rejected suggestions are shown explicitly as unaccepted and never substituted into the accepted field. These checks do not authorize payment.

The offline text demo is collapsed by default. The developer batch ledger is a separate synthetic report and does not count the uploaded receipt. Private photos, transcripts and results belong in ignored `runs/` storage, never public fixtures or documentation screenshots.
