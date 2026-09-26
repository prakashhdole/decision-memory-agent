"""Step 5: personalized recommendations built from retrieved memories.

Every result has the same shape so the UI can show it:
{
  "kind": "plan" | "answer",
  "summary": str,
  "days": [{"date", "weekday", "items": [{"time", "title", "why"}]}],   # plans only
  "notes": [str],             # warnings / tips derived from memory
  "memories_used": [str],     # which stored memories influenced the answer
  "source": "rules" | "gemini" | "openai"
}
The rule-based planner always runs first (deterministic, explainable). If an LLM
is configured it refines that draft into more natural advice.
"""
import json
import re
from datetime import date, timedelta

from . import llm
from .dates import planning_week

SLOTS = {"morning": "09:30", "afternoon": "14:00", "evening": "17:00"}
MEETING_KINDS = {"meeting", "client_meeting", "presentation", "interview", "appointment"}


def recommend(intent, question, mem, today):
    draft = {"plan": rule_plan, "decide": rule_decide,
             "revisit": rule_revisit}.get(intent, rule_recall)(question, mem, today)
    draft["source"] = "rules"
    if llm.provider():
        refined = _llm_refine(intent, question, mem, today, draft)
        if refined:
            return refined
    return draft


# ------------------------------------------------------------------ helpers
def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _pref(mem, category):
    prefs = [p for p in mem["preferences"] if p.get("category") == category]
    return prefs[-1] if prefs else None


def _working_days_before(d, n):
    """The n working days immediately before date d (oldest first)."""
    out, cur = [], d
    while len(out) < n:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur)
    return sorted(out)


def _words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())}


# ------------------------------------------------------------------ plan
def rule_plan(question, mem, today):
    days = planning_week(today)
    if not days:
        days = planning_week(today + timedelta(days=1))
    items = {d: [] for d in days}
    used, notes = [], []

    def use(label, text):
        tag = f"{label}: {text}"
        if tag not in used:
            used.append(tag)

    meet_pref = _pref(mem, "meetings")
    meet_tod = (meet_pref or {}).get("timeOfDay")
    meet_slot = SLOTS.get(meet_tod, "10:00")
    focus_slot = "14:00" if meet_tod == "morning" else "09:30"
    prep_pref = _pref(mem, "preparation")
    prep_days = (prep_pref or {}).get("prepDays")

    # 1) fixed commitments
    for c in mem["commitments"]:
        cd = _d(c.get("date"))
        if cd not in items:
            continue
        why = "Commitment you told me about"
        time = c.get("time")
        if not time and c.get("kind") in MEETING_KINDS:
            time = meet_slot
            if meet_pref:
                why += f"; placed in the {meet_tod} because you prefer {meet_tod} meetings"
                use("Preference", meet_pref["text"])
        if c.get("time") and meet_tod == "morning" and c.get("kind") in MEETING_KINDS and c["time"] >= "12:00":
            notes.append(f"⚠️ **{c['title']}** is at {c['time']} ({cd:%A}), outside your preferred morning "
                         f"meeting time. Consider asking to move it to the morning.")
            use("Preference", meet_pref["text"])
        items[cd].append({"time": time or meet_slot, "title": f"📅 {c['title']}", "why": why})
        use("Commitment", f"{c['title']} on {cd:%A}")

    # 2) decisions the user already made
    decided_for = {}
    for dcs in mem["decisions"]:
        dd = _d(dcs.get("date"))
        if dcs.get("relatedTo"):
            decided_for.setdefault(dcs["relatedTo"], []).append(dcs)
        if dd in items and dcs.get("status") == "planned":
            action = (dcs.get("action") or dcs["text"]).strip()
            items[dd].append({"time": focus_slot, "title": f"✅ {action[:1].upper() + action[1:]}",
                              "why": f"Your decision: “{dcs['text']}”"})
            use("Decision", dcs["text"])

    # 3) preparation rule for important events
    if prep_days:
        for c in mem["commitments"]:
            cd = _d(c.get("date"))
            important = c.get("importance") == "high" or c.get("kind") in ("client_meeting", "presentation")
            if not cd or cd < today or not important:
                continue
            prep = _working_days_before(cd, prep_days)
            decs = [x for x in decided_for.get(c["title"], []) if x.get("date")]
            use("Preference", prep_pref["text"])
            if decs:
                start = min(_d(x["date"]) for x in decs)
                if start <= prep[0]:
                    notes.append(f"✔️ Your plan to start on **{start:%A}** gives you {prep_days}+ days before "
                                 f"**{c['title']}** ({cd:%A}), which matches your {prep_days}-day prep habit.")
                else:
                    notes.append(f"⚠️ Starting on **{start:%A}** leaves less than your usual {prep_days} days "
                                 f"to prepare for **{c['title']}**. Consider starting on **{prep[0]:%A}**.")
                decided_days = {_d(x["date"]) for x in decs}
                action = (decs[0].get("action") or "prepare").strip()
                for p in prep:
                    if p in items and p not in decided_days and p >= start:
                        items[p].append({"time": focus_slot, "title": f"🛠️ Continue: {action}",
                                         "why": f"You usually need {prep_days} days to prepare for "
                                                f"important client presentations"})
            else:
                for p in prep:
                    if p in items:
                        items[p].append({"time": focus_slot, "title": f"🛠️ Prepare for {c['title']}",
                                         "why": f"You haven't decided when to prepare. Blocked based on your "
                                                f"{prep_days}-day prep habit"})
                notes.append(f"💡 You haven't told me when you'll prepare for **{c['title']}**, so I blocked "
                             f"{', '.join(f'{p:%A}' for p in prep)} for it.")

    # 4) open tasks
    for t in mem["tasks"]:
        due = _d(t.get("dueDate"))
        if due and due < days[0]:
            notes.append(f"⏰ **{t['title']}** was due {due:%A %d %b}. It's overdue.")
            target = days[0]
        elif due in items:
            target = due
        elif due:
            continue  # due later than this week
        else:
            target = min(items, key=lambda d: len(items[d]))
        items[target].append({"time": "11:30" if meet_tod == "morning" else focus_slot,
                              "title": f"📝 {t['title']}",
                              "why": "Task" + (f" due {due:%A}" if due else " with no deadline, put on your lightest day")})
        use("Task", t["title"])

    # 5) learn from failures: add a rehearsal/buffer slot before important events
    failures = [o for o in mem["outcomes"] if o.get("success") is False]
    if failures:
        for c in mem["commitments"]:
            cd = _d(c.get("date"))
            important = c.get("importance") == "high" or c.get("kind") in ("client_meeting", "presentation")
            if cd in items and important:
                before = _working_days_before(cd, 1)[0]
                target = before if before in items else cd
                items[target].append({
                    "time": "11:00" if meet_tod == "morning" else "16:30",
                    "title": f"🛟 Buffer: rehearse & finalise for {c['title']}",
                    "why": f"Added because last time: “{failures[-1]['text']}”"})
        notes.append(f"🛟 I added buffer time before important events because last time "
                     f"“{failures[-1]['text']}”.")

    # 6) lessons from past outcomes
    for o in mem["outcomes"]:
        if o.get("success") is False:
            notes.append(f"📉 Last time: “{o['text']}”. Leave extra buffer for similar work.")
            use("Outcome", o["text"])
        elif o.get("success") is True:
            notes.append(f"📈 What worked before: “{o['text']}”. Repeating the same approach.")
            use("Outcome", o["text"])

    if meet_tod == "morning":
        notes.append("🧠 Afternoons are kept for focus work, because your meetings go in the morning.")

    out_days = [{"date": d.isoformat(), "weekday": f"{d:%A}",
                 "items": sorted(items[d], key=lambda x: x["time"])} for d in days]
    busy = sum(len(d["items"]) for d in out_days)
    return {"kind": "plan",
            "summary": (f"Here's your plan for {days[0]:%A %d %b} – {days[-1]:%A %d %b}, "
                        f"built from {len(used)} things I remember about you." if busy else
                        "I don't have any tasks, commitments or decisions for this week yet. "
                        "Tell me about your week first."),
            "days": out_days, "notes": notes, "memories_used": used}


# ------------------------------------------------------------------ decide
def rule_decide(question, mem, today):
    q = _words(question)
    used, lines = [], []
    for dcs in mem["decisions"]:
        if q & _words(dcs["text"] + " " + (dcs.get("relatedTo") or "")):
            res = (f", and it **{'worked' if dcs.get('outcomeSuccess') else 'did not work out'}** "
                   f"(“{dcs['outcome']}”)" if dcs.get("outcome") else "")
            lines.append(f"- Earlier you decided: “{dcs['text']}”{res}.")
            used.append(f"Decision: {dcs['text']}")
    for p in mem["preferences"]:
        if q & _words(p["text"]) or p.get("category") in ("preparation", "meetings", "focus"):
            lines.append(f"- Your preference: “{p['text']}”.")
            used.append(f"Preference: {p['text']}")
    week = planning_week(today)
    load = sum(1 for c in mem["commitments"] if _d(c.get("date")) in week) + \
           sum(1 for t in mem["tasks"] if not t.get("dueDate") or _d(t["dueDate"]) in week)
    lines.append(f"- This week you already have **{load}** commitments/tasks.")
    advice = ("Your week is already busy, so I'd only say yes if it can wait until next week or replace something."
              if load >= 4 else "You have room this week, so this looks feasible if it fits your preferences above.")
    return {"kind": "answer", "summary": "Here's what I remember that's relevant:\n" + "\n".join(lines) +
            f"\n\n**Suggestion:** {advice}", "days": [], "notes": [], "memories_used": used}


# ------------------------------------------------------------------ revisit a decision
def rule_revisit(question, mem, today):
    """Explain a past decision: why, what it was for, which habits support it, how it went."""
    if not mem["decisions"]:
        return {"kind": "answer", "summary": "You haven't told me about any decisions yet. "
                "Try: “I'll prepare the presentation on Monday because the client meeting is on Wednesday.”",
                "days": [], "notes": [], "memories_used": []}
    q = _words(question)
    best = max(mem["decisions"], key=lambda d: (len(q & _words(d["text"] + " " + (d.get("relatedTo") or ""))),
                                                d.get("createdAt") or ""))
    used = [f"Decision: {best['text']}"]
    lines = [f"**Decision:** “{best['text']}”"]
    if best.get("createdAt"):
        lines.append(f"**Made on:** {best['createdAt'][:10]}")
    lines.append(f"**Your reason:** {best.get('reason') or 'you did not give a reason'}")

    dd, rd = _d(best.get("date")), _d(best.get("relatedDate"))
    if best.get("relatedTo"):
        lines.append(f"**Linked to:** {best['relatedTo']}" + (f" on {rd:%A %d %b}" if rd else "") +
                     "  \n`Decision ─FOR→ " + best["relatedTo"] + "` in the memory graph")
        used.append(f"Commitment: {best['relatedTo']}")

    prep = _pref(mem, "preparation")
    if prep and prep.get("prepDays") and dd and rd:
        gap = len([1 for i in range((rd - dd).days) if (dd + timedelta(days=i)).weekday() < 5])
        fits = gap >= prep["prepDays"]
        lines.append(f"**Fits your habits?** {'✔️ Yes' if fits else '⚠️ Not quite'}: you gave yourself "
                     f"{gap} working day(s), and you usually need {prep['prepDays']} "
                     f"(“{prep['text']}”).")
        used.append(f"Preference: {prep['text']}")

    if best.get("outcome"):
        ok = best.get("outcomeSuccess")
        lines.append(f"**Outcome:** {'📈' if ok else '📉' if ok is False else '➖'} “{best['outcome']}”")
        used.append(f"Outcome: {best['outcome']}")
        if ok is False:
            advice = ("Next time, start preparing one day earlier and block a rehearsal slot the day before. "
                      "I'll add that buffer automatically when I plan your week.")
        elif ok:
            advice = "This approach worked, so I'll suggest the same timing for similar events."
        else:
            advice = "Mixed result. Tell me what you'd change and I'll remember it."
    else:
        advice = ("No outcome recorded yet. After it happens, tell me how it went "
                  "(e.g. “The client presentation went well”) and I'll learn from it.")
    lines.append(f"\n**💡 Looking back:** {advice}")
    return {"kind": "answer", "summary": "\n\n".join(lines), "days": [], "notes": [], "memories_used": used}


# ------------------------------------------------------------------ recall
def rule_recall(question, mem, today):
    lines, used = [], []
    for label, key, fmt in [
        ("Preference", "preferences", lambda x: x["text"]),
        ("Commitment", "commitments", lambda x: f"{x['title']} ({x.get('date') or 'no date'})"),
        ("Task", "tasks", lambda x: f"{x['title']} (due {x.get('dueDate') or 'anytime'})"),
        ("Decision", "decisions", lambda x: x["text"] + (f" → outcome: {x['outcome']}" if x.get("outcome") else "")),
        ("Outcome", "outcomes", lambda x: x["text"]),
    ]:
        for x in mem[key]:
            lines.append(f"- **{label}:** {fmt(x)}")
            used.append(f"{label}: {fmt(x)}")
    return {"kind": "answer",
            "summary": ("Here's everything I remember:\n" + "\n".join(lines)) if lines else
                       "I don't remember anything yet. Tell me your preferences, tasks or decisions.",
            "days": [], "notes": [], "memories_used": used}


# ------------------------------------------------------------------ LLM refinement
SYSTEM = """You are a personal productivity and decision-memory assistant.
You receive the user's stored MEMORY (from a Neo4j graph) and a DRAFT answer produced by a
rule engine. Improve the draft into clear, friendly, personalized advice.
Rules: use ONLY facts from MEMORY; never invent meetings, tasks or dates; keep every
commitment and decision from the draft; each plan item needs a short "why" that cites the memory.
Return ONLY JSON with keys: summary (string, markdown ok), days (same format as draft,
[] if not a plan), notes (list of strings), memories_used (list of strings)."""


def _llm_refine(intent, question, mem, today, draft):
    prompt = json.dumps({"today": today.isoformat(), "intent": intent, "question": question,
                         "MEMORY": mem, "DRAFT": draft}, default=str)
    data = llm.chat_json(SYSTEM, prompt)
    if not isinstance(data, dict) or "summary" not in data:
        return None
    return {"kind": draft["kind"], "summary": data.get("summary", draft["summary"]),
            "days": data.get("days") if draft["kind"] == "plan" and data.get("days") else draft["days"],
            "notes": data.get("notes") or draft["notes"],
            "memories_used": data.get("memories_used") or draft["memories_used"],
            "source": llm.provider()}
