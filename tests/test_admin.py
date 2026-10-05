"""Super admin features: user accounts and rules added in the app."""
import pytest
from engine import audit, users, rules_admin, ai_checks
from engine.loader import load_applications, load_rubric
from engine.code_checks import run_code_checks
from engine.ai_checks import run_ai_checks
from engine.models import Verdict

APPS = load_applications()

@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "DB", tmp_path / "audit.sqlite")
    monkeypatch.setattr(rules_admin, "CUSTOM_FILE", tmp_path / "custom_rules.json")
    monkeypatch.setattr(ai_checks, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("AI_MODE", "offline")

# ---------- users ----------
def test_password_is_hashed_and_verified():
    users.create("Admin", "Ada Admin", "super_admin", "correct horse", "setup")
    assert users.verify("admin", "correct horse") == {"username": "admin", "display_name": "Ada Admin", "role": "super_admin"}
    assert users.verify("admin", "wrong password") is None
    assert "correct horse" not in str(audit._rows("SELECT * FROM users"))

def test_user_rules():
    users.create("admin", "A", "super_admin", "password1", "setup")
    with pytest.raises(ValueError):
        users.create("admin", "B", "officer", "password1", "admin")      # duplicate
    with pytest.raises(ValueError):
        users.create("bob", "Bob", "officer", "short", "admin")          # weak password
    with pytest.raises(ValueError):
        users.create("eve", "Eve", "hacker", "password1", "admin")       # unknown role
    with pytest.raises(ValueError):
        users.set_active("admin", False)                                 # last super admin
    users.create("bob", "Bob", "officer", "password1", "admin")
    users.set_active("bob", False)
    assert users.verify("bob", "password1") is None

# ---------- custom rules ----------
def add(**kw):
    base = dict(by="admin", short_name="x", rule="x", check="x", evidence_needed="x", plain_english_reason="x")
    return rules_admin.add_rule(**{**base, **kw})

def test_official_rubric_is_untouched():
    add(check_method="officer_judgement", rtype="assessment_criterion")
    assert len(load_rubric().rules) == 26
    assert len(rules_admin.active_rubric().rules) == 27

def test_category_cap_template():
    p = {"template": "category_cap", "category": "marketing", "pct": 0.05}
    r = add(check_method="code", rtype="numeric_cap", params=p, **{k: v for k, v in
            rules_admin.code_rule_text("category_cap", p).items() if k == "plain_english_reason"})
    assert r.id == "C01"
    v = {c.rule_id: c for c in run_code_checks(APPS["A01"], rules_admin.active_rubric())}
    assert v["C01"].verdict == Verdict.NOT_MET          # A01 spends $700 of $8,000 on marketing (8.75%)
    assert v["C01"].reason_values["limit"] == "400.00"

def test_max_total_and_required_field_templates():
    add(check_method="code", rtype="numeric_cap", params={"template": "max_total", "amount": 7000})
    add(check_method="code", rtype="eligibility_gate", params={"template": "required_field", "field": "applicant.abn"})
    rb = rules_admin.active_rubric()
    a01 = {c.rule_id: c.verdict for c in run_code_checks(APPS["A01"], rb)}
    a03 = {c.rule_id: c.verdict for c in run_code_checks(APPS["A03"], rb)}
    assert a01["C01"] == Verdict.NOT_MET and a03["C01"] == Verdict.MET   # $8,000 vs $6,000
    assert a03["C02"] == Verdict.INSUFFICIENT_EVIDENCE                   # student group, no ABN -> ask, never reject

def test_custom_ai_exclusion_offline():
    add(check_method="ai_evidence", rtype="exclusion", keywords=["medals"])
    rb = rules_admin.active_rubric()
    c = {x.rule_id: x for x in run_ai_checks(APPS["A01"], rb, call_api=True)}["C01"]
    assert c.verdict == Verdict.NOT_MET and c.applicant_quotes[0].verified
    assert c.reason_values["evidence"] == "Participation medals"
    assert {x.rule_id: x for x in run_ai_checks(APPS["A02"], rb, call_api=True)}["C01"].verdict == Verdict.MET

def test_custom_ai_rule_without_keywords_goes_to_officer():
    add(check_method="ai_evidence", rtype="exclusion")
    c = {x.rule_id: x for x in run_ai_checks(APPS["A01"], rules_admin.active_rubric(), call_api=True)}["C01"]
    assert c.verdict == Verdict.NEEDS_OFFICER_JUDGEMENT

def test_switched_off_rule_is_not_checked_and_change_is_logged():
    add(check_method="code", rtype="numeric_cap", params={"template": "max_total", "amount": 1})
    rules_admin.set_active("C01", False, "admin")
    assert "C01" not in {r.id for r in rules_admin.active_rubric().rules}
    assert [c["action"] for c in audit.rule_changes()] == ["disabled", "added"]
