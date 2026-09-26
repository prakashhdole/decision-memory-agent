"""Find accounts involved in circular transaction chains of length 3 to 5.

A "circular chain" = money leaves an account, passes through 2-4 other
accounts, and comes back to where it started. Classic money-laundering signal.

Usage:
    python find_cycles.py
"""
from db import DATABASE, get_driver

MIN_HOPS, MAX_HOPS = 3, 5

# Cypher explained:
# 1. Follow 3-5 TRANSFERRED_TO hops that end back at the start account `a`.
# 2. Keep only simple cycles: no account visited twice (except start = end).
# 3. Each cycle is found once per member (A->B->C->A, B->C->A->B, ...).
#    Keep just one copy: the rotation that starts at the smallest accountId.
# 4. If two different transfers follow the same account route, list the route once.
CYCLE_QUERY = f"""
MATCH path = (a:Account)-[:TRANSFERRED_TO*{MIN_HOPS}..{MAX_HOPS}]->(a)
WITH a, path, nodes(path)[..-1] AS ring
WHERE size(ring) = size(reduce(seen = [], n IN ring |
          CASE WHEN n IN seen THEN seen ELSE seen + n END))
  AND all(n IN ring WHERE a.accountId <= n.accountId)
WITH [n IN nodes(path) | n.accountId]         AS cyclePath,
     [r IN relationships(path) | r.amount]     AS amounts
WITH cyclePath, collect(amounts)[0] AS amounts
RETURN cyclePath, amounts, size(cyclePath) - 1 AS hops
ORDER BY hops, cyclePath[0]
LIMIT 100
"""


def main():
    with get_driver() as driver:
        records, _, _ = driver.execute_query(CYCLE_QUERY, database_=DATABASE)

    if not records:
        print("No circular transaction chains found.")
        return

    flagged = set()
    print(f"Found {len(records)} circular chain(s) of length {MIN_HOPS}-{MAX_HOPS}:\n")
    for i, rec in enumerate(records, 1):
        path, amounts = rec["cyclePath"], rec["amounts"]
        flagged.update(path)
        # Show each hop with its amount: ACC1 --[12,000.00]--> ACC2 ...
        hops = " ".join(f"{src} --[{amt:,.2f}]-->" for src, amt in zip(path, amounts))
        print(f"  Cycle {i} ({rec['hops']} hops): {hops} {path[-1]}")

    print(f"\nFlagged accounts ({len(flagged)}): {', '.join(sorted(flagged))}")


if __name__ == "__main__":
    main()
