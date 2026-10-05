"""Plain-English letter to the applicant, built from the rubric's plain_english_reason."""
from __future__ import annotations
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from engine.loader import ROOT
from engine.models import Application, Rubric, Cell, Verdict, OfficerDecision
from engine.assess import fill_reason

_ENV = Environment(loader=FileSystemLoader(ROOT / "letters"))
REASON_VERDICT = {"reject": Verdict.NOT_MET, "clarify": Verdict.INSUFFICIENT_EVIDENCE}

def render_letter(rubric: Rubric, app: Application, outcome: str, cells: dict[str, Cell],
                  verdicts: dict[str, Verdict], decisions: dict[str, OfficerDecision],
                  officer: str, final_note: Optional[str] = None) -> str:
    want = REASON_VERDICT.get(outcome)
    reasons = [{"rule_id": r.id, "source": f"{r.source.document}, {r.source.section}",
                "text": fill_reason(r.plain_english_reason, cells[r.id].reason_values),
                "officer_note": decisions[r.id].officer_note if r.id in decisions else None}
               for r in rubric.rules if want and verdicts[r.id] == want]
    return _ENV.get_template("decision_letter.txt.j2").render(
        applicant_name=app.applicant.name, grant=rubric.grant, round_name=rubric.round.name,
        project_title=app.project.title, application_id=app.id, outcome=outcome, reasons=reasons,
        final_note=final_note, officer=officer or "[officer name]")
