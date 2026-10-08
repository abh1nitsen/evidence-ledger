"""Document roles, optional fields and transparent (uncalibrated) review scores."""
import math
import re
from .core import FIELDS, EXTRA_FIELDS, canonical, digest, validate

DOCUMENT_TYPES = ("invoice", "retail_receipt", "payment_slip", "unknown")
SCORE_VERSION = "evidence-score-v1"

def classify(text):
    if re.search(r"\b(?:BASE|TIP)\s*:", text, re.I) and re.search(r"\b(?:TID|APPR CODE|CARD LABEL|PIN VERIFIED)\b", text, re.I):
        return "payment_slip"
    if re.search(r"tax invoice|subtotal|invoice (?:id|number|no)", text, re.I):
        return "invoice"
    if re.search(r"receipt|total sale|customer copy", text, re.I):
        return "retail_receipt"
    return "unknown"

def optional_fields(text):
    fields = {k:{"value":None,"quote":None} for k in EXTRA_FIELDS}
    clock = re.search(r"(?:DATE/TIME|TIME)\s*:\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+)?(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)",text,re.I)
    if clock:
        fields["transaction_time"]={"value":clock.group(1).strip(),"quote":clock.group(1).strip()}
    for key,label in (("base_amount","BASE"),("tip","TIP")):
        m=re.search(r"^\s*"+label+r"\s*:\s*((?:S\$|US\$|[$£€₹]|[A-Z]{3})?\s*\d+(?:\.\d{1,2})?)\s*$",text,re.M|re.I)
        if m:
            fields[key]={"value":m.group(1).strip(),"quote":m.group(1).strip()}
    return fields

def attach_document(result, text, extras=None, document_type=None, ocr=None):
    if document_type is not None and document_type not in DOCUMENT_TYPES:
        raise ValueError("invalid document type")
    kind=document_type if document_type is not None else classify(text)
    if kind not in DOCUMENT_TYPES:
        raise ValueError("invalid document type")
    # Recognizable payment syntax overrides a model's generic invoice classification.
    if classify(text)=="payment_slip":
        kind="payment_slip"
    extra=validate(text, optional_fields(text) if extras is None else extras, EXTRA_FIELDS)
    result["fields"].update(extra["fields"])
    result["issues"].extend(extra["issues"])
    result["document_type"]=kind
    result["document_type_basis"]="rule_and_model" if document_type else "source_rules"
    result["score_policy"]={"version":SCORE_VERSION,"calibrated":False,"threshold":0.85,
        "description":"Evidence support score, not probability of correctness. Image fields always remain reviewable."}
    if ocr:
        result["ocr"]=ocr
    for key,f in result["fields"].items():
        raw=f["value"] if f["value"] is not None else f.get("candidate")
        proposal=None
        if raw is not None:
            try: proposal=canonical(key,raw)
            except ValueError: pass
        f["proposal_value"]=proposal
        f["required"]= key in {"vendor","invoice_date","invoice_id","currency"} or key=="total" and kind!="payment_slip"
        codes=[i["code"] for i in result["issues"] if i["field"]==key]
        f["state"]="found" if f["value"] is not None else "needs_review" if raw is not None else "missing" if f["required"] else "not_present"
        quote=f.get("quote") or f.get("candidate_quote")
        lines=[]
        if ocr and quote:
            # Match literal OCR evidence; never invent an image location from an LLM quote.
            for line in ocr["lines"]:
                if quote in line["text"] or proposal and re.search(r"(?<![\w.,-])"+re.escape(str(raw))+r"(?![\w.,-])",line["text"]):
                    lines.append(line)
        f["ocr_evidence"]=lines[:16]
        evidence=bool(quote and quote in text)
        format_ok=proposal is not None
        semantic=f["valid"] and not any(x in codes for x in ("semantic_binding_needs_review","evidence_label_mismatch","evidence_value_mismatch"))
        recognition=min((x["score"] for x in lines),default=None)
        components={"source_match":0.45 if evidence else 0,"supported_format":0.15 if format_ok else 0,
                    "label_support":0.15 if semantic and raw is not None else 0,
                    "ocr_support":0.2*recognition if recognition is not None else 0}
        score=round(sum(components.values()),3) if raw is not None else 0
        # Conflict and assumptions always force review, independent of OCR recognition.
        hard=(raw is not None and not f["valid"]) or any(x in codes for x in ("arithmetic_mismatch","evidence_label_mismatch","evidence_value_mismatch","evidence_not_in_source","two_digit_year_assumption","duplicate_label"))
        if hard:
            score=min(score,0.49)
        f["review_score"]={"value":score,"calibrated":False,"components":components,"ocr_recognition":recognition,"forced_review":hard}
    return result
