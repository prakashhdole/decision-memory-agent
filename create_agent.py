"""Create (or update) an Aura Agent on your database via the Aura v2beta1 API.

Uses the same API key as create_instance.py (aura_keys.txt).
The agent is kept INTERNAL (is_private=True) so it's free to use in the console.

Usage:
    python create_agent.py
"""
import json
import sys

from create_instance import get_token, API
import urllib.error
import urllib.request

DBID = "319896c3"  # your AuraDB instance id

OLD_NAMES = ["Hackathon Graph Agent"]  # earlier names, so we update instead of duplicating

AGENT = {
    "name": "Fraud Detection Agent",
    "description": "Investigates bank accounts and money transfers to spot fraud rings "
                   "(circular transaction chains) and explain suspicious activity.",
    "system_prompt": (
        "You are a fraud investigation assistant for a bank's Neo4j transaction graph.\n"
        "Graph schema:\n"
        "- Node (:Account {accountId, holderName, createdAt})\n"
        "- Relationship (:Account)-[:TRANSFERRED_TO {txId, amount, timestamp}]->(:Account)\n"
        "Key fraud signal: a circular chain, where money leaves an account, passes through "
        "2-4 other accounts and returns to the start (3-5 hops). This is a typical "
        "money-laundering pattern. Use the find_fraud_rings tool for any question about "
        "rings, cycles, laundering or which accounts are suspicious.\n"
        "When you report a ring, show the path like ACC001 -> ACC002 -> ACC003 -> ACC001 "
        "with amounts. Answer using only data returned by your tools; if the data doesn't "
        "contain the answer, say so plainly. Flagged accounts are suspicious, not proven "
        "fraud, so say they need human review. Keep answers short and clear."
    ),
    "dbid": DBID,
    "is_private": True,       # internal = free; set False only if you need a public API
    "is_mcp_enabled": False,
    "enabled": True,
    "tools": [
        {
            "type": "text2cypher",
            "name": "Natural Language to Cypher Tool",
            "description": "Converts any natural-language question into a Cypher query, "
                           "runs it, and returns the results. Use when no other tool fits.",
            "enabled": True,
            "config": {},
        },
        {
            "type": "cypherTemplate",
            "name": "find_fraud_rings",
            "description": "Find all circular transaction chains of 3-5 hops (possible "
                           "money-laundering rings). Returns each ring's account path, "
                           "the amounts on each hop, and the number of hops.",
            "enabled": True,
            "config": {"template": (
                "MATCH path = (a:Account)-[:TRANSFERRED_TO*3..5]->(a)\n"
                "WITH a, path, nodes(path)[..-1] AS ring\n"
                "WHERE size(ring) = size(reduce(seen = [], n IN ring |\n"
                "        CASE WHEN n IN seen THEN seen ELSE seen + n END))\n"
                "  AND all(n IN ring WHERE a.accountId <= n.accountId)\n"
                "WITH [n IN nodes(path) | n.accountId] AS cyclePath,\n"
                "     [r IN relationships(path) | r.amount] AS amounts\n"
                "WITH cyclePath, collect(amounts)[0] AS amounts\n"
                "RETURN cyclePath, amounts, size(cyclePath) - 1 AS hops\n"
                "ORDER BY hops, cyclePath[0]\nLIMIT 50"
            )},
        },
        {
            "type": "cypherTemplate",
            "name": "account_activity",
            "description": "Show one account's holder, money sent and received (with "
                           "counterparties), and whether it is part of a fraud ring.",
            "enabled": True,
            "config": {
                "template": (
                    "MATCH (a:Account {accountId: $accountId})\n"
                    "OPTIONAL MATCH (a)-[o:TRANSFERRED_TO]->(to:Account)\n"
                    "WITH a, collect({to: to.accountId, amount: o.amount, "
                    "at: toString(o.timestamp)})[..20] AS sent, sum(o.amount) AS totalSent\n"
                    "OPTIONAL MATCH (from:Account)-[i:TRANSFERRED_TO]->(a)\n"
                    "WITH a, sent, totalSent, collect({from: from.accountId, amount: i.amount, "
                    "at: toString(i.timestamp)})[..20] AS received, sum(i.amount) AS totalReceived\n"
                    "RETURN a.accountId AS accountId, a.holderName AS holder,\n"
                    "       round(totalSent, 2) AS totalSent, round(totalReceived, 2) AS totalReceived,\n"
                    "       sent, received,\n"
                    "       EXISTS { MATCH (a)-[:TRANSFERRED_TO*3..5]->(a) } AS inFraudRing"
                ),
                "parameters": [
                    {"name": "accountId", "data_type": "string",
                     "description": "Account ID like ACC004"}
                ],
            },
        },
    ],
}

API2 = API + "/v2beta1"


def call(method, path, token, body=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(API2 + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def main():
    token = get_token()

    code, orgs = call("GET", "/organizations", token)
    if code != 200:
        sys.exit(f"GET /organizations -> {code} {orgs}")
    org_id = orgs["data"][0]["id"]

    code, projs = call("GET", f"/organizations/{org_id}/projects", token)
    if code != 200:
        sys.exit(f"GET projects -> {code} {projs}")
    proj_id = projs["data"][0]["id"]
    print(f"Organization: {org_id}\nProject: {proj_id}")

    base = f"/organizations/{org_id}/projects/{proj_id}/agents"
    code, body = call("GET", base, token)
    if code != 200:
        sys.exit(f"GET agents -> {code} {body}")
    agents = body if isinstance(body, list) else body.get("data", [])
    names = [AGENT["name"], *OLD_NAMES]
    existing = next((a for a in agents if a.get("name") in names), None)

    if existing:
        print(f"Updating existing agent {existing['id']}...")
        code, resp = call("PUT", f"{base}/{existing['id']}", token, AGENT)
    else:
        print("Creating agent...")
        code, resp = call("POST", base, token, AGENT)

    if code not in (200, 201):
        sys.exit(f"Agent request failed -> {code} {json.dumps(resp, indent=2)}")
    agent_id = resp.get("id") or (existing or {}).get("id")
    print(f"Agent ready: '{AGENT['name']}'  id={agent_id}")
    print("Open console.neo4j.io -> Agents to chat with it.")


if __name__ == "__main__":
    main()
