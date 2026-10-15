"""Connect a mailbox from the app: test the IMAP login first, then save it to .env (no restart needed).

Providers:
- Gmail: IMAP with a 16-character App Password (needs 2-Step Verification). Normal passwords are refused.
- Outlook / Hotmail / Microsoft 365: since 16 Sep 2024 Microsoft refuses passwords and app passwords for
  IMAP and requires OAuth, so this tool can't log in directly. The app guides the officer to forward
  matching emails to a connected Gmail inbox instead, or to drag and drop .eml files.
- Other: any IMAP server that accepts a password.
"""
from __future__ import annotations
import imaplib, os, socket
from dataclasses import dataclass
from engine.ai_checks import _load_env
from engine.ai_settings import write_env
from engine.demo import guard

GMAIL_HOST = "imap.gmail.com"
GMAIL_APP_PASSWORDS_URL = "https://myaccount.google.com/apppasswords"
GMAIL_2SV_URL = "https://myaccount.google.com/signinoptions/twosv"
OUTLOOK_RULES_URL = "https://outlook.live.com/mail/0/options/mail/rules"
VARS = ("MAIL_IMAP_HOST", "MAIL_USER", "MAIL_PASSWORD", "MAIL_FOLDER", "MAIL_SUBJECT")
DEFAULT_SUBJECT = "Grant application"


@dataclass
class MailCheck:
    ok: bool
    message: str
    matching: int = 0


def current() -> dict:
    _load_env()
    return {v: os.environ.get(v, "") for v in VARS}


def subject() -> str:
    return current()["MAIL_SUBJECT"] or DEFAULT_SUBJECT


def test_connection(host: str, user: str, password: str, folder: str = "INBOX", subj: str = DEFAULT_SUBJECT) -> MailCheck:
    """Log in read-only and count emails whose subject contains `subj`. Never changes the mailbox."""
    guard("Connecting a mailbox")
    host, user = host.strip(), user.strip()
    password = password.replace(" ", "").strip() if host == GMAIL_HOST else password.strip()
    if not (host and user and password):
        return MailCheck(False, "Fill in the email address and password.")
    try:
        with imaplib.IMAP4_SSL(host, timeout=20) as box:
            box.login(user, password)
            status, _ = box.select(folder or "INBOX", readonly=True)
            if status != "OK":
                return MailCheck(False, f"Logged in, but the folder “{folder}” doesn't exist.")
            _, data = box.search(None, f'(SUBJECT "{subj.replace(chr(34), "")}")')
            n = len(data[0].split()) if data and data[0] else 0
    except imaplib.IMAP4.error as e:
        text = str(e).lower()
        if host == GMAIL_HOST:
            return MailCheck(False, "Gmail refused the login. Use a 16-character App Password (not your normal "
                                    "password), and check the email address is right.")
        if "basicauth" in text or "authenticate" in text or "logondenied" in text:
            return MailCheck(False, "The server refused the password. Microsoft accounts (Outlook, Hotmail, 365) no "
                                    "longer allow password logins for email apps: use the Outlook option instead.")
        return MailCheck(False, f"The server refused the login: {e}")
    except (socket.gaierror, socket.timeout, ConnectionError, OSError):
        return MailCheck(False, f"Couldn't reach {host}. Check the server name and your internet connection.")
    return MailCheck(True, f"Connected to {user}. {n} email(s) with “{subj}” in the subject are waiting to be read.", n)


def save(host: str, user: str, password: str, folder: str = "INBOX", subj: str = DEFAULT_SUBJECT) -> None:
    if host.strip() == GMAIL_HOST:
        password = password.replace(" ", "")
    values = {"MAIL_IMAP_HOST": host.strip(), "MAIL_USER": user.strip(), "MAIL_PASSWORD": password.strip(),
              "MAIL_FOLDER": folder.strip() or "INBOX", "MAIL_SUBJECT": subj.strip() or DEFAULT_SUBJECT}
    for k, v in values.items():
        write_env(k, v)
        os.environ[k] = v


def disconnect() -> None:
    for k in ("MAIL_IMAP_HOST", "MAIL_USER", "MAIL_PASSWORD"):
        write_env(k, None)
        os.environ.pop(k, None)
