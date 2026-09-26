"""Shared Neo4j connection helper. Reads credentials from aura_credentials.txt."""
import os

from neo4j import GraphDatabase

_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura_credentials.txt")
if os.path.exists(_creds):
    with open(_creds, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", USERNAME)  # Aura: database name = instance id


def get_driver():
    if not (URI and USERNAME and PASSWORD):
        raise SystemExit("Missing Neo4j credentials. Check aura_credentials.txt.")
    # notifications off: hides harmless "label does not exist yet" warnings
    return GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD), notifications_min_severity="OFF")
