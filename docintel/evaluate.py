"""Exact-match and review-policy evaluation against authored synthetic labels."""
import json
from pathlib import Path

from .core import FIELDS, validate
from .pipeline import read_document


def evaluate(dataset, provider):
    dataset = Path(dataset)
    cases = json.loads((dataset / "gold.json").read_text(encoding="utf-8"))
    correct, total, decisions, unsafe, failures, details = 0, 0, 0, 0, 0, []
    for case in cases:
        text = read_document(dataset / "invoices" / case["document"])
        try:
            result = validate(text, provider.extract(text))
            values = {key: result["fields"][key]["value"] for key in FIELDS}
            matches = sum(values[key] == case["fields"][key] for key in FIELDS)
            decision_correct = result["decision"] == case["decision"]
            unsafe += case["decision"] == "review" and result["decision"] == "validated"
            error = None
        except (ValueError, RuntimeError):
            matches, decision_correct, values, error = 0, False, None, "extraction_failed"
            failures += 1
        correct += matches
        total += len(FIELDS)
        decisions += decision_correct
        details.append({"document": case["document"], "slice": case["slice"],
                        "correct_fields": matches, "total_fields": len(FIELDS),
                        "decision_correct": decision_correct, "error": error, "actual": values})
    slices = {}
    for item in details:
        group = slices.setdefault(item["slice"], {"correct_fields": 0, "total_fields": 0})
        group["correct_fields"] += item["correct_fields"]
        group["total_fields"] += item["total_fields"]
    return {"provider": provider.name, "provider_identity": provider.identity,
            "dataset": "authored-synthetic-v1", "documents": len(cases),
            "field_exact_match": correct / total, "decision_accuracy": decisions / len(cases),
            "unsafe_validations": unsafe, "extraction_failures": failures,
            "slices": slices, "cases": details,
            "limitation": "Synthetic regression evidence; not a real-world accuracy estimate."}
