"""User accounts and roles, stored in the audit DB. Passwords are salted PBKDF2 hashes, never plain text.

Roles:
- super_admin: everything an officer can do, plus manage rules and users
- officer: review applications and send decisions

Prototype-grade login (no SSO, no lockout). For production use the department's identity provider.
"""
from __future__ import annotations
import hashlib, hmac, secrets
from datetime import datetime
from typing import Optional
from engine import audit

ROLES = {"super_admin": "Super admin", "officer": "Grant officer"}
MIN_PASSWORD = 8

def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()

def count() -> int:
    return len(audit._rows("SELECT username FROM users"))

def list_users() -> list[dict]:
    return audit._rows("SELECT username, display_name, role, active, created_by, created_at FROM users ORDER BY created_at")

def create(username: str, display_name: str, role: str, password: str, created_by: str) -> None:
    username = username.strip().lower()
    if role not in ROLES:
        raise ValueError(f"Unknown role {role}")
    if not username or not display_name.strip():
        raise ValueError("Username and name are required.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    if audit._rows("SELECT 1 FROM users WHERE username = ?", (username,)):
        raise ValueError(f"Username '{username}' already exists.")
    salt = secrets.token_hex(16)
    with audit._conn() as c:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)", (username, display_name.strip(), role, salt,
                  _hash(password, salt), 1, created_by, datetime.now().isoformat()))

def verify(username: str, password: str) -> Optional[dict]:
    """The user (without password fields) if the login is valid and the account is active."""
    rows = audit._rows("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
    if not rows or not rows[0]["active"]:
        return None
    u = rows[0]
    if not hmac.compare_digest(_hash(password, u["salt"]), u["pw_hash"]):
        return None
    return {k: u[k] for k in ("username", "display_name", "role")}

def _active_admins() -> int:
    return len(audit._rows("SELECT 1 FROM users WHERE role = 'super_admin' AND active = 1"))

def set_active(username: str, active: bool) -> None:
    u = audit._rows("SELECT role, active FROM users WHERE username = ?", (username,))
    if not active and u and u[0]["role"] == "super_admin" and u[0]["active"] and _active_admins() <= 1:
        raise ValueError("You can't deactivate the last active super admin.")
    with audit._conn() as c:
        c.execute("UPDATE users SET active = ? WHERE username = ?", (int(active), username))

def set_password(username: str, password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    salt = secrets.token_hex(16)
    with audit._conn() as c:
        c.execute("UPDATE users SET salt = ?, pw_hash = ? WHERE username = ?", (salt, _hash(password, salt), username))
