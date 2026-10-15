"""Rules a super admin adds in the app. Stored in data/custom_rules.json, on top of the official data/rubric.json.

Official rules are read-only here (they come from the published guidelines). Custom rules can be added, edited
and switched off, never deleted, so old decisions stay explainable. Every change is logged in the audit DB.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional
from engine.loader import ROOT, load_rubric
from engine.models import Rubric, Rule, Source
from engine import audit
from engine.demo import guard

CUSTOM_FILE = ROOT / "data/custom_rules.json"
INTERNAL_SOURCE = {"document": "Internal policy (added by super admin)", "section": "", "url": ""}

# Code rules an admin can build without writing code.
REQUIRED_FIELDS = {
    "applicant.abn": "ABN", "applicant.contact_role": "Contact role", "project.location": "Location",
    "project.who_can_attend": "Who can attend", "project.wellbeing_benefit": "Wellbeing benefit",
    "project.description": "Description", "applicant.auspicing_body.name": "Auspicing body",
}
TEMPLATES = {
    "category_cap": "Budget category limit (e.g. marketing ≤ 20%)",
    "max_total": "Maximum amount requested (e.g. ≤ $5,000)",
    "required_field": "A field must be filled in",
}

def load_custom() -> list[Rule]:
    if not CUSTOM_FILE.exists():
        return []
    return [Rule.model_validate(r) for r in json.loads(CUSTOM_FILE.read_text())]

def _save(rules: list[Rule]) -> None:
    guard("Changing rules")
    CUSTOM_FILE.write_text(json.dumps([r.model_dump(mode="json", exclude_none=True) for r in rules], indent=2))

def active_rubric() -> Rubric:
    """Official rules + active custom rules. This is what the app checks applications against."""
    base = load_rubric()
    return base.model_copy(update={"rules": base.rules + [r for r in load_custom() if r.active]})

def next_id() -> str:
    used = [int(r.id[1:]) for r in load_custom() if r.id[1:].isdigit()]
    return f"C{max(used, default=0) + 1:02d}"

def code_rule_text(template: str, p: dict) -> dict:
    """Rule wording, check description and default letter text for a code template."""
    if template == "category_cap":
        cat, pct = p["category"].replace("_", " "), round(p["pct"] * 100)
        return {"rule": f"{cat.capitalize()} costs must not exceed {pct}% of the total grant.",
                "check": f"sum(budget[category=={p['category']}]) <= {p['pct']} * total_requested",
                "plain_english_reason": f"Your budget asks for ${{amount}} for {cat}. The limit is {pct}% of the grant "
                                        f"(${{limit}}). Please reduce this amount.", "type": "numeric_cap"}
    if template == "max_total":
        return {"rule": f"The grant amount requested must not exceed ${p['amount']:,.0f}.",
                "check": f"total_requested <= {p['amount']}",
                "plain_english_reason": f"You asked for ${{total_requested}}. The most we can provide is ${p['amount']:,.0f}.",
                "type": "numeric_cap"}
    if template == "required_field":
        label = REQUIRED_FIELDS[p["field"]]
        return {"rule": f"The application must include: {label}.", "check": f"{p['field']} is not empty",
                "plain_english_reason": f"Your application did not include: {label}. Please add it.",
                "type": "eligibility_gate"}
    raise ValueError(f"Unknown template {template}")

def default_ai_reason(rule_text: str, rtype: str) -> str:
    if rtype == "exclusion":
        return f"{rule_text} Your application includes: {{evidence}}. Please remove it or explain."
    return f"{rule_text} We could not find this in your application. Please tell us how your project meets it."

def add_rule(*, by: str, short_name: str, rule: str, check_method: str, rtype: str, check: str,
             evidence_needed: str, plain_english_reason: str, source: Optional[dict] = None,
             params: Optional[dict] = None, keywords: Optional[list[str]] = None) -> Rule:
    r = Rule(id=next_id(), type=rtype, check_method=check_method, rule=rule.strip(),
             source=Source(**(source or INTERNAL_SOURCE)), check=check.strip(), evidence_needed=evidence_needed.strip(),
             if_missing="insufficient_evidence", plain_english_reason=plain_english_reason.strip(),
             short_name=short_name.strip(), params=params, keywords=[k.strip() for k in keywords or [] if k.strip()],
             custom=True, active=True, added_by=by, added_at=datetime.now())
    _save(load_custom() + [r])
    audit.record_rule_change(r.id, "added", r.model_dump_json(), by)
    return r

def set_active(rule_id: str, active: bool, by: str) -> None:
    rules = load_custom()
    for i, r in enumerate(rules):
        if r.id == rule_id:
            rules[i] = r.model_copy(update={"active": active})
            _save(rules)
            audit.record_rule_change(rule_id, "enabled" if active else "disabled", rules[i].model_dump_json(), by)
            return
    raise KeyError(rule_id)
