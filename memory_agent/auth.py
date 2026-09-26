"""Simple, safe login for the Streamlit app.

Passwords are never stored in plain text. Each user has a PBKDF2-SHA256 hash:
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
Users are read from Streamlit secrets:

    [users]
    aditya = "pbkdf2_sha256$600000$..."
    judge  = "pbkdf2_sha256$600000$..."

Create a hash with:  python make_user.py <username>
"""
import hashlib
import hmac
import os
import secrets
import time

ITERATIONS = 600_000
MAX_FAILS = 5          # failed attempts allowed...
LOCK_SECONDS = 300     # ...before the username is locked for 5 minutes


def hash_password(password, iterations=ITERATIONS):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


class LoginGuard:
    """Tracks failed logins per username (shared across all browser sessions)."""

    def __init__(self):
        self.fails = {}  # username -> (count, first_fail_time)

    def locked_for(self, user):
        count, since = self.fails.get(user, (0, 0))
        if count >= MAX_FAILS:
            left = LOCK_SECONDS - (time.time() - since)
            if left > 0:
                return int(left)
            self.fails.pop(user, None)
        return 0

    def record(self, user, ok):
        if ok:
            self.fails.pop(user, None)
        else:
            count, since = self.fails.get(user, (0, time.time()))
            self.fails[user] = (count + 1, since)


def check_login(users, guard, username, password):
    """Return (ok, message). Same message for unknown user and wrong password."""
    username = (username or "").strip().lower()
    wait = guard.locked_for(username)
    if wait:
        return False, f"Too many attempts. Try again in {wait // 60 + 1} min."
    stored = users.get(username)
    # verify against a dummy hash for unknown users so timing doesn't reveal who exists
    ok = verify_password(password or "", stored or _DUMMY)
    ok = ok and stored is not None
    guard.record(username, ok)
    return (True, "") if ok else (False, "Wrong username or password.")


_DUMMY = hash_password(os.urandom(8).hex())
