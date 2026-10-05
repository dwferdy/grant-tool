"""Combine code + AI cells into one row of the grid, and work out the suggested outcome."""
from __future__ import annotations
import string
from typing import Optional
from engine.models import Application, Rubric, Cell, Verdict
from engine.code_checks import run_code_checks
from engine.ai_checks import run_ai_checks

def assess(app: Application, rubric: Rubric, call_api: bool = False) -> dict[str, Cell]:
    cells = {c.rule_id: c for c in run_code_checks(app, rubric) + run_ai_checks(app, rubric, call_api)}
    return {r.id: cells[r.id] for r in rubric.rules}

def outcome(rubric: Rubric, verdicts: dict[str, Verdict], officer_decided: Optional[set[str]] = None) -> str:
    """approve | reject | clarify | officer_decides.
    officer_judgement rules count only once an officer has decided them (until then they always need a human)."""
    decided = officer_decided or set()
    counted = [verdicts[r.id] for r in rubric.rules if r.check_method != "officer_judgement" or r.id in decided]
    if Verdict.NOT_MET in counted:
        return "reject"
    if Verdict.INSUFFICIENT_EVIDENCE in counted:
        return "clarify"
    if Verdict.NEEDS_OFFICER_JUDGEMENT in counted:
        return "officer_decides"
    return "approve"

class _Blank(dict):
    def __missing__(self, key):
        return f"[{key}]"

def fill_reason(template: str, values: dict) -> str:
    """Fill {placeholders}; any value the engine could not supply stays visible as [name] for the officer to edit."""
    return string.Formatter().vformat(template, (), _Blank({k: v for k, v in values.items() if v}))
