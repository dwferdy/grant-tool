"""Which reviewer runs the AI rules, and the Anthropic API key — editable from the app.

Two modes:
- offline: the free keyword reviewer (no API calls, no cost). Good for demos and training.
- online:  Claude reads each application and quotes its evidence. Needs an API key with credits.

The choice and the key live in .env (git-ignored) so they survive restarts. Changes are also applied
to os.environ straight away, because load_dotenv() never overrides a value that is already set.
A launcher can force a mode for one run: AI_MODE=offline ./run_app.sh (see run_offline.sh / run_online.sh).
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from engine.loader import ROOT
from engine.ai_checks import _load_env, offline_mode
from engine.demo import is_demo, guard

ENV_PATH = ROOT / ".env"
KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
CONSOLE_KEYS_URL = "https://console.anthropic.com/settings/keys"
CONSOLE_BILLING_URL = "https://console.anthropic.com/settings/billing"
TEST_MODEL = "claude-haiku-4-5-20251001"   # cheapest model, used only for the 1-token credit check


def mode() -> str:
    return "offline" if offline_mode() else "online"


def api_key() -> str:
    if is_demo():
        return ""   # public demo: refuse to read ANTHROPIC_API_KEY, even if the host sets one
    _load_env()
    return next((os.environ[v] for v in KEY_VARS if os.environ.get(v)), "")


def key_hint() -> str:
    """Masked key for display, e.g. 'sk-ant-…a1B2'."""
    k = api_key()
    return f"{k[:7]}…{k[-4:]}" if len(k) > 12 else ("set" if k else "")


def write_env(name: str, value: str | None) -> None:
    """Set (or remove, when value is None) one variable in .env, keeping comments and other lines."""
    guard("Writing .env")
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    out, done = [], False
    for line in lines:
        if line.strip().startswith(f"{name}="):
            if value is not None and not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if value is not None and not done:
        out.append(f"{name}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n")
    os.chmod(ENV_PATH, 0o600)   # the file holds a secret: owner read/write only


def set_mode(new_mode: str) -> None:
    guard("Changing the AI mode")
    value = "offline" if new_mode == "offline" else "claude"
    write_env("AI_MODE", value)
    os.environ["AI_MODE"] = value


def save_api_key(key: str) -> None:
    write_env("ANTHROPIC_API_KEY", key)
    os.environ["ANTHROPIC_API_KEY"] = key
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


def remove_api_key() -> None:
    for v in KEY_VARS:
        write_env(v, None)
        os.environ.pop(v, None)


@dataclass
class KeyCheck:
    ok: bool
    message: str


def test_api_key(key: str) -> KeyCheck:
    """Check the key is valid and the account can run requests (sends one 1-token message, < $0.001)."""
    guard("Testing an API key")
    key = key.strip()
    if not key.startswith("sk-ant-"):
        return KeyCheck(False, "That doesn't look like an Anthropic API key. Keys start with “sk-ant-”.")
    try:
        import anthropic
    except ImportError:
        return KeyCheck(False, "The anthropic package isn't installed. Run: .venv/bin/pip install -r requirements.txt")
    client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=20)
    try:
        client.messages.create(model=TEST_MODEL, max_tokens=1, messages=[{"role": "user", "content": "Hi"}])
    except anthropic.AuthenticationError:
        return KeyCheck(False, "Anthropic didn't recognise this key. Check you copied all of it, or create a new one.")
    except anthropic.PermissionDeniedError:
        return KeyCheck(False, "This key isn't allowed to make requests. Check its permissions in the Anthropic Console.")
    except anthropic.BadRequestError as e:
        if "credit" in str(e).lower():
            return KeyCheck(False, "The key works, but the account has no credits yet. Add credits under Billing, then test again.")
        return KeyCheck(False, f"Anthropic rejected the test request: {e}")
    except anthropic.APIConnectionError:
        return KeyCheck(False, "Couldn't reach Anthropic. Check your internet connection and try again.")
    except anthropic.APIStatusError as e:
        return KeyCheck(False, f"Anthropic returned an error ({e.status_code}). Try again in a minute.")
    return KeyCheck(True, "Connected. Claude will review new applications.")
