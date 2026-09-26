"""Neo4j Aura quickstart: connect, create a small graph, query it, close.

Credentials are read automatically from aura_credentials.txt (never hardcode passwords).
You can also override them with $env:NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE.
"""
import os
import sys

from neo4j import GraphDatabase

# Auto-load credentials from aura_credentials.txt (created by create_instance.py)
_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura_credentials.txt")
if os.path.exists(_creds):
    with open(_creds, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

URI = os.getenv("NEO4J_URI", "neo4j+s://319896c3.databases.neo4j.io")
USERNAME = os.getenv("NEO4J_USERNAME", "319896c3")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "319896c3")


def create_example_graph(driver):
    # Parameters are passed as keyword args, never concatenated into the query.
    summary = driver.execute_query(
        """
        CREATE (a:Person {name: $name})
        CREATE (b:Person {name: $friendName})
        CREATE (a)-[:KNOWS]->(b)
        """,
        name="Alice",
        friendName="David",
        database_=DATABASE,
    ).summary
    print(
        f"Created {summary.counters.nodes_created} nodes "
        f"in {summary.result_available_after} ms."
    )


def query_graph(driver):
    records, summary, keys = driver.execute_query(
        """
        MATCH (p:Person)-[:KNOWS]->(:Person)
        RETURN p.name AS name
        """,
        database_=DATABASE,
    )
    for record in records:
        print(record.data())
    print(
        f"The query `{summary.query.strip()}` returned {len(records)} records "
        f"in {summary.result_available_after} ms."
    )


def main():
    if not PASSWORD:
        sys.exit("NEO4J_PASSWORD is not set. Set it in your shell first.")

    # The `with` block closes the driver automatically (step 5).
    with GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD)) as driver:
        driver.verify_connectivity()
        print("Connected to Neo4j.")
        create_example_graph(driver)
        query_graph(driver)


if __name__ == "__main__":
    main()
