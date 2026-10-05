"""Rules checked by plain code: 100% consistent, no AI involved."""
from __future__ import annotations
import re
from engine.models import Application, Rubric, Cell, Verdict, Quote

def _cell(app, rid, verdict, reasoning, missing=None, **values):
    return Cell(application_id=app.id, rule_id=rid, verdict=verdict, checked_by="code",
                reasoning=reasoning, missing=missing, reason_values=values)

def _cat_sum(app, cat):
    return round(sum(b.amount for b in app.budget if b.category == cat), 2)

def _cap(app, rid, cat, pct, label):
    amount, total = _cat_sum(app, cat), app.total_requested
    limit = round(pct * total, 2)
    ok = amount <= limit
    return _cell(app, rid, Verdict.MET if ok else Verdict.NOT_MET,
                 f"{label}: ${amount:,.2f} of ${total:,.2f} ({amount/total:.0%}); limit {pct:.0%} = ${limit:,.2f}.",
                 None if ok else f"Reduce {label.lower()} to ${limit:,.2f} or less.",
                 amount=f"{amount:,.2f}", limit=f"{limit:,.2f}")

def check_r02(app, rb):
    a = app.applicant
    if a.type not in ("registered_business", "nfp_incorporated"):
        return _cell(app, "R02", Verdict.NOT_APPLICABLE, f"Applicant type '{a.type}' - ABN rule does not apply.")
    if a.abn or (a.auspicing_body and a.auspicing_body.name):
        return _cell(app, "R02", Verdict.MET, "ABN or auspicing body provided.")
    return _cell(app, "R02", Verdict.INSUFFICIENT_EVIDENCE, "No ABN and no auspicing body.", "ABN or auspicing body name")

def check_r03(app, rb):
    a = app.applicant
    if a.type != "student_or_community_group":
        return _cell(app, "R03", Verdict.NOT_APPLICABLE, f"Applicant type '{a.type}' - auspicing rule does not apply.")
    ab = a.auspicing_body
    if ab and ab.name and ab.confirmed:
        return _cell(app, "R03", Verdict.MET, f"Auspicing body '{ab.name}' named and confirmed.")
    return _cell(app, "R03", Verdict.INSUFFICIENT_EVIDENCE,
                 "Auspicing body not named or not confirmed." + (f" Applicant wrote: '{ab.name}'." if ab and ab.name else ""),
                 "Name of the auspicing body and written confirmation it agrees")

def check_r06(app, rb):
    r, p = rb.round, app.project
    ok = r.window_start <= p.start_date and p.end_date <= r.window_end
    return _cell(app, "R06", Verdict.MET if ok else Verdict.NOT_MET,
                 f"Event {p.start_date} to {p.end_date}; window {r.window_start} to {r.window_end}.",
                 None if ok else "Event dates inside the funding window",
                 start_date=str(p.start_date), end_date=str(p.end_date))

def check_r08(app, rb):
    d = rb.round.earliest_approval_date
    ok = app.project.start_date > d
    return _cell(app, "R08", Verdict.MET if ok else Verdict.NOT_MET,
                 f"Starts {app.project.start_date}; earliest approval {d} (assumed).",
                 start_date=str(app.project.start_date), earliest_approval_date=str(d))

REQUIRED = ["applicant.name","applicant.type","project.title","project.description",
            "project.start_date","project.end_date","project.who_can_attend"]
def check_r11(app, rb):
    data = app.model_dump()
    missing = [f for f in REQUIRED if not data[f.split('.')[0]].get(f.split('.')[1])]
    if not app.budget: missing.append("budget")
    return _cell(app, "R11", Verdict.INSUFFICIENT_EVIDENCE if missing else Verdict.MET,
                 "Missing: " + ", ".join(missing) if missing else "All required fields present.",
                 ", ".join(missing) or None, missing_fields=", ".join(missing))

def check_r12(app, rb):
    ok = app.total_requested <= 10000
    return _cell(app, "R12", Verdict.MET if ok else Verdict.NOT_MET,
                 f"Requested ${app.total_requested:,.2f}; maximum $10,000.", total_requested=f"{app.total_requested:,.2f}")

def check_r13(app, rb):
    s = round(sum(b.amount for b in app.budget), 2)
    ok = abs(s - app.total_requested) < 0.01
    return _cell(app, "R13", Verdict.MET if ok else Verdict.INSUFFICIENT_EVIDENCE,
                 f"Budget lines sum to ${s:,.2f}; requested ${app.total_requested:,.2f}.",
                 None if ok else "Budget lines that add up to the total",
                 budget_sum=f"{s:,.2f}", total_requested=f"{app.total_requested:,.2f}")

CHECKS = {
  "R02": check_r02, "R03": check_r03, "R06": check_r06, "R08": check_r08, "R11": check_r11,
  "R12": check_r12, "R13": check_r13,
  "R14": lambda a, rb: _cap(a, "R14", "travel", 0.50, "Travel"),
  "R15": lambda a, rb: _cap(a, "R15", "facilitator_fees", 0.50, "Facilitator fees"),
  "R16": lambda a, rb: _cap(a, "R16", "catering", 0.25, "Catering"),
}

def run_code_checks(app: Application, rubric: Rubric) -> list[Cell]:
    code_rules = [r.id for r in rubric.rules if r.check_method == "code"]
    assert set(code_rules) == set(CHECKS), f"Rubric/code mismatch: {set(code_rules) ^ set(CHECKS)}"
    return [CHECKS[rid](app, rubric) for rid in code_rules]

# ---------- Anti-hallucination guard ----------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u2019", "'").replace("\u2018", "'")
                  .replace("\u201c", '"').replace("\u201d", '"')).strip().lower()

def field_text(app: Application, field: str) -> str:
    """Resolve 'project.description' or 'budget[2].item' to its text."""
    m = re.fullmatch(r"budget\[(\d+)\]\.(\w+)", field)
    if m:
        return str(getattr(app.budget[int(m[1])], m[2]))
    obj = app
    for part in field.split("."):
        obj = getattr(obj, part)
    return "" if obj is None else str(obj)

def verify_quote(app: Application, q: Quote) -> Quote:
    """A quote counts only if it appears verbatim (ignoring whitespace/case/curly quotes) in the cited field."""
    try:
        ok = len(q.text.strip()) > 0 and _norm(q.text) in _norm(field_text(app, q.field))
    except (AttributeError, IndexError):
        ok = False
    return q.model_copy(update={"verified": ok})
