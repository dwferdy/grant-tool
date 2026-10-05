"""Free stand-in for Claude: simple keyword rules, no API call. Turn on with AI_MODE=offline in .env.

For testing the workflow and UI without billing. It is NOT an AI and will miss anything phrased differently
from its keyword lists. Its output goes through the same safeguards as Claude's (quote verification, double run).
"""
from __future__ import annotations
import re
from typing import Optional
from engine.models import Application, Rubric, Rule

NAME = "offline-keywords"

def _r(rid, verdict, reasoning, quotes=(), missing="", value=""):
    from engine.ai_checks import _AIRuleResult, _AIQuote
    return _AIRuleResult(rule_id=rid, verdict=verdict, reasoning=reasoning, missing=missing, reason_value=value,
                         quotes=[_AIQuote(field=f, text=t) for f, t in quotes])

def _search(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text or "", re.I)
    return m[0] if m else None

def _sentence(text: str, pattern: str) -> Optional[str]:
    """The whole sentence that contains the pattern, copied verbatim."""
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        if re.search(pattern, s, re.I):
            return s
    return None

def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip())[0] if text else ""

# Exclusions: (pattern in budget items, pattern in description, grey-area pattern -> officer)
EXCLUSIONS = {
    "R17": (r"laptop|mobile phone|\bphones?\b|tablet|ipad|computer|camera", None, None),
    "R18": (None, r"profit|surplus|tickets? will be sold|retained by the company", None),
    "R19": (r"wages|salar|rent\b|utilities|office|insurance", None, r"insurance"),
    "R20": (r"membership", r"membership fee", None),
    "R21": (r"fundrais|donation|charity", r"fundrais|charity|donation", None),
    "R22": (r"(?<!non-)alcohol|\bbeer\b|\bwine\b|spirits|liquor|cocktail", r"(?<!non-)alcohol|\bbeer\b|\bwine\b", None),
    "R23": (r"illegal|drugs|gambling", r"illegal|drugs|gambling", None),
    "R24": (r"grant writ|application prep|writing (this|the) application", r"grant writ", None),
    "R25": (r"political|election|campaign", r"political|election|campaign|rally", None),
    "R26": (None, r"\b(only|exclusively) (for )?(men|women|males|females|christians|muslims|hindus)\b", None),
}

def _exclusion(app: Application, rid: str):
    item_pat, desc_pat, grey_pat = EXCLUSIONS[rid]
    if item_pat:
        for i, b in enumerate(app.budget):
            if re.search(item_pat, b.item, re.I):
                if grey_pat and re.search(grey_pat, b.item, re.I):
                    return _r(rid, "needs_officer_judgement",
                              f"Budget line '{b.item}' may be a running cost, but the guidelines may also require it. Grey area.",
                              [(f"budget[{i}].item", b.item)], "Officer to decide whether this cost is allowed.", b.item)
                return _r(rid, "not_met", f"Budget line '{b.item}' matches this exclusion.",
                          [(f"budget[{i}].item", b.item)], "Remove this item from the budget.", b.item)
    if desc_pat:
        s = _sentence(app.project.description, desc_pat)
        if s:
            return _r(rid, "not_met", "The project description matches this exclusion.",
                      [("project.description", s)], "Change the project so it no longer falls under this exclusion.", s)
    return _r(rid, "met", "No budget item or description text matches this exclusion.")

def _r01(app: Application, rb: Rubric):
    t = app.applicant.type
    if t in rb.allowed_applicant_types:
        return _r("R01", "met", f"Applicant type '{t}' is an allowed type.", [("applicant.type", t)])
    return _r("R01", "insufficient_evidence", f"Applicant type '{t}' is not one of the allowed types.",
              missing="Confirm which allowed applicant type you are.")

def _r04(app: Application):
    pat = r"Darwin|Northern Territory|\bNT\b|Litchfield|Kakadu|Territory"
    for field in ("project.location", "project.who_can_attend", "project.description"):
        text = {"project.location": app.project.location, "project.who_can_attend": app.project.who_can_attend,
                "project.description": app.project.description}[field]
        hit = _search(text, pat)
        if hit and app.applicant.nt_based is not False:
            return _r("R04", "met", "The activity takes place in or targets students in the NT.", [(field, hit)])
    return _r("R04", "insufficient_evidence", "No clear link to the NT found.", missing="Where the event is held and who it serves.")

def _r07(app: Application):
    who = app.project.who_can_attend or ""
    if not who.strip():
        return _r("R07", "insufficient_evidence", "'Who can attend' is blank.",
                  missing="State that all international students can attend, or name at least 3 providers.")
    narrow = _search(who, r"\b(one|only|single)\b[^.,]*")
    if narrow:
        return _r("R07", "not_met", "Attendance is limited to a single provider or group.", [("project.who_can_attend", narrow)],
                  "Open the event to all international students or to students from at least 3 providers.", narrow)
    open_all = _search(who, r"all international students?[^.,]*")
    if open_all:
        return _r("R07", "met", "The application says all international students can attend.", [("project.who_can_attend", open_all)])
    return _r("R07", "insufficient_evidence", "It is not clear the event is open to all international students.",
              missing="State that all international students can attend, or name at least 3 providers.")

def review(app: Application, rules: list[Rule], rubric: Rubric) -> dict:
    out = {}
    for r in rules:
        if r.id in EXCLUSIONS:
            out[r.id] = _exclusion(app, r.id)
        elif r.id == "R01":
            out[r.id] = _r01(app, rubric)
        elif r.id == "R04":
            out[r.id] = _r04(app)
        elif r.id == "R07":
            out[r.id] = _r07(app)
        elif r.id == "R09":
            s = _first_sentence(app.project.wellbeing_benefit)
            out[r.id] = _r("R09", "met" if s else "insufficient_evidence", "Stated wellbeing benefit quoted for the officer.",
                           [("project.wellbeing_benefit", s)] if s else [], value=s)
        elif r.id == "R10":
            s = _first_sentence(app.project.description)
            out[r.id] = _r("R10", "needs_officer_judgement", "Officer to judge the description against objectives (a)-(e).",
                           [("project.description", s)] if s else [], value="")
    return out
