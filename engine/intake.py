"""Email intake: mailbox (IMAP) or .eml file -> Application JSON in data/received/.

Applicants fill in the PDF form letters/application_form.pdf (built by scripts/build_application_form.py) and
attach it to an email, or an officer drops the PDF straight into the inbox. The older plain-text form in the
email body (letters/email_template.txt) still works.
Parsing is plain code: nothing is guessed. A field that is missing stays empty, so R11 (complete application)
flags it and the applicant is asked to clarify. Only unreadable dates block intake, because the
Application contract requires them.

.env settings (usually written by the in-app "Connect a mailbox" wizard, see engine/mail_settings.py):
  MAIL_IMAP_HOST=imap.gmail.com
  MAIL_USER=you@gmail.com
  MAIL_PASSWORD=<16-character Google App Password, not your normal password>
  MAIL_FOLDER=INBOX
  MAIL_SUBJECT=Grant application        # only emails whose subject contains this are read
"""
from __future__ import annotations
import email, hashlib, imaplib, json, os, re
from dataclasses import dataclass, field
from datetime import date, datetime
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional
from engine.loader import ROOT
from engine.models import Application
from engine import audit

RECEIVED_DIR = ROOT / "data/received"
TEMPLATE = ROOT / "letters/email_template.txt"
TEMPLATE_EXAMPLE = ROOT / "letters/email_template_example.txt"
PDF_FORM = ROOT / "letters/application_form.pdf"
PDF_FORM_EXAMPLE = ROOT / "letters/application_form_example.pdf"
# PDF field name -> label understood by parse_application. Must match scripts/build_application_form.py.
PDF_FIELDS = {
    "applicant_name": "Applicant name", "applicant_type": "Applicant type", "abn": "ABN", "nt_based": "NT based",
    "contact_role": "Contact role", "auspicing_body": "Auspicing body", "auspice_confirmed": "Auspicing body confirmed",
    "project_title": "Project title", "description": "Description", "location": "Location", "start_date": "Start date",
    "end_date": "End date", "who_can_attend": "Who can attend", "wellbeing_benefit": "Wellbeing benefit",
    "total_requested": "Total requested",
}
PDF_BUDGET_ROWS = 10
PDF_PLACEHOLDERS = {"choose", "choose one"}

LABELS = {
    "applicant name": "name", "applicant type": "type", "abn": "abn", "nt based": "nt_based",
    "contact role": "contact_role", "auspicing body": "auspice", "auspicing body confirmed": "auspice_confirmed",
    "project title": "title", "description": "description", "location": "location", "start date": "start_date",
    "end date": "end_date", "who can attend": "who_can_attend", "wellbeing benefit": "wellbeing_benefit",
    "budget": "budget", "total requested": "total",
    # the same fields as they are labelled in the PDF form and in the app's own application view
    "organisation or group name": "name", "organisation": "name", "organization": "name", "type of applicant": "type",
    "your role": "contact_role", "event name": "title", "project": "title", "event": "title",
    "what will happen, and why?": "description", "where": "location", "who can attend?": "who_can_attend",
    "how will it help students' wellbeing?": "wellbeing_benefit", "total": "total", "total requested ($)": "total",
}
# Labels that may also be written without a colon on the same line ("Total requested $6,000"), when the value is short.
INLINE_NO_COLON = {"abn", "nt based", "total requested", "total", "start date", "end date", "contact role"}
COST_NAMES = {"venue hire": "venue_hire", "equipment hire": "equipment_hire", "facilitator fees": "facilitator_fees",
              "facilitator fee": "facilitator_fees", "catering": "catering", "travel": "travel", "materials": "materials",
              "marketing": "marketing", "other": "other"}
_DATE = r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2} [A-Za-z]+,? \d{4}|[A-Za-z]+ \d{1,2},? \d{4}"
DATE_RANGE = re.compile(rf"^\s*({_DATE})\s*(?:→|->|–|—|-|to|until)\s*({_DATE})\s*(?:[·|,]\s*(.+))?$", re.I)
TYPES = [("not-for-profit", "nfp_incorporated"), ("nfp", "nfp_incorporated"), ("incorporated", "nfp_incorporated"),
         ("education", "education_provider"), ("provider", "education_provider"), ("business", "registered_business"),
         ("company", "registered_business"), ("student", "student_or_community_group"), ("community", "student_or_community_group")]
CATEGORIES = ["travel", "facilitator_fees", "catering", "venue_hire", "equipment_hire", "materials", "marketing", "other"]
# Everyday words applicants use for a cost type (checked after the exact names).
CATEGORY_WORDS = {
    "travel": ("transport", "bus", "coach", "flight", "fuel", "taxi"),
    "facilitator_fees": ("facilitator", "speaker", "trainer", "teacher", "instructor", "presenter", "consultant", "fee"),
    "catering": ("food", "meal", "lunch", "dinner", "breakfast", "snack", "drink", "refreshment"),
    "venue_hire": ("venue", "hall", "room", "space", "court"),
    "equipment_hire": ("equipment",),
    "materials": ("material", "supplies", "printing"),
    "marketing": ("promotion", "advertising", "poster", "flyer"),
}

@dataclass
class IntakeResult:
    message_id: str
    sender: str
    subject: str
    application_id: Optional[str] = None
    problems: list = field(default_factory=list)

def mail_configured() -> bool:
    from engine.ai_checks import _load_env
    _load_env()
    return all(os.environ.get(k) for k in ("MAIL_IMAP_HOST", "MAIL_USER", "MAIL_PASSWORD"))

# ---------- parsing ----------
def _body_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
    return text

def _lines(body: str) -> list[str]:
    """Body lines, rewritten into 'Label: value' form where an applicant used a looser layout:
    'ABN: 1 · NT based: yes' (two fields on one line), '22 Mar 2025 → 22 Mar 2025 · Darwin NT' (dates and place),
    'From: Group Inc. (nfp incorporated, Secretary)' (name, type and role)."""
    out = []
    for line in body.splitlines():
        m = DATE_RANGE.match(line)
        if m:
            out += [f"Start date: {m[1]}", f"End date: {m[2]}"] + ([f"Location: {m[3].strip()}"] if m[3] else [])
            continue
        m = re.match(r"^\s*from\s*:\s*([^<(]+?)\s*(?:\((.+)\))?\s*(?:<.*>)?\s*$", line, re.I)
        if m:
            out.append(f"Applicant name: {m[1]}")
            if m[2]:
                kind, _, role = m[2].partition(",")
                out += [f"Applicant type: {kind.strip()}"] + ([f"Contact role: {role.strip()}"] if role.strip() else [])
            out.append("")      # a From line is one line only, never continued
            continue
        if " · " in line and line.count(":") >= 2:
            out += line.split(" · ")
            continue
        out.append(line)
    return out

def _fields(body: str) -> dict:
    """Split the body into template fields. A value may continue over several lines until the next label.
    A label may be followed by a colon and the value, or stand alone as a heading with the value below it."""
    out, current = {}, None
    alts = "|".join(sorted(map(re.escape, LABELS), key=len, reverse=True))
    label_re = re.compile(rf"^\s*({alts})\s*:\s*(.*)$", re.I)
    heading_re = re.compile(rf"^\s*({alts})\s*:?\s*$", re.I)
    inline_re = re.compile(rf"^\s*({'|'.join(map(re.escape, INLINE_NO_COLON))})\s+([^:]{{1,40}})$", re.I)
    for line in _lines(body):
        if line.strip() in ("--", "-- "):      # email signature
            break
        if line.startswith(">"):               # quoted reply
            continue
        stripped = line.strip()
        if not stripped:
            if current == "name":              # end of a one-line From
                current = None
            continue
        if stripped.startswith("#") or stripped.startswith("==") or stripped in ("-", "•", "*"):
            continue                           # help text, section headings, empty budget bullets
        m = label_re.match(line) or heading_re.match(line) or inline_re.match(line)
        if m:
            current = LABELS[m[1].lower()]
            value = m[2].strip() if m.lastindex and m.lastindex >= 2 else ""
            if re.fullmatch(r"\(.*\)|<.*>", value):   # an old-style "(yes / no)" hint left in place
                value = ""
            if current in out and current in ("type", "contact_role") and not value:
                continue
            out[current] = [value] if value else []
        elif current and stripped:
            out[current].append(stripped)
    return out

def _join(v) -> str:
    return " ".join(v or []).strip()

def _date(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y",
                "%d %B, %Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None

def _money(s: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*(\.\d+)?", s or "")
    return float(m[0].replace(",", "")) if m else None

def _yes(s: str) -> Optional[bool]:
    s = s.strip().lower()
    return True if s.startswith(("y", "ya", "iya")) else False if s.startswith(("n", "tidak")) else None

def _category(s: str) -> Optional[str]:
    """The cost type named in s, or None if s doesn't name one."""
    s = s.strip().lower().replace(" ", "_")
    exact = next((c for c in CATEGORIES if c == s or c.split("_")[0] in s), None)
    if exact:
        return exact
    return next((c for c, words in CATEGORY_WORDS.items() if any(w in s for w in words)), None)

def _budget_line(line: str) -> tuple[Optional[dict], Optional[str]]:
    """'Hall hire, venue hire, $2000' or 'Hall hire | venue hire | 2000' or 'Hall hire $2000'.
    Returns (budget item or None, intake note or None)."""
    text = line.lstrip("-•* ").strip()
    sep = "|" if "|" in text else ","
    # never split inside an amount like $1,000.00
    parts = [p.strip() for p in (text.split("|") if sep == "|" else re.split(r",(?!\d{3}\b)", text))]
    joiner = ", " if sep == "," else " | "      # rebuild an item name that itself contained the separator
    amount = _money(parts[-1]) if len(parts) >= 2 else None
    if amount is not None and len(parts) >= 3 and _category(parts[-2]):
        return {"item": joiner.join(parts[:-2]).strip(), "category": _category(parts[-2]), "amount": amount}, None
    if amount is not None:
        item = joiner.join(parts[:-1]).strip()
    else:
        m = re.search(r"\$?\s*-?\d[\d,]*(\.\d+)?\s*(aud|dollars?)?\s*$", text, re.I)   # "Hall hire $2000"
        if not m:
            return None, f"Budget line skipped (no amount found): '{line.strip()}'"
        amount, item = _money(m[0]), text[:m.start()].strip(" ,|-")
    if amount is None or not item:
        return None, f"Budget line skipped (no amount found): '{line.strip()}'"
    # "Picnic food catering $1,500": the cost type written at the end of the item, without a separator
    for name in sorted(COST_NAMES, key=len, reverse=True):
        if item.lower().endswith(" " + name) and item[:-len(name)].strip(" ,|-"):
            return {"item": item[:-len(name)].strip(" ,|-"), "category": COST_NAMES[name], "amount": amount}, None
    return {"item": item, "category": "other", "amount": amount}, \
        f"No cost type given for '{item}', so it was counted as 'other'. Check the catering, travel and fee limits."

def parse_application(body: str, app_id: str, sender: str, received: str) -> tuple[Optional[Application], list[str]]:
    f = _fields(body)
    if len(f) < 3:
        return None, ["This email doesn't contain an application form. If it is an application, ask the sender to "
                      "fill in the PDF form (Inbox → Application form) and attach it. Otherwise, dismiss it."]
    problems, notes = [], []

    start, end = _date(_join(f.get("start_date"))), _date(_join(f.get("end_date")))
    if not start:
        problems.append(f"Start date missing or not readable: '{_join(f.get('start_date'))}' (write it like 19/10/2024).")
    if not end:
        problems.append(f"End date missing or not readable: '{_join(f.get('end_date'))}' (write it like 19/10/2024).")

    budget = []
    for line in f.get("budget", []):
        item, note = _budget_line(line)
        if item:
            budget.append(item)
        if note:
            notes.append(note)
    total = _money(_join(f.get("total")))
    if total is None:
        total = sum(b["amount"] for b in budget)
        notes.append("Total requested not given; used the sum of the budget lines.")

    raw_type = _join(f.get("type")).lower()
    app_type = next((t for k, t in TYPES if k in raw_type), "")
    auspice = _join(f.get("auspice"))
    if problems:
        return None, problems + notes

    app = Application.model_validate({
        "id": app_id,
        "test_purpose": f"Received by email from {sender} on {received}." + (" Intake notes: " + " ".join(notes) if notes else ""),
        "applicant": {"name": _join(f.get("name")) or parseaddr(sender)[0] or sender, "type": app_type,
                      "abn": _join(f.get("abn")) or None, "nt_based": _yes(_join(f.get("nt_based"))),
                      "contact_role": _join(f.get("contact_role")) or None,
                      "auspicing_body": {"name": auspice, "confirmed": bool(_yes(_join(f.get("auspice_confirmed"))))}
                      if auspice else None},
        "project": {"title": _join(f.get("title")), "description": _join(f.get("description")),
                    "location": _join(f.get("location")), "start_date": start, "end_date": end,
                    "who_can_attend": _join(f.get("who_can_attend")), "wellbeing_benefit": _join(f.get("wellbeing_benefit"))},
        "budget": budget, "total_requested": total,
    })
    return app, notes

# ---------- PDF form ----------
def read_pdf_form(data: bytes) -> Optional[str]:
    """Turn a filled application_form.pdf into the label: value text that parse_application reads.
    None if the PDF isn't our form (no fields, or none of ours)."""
    import io, logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)     # reportlab PDFs trigger a harmless /Font warning
    try:
        fields = PdfReader(io.BytesIO(data)).get_fields() or {}
    except Exception:
        return None
    if "applicant_name" not in fields:
        return None

    def val(name: str) -> str:
        v = fields.get(name, {}).get("/V")
        v = "" if v is None else str(v).strip()
        return "" if v.lower() in PDF_PLACEHOLDERS else v

    lines = [f"{label}: {' '.join(val(name).splitlines())}" for name, label in PDF_FIELDS.items() if name != "total_requested"]
    lines.append("Budget:")
    for i in range(1, PDF_BUDGET_ROWS + 1):
        item, cost, amount = val(f"item_{i}"), val(f"cost_type_{i}"), val(f"amount_{i}")
        if item or amount:
            lines.append(f"- {item} | {cost} | {amount}" if cost else f"- {item} | {amount}")
    lines.append(f"Total requested: {val('total_requested')}")
    return "\n".join(lines)

def _pdf_attachment(msg) -> tuple[Optional[str], Optional[bytes], Optional[str]]:
    """(form text, pdf bytes, file name) for the first attached PDF that is our application form."""
    for part in msg.iter_attachments():
        name = part.get_filename() or ""
        if part.get_content_type() == "application/pdf" or name.lower().endswith(".pdf"):
            data = part.get_payload(decode=True) or b""
            text = read_pdf_form(data)
            if text:
                return text, data, name or "application.pdf"
    return None, None, None

# ---------- storage ----------
def _next_id() -> str:
    RECEIVED_DIR.mkdir(parents=True, exist_ok=True)
    n = len(list(RECEIVED_DIR.glob("E*.json"))) + 1
    return f"E{n:03d}"

def load_received() -> dict[str, Application]:
    return {p.stem: Application.model_validate(json.loads(p.read_text())) for p in sorted(RECEIVED_DIR.glob("E*.json"))}

def original_email(app_id: str) -> Optional[str]:
    p = RECEIVED_DIR / f"{app_id}.txt"
    return p.read_text() if p.exists() else None

def original_pdf(app_id: str) -> Optional[bytes]:
    p = RECEIVED_DIR / f"{app_id}.pdf"
    return p.read_bytes() if p.exists() else None

def _save(app_id: str, app: Application, original: str, pdf: Optional[bytes]) -> None:
    (RECEIVED_DIR / f"{app_id}.json").write_text(app.model_dump_json(indent=2))
    (RECEIVED_DIR / f"{app_id}.txt").write_text(original)
    if pdf:
        (RECEIVED_DIR / f"{app_id}.pdf").write_bytes(pdf)

def _already(mid: str, res: IntakeResult) -> bool:
    """True if this message needs no more work: it became an application, or the officer dismissed it.
    An email that couldn't be read before is tried again (the parser may have learnt its layout since)."""
    seen = audit.mail_seen(mid)
    if seen and (seen["application_id"] or audit.mail_dismissed(mid)):
        res.application_id, res.problems = seen["application_id"], ["Already received."]
        return True
    return False

def _quiet_if_retried(was_seen: bool, res: IntakeResult) -> IntakeResult:
    """A retried email that still can't be read is already listed for the officer: don't warn about it again."""
    if was_seen and not res.application_id:
        res.problems = ["Already received."]
    return res

def ingest(raw: bytes) -> IntakeResult:
    """Parse one email. Saves the application and the original text. Never turns the same message into two applications."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    mid = (msg.get("Message-ID") or "").strip() or "no-id-" + hashlib.sha1(raw).hexdigest()[:16]
    sender, subject = str(msg.get("From", "")), str(msg.get("Subject", ""))
    res = IntakeResult(message_id=mid, sender=sender, subject=subject)
    if _already(mid, res):
        return res
    was_seen = audit.mail_seen(mid) is not None
    try:
        received = parsedate_to_datetime(msg["Date"]).strftime("%d %b %Y %H:%M") if msg["Date"] else "unknown date"
    except (TypeError, ValueError):
        received = "unknown date"
    body = _body_text(msg)
    form_text, pdf, pdf_name = _pdf_attachment(msg)
    app_id = _next_id()
    app, res.problems = parse_application(form_text or body, app_id, sender, received)
    if app:
        original = f"From: {sender}\nSubject: {subject}\nDate: {received}\n\n{body}"
        if form_text:
            original += f"\n\n----- Attached form: {pdf_name} -----\n{form_text}"
        _save(app_id, app, original, pdf)
        res.application_id = app_id
    audit.record_mail(mid, sender, subject, res.application_id, res.problems, body)
    return _quiet_if_retried(was_seen, res)

def ingest_pdf(data: bytes, filename: str) -> IntakeResult:
    """A filled PDF form dropped straight into the inbox (no email). Never turns the same file into two applications."""
    mid = "pdf-" + hashlib.sha1(data).hexdigest()[:16]
    res = IntakeResult(message_id=mid, sender=f"Uploaded form ({filename})", subject=filename)
    if _already(mid, res):
        return res
    was_seen = audit.mail_seen(mid) is not None
    form_text = read_pdf_form(data)
    if not form_text:
        res.problems = ["This PDF isn't the grant application form (no form fields found). "
                        "Ask the applicant to use the downloadable form."]
        audit.record_mail(mid, res.sender, filename, None, res.problems, "")
        return _quiet_if_retried(was_seen, res)
    app_id = _next_id()
    received = datetime.now().strftime("%d %b %Y %H:%M")
    app, res.problems = parse_application(form_text, app_id, res.sender, received)
    if app:
        _save(app_id, app, f"Uploaded PDF form: {filename}\nReceived: {received}\n\n{form_text}", data)
        res.application_id = app_id
    audit.record_mail(mid, res.sender, filename, res.application_id, res.problems, form_text)
    return _quiet_if_retried(was_seen, res)

def check_mailbox(limit: int = 50) -> list[IntakeResult]:
    """Read (never delete or mark as read) matching emails from the configured IMAP folder."""
    if not mail_configured():
        raise RuntimeError("Mailbox not configured: set MAIL_IMAP_HOST, MAIL_USER and MAIL_PASSWORD in .env.")
    subject = os.environ.get("MAIL_SUBJECT", "Grant application").replace('"', "")
    with imaplib.IMAP4_SSL(os.environ["MAIL_IMAP_HOST"]) as box:
        box.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
        box.select(os.environ.get("MAIL_FOLDER", "INBOX"), readonly=True)
        _, data = box.search(None, f'(SUBJECT "{subject}")')
        results = []
        for num in data[0].split()[-limit:]:
            _, parts = box.fetch(num, "(BODY.PEEK[])")
            results.append(ingest(parts[0][1]))
        return results
