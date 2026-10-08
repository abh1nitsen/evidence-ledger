# Dataset card

**Name:** authored-synthetic-v1. **Provenance:** authored specifically for this prototype; no real invoices, companies, customers, bank accounts, identifiers, or private source files were copied. Example supplier names are fictional. **License:** MIT with the repository.

Sixteen UTF-8 invoice text fixtures in `data/invoices/` are paired with `data/gold.json`. Each gold row contains the filename, test slice, expected decision, and all seven canonical field values. A null label means the current conservative extraction contract must abstain, not that every semantic fact is absent from the text.

The set is derived from a small shared template with intentional variations. This makes it suitable for contract regression and unsuitable for broad accuracy claims. It contains no training split or independent test split. Numeric and date formats are intentionally narrow. Prose case 16 is expected to abstain under the baseline.

Version 0.2 adds four synthetic image fixtures and authored gold in `data/images/`. The invoice render and its simulated shadow/angle variants contain the same seven expected values; the blank non-invoice expects seven nulls. All image cases require review. `scripts/generate_image_fixtures.py` rebuilds these from authored text using Pillow. No actual camera photograph or private invoice is included; the lighting simulation is not evidence for arbitrary natural-light conditions.

Names and values are fictional, but downstream outputs from your own invoices may contain sensitive data. Runtime reports and databases are ignored by Git. Add only de-identified, reviewed fixtures to the public dataset and manually author gold labels before running the system.

Version 0.4 adds three authored layout-diversity renders in `data/documents/`: a EUR invoice, SGD retail receipt and payment slip. `gold.json` independently specifies all ten proposed fields and expected document roles; a proposed century is not an automatically accepted date. `scripts/generate_document_fixtures.py` regenerates the fixtures. Printed fields and correctly absent fields are scored separately. No private receipt, identity, card detail or real-photo screenshot is included.
