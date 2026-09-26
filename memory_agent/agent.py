"""The full 5-step loop in one function: message in -> memories stored -> answer out."""
from datetime import date

from . import graph
from .extract import extract
from .planner import recommend


def handle(driver, user_id, message, today=None):
    today = today or date.today()
    mem_in = extract(message, today)                      # Step 1: understand the message
    saved = graph.store(driver, user_id, message, mem_in)  # Step 2: memory creation in Neo4j
    result = None
    if mem_in.get("intent") in ("plan", "decide", "recall", "revisit"):
        memory = graph.retrieve(driver, user_id)            # Step 4: memory retrieval
        result = recommend(mem_in["intent"], message, memory, today)  # Step 5: recommendation
    return {"intent": mem_in.get("intent"), "extracted_by": mem_in.get("source"),
            "saved": saved, "result": result}
