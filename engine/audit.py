"""SQLite store for the officer workflow. Append-only: a changed decision is a new row.

Tables:
- inbox: when each application arrived
- decisions: one OfficerDecision per rule the officer reviewed
- final_decisions: the outcome and letter sent to the applicant
"""
from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Optional
from engine.loader import ROOT
from engine.models import OfficerDecision

DB = ROOT / "data/audit.sqlite"

def _conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, rule_id TEXT, ai_verdict TEXT,
        officer_verdict TEXT, overridden INTEGER, blind_review INTEGER, officer_note TEXT,
        officer TEXT, decided_at TEXT, seconds_spent REAL)""")
    c.execute("CREATE TABLE IF NOT EXISTS inbox (application_id TEXT PRIMARY KEY, received_at TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, display_name TEXT, role TEXT,
        salt TEXT, pw_hash TEXT, active INTEGER, created_by TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rule_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id TEXT,
        action TEXT, rule_json TEXT, changed_by TEXT, changed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS mail (message_id TEXT PRIMARY KEY, sender TEXT, subject TEXT,
        application_id TEXT, problems TEXT, body TEXT, fetched_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS final_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, outcome TEXT, suggested_outcome TEXT,
        officer_note TEXT, letter TEXT, officer TEXT, decided_at TEXT)""")
    return c

def _rows(sql: str, args=()) -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql, args)]

# ---------- inbox ----------
def receive(application_id: str) -> None:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO inbox VALUES (?, ?)", (application_id, datetime.now().isoformat()))

def received() -> dict[str, datetime]:
    return {r["application_id"]: datetime.fromisoformat(r["received_at"])
            for r in _rows("SELECT * FROM inbox ORDER BY received_at DESC")}

def reset_demo() -> None:
    """Empty the inbox, all decisions and the email log (demo only). Emails can be fetched again afterwards."""
    with _conn() as c:
        for t in ("inbox", "decisions", "final_decisions", "mail"):
            c.execute(f"DELETE FROM {t}")
    for p in (ROOT / "data/received").glob("E*.*"):
        p.unlink()

# ---------- email intake ----------
def mail_seen(message_id: str) -> Optional[dict]:
    rows = _rows("SELECT * FROM mail WHERE message_id = ?", (message_id,))
    return rows[0] if rows else None

def record_mail(message_id: str, sender: str, subject: str, application_id: Optional[str],
                problems: list[str], body: str) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO mail VALUES (?,?,?,?,?,?,?)",
                  (message_id, sender, subject, application_id, "\n".join(problems), body, datetime.now().isoformat()))

def unreadable_mail() -> list[dict]:
    """Emails that could not be turned into an application, newest first."""
    return _rows("SELECT * FROM mail WHERE application_id IS NULL ORDER BY fetched_at DESC")

# ---------- rule decisions ----------
def record(d: OfficerDecision) -> None:
    with _conn() as c:
        c.execute("INSERT INTO decisions (application_id, rule_id, ai_verdict, officer_verdict, overridden, blind_review,"
                  " officer_note, officer, decided_at, seconds_spent) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (d.application_id, d.rule_id, d.ai_verdict.value, d.officer_verdict.value, int(d.overridden),
                   int(d.blind_review), d.officer_note, d.officer, d.decided_at.isoformat(), d.seconds_spent))

def all_rows() -> list[dict]:
    return _rows("SELECT * FROM decisions ORDER BY id DESC")

def latest() -> dict[tuple[str, str], OfficerDecision]:
    """Most recent decision per (application, rule)."""
    out = {}
    for r in reversed(all_rows()):
        r.pop("id")
        out[(r["application_id"], r["rule_id"])] = OfficerDecision.model_validate(r)
    return out

# ---------- final decisions ----------
def record_final(application_id: str, outcome: str, suggested_outcome: str, officer_note: Optional[str],
                 letter: str, officer: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO final_decisions (application_id, outcome, suggested_outcome, officer_note, letter, officer,"
                  " decided_at) VALUES (?,?,?,?,?,?,?)",
                  (application_id, outcome, suggested_outcome, officer_note, letter, officer, datetime.now().isoformat()))

def all_finals() -> list[dict]:
    return _rows("SELECT * FROM final_decisions ORDER BY id DESC")

def finals() -> dict[str, dict]:
    """Most recent final decision per application."""
    return {r["application_id"]: r for r in reversed(all_finals())}

# ---------- rule changes (super admin) ----------
def record_rule_change(rule_id: str, action: str, rule_json: str, by: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO rule_changes (rule_id, action, rule_json, changed_by, changed_at) VALUES (?,?,?,?,?)",
                  (rule_id, action, rule_json, by, datetime.now().isoformat()))

def rule_changes() -> list[dict]:
    return _rows("SELECT id, rule_id, action, changed_by, changed_at FROM rule_changes ORDER BY id DESC")
