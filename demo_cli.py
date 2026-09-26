"""Run the challenge's example scenario end-to-end in the terminal.

    python demo_cli.py            # runs the scenario for user 'demo'
"""
from datetime import date

from db import get_driver
from memory_agent import graph
from memory_agent.agent import handle

SCENARIO = [
    "I prefer meetings in the morning and usually need two days to prepare for important client presentations.",
    "I'll prepare the presentation on Monday because the client meeting is on Wednesday.",
    "I need to send the invoice to Acme by Friday.",
    "I have a team sync on Thursday at 3pm.",
    "Help me plan my week.",
]


def show(result):
    r = result["result"]
    if result["saved"]:
        for label, text in result["saved"]:
            print(f"   💾 stored {label}: {text}")
    if not r:
        return
    print(f"\n🤖 ({r['source']}) {r['summary']}\n")
    for d in r["days"]:
        print(f"  {d['weekday']} {d['date']}")
        for it in d["items"] or [{"time": "", "title": "(free)", "why": ""}]:
            print(f"     {it['time']:>5}  {it['title']}   ← {it['why']}")
    for n in r["notes"]:
        print("  ", n)
    print("\n  Memories used:", *r["memories_used"], sep="\n   - ")


if __name__ == "__main__":
    today = date.today()
    with get_driver() as d:
        graph.ensure_schema(d)
        graph.reset(d, "demo")
        for msg in SCENARIO:
            print(f"\n👤 {msg}")
            show(handle(d, "demo", msg, today))
