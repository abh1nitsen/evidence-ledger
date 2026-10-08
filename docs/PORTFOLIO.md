# Portfolio positioning

## First project in this series

**Evidence Ledger — document intelligence for invoice intake.**

**AI building aspect:** schema-bound extraction, grounding, abstention, and operational recovery. **Domain problem:** document intake teams need usable structured data and explicit exceptions rather than plausible-looking unsupported fields. **Demonstrable outcome:** recoverable extraction runs with evidence, review policy, tests, and reproducible regression metrics.

Portfolio statement: “Built a document-intelligence prototype with optional structured LLM extraction, field-level source evidence, conservative review routing, resumable SQLite checkpoints, fault-injection tests, and reproducible evaluation.” Do not describe the offline rules as a trained model or the synthetic score as real-world accuracy.

## Five-minute walkthrough

1. Explain the domain problem and why schema correctness alone is insufficient.
2. Run the offline demo and locate vendor/amount evidence.
3. Show a missing field, conflicting total and instruction-containing source triggering review.
4. Stop a batch after two documents; rerun twice to show recovery and reuse.
5. Run tests and show the synthetic evaluation report, then discuss the gap to real supplier invoices.
6. Explain the optional AI provider and the live-evaluation work still required.

## Principle for future projects

Each project must name one domain problem and one distinct AI engineering skill, define a baseline, publish an honest evaluation, document recovery, and provide a clean-clone walkthrough. Avoid repeating a skill unless the domain change introduces a new technical challenge.

This account already contains projects in safety/red teaming, RAG evaluation, threat investigation, hospital workflows, road analysis, churn, and power-grid modeling. The following are **proposed future projects**, not implemented or evaluated in this repository:

| Proposed project | Domain | Distinct AI building aspect | Evidence to publish |
|---|---|---|---|
| Quality Sentinel | Manufacturing sensor quality | Drift detection and model monitoring | Temporal holdout, drift detection delay, false alerts |
| Demand Compass | Retail inventory | Probabilistic forecasting and uncertainty | Rolling-origin backtests, interval coverage, stockout simulations |
| Vision Triage | Visual quality inspection | Active learning and label efficiency | Label-budget curves, independent defect recall |
| Private Signal | Customer analytics | Privacy-preserving data preparation | Utility/privacy tradeoffs, explicit threat model |

Do not claim these projects exist until built. This repository can serve as the implementation and documentation standard for subsequent work.

Version 0.4 deepens the same engineering aspect through independent pretrained OCR, document-role-aware extraction, transparent uncalibrated review scores and durable human corrections. The key lesson is separating recognition, semantic assignment, validation and acceptance. Three authored layouts and two private debugging cases are useful regressions; confidence calibration and merchant-disjoint generalisation remain future evidence requirements.
