"""Create a free Neo4j AuraDB instance from the terminal (no website clicking).

Needs Aura API credentials (Console -> your email top right -> Account details
-> API credentials -> Create). Either set env vars first:
    $env:AURA_CLIENT_ID = "..."
    $env:AURA_CLIENT_SECRET = "..."
or just run the script and it will ask you for them.

Usage:
    python create_instance.py          # lists your instances, creates a free one if you have none
    python create_instance.py --force  # try to create even if instances exist
"""
import base64
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.neo4j.io"
PROJECT_ID = "a6557ffc-ab76-4844-8111-0472b37cc38d"  # from your console URL
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura_credentials.txt")


def request(method, path, token=None, body=None, form=None, basic=None):
    """Tiny HTTP helper using only the standard library."""
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if basic:
        headers["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code} on {path}: {e.read().decode()}")


def load_keys_file():
    """Read AURA_CLIENT_ID / AURA_CLIENT_SECRET from aura_keys.txt if it exists."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura_keys.txt")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"')
                if value and "PASTE_" not in value:
                    os.environ.setdefault(key.strip(), value)


def get_token():
    load_keys_file()
    client_id = os.getenv("AURA_CLIENT_ID") or input("Aura Client ID: ").strip()
    client_secret = os.getenv("AURA_CLIENT_SECRET") or getpass.getpass("Aura Client Secret (hidden): ").strip()
    if not client_id or not client_secret:
        sys.exit("Client ID or Secret is empty (paste may not have worked). "
                 "Set them with $env:AURA_CLIENT_ID / $env:AURA_CLIENT_SECRET and run again.")
    # Show length only (never the secret itself) so you can tell if the paste worked
    print(f"Got secret with {len(client_secret)} characters.")
    resp = request("POST", "/oauth/token", form={"grant_type": "client_credentials"},
                   basic=f"{client_id}:{client_secret}")
    return resp["access_token"]


def main():
    token = get_token()
    print("Logged in to Aura API.")

    # --replace <id>: delete that instance first, then wait until it's gone
    if "--replace" in sys.argv:
        old_id = sys.argv[sys.argv.index("--replace") + 1]
        print(f"Deleting old instance {old_id}...")
        request("DELETE", f"/v1/instances/{old_id}", token)
        for _ in range(60):
            ids = [i["id"] for i in request("GET", f"/v1/instances?tenantId={PROJECT_ID}", token)["data"]]
            if old_id not in ids:
                print("Old instance deleted.")
                break
            time.sleep(10)

    existing = request("GET", f"/v1/instances?tenantId={PROJECT_ID}", token)["data"]
    if existing:
        print("\nInstances you already have:")
        for inst in existing:
            print(f"  - {inst['name']}  id={inst['id']}")
        if "--force" not in sys.argv:
            print("\nYou already have an instance (free tier allows only one). "
                  "Use it, or run with --force to try creating another.")
            return

    print("\nCreating free AuraDB instance...")
    created = request("POST", "/v1/instances", token, body={
        "version": "5",
        "region": "asia-southeast1",  # same region as your old instance (closest to you)
        "memory": "1GB",
        "name": "hackathon-db",
        "type": "free-db",
        "tenant_id": PROJECT_ID,
        "cloud_provider": "gcp",
    })["data"]

    # Password is only shown ONCE, so save it to a file right away
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        f.write(f"NEO4J_URI={created['connection_url']}\n")
        f.write(f"NEO4J_USERNAME={created['username']}\n")
        f.write(f"NEO4J_PASSWORD={created['password']}\n")
        f.write(f"AURA_INSTANCEID={created['id']}\n")
    print(f"Created! Credentials saved to {CREDS_FILE} (keep this file private).")
    print(f"URI: {created['connection_url']}   Username: {created['username']}")

    # Wait until it's ready (usually 1-3 minutes)
    print("Waiting for instance to be running", end="", flush=True)
    for _ in range(60):
        status = request("GET", f"/v1/instances/{created['id']}", token)["data"]["status"]
        if status == "running":
            print("\nInstance is RUNNING. You can connect now.")
            return
        print(".", end="", flush=True)
        time.sleep(10)
    print("\nStill starting. Check the console in a minute.")


if __name__ == "__main__":
    main()
