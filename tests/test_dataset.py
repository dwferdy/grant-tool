"""Runs every application in data/applications against the answer key in data/expected.json."""
import json, pytest
from collections import defaultdict
from engine.loader import load_rubric, load_applications, ROOT
from engine.code_checks import run_code_checks
from engine.models import Verdict

RB, APPS = load_rubric(), load_applications()
EXPECTED = {k: v for k, v in json.loads((ROOT / "data/expected.json").read_text()).items() if not k.startswith("_")}
PASSING = {Verdict.MET, Verdict.NOT_APPLICABLE}

def test_every_application_has_an_answer_key():
    assert set(APPS) == set(EXPECTED)

@pytest.mark.parametrize("aid", sorted(EXPECTED))
def test_code_verdicts_match_answer_key(aid):
    got = {c.rule_id: c.verdict for c in run_code_checks(APPS[aid], RB)}
    want = {r: Verdict(v) for r, v in EXPECTED[aid]["code"].items()}
    for rid, v in got.items():
        if rid in want:
            assert v == want[rid], f"{aid} {rid}: expected {want[rid].value}, got {v.value}"
        else:
            assert v in PASSING, f"{aid} {rid}: unexpected {v.value}"

@pytest.mark.parametrize("aid", sorted(EXPECTED))
def test_clarify_cases_are_never_rejected_by_code(aid):
    if EXPECTED[aid]["outcome"] == "clarify":
        assert all(c.verdict != Verdict.NOT_MET for c in run_code_checks(APPS[aid], RB))

def test_all_fairness_pairs_identical():
    pairs = defaultdict(list)
    for a in APPS.values():
        if a.pair_id: pairs[a.pair_id].append(a)
    assert len(pairs) >= 2
    for pid, members in pairs.items():
        results = [{c.rule_id: c.verdict for c in run_code_checks(a, RB)} for a in members]
        assert all(r == results[0] for r in results), f"Pair {pid} differs"
        assert members[0].budget == members[1].budget, f"Pair {pid}: budgets must be identical"
