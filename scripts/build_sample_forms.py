"""Test dataset for the PDF route: the 10 dummy text emails (D01-D10) rebuilt as filled PDF forms.

For every case it writes two files to data/sample_forms/:
  Dxx_name.pdf  the filled application form: drag it straight into the Inbox
  Dxx_name.eml  a short email with that PDF attached: what a real applicant sends (drag it in, or forward it
                to the connected mailbox)
plus expected_results.csv (the answer key, same outcomes as the text emails).

Each PDF is read back with the app's own parser and must give the same application as the text email.
Run from the project root:
  .venv/bin/python scripts/build_sample_forms.py [folder with the D01-D10 .eml files, default ~/Downloads/dummy-emails-10]
"""
import csv, email, sys
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_application_form import Form            # noqa: E402
from engine import intake                         # noqa: E402
from engine.loader import ROOT                    # noqa: E402

OUT = ROOT / "data/sample_forms"
TYPE_LABEL = {"nfp_incorporated": "Not-for-profit organisation", "student_or_community_group": "Student or community group",
              "education_provider": "Education provider", "registered_business": "Registered business"}
COST_LABEL = {"venue_hire": "Venue hire", "catering": "Catering", "travel": "Travel", "facilitator_fees": "Facilitator fees",
              "equipment_hire": "Equipment hire", "materials": "Materials", "marketing": "Marketing", "other": "Other"}


def yes_no(v):
    return "Choose" if v is None else "Yes" if v else "No"


def money(x: float) -> str:
    return f"{x:g}"


def form_values(app) -> dict:
    a, p = app.applicant, app.project
    return {
        "applicant_name": a.name, "applicant_type": TYPE_LABEL.get(a.type, "Choose one"), "abn": a.abn or "",
        "nt_based": yes_no(a.nt_based), "contact_role": a.contact_role or "",
        "auspicing_body": a.auspicing_body.name if a.auspicing_body else "",
        "auspice_confirmed": yes_no(a.auspicing_body.confirmed) if a.auspicing_body else "Choose",
        "project_title": p.title, "description": p.description, "location": p.location,
        "start_date": p.start_date.strftime("%d/%m/%Y"), "end_date": p.end_date.strftime("%d/%m/%Y"),
        "who_can_attend": p.who_can_attend, "wellbeing_benefit": p.wellbeing_benefit,
        "budget": [(b.item, COST_LABEL[b.category], money(b.amount)) for b in app.budget],
        "total_requested": money(app.total_requested),
    }


def same(a, b) -> bool:
    keep = lambda x: x.model_dump(exclude={"id", "test_purpose"})
    return keep(a) == keep(b)


def main(src: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((src / "expected_results.csv").open()))
    for row in rows:
        eml = src / row["file"]
        msg = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
        text_app, notes = intake.parse_application(intake._body_text(msg), row["id"], "x", "t")
        assert text_app, f"{eml.name}: {notes}"

        stem = eml.stem
        pdf_path = OUT / f"{stem}.pdf"
        Form(str(pdf_path), form_values(text_app)).build()
        pdf = pdf_path.read_bytes()
        pdf_app, _ = intake.parse_application(intake.read_pdf_form(pdf), row["id"], "x", "t")
        assert pdf_app and same(text_app, pdf_app), f"{stem}: the PDF doesn't read back as the same application"

        name, addr = parseaddr(msg["From"])
        out = EmailMessage()
        out["From"], out["To"] = msg["From"], msg["To"]
        out["Subject"] = f"Grant application - {text_app.project.title}"
        out["Date"] = msg["Date"]
        out["Message-ID"] = f"<form-{row['id'].lower()}@example.org>"
        out.set_content(f"Hello,\n\nPlease find our grant application form attached.\n\n"
                        f"Kind regards,\n{name or addr}\n{text_app.applicant.name}\n")
        out.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"Application form - {text_app.project.title}.pdf")
        (OUT / f"{stem}.eml").write_bytes(bytes(out))
        row["pdf"], row["email_with_pdf"] = pdf_path.name, f"{stem}.eml"
        print(f"{row['id']}  {stem}.pdf + .eml  -> expected {row['expected_outcome']}")

    with (OUT / "expected_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "pdf", "email_with_pdf", "scenario", "expected_outcome", "rules_flagged"])
        w.writeheader()
        w.writerows({k: r[k] for k in w.fieldnames} for r in rows)
    print(f"written: {OUT.relative_to(ROOT)}/ ({len(rows)} PDFs, {len(rows)} emails, expected_results.csv)")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "Downloads/dummy-emails-10")
