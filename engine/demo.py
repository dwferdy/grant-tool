"""Public demo mode: a locked, read-only-on-disk version of the app for Streamlit Community Cloud.

Turned on by DEMO_MODE=1 (an environment variable, or a root-level Streamlit secret, which Streamlit also
exposes as an environment variable). As a safety net it is also on whenever the app runs from Streamlit
Community Cloud's checkout folder (/mount/src/...), so a deploy without the secret still can't go online.

In demo mode:
- the AI rules are always checked by the free offline keyword checker: no Anthropic API calls, ever;
- .env is never read or written, and ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are ignored;
- nobody can sign in as a super admin (everyone is a demo grant officer), so AI mode, rules, users and the
  mailbox wizard are not available;
- nothing is written to the server's disk: the audit store is an in-memory database per browser session,
  email/PDF intake and the AI result cache are switched off.

Local runs without DEMO_MODE behave exactly as before.
"""
from __future__ import annotations
import os
from pathlib import Path

REPO_URL = "https://github.com/dwferdy/grant-tool"
BANNER = "Public demo: offline keyword checker, fictional applications, no AI calls"
_TRUE = {"1", "true", "yes", "on"}
_ROOT = Path(__file__).resolve().parent.parent
DEMO_USER = {"username": "demo", "display_name": "Demo Officer", "role": "officer"}


class DemoModeError(RuntimeError):
    """Raised when something tries to call an API or write a file while the public demo is running."""


def on_community_cloud() -> bool:
    return str(_ROOT).startswith("/mount/src/")


def is_demo() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in _TRUE or on_community_cloud()


def guard(action: str) -> None:
    """Stop `action` (an API call, a file write, a login to a mailbox) when the public demo is running."""
    if is_demo():
        raise DemoModeError(f"{action} is disabled in the public demo.")
