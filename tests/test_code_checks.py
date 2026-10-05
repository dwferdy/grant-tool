import pytest
from engine.loader import load_rubric, load_applications
from engine.code_checks import run_code_checks, verify_quote
from engine.models import Quote, Verdict

RB, APPS = load_rubric(), load_applications()
def verdicts(aid): return {c.rule_id: c.verdict for c in run_code_checks(APPS[aid], RB)}

def test_a01_all_code_rules_pass():
    assert all(v in (Verdict.MET, Verdict.NOT_APPLICABLE) for v in verdicts("A01").values())

def test_a02_catering_over_cap():
    v = verdicts("A02")
    assert v["R16"] == Verdict.NOT_MET   # $4,500 of $10,000 = 45% > 25%

def test_a03_auspice_unconfirmed_is_insufficient_not_rejected():
    v = verdicts("A03")
    assert v["R03"] == Verdict.INSUFFICIENT_EVIDENCE
    assert Verdict.NOT_MET not in v.values()

def test_fairness_pair_identical_code_verdicts():
    assert verdicts("A04") == verdicts("A05")

def test_quote_guard_accepts_verbatim_and_rejects_invented():
    a = APPS["A02"]
    assert verify_quote(a, Quote(field="budget[2].item", text="Beer and wine package")).verified
    assert verify_quote(a, Quote(field="project.description", text="any SURPLUS will be retained")).verified
    assert not verify_quote(a, Quote(field="project.description", text="profits go to shareholders")).verified
    assert not verify_quote(a, Quote(field="budget[99].item", text="x")).verified
    assert not verify_quote(a, Quote(field="project.description", text="   ")).verified
