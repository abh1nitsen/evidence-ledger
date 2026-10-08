# Evidence Ledger

**Document intelligence for accounts payable: structured invoice extraction with inspectable evidence and resumable processing.**

Built by [Abhinit Sen](https://github.com/abh1nitsen). This portfolio project demonstrates one AI engineering aspect: **turning probabilistic model output into a validated, auditable data contract**. Its domain is invoice intake. The engineering emphasis is grounding, conservative abstention, evaluation, and recovery.

An invoice with `Subtotal: 1200.00`, `Tax: 96.00`, and `Total: 1300.00` produces structured fields plus an `arithmetic_mismatch` review reason. An invented vendor with no source quote is discarded. A crashed batch resumes from its SQLite checkpoints.

![Invoice photo upload with live Groq extraction and review](docs/images/receipt-reader.png)

## What is implemented

- Seven fields: invoice ID, vendor, date, currency, subtotal, tax, total.
- An offline label-based baseline, optional OpenAI text extraction, and Groq text/vision extraction.
- Invoice photo upload (JPEG, PNG, WebP), orientation correction, metadata removal, bounded image preparation, and conservative image review.
- Exact source quotes, character spans, content fingerprints, semantic label checks, and decimal arithmetic validation.
- Human-review decisions for missing/ambiguous values, unsupported formats, conflicting labels, and unlabelled AI interpretations.
- Transactional per-document checkpoints, process locking, content/configuration-aware caching, atomic JSON exports, and bounded network retries.
- A local review UI with source highlighting, example invoices, JSON download, and the exported batch ledger.
- Authored synthetic data, regression tests, evaluation reports, and Windows/Linux CI.

**Prototype boundary:** input is UTF-8 `.txt` or a single JPEG/PNG/WebP invoice image. Groq vision transcribes photographed/scanned invoices and extracts fields. PDF parsing, HEIC/TIFF, line items, reviewer workflow persistence, ERP integration, and payment execution are not implemented. The offline baseline is deterministic rules, not a trained AI model. There is no hidden AI fallback.

## Run in five minutes

Python **3.11+** and Git are sufficient for the dependency-free offline text demo. Image mode additionally needs Pillow (the `vision` extra) and a Groq API key.

```sh
git clone https://github.com/abh1nitsen/evidence-ledger.git
cd evidence-ledger
python -m unittest discover -s tests -v
python -m docintel evaluate
python -m docintel run
python -m docintel serve
```

Open **http://127.0.0.1:8765**. Expand **Try an offline text example**, use the complete invoice and click **Read text**. Open its supporting text and choose **Locate in reading**. Then try the arithmetic-mismatch example. Text examples run offline; photo uploads use Groq when configured.

Windows: use `py -3.12` in place of `python` if needed. macOS/Linux: use `python3` when `python` is unavailable. Run from the repository root so default dataset paths resolve.

## Demonstrate resumability

Use a fresh checkpoint path for a reproducible demonstration:

```sh
python -m docintel run --db runs/recovery.sqlite --output runs/recovery.json --stop-after 2
python -m docintel run --db runs/recovery.sqlite --output runs/recovery.json
python -m docintel run --db runs/recovery.sqlite --output runs/recovery.json
```

Expected summaries: `processed=2, remaining=14`; then `processed=14, skipped=2`; then `processed=0, skipped=16`. The same content with a different file name is computed once, but both file names appear in the report.

## Optional AI mode

### Groq invoice photos

Create a virtual environment, install the vision extra and set the server-side key. PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[vision]"
$env:GROQ_API_KEY = (Get-Content -Raw 'PATH_TO_YOUR_GROQ_KEY_FILE').Trim()
.\.venv\Scripts\python.exe -m docintel serve --vision-model qwen/qwen3.8-27b
```

Bash: activate a virtual environment, run `python -m pip install -e '.[vision]'`, export `GROQ_API_KEY`, then run the same `serve` command with `python`. The key stays on the server and is never sent to the browser. Model availability can change; use a vision-capable model listed in your account and [Groq's vision documentation](https://console.groq.com/docs/vision).

Open http://127.0.0.1:8765, choose **Upload invoice image**, inspect the local preview, then click **Read receipt**. Only that click sends a metadata-stripped normalized copy to Groq. Results show the model transcription, fields, source quotes, quality issues and a persisted checkpoint. Uploading identical bytes again reuses a completed result. Every image result requires human review against the original; quotes/spans refer to the model transcription, **not verified pixel locations**.

Camera advice: include the whole page, keep the phone approximately parallel to the invoice, focus on the print, use diffuse natural light, and avoid glare/strong shadows. Natural light is supported as an input condition, **not a guarantee for every photo or invoice**. Unreadable or ambiguous fields abstain. Unsupported dates/amounts/layouts can still require manual entry.

For resumable mixed text/image batches:

```sh
python -m docintel run --input YOUR_INVOICE_FOLDER --provider groq --db runs/groq.sqlite --output runs/groq-report.json
python -m docintel run --input YOUR_INVOICE_FOLDER --provider groq --db runs/groq.sqlite --output runs/groq-report.json --retry-failed
python -m docintel evaluate --images --dataset data/images --provider groq --output runs/image-evaluation.json
```

Use the virtual-environment Python executable on Windows. Supported images are at most **8,000,000 bytes / 20 megapixels**, single-frame, and at least 32 pixels on both sides. Images are normalized to upright RGB JPEG with a longest edge of 2,000 pixels. No perspective correction or separate independent OCR is claimed.

Groq uses JSON object mode with independent schema validation, a 45-second per-request timeout, and at most two retries. Rate-limit retries honor numeric `Retry-After`, capped at 60 seconds per delay; otherwise wait 20 seconds. There is no silent provider/model switch. See [IMAGE_INPUT.md](docs/IMAGE_INPUT.md) for evidence, privacy, quality and recovery boundaries.

### OpenAI text extraction

The application sends invoice text to OpenAI only when explicitly invoked with `--provider openai`. Configure a compatible model you can access. The sample model name below illustrates configuration and is not a recommendation or guarantee of account availability.

PowerShell:

```powershell
$env:OPENAI_API_KEY = 'your-key'
python -m docintel run --provider openai --model gpt-4o-mini --db runs/ai.sqlite --output runs/ai-report.json
python -m docintel evaluate --provider openai --model gpt-4o-mini --output runs/ai-evaluation.json
Remove-Item Env:OPENAI_API_KEY
```

Bash:

```sh
export OPENAI_API_KEY='your-key'
python -m docintel run --provider openai --model gpt-4o-mini --db runs/ai.sqlite --output runs/ai-report.json
unset OPENAI_API_KEY
```

Do not commit keys. `.env.example` is documentation; dotenv files are not automatically loaded. Provider requests use a 30-second timeout, two retries after the initial attempt, and `store: false`. A crash after a remote response but before the local commit may repeat a paid request. No exactly-once billing guarantee is claimed.

The OpenAI provider contract is based on the [official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). Schema adherence does not establish factual correctness. OpenAI remains mock-tested; Groq vision has a separately recorded live synthetic smoke test. See [VALIDATION.md](docs/VALIDATION.md).

## Results and limits

The committed [baseline evaluation report](reports/baseline-evaluation.json) records **112/112 field matches**, **16/16 expected decisions**, and **zero unsafe validations** on the authored synthetic regression set. Null/abstention matches count as correct field matches, so this is not an extraction coverage score. Five fixtures are expected to validate and eleven require review.

This small dataset intentionally exercises supported and unsupported behavior. It is not held-out real-world evidence or a benchmark against other products. AI and baseline scores must be reported separately. Real supplier layouts, OCR noise, fraud, rounding policies, and regulatory requirements need a larger, independent evaluation.

## Documentation

| Document | Purpose |
|---|---|
| [REPRODUCE.md](docs/REPRODUCE.md) | Clean setup, commands, outputs, tests, exit codes |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Data flow, contracts, checkpoint design, tradeoffs |
| [RUNBOOK.md](docs/RUNBOOK.md) | Interruptions, provider failures, export repair, checkpoint operations |
| [EVALUATION.md](docs/EVALUATION.md) | Metrics, test slices, limits, AI comparison protocol |
| [MODEL_CARD.md](docs/MODEL_CARD.md) | Baseline/AI behavior, limitations, review policy |
| [DATA_CARD.md](docs/DATA_CARD.md) | Synthetic data provenance and label definitions |
| [PORTFOLIO.md](docs/PORTFOLIO.md) | Project positioning, walkthrough, next distinct AI/domain projects |
| [VALIDATION.md](docs/VALIDATION.md) | What was actually verified |
| [IMAGE_INPUT.md](docs/IMAGE_INPUT.md) | Photo upload, Groq configuration, transcription evidence and limitations |
| [SECURITY.md](SECURITY.md) | Credential, document, provider and local UI boundaries |

MIT licensed. Read [CONTRIBUTING.md](CONTRIBUTING.md) to extend providers or document types.

## Using the receipt reader

Choose a photo, click **Read receipt**, then compare the merchant, date, total and seven detailed fields with your original. **Enlarge photo** opens a larger view; **Show supporting text** reveals evidence, and **Locate in reading** highlights matching transcription characters. **Not confirmed** is an abstention, not a zero. Rejected model suggestions remain separate from usable values. A successful reading still needs human confirmation; the yellow notice is not an API failure. Currency is independent of amounts: `$14.09` can become `14.09` while the currency stays unknown. Download JSON when ready. Text examples and the sample batch ledger are secondary views. See [the UI walkthrough](docs/UI_GUIDE.md).
