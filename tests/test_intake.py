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
    assert app is None and "application form" in problems[0]

# ---------- the easy form (letters/email_template*.txt) ----------
def test_filled_example_form_is_a_clean_application():
    app, notes = intake.parse_application(intake.TEMPLATE_EXAMPLE.read_text(), "E900", "x@example.org", "today")
    assert app is not None and notes == []
    assert app.applicant.type == "nfp_incorporated" and app.applicant.nt_based is True
    assert str(app.project.start_date) == "2024-10-19"
    assert [b.category for b in app.budget] == ["venue_hire", "equipment_hire", "catering", "facilitator_fees", "marketing", "materials"]
    assert app.budget[1].item == "Bibs, balls and goal hire"          # commas inside an item name are kept
    assert app.total_requested == 8000 == sum(b.amount for b in app.budget)
    assert "Example:" not in app.project.description and "#" not in app.project.description
    passing = {Verdict.MET, Verdict.NOT_APPLICABLE}
    assert all(c.verdict in passing for c in run_code_checks(app, load_rubric()))

def test_blank_form_is_held_back_with_reasons_not_misread():
    app, problems = intake.parse_application(intake.TEMPLATE.read_text(), "E901", "x@example.org", "today")
    assert app is None and any("Start date" in p for p in problems)

def test_help_lines_and_left_over_hints_are_ignored():
    body = """Applicant name: Darwin Chess Club
# Your organisation or group. Example: Darwin Nepali Students Association
Applicant type: student group
NT based: (yes / no)
Project title: Chess Nights
Start date: 5 March 2025
End date: 05-03-2025
Who can attend: All international students in the NT.
Budget:
# One line per cost
- Room hire, venue hire, $300
- Pizza for 20 players, $200
- Chess sets | equipment hire | 150
-
"""
    app, notes = intake.parse_application(body, "E902", "x@example.org", "today")
    assert app.applicant.name == "Darwin Chess Club" and app.applicant.nt_based is None   # hint is not an answer
    assert app.applicant.type == "student_or_community_group"
    assert str(app.project.start_date) == str(app.project.end_date) == "2025-03-05"
    assert [(b.category, b.amount) for b in app.budget] == [("venue_hire", 300), ("other", 200), ("equipment_hire", 150)]
    assert any("Pizza for 20 players" in n and "'other'" in n for n in notes)   # officer is told about the guess
    assert app.total_requested == 650

# ---------- fillable PDF form (letters/application_form*.pdf) ----------
import io
from email.message import EmailMessage

def _fill(values: dict) -> bytes:
    """Fill the blank PDF the way a PDF viewer would."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(str(intake.PDF_FORM)))
    for page in w.pages:
        w.update_page_form_field_values(page, values, auto_regenerate=False)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()

FILLED = {"applicant_name": "Darwin Chess Club", "applicant_type": "Student or community group", "nt_based": "Yes",
          "contact_role": "President", "auspicing_body": "Darwin Multicultural Community Council Inc.", "auspice_confirmed": "Yes",
          "project_title": "Chess Nights", "description": "Four chess evenings for international students.\nBeginners welcome.",
          "location": "Darwin NT", "start_date": "05/03/2025", "end_date": "26/03/2025",
          "who_can_attend": "All international students in the NT. Free.", "wellbeing_benefit": "Friendship and focus.",
          "item_1": "Room hire", "cost_type_1": "Venue hire", "amount_1": "$300",
          "item_2": "Pizza for 20 players", "cost_type_2": "Choose", "amount_2": "200"}

def _email(attachment: bytes, mid: str) -> bytes:
    m = EmailMessage()
    m["From"], m["Subject"], m["Message-ID"] = "Ana <ana@example.org>", "Grant application - Chess Nights", mid
    m["Date"] = "Mon, 03 Feb 2025 10:00:00 +0930"
    m.set_content("Hello, our form is attached. Thanks, Ana")
    m.add_attachment(attachment, maintype="application", subtype="pdf", filename="our-application.pdf")
    return m.as_bytes()

def test_filled_example_pdf_matches_the_text_example():
    pdf_app, notes = intake.parse_application(intake.read_pdf_form(intake.PDF_FORM_EXAMPLE.read_bytes()), "E910", "x", "today")
    txt_app, _ = intake.parse_application(intake.TEMPLATE_EXAMPLE.read_text(), "E910", "x", "today")
    assert notes == [] and pdf_app.budget == txt_app.budget and pdf_app.total_requested == 8000
    assert pdf_app.applicant == txt_app.applicant and pdf_app.project.start_date == txt_app.project.start_date

def test_blank_pdf_dropdowns_are_not_answers():
    app, problems = intake.parse_application(intake.read_pdf_form(intake.PDF_FORM.read_bytes()), "E911", "x", "today")
    assert app is None and any("Start date" in p for p in problems)
    assert "Choose" not in intake.read_pdf_form(intake.PDF_FORM.read_bytes())

def test_emailed_pdf_form_becomes_application(isolated):
    r = intake.ingest(_email(_fill(FILLED), "<chess-1@example.org>"))
    assert r.application_id == "E001"
    # Accepted, with notes for the officer about what the applicant left out.
    assert any("'Pizza for 20 players'" in n and "'other'" in n for n in r.problems)
    assert any("Total requested not given" in n for n in r.problems)
    app = intake.load_received()["E001"]
    assert app.applicant.type == "student_or_community_group" and app.applicant.auspicing_body.confirmed
    assert app.project.description == "Four chess evenings for international students. Beginners welcome."
    assert [(b.item, b.category, b.amount) for b in app.budget] == [("Room hire", "venue_hire", 300), ("Pizza for 20 players", "other", 200)]
    assert app.total_requested == 500
    assert intake.original_pdf("E001").startswith(b"%PDF")
    assert "Attached form: our-application.pdf" in intake.original_email("E001")

def test_pdf_dropped_into_inbox_once_only(isolated):
    data = _fill(FILLED)
    first, again = intake.ingest_pdf(data, "chess.pdf"), intake.ingest_pdf(data, "chess.pdf")
    assert first.application_id == "E001" and again.problems == ["Already received."]

def test_pdf_that_is_not_our_form_is_explained(isolated):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf); c.drawString(100, 700, "Just a letter"); c.save()
    r = intake.ingest_pdf(buf.getvalue(), "letter.pdf")
    assert r.application_id is None and "isn't the grant application form" in r.problems[0]

# ---------- looser layouts: headings without colons, as copied from the app's application view ----------
LOOSE = """From: Darwin Multifaith Youth Network Inc. (nfp incorporated, Secretary)
ABN: 61 234 567 009 · NT based: yes
Project
Harmony Week Picnic
22 Mar 2025 → 22 Mar 2025 · Darwin NT
Description
A Harmony Week picnic in the Darwin Botanic Gardens with games, music and
food from students' home countries.
Who can attend
Open to all international students studying in the Northern Territory.
Wellbeing benefit
Social connection and wellbeing for international students.
Budget
Picnic area booking venue hire $1,000.00
Picnic food catering $1,500.00
Musicians facilitator fees $1,500.00
Total requested $4,000.00
"""

def test_headings_without_colons_are_read():
    app, notes = intake.parse_application(LOOSE, "E901", "x", "today")
    assert app is not None and notes == []
    a, p = app.applicant, app.project
    assert (a.name, a.type, a.contact_role, a.abn, a.nt_based) == \
        ("Darwin Multifaith Youth Network Inc.", "nfp_incorporated", "Secretary", "61 234 567 009", True)
    assert (p.title, p.location, str(p.start_date), str(p.end_date)) == ("Harmony Week Picnic", "Darwin NT", "2025-03-22", "2025-03-22")
    assert p.description.endswith("home countries.")
    assert [(b.item, b.category, b.amount) for b in app.budget] == [
        ("Picnic area booking", "venue_hire", 1000), ("Picnic food", "catering", 1500), ("Musicians", "facilitator_fees", 1500)]
    assert app.total_requested == 4000

def test_thousands_comma_is_not_a_separator():
    item, note = intake._budget_line("- Hall hire, venue hire, $2,500.00")
    assert item == {"item": "Hall hire", "category": "venue_hire", "amount": 2500} and note is None

def _eml(body, mid="<loose@test>"):
    return (f"From: Jimmy <j@example.org>\nSubject: Grant application\nMessage-ID: {mid}\n"
            f"Content-Type: text/plain; charset=utf-8\n\n{body}").encode()

def test_unreadable_email_is_retried_after_the_parser_improves(isolated, monkeypatch):
    real = intake.parse_application
    monkeypatch.setattr(intake, "parse_application", lambda *a: (None, ["old parser"]))
    first = intake.ingest(_eml(LOOSE))
    assert first.application_id is None and len(audit.unreadable_mail()) == 1
    again = intake.ingest(_eml(LOOSE))
    assert again.problems == ["Already received."]            # still unreadable: no second warning
    monkeypatch.setattr(intake, "parse_application", real)
    fixed = intake.ingest(_eml(LOOSE))
    assert fixed.application_id == "E001" and audit.unreadable_mail() == []

def test_dismissed_email_is_hidden_and_not_retried(isolated):
    intake.ingest(_eml("Hi, can I apply?", "<hello@test>"))
    [m] = audit.unreadable_mail()
    audit.dismiss_mail(m["message_id"])
    assert audit.unreadable_mail() == []
    r = intake.ingest(_eml("Hi, can I apply?", "<hello@test>"))
    assert r.application_id is None and r.problems == ["Already received."]
