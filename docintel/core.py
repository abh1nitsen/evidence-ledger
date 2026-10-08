"""Shared schema, normalization, grounding and review policy; no third-party dependencies."""
import datetime as dt
import decimal
import hashlib
import json
import re

VERSION = "invoice-v1.2"
FIELDS = ("invoice_id", "vendor", "invoice_date", "currency", "subtotal", "tax", "total")
LABELS = {
    "invoice_id": r"(?:Invoice (?:ID|Number|No\.?)|(?:Tax )?invoice/Receipt No\.?)",
    "vendor": r"(?:Vendor|Supplier)",
    "invoice_date": r"(?:Invoice Date|Date)",
    "currency": r"Currency",
    "subtotal": r"Subtotal", "tax": r"Tax", "total": r"(?:Grand Total|Total Sale|Total)",
}
AMOUNTS = {"subtotal", "tax", "total"}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {name: {
        "type": "object", "additionalProperties": False,
        "properties": {"value": {"type": ["string", "null"]},
                       "quote": {"type": ["string", "null"]}},
        "required": ["value", "quote"],
    } for name in FIELDS}, "required": list(FIELDS),
}


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(field, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty value")
    value = value.strip()
    if field in AMOUNTS:
        # Currency markers do not identify currency; that is validated separately.
        value = re.sub(r"^(?:USD|SGD|EUR|GBP|INR|CAD|AUD|JPY|S\$|US\$|[$£€₹])\s*", "", value, flags=re.I)
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", value):
            raise ValueError("unsupported amount format")
        amount = decimal.Decimal(value.replace(",", ""))
        if amount > decimal.Decimal("1000000000"):
            raise ValueError("amount outside prototype limit")
        return format(amount.quantize(decimal.Decimal("0.01")), ".2f")
    if field == "invoice_date":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return dt.date.fromisoformat(value).isoformat()
        match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)?", value, re.I)
        if match:
            first, second, year = map(int, match.groups())
            if first > 12 and second <= 12:
                return dt.date(year, second, first).isoformat()
            if second > 12 and first <= 12:
                return dt.date(year, first, second).isoformat()
        raise ValueError("ambiguous_or_unsupported_date")
    if field == "currency":
        if value.upper() not in {"USD", "SGD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY"}:
            raise ValueError("unsupported currency")
        return value.upper()
    if len(value) > 200:
        raise ValueError("value too long")
    return value


def baseline(text):
    result = {}
    for field, label in LABELS.items():
        matches = list(re.finditer(r"^\s*" + label + r"\s*:\s*([^\r\n]+?)\s*$", text,
                                   flags=re.MULTILINE | re.IGNORECASE))
        # Ambiguous duplicate labels abstain, even when amounts happen to agree.
        result[field] = {"value": matches[0].group(1), "quote": matches[0].group(1)} if len(matches) == 1 else {"value": None, "quote": None}
    return result


def validate(text, proposed):
    if not isinstance(proposed, dict) or set(proposed) != set(FIELDS):
        raise ValueError("provider output has invalid field schema")
    fields, issues = {}, []
    for field in FIELDS:
        entry = proposed[field]
        if not isinstance(entry, dict) or set(entry) != {"value", "quote"}:
            raise ValueError("provider output has invalid evidence schema")
        value, quote = entry["value"], entry["quote"]
        if any(x is not None and not isinstance(x, str) for x in (value, quote)):
            raise ValueError("provider values must be strings or null")
        reason = None
        normalized, span, spans = None, None, []
        if value is None:
            reason = "missing_or_ambiguous"
        else:
            try:
                normalized = canonical(field, value)
                if not quote or len(quote) > 500 or quote not in text:
                    raise ValueError("evidence_not_in_source")
                # A quote must be the raw field value, not a broad passage containing it.
                if canonical(field, quote) != normalized:
                    raise ValueError("evidence_value_mismatch")
                labelled = list(re.finditer(r"^\s*" + LABELS[field] + r"\s*:\s*([^\r\n]+?)\s*$", text, re.M | re.I))
                if labelled and (len(labelled) != 1 or canonical(field, labelled[0].group(1)) != normalized):
                    raise ValueError("evidence_label_mismatch")
                if not labelled:
                    issues.append({"field": field, "code": "semantic_binding_needs_review"})
                locations = list(re.finditer(r"(?<![\w.,-])" + re.escape(quote) + r"(?![\w.,-])", text))
                if not locations:
                    raise ValueError("evidence_not_in_source")
                spans = [{"start": loc.start(), "end": loc.end()} for loc in locations[:32]]
                if len(locations) != 1:
                    issues.append({"field": field, "code": "ambiguous_evidence_location"})
                else:
                    span = spans[0]
            except ValueError as exc:
                reason = str(exc)
                normalized, span, spans = None, None, []
        fields[field] = {"value": normalized, "quote": quote if spans else None,
                         "span": span, "spans": spans, "valid": reason is None,
                         "candidate": value if reason else None,
                         "candidate_quote": quote if reason else None}
        if reason:
            issues.append({"field": field, "code": reason})
    if all(fields[x]["valid"] for x in AMOUNTS):
        numbers = {x: decimal.Decimal(fields[x]["value"]) for x in AMOUNTS}
        if numbers["subtotal"] + numbers["tax"] != numbers["total"]:
            issues.append({"field": "total", "code": "arithmetic_mismatch"})
    # Local diagnostics are intentionally conservative, not a complete injection detector.
    if re.search(r"ignore\s+(?:all\s+)?(?:previous|prior)|system\s*prompt|override\s+instructions", text, re.I):
        issues.append({"field": "document", "code": "instruction_like_content"})
    # Detect duplicate labelled values independently of the AI provider's interpretation.
    for field, label in LABELS.items():
        if len(re.findall(r"^\s*" + label + r"\s*:", text, re.M | re.I)) > 1:
            issues.append({"field": field, "code": "duplicate_label"})
    return {"schema_version": VERSION, "source_sha256": digest(text), "fields": fields,
            "decision": "review" if issues else "validated", "issues": issues,
            "policy": "Validation checks are not an authorization to pay."}


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
