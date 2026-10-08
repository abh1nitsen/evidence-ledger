# Dataset card

**Name:** authored-synthetic-v1. **Provenance:** authored specifically for this prototype; no real invoices, companies, customers, bank accounts, identifiers, or private source files were copied. Example supplier names are fictional. **License:** MIT with the repository.

Sixteen UTF-8 invoice text fixtures in `data/invoices/` are paired with `data/gold.json`. Each gold row contains the filename, test slice, expected decision, and all seven canonical field values. A null label means the current conservative extraction contract must abstain, not that every semantic fact is absent from the text.

The set is derived from a small shared template with intentional variations. This makes it suitable for contract regression and unsuitable for broad accuracy claims. It contains no training split or independent test split. Numeric and date formats are intentionally narrow. Prose case 16 is expected to abstain under the baseline.

Names and values are fictional, but downstream outputs from your own invoices may contain sensitive data. Runtime reports and databases are ignored by Git. Add only de-identified, reviewed fixtures to the public dataset and manually author gold labels before running the system.
