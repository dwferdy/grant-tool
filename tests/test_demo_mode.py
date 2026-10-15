"""Public demo (DEMO_MODE=1): locked offline, no API key read, nothing written to disk."""
import os
import sqlite3
import pytest
from engine import ai_checks, ai_settings, audit, demo, intake, mail_settings, rules_admin, users
from engine.assess import assess
from engine.loader import load_applications, load_rubric
from engine.models import Verdict


@pytest.fixture
def demo_on(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("AI_MODE", "claude")                     # even an online setting must be ignored
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-read-1234")
    # Point every on-disk location at a temp folder, so the test can prove nothing gets written there.
    env = tmp_path / ".env"
    monkeypatch.setattr(ai_settings, "ENV_PATH", env)
    monkeypatch.setattr(ai_checks, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(audit, "DB", tmp_path / "audit.sqlite")
    monkeypatch.setattr(intake, "RECEIVED_DIR", tmp_path / "received")
    monkeypatch.setattr(rules_admin, "CUSTOM_FILE", tmp_path / "custom_rules.json")
    db = sqlite3.connect(":memory:")
    monkeypatch.setattr(audit, "_memory_store", lambda: db)
    return tmp_path


def test_demo_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    if demo.on_community_cloud():
        pytest.skip("running on Streamlit Community Cloud")
    assert not demo.is_demo()


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_demo_mode_values(monkeypatch, value):
    monkeypatch.setenv("DEMO_MODE", value)
    assert demo.is_demo()


def test_demo_is_locked_offline_and_ignores_the_key(demo_on):
    assert ai_checks.offline_mode()
    assert ai_settings.mode() == "offline"
    assert ai_settings.api_key() == ""
    assert ai_settings.key_hint() == ""


def test_demo_refuses_settings_changes_and_writes_no_env(demo_on):
    with pytest.raises(demo.DemoModeError):
        ai_settings.set_mode("online")
    with pytest.raises(demo.DemoModeError):
        ai_settings.save_api_key("sk-ant-test-1234567890abcd")
    with pytest.raises(demo.DemoModeError):
        ai_settings.remove_api_key()
    with pytest.raises(demo.DemoModeError):
        ai_settings.test_api_key("sk-ant-test-1234567890abcd")
    with pytest.raises(demo.DemoModeError):
        mail_settings.save("imap.gmail.com", "a@gmail.com", "abcdefghijklmnop")
    with pytest.raises(demo.DemoModeError):
        mail_settings.test_connection("imap.gmail.com", "a@gmail.com", "abcdefghijklmnop")
    assert not (demo_on / ".env").exists()
    assert os.environ["AI_MODE"] == "claude"                    # untouched


def test_demo_never_calls_claude(demo_on, monkeypatch):
    rb, app = load_rubric(), load_applications()["A02"]
    with pytest.raises(demo.DemoModeError):
        ai_checks._call_claude(app, ai_checks.ai_rules(rb), rb)
    # The normal path uses the offline keyword checker and still finds A02's problems.
    cells = assess(app, rb, call_api=True)
    assert cells["R22"].verdict == Verdict.NOT_MET
    assert "keyword" in ai_checks.reviewer_name().lower() or "offline" in ai_checks.reviewer_name().lower()


def test_demo_writes_nothing_to_disk(demo_on):
    rb, apps = load_rubric(), load_applications()
    assess(apps["A01"], rb, call_api=True)
    audit.receive("A01")
    audit.record_final("A01", "approve", "approve", None, "Dear applicant", "Demo Officer")
    assert "A01" in audit.received() and audit.finals()["A01"]["outcome"] == "approve"
    audit.reset_demo()
    assert audit.received() == {}
    with pytest.raises(demo.DemoModeError):
        intake.ingest(b"Subject: Grant application\n\nhello")
    with pytest.raises(demo.DemoModeError):
        intake.ingest_pdf(b"%PDF-1.4", "form.pdf")
    with pytest.raises(demo.DemoModeError):
        intake.check_mailbox()
    assert not intake.mail_configured()
    assert list(demo_on.iterdir()) == []                        # no .env, cache, audit.sqlite, received/ ...


def test_demo_has_no_accounts_or_rule_changes(demo_on):
    with pytest.raises(demo.DemoModeError):
        users.create("boss", "Boss", "super_admin", "password123", created_by="test")
    with pytest.raises(demo.DemoModeError):
        users.verify("boss", "password123")
    with pytest.raises(demo.DemoModeError):
        rules_admin.add_rule(by="x", short_name="x", rule="x", check_method="code", rtype="eligibility_gate",
                             check="x", evidence_needed="x", plain_english_reason="x")
    assert demo.DEMO_USER["role"] != "super_admin"


def test_demo_without_memory_store_never_opens_the_file(demo_on, monkeypatch):
    monkeypatch.setattr(audit, "_memory_store", None)
    with pytest.raises(demo.DemoModeError):
        audit.received()
    assert not (demo_on / "audit.sqlite").exists()
