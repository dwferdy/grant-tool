"""Safeguards around the AI output. No API calls: fake model results are fed into the post-processing."""
import pytest
from engine.loader import load_rubric, load_applications
from engine.ai_checks import _to_cell, _AIRuleResult, _AIQuote, run_ai_checks, cached_cells
from engine.assess import assess, outcome, fill_reason
from engine.models import Verdict

RB, APPS = load_rubric(), load_applications()
RULES = {r.id: r for r in RB.rules}

def res(rid, verdict, quotes=(), value=""):
    return _AIRuleResult(rule_id=rid, verdict=verdict, quotes=[_AIQuote(field=f, text=t) for f, t in quotes],
                         reasoning="x", missing="", reason_value=value)

def test_verified_quote_keeps_not_met():
    r = res("R22", "not_met", [("budget[2].item", "Beer and wine package")], "Beer and wine package")
    c = _to_cell(APPS["A02"], RULES["R22"], r, r)
    assert c.verdict == Verdict.NOT_MET and c.applicant_quotes[0].verified
    assert c.reason_values == {"item": "Beer and wine package"}

def test_invented_quote_cannot_reject():
    r = res("R18", "not_met", [("project.description", "profits go to shareholders")])
    c = _to_cell(APPS["A02"], RULES["R18"], r, r)
    assert c.verdict == Verdict.INSUFFICIENT_EVIDENCE and c.applicant_quotes == []

def test_gate_met_needs_evidence():
    r = res("R07", "met")
    assert _to_cell(APPS["A01"], RULES["R07"], r, r).verdict == Verdict.INSUFFICIENT_EVIDENCE

def test_runs_disagree_goes_to_officer():
    c = _to_cell(APPS["A01"], RULES["R19"], res("R19", "met"), res("R19", "not_met"))
    assert c.verdict == Verdict.NEEDS_OFFICER_JUDGEMENT and c.ai_runs_agree is False

def test_officer_judgement_rules_never_decided_by_ai():
    r = res("R09", "met", [("project.wellbeing_benefit", APPS["A01"].project.wellbeing_benefit[:20])])
    c = _to_cell(APPS["A01"], RULES["R09"], r, r)
    assert c.verdict == Verdict.NEEDS_OFFICER_JUDGEMENT and c.reasoning.startswith("AI suggestion: met")

def test_no_api_call_without_permission():
    cells = run_ai_checks(APPS["A01"], RB, call_api=False)
    assert {c.rule_id for c in cells} == {r.id for r in RB.rules if r.check_method != "code"}

def test_grid_has_every_rule():
    assert list(assess(APPS["A01"], RB)) == [r.id for r in RB.rules]

def test_outcome_priority():
    base = {r.id: Verdict.MET for r in RB.rules}
    assert outcome(RB, base) == "approve"
    assert outcome(RB, {**base, "R09": Verdict.NOT_MET}) == "approve"          # officer rule not yet decided
    assert outcome(RB, {**base, "R09": Verdict.NOT_MET}, {"R09"}) == "reject"
    assert outcome(RB, {**base, "R07": Verdict.INSUFFICIENT_EVIDENCE}) == "clarify"
    assert outcome(RB, {**base, "R07": Verdict.INSUFFICIENT_EVIDENCE, "R16": Verdict.NOT_MET}) == "reject"

def test_fill_reason_leaves_gaps_visible():
    assert fill_reason("Item {item} costs {amount}", {"item": "beer"}) == "Item beer costs [amount]"

@pytest.mark.parametrize("pair", [("A04", "A05"), ("A14", "A15")])
def test_ai_fairness_pair(pair):
    """Runs only after AI checks have been cached (streamlit button or scripts/run_ai_checks.py)."""
    a, b = (cached_cells(APPS[x], RB) for x in pair)
    if a is None or b is None:
        pytest.skip("AI results not cached yet")
    assert {c.rule_id: c.verdict for c in a} == {c.rule_id: c.verdict for c in b}

# ---------- offline keyword reviewer (AI_MODE=offline) ----------
import json
from engine import ai_checks
from engine.loader import ROOT
EXPECTED = {k: v for k, v in json.loads((ROOT / "data/expected.json").read_text()).items() if not k.startswith("_")}

@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "offline")
    monkeypatch.setattr(ai_checks, "CACHE_DIR", tmp_path)

@pytest.mark.parametrize("aid", sorted(EXPECTED))
def test_offline_reviewer_matches_answer_key(offline, aid):
    cells = {c.rule_id: c for c in run_ai_checks(APPS[aid], RB, call_api=True)}
    for r in RB.rules:
        if r.check_method == "ai_evidence":
            want = Verdict(EXPECTED[aid]["ai"].get(r.id, "met"))
            assert cells[r.id].verdict == want, f"{aid} {r.id}: {cells[r.id].reasoning}"
    assert outcome(RB, {k: c.verdict for k, c in assess(APPS[aid], RB).items()}) == EXPECTED[aid]["outcome"]

def test_offline_fairness_pairs(offline):
    for a, b in [("A04", "A05"), ("A14", "A15")]:
        va = {c.rule_id: c.verdict for c in run_ai_checks(APPS[a], RB, call_api=True)}
        vb = {c.rule_id: c.verdict for c in run_ai_checks(APPS[b], RB, call_api=True)}
        assert va == vb
