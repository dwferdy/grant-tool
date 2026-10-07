"""Connect-a-mailbox: login is tested before saving, and settings land in .env (with a fake IMAP server)."""
import imaplib, os
import pytest
from engine import mail_settings, ai_settings, ai_checks


class FakeIMAP:
    """Minimal stand-in for imaplib.IMAP4_SSL."""
    accept = ("grants@gmail.com", "abcdefghijklmnop")
    def __init__(self, host, timeout=None): self.host = host
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, pw):
        if (user, pw) != self.accept:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
    def select(self, folder, readonly=False): return ("OK", [b"3"]) if folder == "INBOX" else ("NO", [b""])
    def search(self, charset, criteria): return ("OK", [b"1 2"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("AI_MODE=offline\n")
    monkeypatch.setattr(ai_settings, "ENV_PATH", path)
    monkeypatch.setattr(ai_checks, "_load_env", lambda: None)
    monkeypatch.setattr(mail_settings, "_load_env", lambda: None)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeIMAP)
    for v in mail_settings.VARS:
        monkeypatch.delenv(v, raising=False)
    return path


def test_gmail_app_password_with_spaces_connects(env):
    res = mail_settings.test_connection("imap.gmail.com", "grants@gmail.com", "abcd efgh ijkl mnop")
    assert res.ok and res.matching == 2


def test_wrong_gmail_password_explains_app_passwords(env):
    res = mail_settings.test_connection("imap.gmail.com", "grants@gmail.com", "my-normal-password")
    assert not res.ok and "App Password" in res.message


def test_missing_folder_is_reported(env):
    res = mail_settings.test_connection("imap.gmail.com", "grants@gmail.com", "abcdefghijklmnop", folder="Grants")
    assert not res.ok and "Grants" in res.message


def test_save_then_disconnect(env):
    mail_settings.save("imap.gmail.com", "grants@gmail.com", "abcd efgh ijkl mnop")
    text = env.read_text()
    assert "MAIL_PASSWORD=abcdefghijklmnop" in text and "AI_MODE=offline" in text
    assert os.environ["MAIL_USER"] == "grants@gmail.com"
    mail_settings.disconnect()
    assert "MAIL_PASSWORD" not in env.read_text() and "MAIL_USER" not in os.environ
