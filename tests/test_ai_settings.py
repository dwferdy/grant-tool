"""AI mode and API key settings are written to .env without disturbing other lines."""
import os
import pytest
from engine import ai_settings, ai_checks


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# comment stays\nAI_MODE=offline\nOTHER=1\n")
    monkeypatch.setattr(ai_settings, "ENV_PATH", path)
    # Never read the project's real .env (it may hold a real key) during tests.
    monkeypatch.setattr(ai_settings, "_load_env", lambda: None)
    monkeypatch.setattr(ai_checks, "_load_env", lambda: None)
    for v in ("AI_MODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    return path


def test_set_mode_rewrites_line_and_environment(env_file):
    ai_settings.set_mode("online")
    assert env_file.read_text() == "# comment stays\nAI_MODE=claude\nOTHER=1\n"
    assert os.environ["AI_MODE"] == "claude"
    assert ai_settings.mode() == "online"
    ai_settings.set_mode("offline")
    assert ai_settings.mode() == "offline"


def test_save_and_remove_key(env_file):
    ai_settings.save_api_key("sk-ant-test-1234567890abcd")
    assert "ANTHROPIC_API_KEY=sk-ant-test-1234567890abcd" in env_file.read_text()
    assert ai_settings.key_hint() == "sk-ant-…abcd"
    assert oct(env_file.stat().st_mode)[-3:] == "600"
    ai_settings.remove_api_key()
    assert "ANTHROPIC_API_KEY" not in env_file.read_text()
    assert ai_settings.api_key() == ""
    assert "OTHER=1" in env_file.read_text()


def test_rejects_malformed_key_without_calling_api():
    res = ai_settings.test_api_key("not-a-key")
    assert not res.ok and "sk-ant-" in res.message
