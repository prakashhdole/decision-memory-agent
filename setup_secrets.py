"""One-time: build .streamlit/secrets.toml (git-ignored) + logins.txt (git-ignored).

    python setup_secrets.py aditya judge teammate
"""
import os
import secrets
import sys

from memory_agent.auth import hash_password

root = os.path.dirname(os.path.abspath(__file__))
creds = {}
with open(os.path.join(root, "aura_credentials.txt"), encoding="utf-8") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            creds[k] = v
llm = {}
keys = os.path.join(root, "llm_keys.txt")
if os.path.exists(keys):
    for line in open(keys, encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            if v.strip():
                llm[k.strip()] = v.strip()

users = [u.lower() for u in (sys.argv[1:] or ["aditya", "judge"])]
passwords = {u: secrets.token_urlsafe(9) for u in users}

toml = ["# App secrets - NEVER commit this file. Paste the same text into Streamlit Cloud > Secrets."]
for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
    toml.append(f'{k} = "{creds[k]}"')
toml.append(f'NEO4J_DATABASE = "{creds.get("NEO4J_DATABASE", creds["NEO4J_USERNAME"])}"')
for k, v in llm.items():
    toml.append(f'{k} = "{v}"')
toml.append("\n[users]")
toml += [f'{u} = "{hash_password(p)}"' for u, p in passwords.items()]

os.makedirs(os.path.join(root, ".streamlit"), exist_ok=True)
with open(os.path.join(root, ".streamlit", "secrets.toml"), "w", encoding="utf-8") as f:
    f.write("\n".join(toml) + "\n")
with open(os.path.join(root, "logins.txt"), "w", encoding="utf-8") as f:
    f.write("App logins (keep private, don't commit):\n")
    f.write("\n".join(f"  {u} / {p}" for u, p in passwords.items()) + "\n")
print(f"Wrote .streamlit/secrets.toml and logins.txt for users: {', '.join(users)}")
