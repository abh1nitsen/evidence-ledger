# Reproduce from a clean clone

Requirements: Python 3.11+, Git, and a local filesystem with SQLite support. Tested locally on Windows with Python 3.12.10. CI covers Python 3.11/3.12 on Ubuntu and Windows. Offline mode does not require package installation, network access, an API key, or external data downloads.

```sh
git clone https://github.com/abh1nitsen/evidence-ledger.git
cd evidence-ledger
python --version
python -m unittest discover -s tests -v
python -m docintel evaluate --output runs/evaluation.json
python -m docintel run --db runs/demo.sqlite --output runs/report.json --stop-after 2
python -m docintel run --db runs/demo.sqlite --output runs/report.json
python -m docintel run --db runs/demo.sqlite --output runs/report.json
python -m docintel serve --report runs/report.json --port 8765
```

The baseline evaluation should match `reports/baseline-evaluation.json` exactly. No timestamps or random data are generated. The first two batch runs process 2 then 14 documents; the third processes zero and reuses 16. Stop the server with Ctrl+C.

For your own documents, put UTF-8 `.txt` files in a separate local directory, then pass `--input PATH`. No recursion occurs. Each file must be nonempty, contain no NUL bytes, and be at most 100,000 bytes. Symlinks are rejected. Use distinct checkpoint and report paths for private experiments.

Example supported format:

```text
Vendor: Northstar Office Supplies
Invoice ID: INV-2026-041
Invoice Date: 2026-10-01
Currency: USD
Subtotal: 1200.00
Tax: 96.00
Total: 1296.00
```

To install the CLI optionally: `python -m pip install -e .`, then use `evidence-ledger` in place of `python -m docintel`. This build installation can download setuptools; direct module execution stays dependency-free.

## Exit codes

- `0`: successful processing/evaluation. Review decisions and an intentional partial run still count as successful processing.
- `2`: one or more batch documents failed, or evaluation failed its strict synthetic regression gate.
- `1`: invalid runtime configuration, unavailable provider, inaccessible files, or locked database.
- Argument parsing errors use argparse's `2`; keyboard interruption during a batch is handled by the process runtime. Resume afterward.

Inspect the printed `remaining` field to distinguish a partial demo from a fully traversed batch. Inspect document status and issues in the JSON, rather than treating exit code zero as invoice approval.

## Reproducibility boundaries

The deterministic baseline and synthetic fixture outputs reproduce offline. AI responses can differ between calls and model versions, incur cost, and depend on provider access. Use a fresh database for repeat model experiments; reusing a database measures cache behavior rather than fresh AI inference. Run both providers against the same independent gold labels and report separate results.
