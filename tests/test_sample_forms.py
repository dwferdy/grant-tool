"""PDF dataset (data/sample_forms, built by scripts/build_sample_forms.py): every filled form, dropped in directly or
attached to an email, must reach the expected outcome with the offline reviewer. No network."""
import csv
import pytest
from engine import intake, audit, ai_checks
from engine.assess import assess, outcome
from engine.loader import ROOT, load_rubric

FORMS = ROOT / "data/sample_forms"
CASES = list(csv.DictReader((FORMS / "expected_results.csv").open()))
RB = load_rubric()

@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "offline")
    monkeypatch.setattr(ai_checks, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(intake, "RECEIVED_DIR", tmp_path / "received")
    monkeypatch.setattr(audit, "DB", tmp_path / "audit.sqlite")

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
@pytest.mark.parametrize("route", ["pdf", "email_with_pdf"])
def test_sample_form_reaches_expected_outcome(isolated, case, route):
    path = FORMS / case[route]
    r = intake.ingest_pdf(path.read_bytes(), path.name) if route == "pdf" else intake.ingest(path.read_bytes())
    assert r.application_id, r.problems
    app = intake.load_received()[r.application_id]
    cells = assess(app, RB, call_api=True)          # offline mode: the free keyword reviewer, no API call
    assert outcome(RB, {k: c.verdict for k, c in cells.items()}) == case["expected_outcome"]
    if route == "email_with_pdf":
        assert intake.original_pdf(r.application_id) == (FORMS / case["pdf"]).read_bytes()
