"""Exact-match and review-policy evaluation against authored synthetic labels."""
import json
from pathlib import Path

from .core import FIELDS, validate
from .pipeline import read_document, run


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
            "dataset": "authored-synthetic-v2", "documents": len(cases),
            "field_exact_match": correct / total, "decision_accuracy": decisions / len(cases),
            "unsafe_validations": unsafe, "extraction_failures": failures,
            "slices": slices, "cases": details,
            "limitation": "Synthetic regression evidence; not a real-world accuracy estimate."}


def evaluate_images(dataset, provider, db, output):
    dataset = Path(dataset)
    gold = json.loads((dataset / "gold.json").read_text(encoding="utf-8"))
    batch = run(dataset, db, output, provider)
    actual = {item["document"]: item for item in batch["documents"]}
    details, matches, decisions, failures = [], 0, 0, 0
    for case in gold:
        record = actual.get(case["document"], {})
        result = record.get("extraction")
        if result:
            values = {key: result["fields"][key]["value"] for key in FIELDS}
            count = sum(values[key] == case["fields"][key] for key in FIELDS)
            decision_correct = result["decision"] == case["decision"]
        else:
            values, count, decision_correct = None, 0, False
            failures += 1
        matches += count
        decisions += decision_correct
        details.append({"document": case["document"], "slice": case["slice"], "actual": values,
                        "correct_fields": count, "decision_correct": decision_correct,
                        "error": record.get("error"), "image_sha256": result.get("source_sha256") if result else None})
    return {"provider": provider.name, "model": provider.model, "provider_identity": provider.image_identity,
            "dataset": "synthetic-image-smoke-v1", "documents": len(gold),
            "field_exact_match": matches / (len(gold)*len(FIELDS)), "decision_accuracy": decisions / len(gold),
            "unsafe_validations": sum(item.get("extraction", {}).get("decision") == "validated" for item in batch["documents"]),
            "extraction_failures": failures, "processed": batch["processed"], "skipped": batch["skipped"],
            "cases": details, "limitation": "Rendered invoices with simulated shadows/angle, not real natural-light photographs."}


def evaluate_documents(dataset,provider,db,output):
    """Score ten proposed fields and document roles; never equate proposals with approval."""
    import time
    dataset=Path(dataset);gold=json.loads((dataset/'gold.json').read_text(encoding='utf-8'))
    started=time.monotonic();batch=run(dataset,db,output,provider)
    indexed={r['document']:r for r in batch['documents']}
    details=[];correct=total=printed_correct=printed_total=absent_correct=absent_total=types=failures=0
    for case in gold:
        record=indexed.get(case['document'],{});extraction=record.get('extraction')
        proposals={k:extraction['fields'].get(k,{}).get('proposal_value') for k in case['proposals']} if extraction else {}
        count=0
        for key,expected in case['proposals'].items():
            matched=bool(extraction) and proposals.get(key)==expected
            count+=matched;total+=1
            if expected is None:absent_total+=1;absent_correct+=matched
            else:printed_total+=1;printed_correct+=matched
        correct+=count;type_match=bool(extraction) and extraction.get('document_type')==case['document_type'];types+=type_match
        failures+=not bool(extraction)
        details.append({'document':case['document'],'document_type':extraction.get('document_type') if extraction else None,'type_correct':type_match,'proposals':proposals,'correct_fields':count,'error':record.get('error')})
    return {'dataset':'authored-document-diversity-v1','provider':provider.name,'model':provider.model,'provider_identity':provider.image_identity,
        'documents':len(gold),'proposed_field_exact_match':correct/total,'printed_field_match':printed_correct/printed_total,
        'absent_field_match':absent_correct/absent_total,'document_type_accuracy':types/len(gold),'extraction_failures':failures,
        'processed':batch['processed'],'skipped':batch['skipped'],'elapsed_seconds':round(time.monotonic()-started,3),'cases':details,
        'limitation':'Three authored layouts; not real-photo generalisation or calibrated confidence. Proposed dates with two-digit years still require human confirmation.'}
