"""Seed mock fraud data: 30 accounts, normal transfers, and 3 planted money-laundering rings.

Data model (fraud detection):
    (:Account {accountId, holderName, createdAt})
    (:Account)-[:TRANSFERRED_TO {txId, amount, timestamp}]->(:Account)

Normal transfers never create loops:
  - between clean accounts they only go lower-number -> higher-number
  - clean accounts may send money INTO ring accounts, but ring accounts only
    send money around their own ring
So the ONLY cycles are the planted rings, which makes it easy to check the detector.

Safe to re-run: uses MERGE, so it won't create duplicates.
Run with --reset to delete all existing :Account data first.
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import DATABASE, get_driver  # noqa: E402

random.seed(42)  # same data every run

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Isha", "Vikram", "Ananya", "Arjun", "Sara"]
LAST = ["Sharma", "Patel", "Iyer", "Khan", "Reddy", "Gupta", "Das", "Nair", "Singh", "Mehta"]

NUM_ACCOUNTS = 30
account_ids = [f"ACC{i:03d}" for i in range(1, NUM_ACCOUNTS + 1)]
base_time = datetime(2026, 9, 1, 9, 0)

accounts = [
    {
        "accountId": acc,
        "holderName": f"{random.choice(FIRST)} {random.choice(LAST)}",
        "createdAt": (base_time - timedelta(days=random.randint(30, 900))).isoformat(),
    }
    for acc in account_ids
]

transfers = []
tx_counter = 0


def add_tx(src, dst, amount, when):
    global tx_counter
    tx_counter += 1
    transfers.append({"txId": f"TX{tx_counter:05d}", "from": src, "to": dst,
                      "amount": round(amount, 2), "timestamp": when.isoformat()})


# Planted rings (length 3, 4, 5): money goes round and comes back, slightly shrinking
RINGS = [
    ["ACC027", "ACC011", "ACC019"],
    ["ACC030", "ACC004", "ACC015", "ACC022"],
    ["ACC025", "ACC008", "ACC013", "ACC002", "ACC017"],
]
ring_members = {acc for ring in RINGS for acc in ring}
clean = [acc for acc in account_ids if acc not in ring_members]
ring_list = sorted(ring_members)

# Normal activity between clean accounts: lower index -> higher index (no loops)
for _ in range(50):
    i, j = sorted(random.sample(range(len(clean)), 2))
    add_tx(clean[i], clean[j], random.uniform(50, 5000),
           base_time + timedelta(hours=random.randint(0, 24 * 20)))

# Clean accounts paying INTO ring accounts (one-way, so still no new loops)
for _ in range(20):
    add_tx(random.choice(clean), random.choice(ring_list), random.uniform(50, 5000),
           base_time + timedelta(hours=random.randint(0, 24 * 20)))
for ring in RINGS:
    amount = random.uniform(9000, 15000)
    when = base_time + timedelta(days=random.randint(1, 15))
    for k, src in enumerate(ring):
        dst = ring[(k + 1) % len(ring)]
        add_tx(src, dst, amount, when)
        amount *= 0.98                      # small "fee" skimmed each hop
        when += timedelta(hours=random.randint(1, 6))

with get_driver() as driver:
    if "--reset" in sys.argv:
        driver.execute_query("MATCH (a:Account) DETACH DELETE a", database_=DATABASE)
        print("Deleted existing :Account nodes and their transfers.")
    driver.execute_query(
        "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.accountId IS UNIQUE",
        database_=DATABASE)
    driver.execute_query(
        """
        UNWIND $rows AS row
        MERGE (a:Account {accountId: row.accountId})
        SET a.holderName = row.holderName, a.createdAt = datetime(row.createdAt)
        """, rows=accounts, database_=DATABASE)
    driver.execute_query(
        """
        UNWIND $rows AS row
        MATCH (s:Account {accountId: row.from}), (d:Account {accountId: row.to})
        MERGE (s)-[t:TRANSFERRED_TO {txId: row.txId}]->(d)
        SET t.amount = row.amount, t.timestamp = datetime(row.timestamp)
        """, rows=transfers, database_=DATABASE)

print(f"Seeded {len(accounts)} accounts and {len(transfers)} transfers "
      f"({len(RINGS)} planted rings: lengths {[len(r) for r in RINGS]}).")
