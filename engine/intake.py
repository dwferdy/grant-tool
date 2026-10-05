"""Email intake: mailbox (IMAP) or .eml file -> Application JSON in data/received/.

Applicants fill in the plain-text template in letters/email_template.txt and send it as the email body.
Parsing is plain code: nothing is guessed. A field that is missing stays empty, so R11 (complete application)
flags it and the applicant is asked to clarify. Only unreadable dates block intake, because the
Application contract requires them.

.env settings (Gmail shown; any IMAP server works):
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

LABELS = {
    "applicant name": "name", "applicant type": "type", "abn": "abn", "nt based": "nt_based",
    "contact role": "contact_role", "auspicing body": "auspice", "auspicing body confirmed": "auspice_confirmed",
    "project title": "title", "description": "description", "location": "location", "start date": "start_date",
    "end date": "end_date", "who can attend": "who_can_attend", "wellbeing benefit": "wellbeing_benefit",
    "budget": "budget", "total requested": "total",
}
TYPES = [("not-for-profit", "nfp_incorporated"), ("nfp", "nfp_incorporated"), ("incorporated", "nfp_incorporated"),
         ("education", "education_provider"), ("provider", "education_provider"), ("business", "registered_business"),
         ("company", "registered_business"), ("student", "student_or_community_group"), ("community", "student_or_community_group")]
CATEGORIES = ["travel", "facilitator_fees", "catering", "venue_hire", "equipment_hire", "materials", "marketing", "other"]

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

def _fields(body: str) -> dict:
    """Split the body into template fields. A value may continue over several lines until the next label."""
    out, current = {}, None
    label_re = re.compile(r"^\s*(" + "|".join(sorted(map(re.escape, LABELS), key=len, reverse=True)) + r")\s*:\s*(.*)$", re.I)
    for line in body.splitlines():
        if line.strip() in ("--", "-- "):      # email signature
            break
        if line.startswith(">"):               # quoted reply
            continue
        m = label_re.match(line)
        if m:
            current = LABELS[m[1].lower()]
            out[current] = [m[2].strip()] if m[2].strip() else []
        elif current and line.strip():
            out[current].append(line.strip())
    return out

def _join(v) -> str:
    return " ".join(v or []).strip()

def _date(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y"):
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
    return True if s.startswith("y") else False if s.startswith("n") else None

def _category(s: str) -> str:
    s = s.strip().lower().replace(" ", "_")
    return next((c for c in CATEGORIES if c == s or c.split("_")[0] in s), "other")

def parse_application(body: str, app_id: str, sender: str, received: str) -> tuple[Optional[Application], list[str]]:
    f = _fields(body)
    if len(f) < 3:
        return None, ["The email is not in the application template format (fewer than 3 template fields found)."]
    problems, notes = [], []

    start, end = _date(_join(f.get("start_date"))), _date(_join(f.get("end_date")))
    if not start:
        problems.append(f"Start date missing or not readable: '{_join(f.get('start_date'))}' (use YYYY-MM-DD).")
    if not end:
        problems.append(f"End date missing or not readable: '{_join(f.get('end_date'))}' (use YYYY-MM-DD).")

    budget = []
    for line in f.get("budget", []):
        parts = [p.strip() for p in line.lstrip("-•* ").split("|")]
        amount = _money(parts[-1]) if len(parts) >= 2 else None
        if amount is None:
            notes.append(f"Budget line skipped (expected 'item | category | amount'): '{line}'")
            continue
        budget.append({"item": parts[0], "category": _category(parts[1]) if len(parts) == 3 else "other", "amount": amount})
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

def ingest(raw: bytes) -> IntakeResult:
    """Parse one email. Saves the application and the original text. Never processes the same message twice."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    mid = (msg.get("Message-ID") or "").strip() or "no-id-" + hashlib.sha1(raw).hexdigest()[:16]
    sender, subject = str(msg.get("From", "")), str(msg.get("Subject", ""))
    res = IntakeResult(message_id=mid, sender=sender, subject=subject)
    seen = audit.mail_seen(mid)
    if seen:
        res.application_id, res.problems = seen["application_id"], ["Already received."]
        return res
    try:
        received = parsedate_to_datetime(msg["Date"]).strftime("%d %b %Y %H:%M") if msg["Date"] else "unknown date"
    except (TypeError, ValueError):
        received = "unknown date"
    body = _body_text(msg)
    app_id = _next_id()
    app, res.problems = parse_application(body, app_id, sender, received)
    if app:
        (RECEIVED_DIR / f"{app_id}.json").write_text(app.model_dump_json(indent=2))
        (RECEIVED_DIR / f"{app_id}.txt").write_text(f"From: {sender}\nSubject: {subject}\nDate: {received}\n\n{body}")
        res.application_id = app_id
    audit.record_mail(mid, sender, subject, res.application_id, res.problems, body)
    return res

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
