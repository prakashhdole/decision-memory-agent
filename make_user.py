"""Create a login for the app.

    python make_user.py judge            # generates a strong random password
    python make_user.py judge MyPass123  # uses the password you give

Paste the printed line under [users] in .streamlit/secrets.toml
(and in the Streamlit Cloud "Secrets" box).
"""
import secrets
import sys

from memory_agent.auth import hash_password

if len(sys.argv) < 2:
    sys.exit("Usage: python make_user.py <username> [password]")
user = sys.argv[1].strip().lower()
pw = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(12)
print(f"Username: {user}\nPassword: {pw}\n\nAdd this line under [users]:\n{user} = \"{hash_password(pw)}\"")
