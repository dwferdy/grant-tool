"""Rules that need the applicant's own words: Claude finds evidence, code verifies every quote.

Safeguards (see README "Next steps"):
- Every quote goes through verify_quote(); unverified quotes are dropped.
- A rejection or a "met" on an eligibility gate needs at least one verified quote, otherwise insufficient_evidence.
- Each application is checked twice; any disagreement -> needs_officer_judgement.
- officer_judgement rules never get a final verdict from the AI, only evidence.
- Results are cached in data/cache/ai/ so the same application is never re-billed.
"""
from __future__ import annotations
import hashlib, json, os
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional
from pydantic import BaseModel
from engine.loader import ROOT
from engine.models import Application, Rubric, Rule, Cell, Verdict, Quote
from engine.code_checks import verify_quote
from engine.demo import is_demo, guard

MODEL = "claude-opus-5-5"
PROMPT_VERSION = "v1"
CACHE_DIR = ROOT / "data/cache/ai"
GATES_NEEDING_EVIDENCE = {"R01", "R04", "R07"}   # "met" must be backed by a verified quote
SKIP_AI = {"R05"}                                 # department records, not application text

SYSTEM = """You assess grant applications against eligibility rules for a government officer.
A human officer makes every final decision; your job is to find evidence.

Rules for you:
- Judge SUBSTANCE only. Never let grammar, spelling, fluency, tone or English level affect a verdict.
  Two applications that say the same thing in different words must get the same verdict.
- Quote the applicant's text EXACTLY, copied character for character from one field, and name that field
  using the field path shown (e.g. "project.description" or "budget[2].item"). Keep quotes short.
  Never paraphrase inside a quote. Quotes are checked by code and invented quotes are discarded.
- Verdicts:
  met: the rule is satisfied (for exclusion rules: nothing in the application falls under the exclusion).
  not_met: clear, quotable evidence the rule is broken.
  insufficient_evidence: the application is vague or silent where the rule needs information; the applicant
    should be asked to clarify. Prefer this over not_met when in doubt.
  needs_officer_judgement: a genuine grey area that a human must decide (say why).
- reason_value: a short phrase to insert into a letter to the applicant: the offending item or evidence for
  exclusions, the stated purpose for R09, the objective not addressed for R10. Empty string if not needed.
- missing: what information would change the outcome. Empty string if nothing.
- reasoning: one or two plain sentences for the officer."""

class _AIQuote(BaseModel):
    field: str
    text: str

class _AIRuleResult(BaseModel):
    rule_id: str
    verdict: Literal["met", "not_met", "insufficient_evidence", "needs_officer_judgement"]
    quotes: list[_AIQuote]
    reasoning: str
    missing: str
    reason_value: str

class _AIResponse(BaseModel):
    results: list[_AIRuleResult]

def ai_rules(rubric: Rubric) -> list[Rule]:
    return [r for r in rubric.rules if r.check_method != "code"]

def _load_env() -> None:
    if is_demo():
        return   # public demo: never read .env (it could hold an API key)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

def offline_mode() -> bool:
    """AI_MODE=offline in .env: use the free keyword reviewer instead of Claude. Always offline in the public demo."""
    if is_demo():
        return True
    _load_env()
    return os.environ.get("AI_MODE", "").strip().lower() == "offline"

def reviewer_name() -> str:
    from engine.offline_reviewer import NAME
    return NAME if offline_mode() else MODEL

def api_available() -> bool:
    _load_env()
    return offline_mode() or bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

# ---------- prompt ----------
def _app_fields(app: Application) -> str:
    a, p = app.applicant, app.project
    lines = [f"applicant.name: {a.name}", f"applicant.type: {a.type}",
             f"applicant.nt_based: {a.nt_based}", f"applicant.contact_role: {a.contact_role}"]
    if a.auspicing_body:
        lines.append(f"applicant.auspicing_body.name: {a.auspicing_body.name}")
    for f in ["title", "description", "location", "start_date", "end_date", "who_can_attend", "wellbeing_benefit"]:
        lines.append(f"project.{f}: {getattr(p, f)}")
    for i, b in enumerate(app.budget):
        lines.append(f"budget[{i}].item: {b.item}   (category: {b.category}, amount: ${b.amount:,.2f})")
    lines.append(f"total_requested: ${app.total_requested:,.2f}")
    return "\n".join(lines)

def _rules_text(rules: list[Rule]) -> str:
    return "\n\n".join(f"{r.id} [{r.type}]\nRule: {r.rule}\nHow to check: {r.check}\nEvidence needed: {r.evidence_needed}"
                       for r in rules)

def _user_prompt(app: Application, rules: list[Rule], rubric: Rubric) -> str:
    return (f"Grant: {rubric.grant}\nAllowed applicant types: {', '.join(rubric.allowed_applicant_types)}\n\n"
            f"RULES (return exactly one result per rule id: {', '.join(r.id for r in rules)}):\n\n{_rules_text(rules)}\n\n"
            f"APPLICATION (field path: value):\n{_app_fields(app)}")

# ---------- API ----------
def _call_claude(app: Application, rules: list[Rule], rubric: Rubric) -> dict[str, _AIRuleResult]:
    guard("Calling Claude")
    import anthropic
    client = anthropic.Anthropic()
    # Opus 5.5 does not accept temperature; consistency comes from the double run below.
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": _schema()}},
        system=SYSTEM,
        messages=[{"role": "user", "content": _user_prompt(app, rules, rubric)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to assess {app.id}")
    text = next(b.text for b in resp.content if b.type == "text")
    return {r.rule_id: r for r in _AIResponse.model_validate_json(text).results}

def _schema() -> dict:
    quote = {"type": "object", "properties": {"field": {"type": "string"}, "text": {"type": "string"}},
             "required": ["field", "text"], "additionalProperties": False}
    result = {"type": "object", "properties": {
        "rule_id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["met", "not_met", "insufficient_evidence", "needs_officer_judgement"]},
        "quotes": {"type": "array", "items": quote},
        "reasoning": {"type": "string"}, "missing": {"type": "string"}, "reason_value": {"type": "string"}},
        "required": ["rule_id", "verdict", "quotes", "reasoning", "missing", "reason_value"], "additionalProperties": False}
    return {"type": "object", "properties": {"results": {"type": "array", "items": result}},
            "required": ["results"], "additionalProperties": False}

# ---------- turning AI output into Cells ----------
_PLACEHOLDER = {"R09": "stated_purpose", "R10": "objective"}

def _to_cell(app: Application, rule: Rule, run1: Optional[_AIRuleResult], run2: Optional[_AIRuleResult]) -> Cell:
    if run1 is None or run2 is None:
        return Cell(application_id=app.id, rule_id=rule.id, verdict=Verdict.NEEDS_OFFICER_JUDGEMENT, checked_by="ai",
                    reasoning="The AI did not return a result for this rule.", ai_runs_agree=False)
    quotes = [verify_quote(app, Quote(field=q.field, text=q.text)) for q in run1.quotes]
    verified = [q for q in quotes if q.verified]
    dropped = len(quotes) - len(verified)
    verdict, reasoning = Verdict(run1.verdict), run1.reasoning
    agree = run1.verdict == run2.verdict

    if verdict == Verdict.NOT_MET and not verified:
        verdict, reasoning = Verdict.INSUFFICIENT_EVIDENCE, reasoning + " [AI suggested not met but gave no verifiable quote.]"
    needs_evidence = rule.id in GATES_NEEDING_EVIDENCE or (rule.custom and rule.type == "eligibility_gate")
    if verdict == Verdict.MET and needs_evidence and not verified:
        verdict, reasoning = Verdict.INSUFFICIENT_EVIDENCE, reasoning + " [No verifiable quote supports this.]"
    if not agree:
        verdict = Verdict.NEEDS_OFFICER_JUDGEMENT
        reasoning += f" [Two AI runs disagreed: {run1.verdict} vs {run2.verdict}.]"
    if rule.check_method == "officer_judgement" and verdict != Verdict.NEEDS_OFFICER_JUDGEMENT:
        reasoning = f"AI suggestion: {verdict.value}. " + reasoning
        verdict = Verdict.NEEDS_OFFICER_JUDGEMENT
    if dropped:
        reasoning += f" [{dropped} unverifiable quote(s) removed.]"

    values = {"item": run1.reason_value, "evidence": run1.reason_value} if rule.custom else \
             {"applicant_name": app.applicant.name} if rule.id == "R01" else \
             {_PLACEHOLDER.get(rule.id, "evidence" if "{evidence}" in rule.plain_english_reason else "item"): run1.reason_value}
    return Cell(application_id=app.id, rule_id=rule.id, verdict=verdict, checked_by="ai",
                applicant_quotes=verified, reasoning=reasoning.strip(), missing=run1.missing or None,
                reason_values=values, ai_runs_agree=agree)

def _officer_only_cell(app: Application, rule: Rule) -> Cell:
    return Cell(application_id=app.id, rule_id=rule.id, verdict=Verdict.NEEDS_OFFICER_JUDGEMENT, checked_by="officer",
                reasoning="Not assessed from the application. " + rule.check)

def _not_run_cell(app: Application, rule: Rule, why: str) -> Cell:
    return Cell(application_id=app.id, rule_id=rule.id, verdict=Verdict.NEEDS_OFFICER_JUDGEMENT, checked_by="ai",
                reasoning=f"AI check not run: {why}", missing="Run the AI checks or assess this rule manually.")

# ---------- cache ----------
def _cache_key(app: Application, rules: list[Rule]) -> str:
    blob = json.dumps([PROMPT_VERSION, reviewer_name(), app.model_dump(mode="json"), [r.model_dump(mode="json") for r in rules]],
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]

def _cache_path(app: Application):
    return CACHE_DIR / f"{app.id}.json"

def cached_cells(app: Application, rubric: Rubric) -> Optional[list[Cell]]:
    path, rules = _cache_path(app), ai_rules(rubric)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("key") != _cache_key(app, rules):
        return None   # application or rubric changed since the last run
    return [Cell.model_validate(c) for c in data["cells"]]

def run_ai_checks(app: Application, rubric: Rubric, call_api: bool = False) -> list[Cell]:
    """Cells for every non-code rule. Uses the cache; calls Claude only when call_api=True."""
    hit = None if is_demo() else cached_cells(app, rubric)
    if hit is not None:
        return hit
    rules = ai_rules(rubric)
    if not call_api:
        return [_officer_only_cell(app, r) if r.id in SKIP_AI else _not_run_cell(app, r, "not run yet for this application.")
                for r in rules]
    if not api_available():
        return [_officer_only_cell(app, r) if r.id in SKIP_AI else _not_run_cell(app, r, "no ANTHROPIC_API_KEY in .env.")
                for r in rules]

    asked = [r for r in rules if r.id not in SKIP_AI]
    if offline_mode():
        from engine.offline_reviewer import review
        call = lambda _: review(app, asked, rubric)
    else:
        call = lambda _: _call_claude(app, asked, rubric)
    with ThreadPoolExecutor(2) as pool:
        run1, run2 = pool.map(call, range(2))
    cells = [_officer_only_cell(app, r) if r.id in SKIP_AI else _to_cell(app, r, run1.get(r.id), run2.get(r.id))
             for r in rules]
    if is_demo():
        return cells   # public demo: no files written on the server (the app keeps results in the session)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(app).write_text(json.dumps({"key": _cache_key(app, rules), "model": reviewer_name(),
                                            "cells": [c.model_dump(mode="json") for c in cells]}, indent=2))
    return cells
