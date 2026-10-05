"""Email intake: template parsing and the .eml samples. No network."""
import pytest
from engine import intake, audit
from engine.loader import ROOT, load_rubric
from engine.code_checks import run_code_checks
from engine.models import Verdict

SAMPLES = ROOT / "data/sample_emails"

@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(intake, "RECEIVED_DIR", tmp_path / "received")
    monkeypatch.setattr(audit, "DB", tmp_path / "audit.sqlite")

def test_sample_email_becomes_application(isolated):
    r = intake.ingest((SAMPLES / "darwin_soccer.eml").read_bytes())
    assert r.application_id == "E001" and r.problems == []
    app = intake.load_received()["E001"]
    assert app.applicant.type == "nfp_incorporated" and app.applicant.nt_based is True
    assert app.total_requested == 4000 and sum(b.amount for b in app.budget) == 4000
    assert [b.category for b in app.budget] == ["venue_hire", "equipment_hire", "catering", "facilitator_fees", "marketing"]
    assert "tropical heat" in app.project.description          # multi-line value joined
    assert "Maria Santos" not in app.project.wellbeing_benefit  # signature ignored
    assert intake.original_email("E001").startswith("From: Maria Santos")

def test_same_email_is_not_processed_twice(isolated):
    raw = (SAMPLES / "darwin_soccer.eml").read_bytes()
    intake.ingest(raw)
    again = intake.ingest(raw)
    assert again.application_id == "E001" and again.problems == ["Already received."]
    assert len(intake.load_received()) == 1

def test_unreadable_dates_are_held_back_with_reasons(isolated):
    r = intake.ingest((SAMPLES / "bad_dates.eml").read_bytes())
    assert r.application_id is None
    assert any("Start date" in p for p in r.problems) and any("End date" in p for p in r.problems)
    assert audit.unreadable_mail()[0]["sender"].startswith("Tom Nguyen")

def test_missing_fields_become_clarification_not_rejection():
    body = "Applicant name: X Club\nProject title: Walks\nStart date: 2025-03-01\nEnd date: 2025-03-02\n" \
           "Budget:\n- Bus | travel | 500\n"
    app, notes = intake.parse_application(body, "E009", "x@example.org", "today")
    assert app and app.total_requested == 500 and any("sum of the budget" in n for n in notes)
    v = {c.rule_id: c.verdict for c in run_code_checks(app, load_rubric())}
    assert v["R11"] == Verdict.INSUFFICIENT_EVIDENCE

def test_not_a_template_email():
    app, problems = intake.parse_application("Hi, can I apply for the grant?", "E010", "x", "today")
    assert app is None and "template" in problems[0]
