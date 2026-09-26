"""Steps 2 & 4: store memories in Neo4j and retrieve them.

Graph model
  (:User {userId})
  (:User)-[:SAID]->(:Interaction {text, at})                      raw messages (provenance)
  (:User)-[:HAS_PREFERENCE]->(:Preference {category, text, timeOfDay, prepDays, active})
  (:User)-[:HAS_COMMITMENT]->(:Commitment {title, date, time, kind, importance})
  (:User)-[:HAS_TASK]->(:Task {title, dueDate, priority, status})
  (:User)-[:MADE_DECISION]->(:Decision {text, action, date, reason, status})
  (:Decision)-[:FOR]->(:Commitment|:Task)                         why the decision exists
  (:User)-[:HAS_OUTCOME]->(:Outcome {text, success})-[:RESULT_OF]->(:Decision)
  (:Preference)-[:SUPERSEDES]->(:Preference)                      preference changed over time
  (every memory)-[:LEARNED_FROM]->(:Interaction)
"""
from neo4j.time import Date, DateTime

SCHEMA = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.userId IS UNIQUE",
    "CREATE INDEX commitment_key IF NOT EXISTS FOR (c:Commitment) ON (c.userId, c.key)",
    "CREATE INDEX task_key IF NOT EXISTS FOR (t:Task) ON (t.userId, t.key)",
]


def _db():
    from db import DATABASE  # root-level helper
    return DATABASE


def ensure_schema(driver):
    for q in SCHEMA:
        driver.execute_query(q, database_=_db())


def _q(driver, query, **params):
    records, _, _ = driver.execute_query(query, params, database_=_db())
    return records


# ------------------------------------------------------------------ store
def store(driver, user_id, message, mem):
    """Save one message and everything extracted from it. Returns short summaries."""
    iid = _q(driver, """
        MERGE (u:User {userId: $uid})
        CREATE (i:Interaction {id: randomUUID(), text: $text, at: datetime()})
        CREATE (u)-[:SAID]->(i)
        RETURN i.id AS id""", uid=user_id, text=message)[0]["id"]
    saved = []
    base = "MATCH (u:User {userId: $uid}), (i:Interaction {id: $iid}) "

    for p in mem.get("preferences", []):
        cat = p.get("category") or "other"
        _q(driver, base + """
            OPTIONAL MATCH (u)-[:HAS_PREFERENCE]->(old:Preference {category: $cat, active: true})
            WHERE old.text <> $text AND (
                  ($cat = 'meetings' AND $tod IS NOT NULL AND old.timeOfDay IS NOT NULL)
               OR ($cat = 'preparation' AND $prep IS NOT NULL AND old.prepDays IS NOT NULL))
            WITH u, i, collect(old) AS olds
            MERGE (u)-[:HAS_PREFERENCE]->(p:Preference {category: $cat, text: $text})
            ON CREATE SET p.id = randomUUID(), p.createdAt = datetime()
            SET p.active = true, p.timeOfDay = $tod, p.prepDays = $prep
            MERGE (p)-[:LEARNED_FROM]->(i)
            FOREACH (o IN olds | SET o.active = false MERGE (p)-[:SUPERSEDES]->(o))""",
           uid=user_id, iid=iid, cat=cat, text=p.get("text", ""),
           tod=p.get("time_of_day"), prep=p.get("prep_days"))
        saved.append(("Preference", p.get("text", "")))

    for c in mem.get("commitments", []):
        _q(driver, base + """
            MERGE (c:Commitment {userId: $uid, key: toLower($title) + '|' + coalesce($date, '')})
            ON CREATE SET c.id = randomUUID(), c.createdAt = datetime(), c.status = 'scheduled'
            SET c.title = $title, c.time = $time, c.kind = $kind, c.importance = $imp,
                c.date = CASE WHEN $date IS NULL THEN null ELSE date($date) END
            MERGE (u)-[:HAS_COMMITMENT]->(c)
            MERGE (c)-[:LEARNED_FROM]->(i)""",
           uid=user_id, iid=iid, title=c.get("title", "Event"), date=c.get("date"),
           time=c.get("time"), kind=c.get("kind") or "other", imp=c.get("importance") or "normal")
        saved.append(("Commitment", f"{c.get('title')} ({c.get('date') or 'no date'})"))

    for t in mem.get("tasks", []):
        _q(driver, base + """
            MERGE (t:Task {userId: $uid, key: toLower($title)})
            ON CREATE SET t.id = randomUUID(), t.createdAt = datetime(), t.status = 'open'
            SET t.title = $title, t.priority = $prio,
                t.dueDate = CASE WHEN $due IS NULL THEN null ELSE date($due) END
            MERGE (u)-[:HAS_TASK]->(t)
            MERGE (t)-[:LEARNED_FROM]->(i)""",
           uid=user_id, iid=iid, title=t.get("title", "Task"), due=t.get("due_date"),
           prio=t.get("priority") or "normal")
        saved.append(("Task", f"{t.get('title')} (due {t.get('due_date') or 'anytime'})"))

    for d in mem.get("decisions", []):
        _q(driver, base + """
            CREATE (d:Decision {id: randomUUID(), text: $text, action: $action, reason: $reason,
                                status: 'planned', createdAt: datetime(),
                                date: CASE WHEN $date IS NULL THEN null ELSE date($date) END})
            CREATE (u)-[:MADE_DECISION]->(d)
            CREATE (d)-[:LEARNED_FROM]->(i)
            WITH u, d
            OPTIONAL MATCH (u)-[:HAS_COMMITMENT|HAS_TASK]->(t)
            WHERE $rel IS NOT NULL AND (toLower(t.title) CONTAINS toLower($rel)
                                        OR toLower($rel) CONTAINS toLower(t.title))
            WITH d, t ORDER BY t.createdAt DESC LIMIT 1
            FOREACH (x IN CASE WHEN t IS NULL THEN [] ELSE [t] END | MERGE (d)-[:FOR]->(x))""",
           uid=user_id, iid=iid, text=d.get("text", ""), action=d.get("action"),
           reason=d.get("reason"), date=d.get("date"), rel=d.get("related_to"))
        saved.append(("Decision", d.get("text", "")))

    for o in mem.get("outcomes", []):
        success = o.get("success")
        linked = _q(driver, base + """
            MATCH (u)-[:MADE_DECISION]->(d:Decision)
            OPTIONAL MATCH (d)-[:FOR]->(t)
            WITH u, i, d, t,
                 CASE WHEN $hint IS NULL THEN 0 ELSE size([w IN split(toLower($hint), ' ')
                      WHERE size(w) > 3 AND (toLower(d.text) CONTAINS w
                                             OR toLower(coalesce(t.title, '')) CONTAINS w)]) END AS score
            ORDER BY score DESC, d.createdAt DESC LIMIT 1
            CREATE (o:Outcome {id: randomUUID(), text: $text, success: $success, createdAt: datetime()})
            CREATE (u)-[:HAS_OUTCOME]->(o)
            CREATE (o)-[:RESULT_OF]->(d)
            CREATE (o)-[:LEARNED_FROM]->(i)
            SET d.status = CASE $success WHEN true THEN 'succeeded' WHEN false THEN 'failed' ELSE 'done' END
            FOREACH (x IN CASE WHEN t IS NULL THEN [] ELSE [t] END | SET x.status = 'done')
            RETURN d.text AS decision""",
            uid=user_id, iid=iid, text=o.get("text", ""), success=success, hint=o.get("decision_hint"))
        if not linked:
            _q(driver, base + """
                CREATE (o:Outcome {id: randomUUID(), text: $text, success: $success, createdAt: datetime()})
                CREATE (u)-[:HAS_OUTCOME]->(o) CREATE (o)-[:LEARNED_FROM]->(i)""",
               uid=user_id, iid=iid, text=o.get("text", ""), success=success)
        saved.append(("Outcome", o.get("text", "") +
                      (f"  → linked to: {linked[0]['decision']}" if linked else "")))
    return saved


# ------------------------------------------------------------------ retrieve
def _plain(v):
    if isinstance(v, (Date, DateTime)):
        return v.iso_format()[:10] if isinstance(v, Date) else v.iso_format()[:16]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items() if k not in ("key", "userId")}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def retrieve(driver, user_id):
    """All active memories for a user, with their graph connections."""
    rec = _q(driver, """
        MATCH (u:User {userId: $uid})
        RETURN
          COLLECT { MATCH (u)-[:HAS_PREFERENCE]->(p:Preference) WHERE p.active
                    RETURN p {.*} ORDER BY p.createdAt } AS preferences,
          COLLECT { MATCH (u)-[:HAS_COMMITMENT]->(c:Commitment)
                    RETURN c {.*} ORDER BY c.date } AS commitments,
          COLLECT { MATCH (u)-[:HAS_TASK]->(t:Task) WHERE t.status <> 'done'
                    RETURN t {.*} ORDER BY t.dueDate } AS tasks,
          COLLECT { MATCH (u)-[:MADE_DECISION]->(d:Decision)
                    OPTIONAL MATCH (d)-[:FOR]->(x)
                    OPTIONAL MATCH (o:Outcome)-[:RESULT_OF]->(d)
                    RETURN d {.*, relatedTo: x.title, relatedDate: coalesce(x.date, x.dueDate),
                              relatedKind: x.kind, outcome: o.text, outcomeSuccess: o.success}
                    ORDER BY d.createdAt } AS decisions,
          COLLECT { MATCH (u)-[:HAS_OUTCOME]->(o:Outcome)
                    OPTIONAL MATCH (o)-[:RESULT_OF]->(d:Decision)
                    RETURN o {.*, decision: d.text} ORDER BY o.createdAt } AS outcomes
        """, uid=user_id)
    if not rec:
        return {k: [] for k in ("preferences", "commitments", "tasks", "decisions", "outcomes")}
    return {k: _plain(rec[0][k]) for k in rec[0].keys()}


def graph_triples(driver, user_id):
    """(fromLabel, fromName, relType, toLabel, toName) for drawing the memory graph."""
    return [r.data() for r in _q(driver, """
        MATCH (u:User {userId: $uid})-[r]->(n) WHERE NOT n:Interaction
          AND (NOT n:Preference OR n.active)
        RETURN 'User' AS fl, u.userId AS fn, type(r) AS rel, labels(n)[0] AS tl,
               coalesce(n.title, n.text) AS tn
        UNION
        MATCH (u:User {userId: $uid})-->(a)-[r:FOR|RESULT_OF|SUPERSEDES]->(b)
        RETURN labels(a)[0] AS fl, coalesce(a.title, a.text) AS fn, type(r) AS rel,
               labels(b)[0] AS tl, coalesce(b.title, b.text) AS tn
        """, uid=user_id)]


def reset(driver, user_id):
    _q(driver, """
        MATCH (u:User {userId: $uid})
        OPTIONAL MATCH (u)-->(n)
        DETACH DELETE n, u""", uid=user_id)
