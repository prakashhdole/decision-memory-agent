// Put your cursor on a query and press Ctrl+Enter to run it.

// See everything in the database
MATCH (n) RETURN n LIMIT 50;

// Who knows who
MATCH (a:Person)-[:KNOWS]->(b:Person) RETURN a.name AS person, b.name AS knows;

// Count nodes by type
MATCH (n) RETURN labels(n) AS type, count(*) AS howMany;
