"""Step 2 helper: turn a user message into structured memories + an intent.

Output shape (same for LLM and rule-based paths):
{
  "intent": "remember" | "plan" | "decide" | "recall",
  "preferences": [{"category", "text", "time_of_day", "prep_days"}],
  "commitments": [{"title", "date", "time", "kind", "importance"}],
  "tasks":       [{"title", "due_date", "priority"}],
  "decisions":   [{"text", "action", "date", "reason", "related_to"}],
  "outcomes":    [{"text", "success", "decision_hint"}]
}
Dates are ISO strings (YYYY-MM-DD) or null.
"""
import json
import re

from . import llm
from .dates import find_days, resolve_day, week_table

EMPTY = {"intent": "remember", "preferences": [], "commitments": [], "tasks": [],
         "decisions": [], "outcomes": []}

SYSTEM = """You extract long-term memories for a personal productivity assistant.
Return ONLY JSON with keys: intent, preferences, commitments, tasks, decisions, outcomes.
- intent: "plan" (user wants a schedule/plan), "decide" (wants help choosing / asks "should I"),
  "recall" (asks what you remember / what they decided), otherwise "remember".
- preferences: stable habits/likes. {category: meetings|preparation|focus|work_hours|breaks|other,
  text: short sentence, time_of_day: morning|afternoon|evening|null, prep_days: integer|null}
- commitments: fixed events with others (meetings, presentations, deadlines, appointments).
  {title, date: YYYY-MM-DD|null, time: HH:MM|null,
   kind: client_meeting|meeting|presentation|deadline|appointment|personal|other,
   importance: high|normal}
- tasks: things the user must do. {title, due_date: YYYY-MM-DD|null, priority: high|normal|low}
- decisions: choices the user made. {text: the full decision, action: what they will do,
  date: YYYY-MM-DD|null (when they will do it), reason: why|null,
  related_to: title of the related commitment/task|null}
  If a decision mentions an event ("because the client meeting is on Wednesday"),
  ALSO add that event to commitments.
- outcomes: results of earlier decisions ("the presentation went well").
  {text, success: true|false|null, decision_hint: few words identifying the decision}
Resolve weekday names using the calendar given. Never invent facts. Use [] when none."""


def extract(message, today):
    """Return the memory dict for a message (LLM first, rules as fallback)."""
    if llm.provider():
        prompt = (f"Today is {today.isoformat()} ({today.strftime('%A')}). "
                  f"Upcoming dates: {week_table(today)}.\n\nUser message:\n{message}")
        data = llm.chat_json(SYSTEM, prompt)
        if isinstance(data, dict):
            out = {k: (data.get(k) or ([] if k != "intent" else "remember")) for k in EMPTY}
            out["source"] = llm.provider()
            return out
    out = rule_extract(message, today)
    out["source"] = "rules"
    return out


# ---------------------------------------------------------------- rule-based
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a couple of": 2, "a": 1}
_EVENT_WORDS = r"(meeting|presentation|call|demo|interview|review|deadline|appointment|pitch|standup|sync|exam|workshop)"
_TIME_RE = re.compile(r"\bat (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def _time_of(text):
    m = _TIME_RE.search(text)
    if not m:
        return None
    h, mins, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def _tod(text):
    for t in ("morning", "afternoon", "evening"):
        if t in text:
            return t
    return None


def _date_in(text, today):
    days = find_days(text)
    d = resolve_day(days[0], today) if days else None
    return d.isoformat() if d else None


def _kind(text):
    t = text.lower()
    if "client" in t:
        return "client_meeting"
    for k in ("presentation", "deadline", "appointment", "interview"):
        if k in t:
            return k
    return "meeting" if re.search(_EVENT_WORDS, t) else "other"


def _clean_title(t):
    t = re.sub(r"\b(on|this|next)\s+(" + "|".join(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
         "today", "tomorrow"]) + r")\b", "", t, flags=re.I)
    t = _TIME_RE.sub("", t)
    t = re.sub(r"^\s*(i have|i've got|i got|there is|there's|we have)\s+", "", t, flags=re.I)
    t = re.sub(r"^\s*(the|a|an|my|our)\s+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" .,!").strip()


def _cap(t):
    return t[:1].upper() + t[1:] if t else t


def _event_from(text, today):
    """Find an event like 'the client meeting is on Wednesday' inside text."""
    m = re.search(r"(?:the |my |a |our )?([\w\s-]*?" + _EVENT_WORDS + r"[\w\s-]*?)\s+(?:is|are|was|will be)?\s*(?:on|this|next)?\s*"
                  r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)",
                  text, re.I)
    if not m:
        return None
    title = _clean_title(m.group(1))
    if not title:
        return None
    imp = "high" if re.search(r"client|important|board|investor|presentation|pitch", text, re.I) else "normal"
    return {"title": _cap(title), "date": resolve_day(m.group(3), today).isoformat(),
            "time": _time_of(text), "kind": _kind(title), "importance": imp}


def rule_extract(message, today):
    out = json.loads(json.dumps(EMPTY))
    low = message.lower()

    if re.search(r"\b(plan|schedule|organi[sz]e)\b.*\b(week|day|days|tomorrow|monday|tuesday|wednesday|thursday|friday)\b", low):
        out["intent"] = "plan"
    elif re.search(r"\b(should i|help me (decide|choose)|which (one|option)|is it (a )?good idea|what do you (recommend|suggest))\b", low):
        out["intent"] = "decide"
    elif re.search(r"\b(what did i (decide|say)|remind me what|what do you (know|remember)|recall|my preferences)\b", low):
        out["intent"] = "recall"

    # split into sentences, then split "X and usually Y" style clauses
    parts = []
    for s in re.split(r"(?<=[.!?])\s+|\n+", message):
        parts += re.split(r",?\s+and\s+(?=(?:i |usually|always|also|need|prefer|like)\b)", s, flags=re.I)

    for raw in parts:
        s = raw.strip()
        if not s:
            continue
        l = s.lower()

        # decisions: "I'll prepare X on Monday because Y"
        dm = re.match(r"^(?:ok(?:ay)?,?\s*)?(?:i'll|i will|i am going to|i'm going to|i've decided to|i have decided to|"
                      r"i decided to|i'm gonna|let's|we'll)\s+(.+)$", s, re.I)
        if dm:
            body = dm.group(1)
            bm = re.search(r"\b(because|since|so that)\b", body, re.I)
            action_part, reason = (body[:bm.start()], body[bm.end():]) if bm else (body, "")
            ev = _event_from(reason, today) if reason else None
            if ev:
                out["commitments"].append(ev)
            out["decisions"].append({
                "text": s.rstrip("."),
                "action": _clean_title(action_part),
                "date": _date_in(action_part, today),
                "reason": reason.strip(" .") or None,
                "related_to": ev["title"] if ev else None,
            })
            continue

        # outcomes of earlier decisions
        if re.search(r"\b(went (well|badly|great|ok|fine|poorly)|was a (success|disaster|failure)|worked( out)?|"
                     r"didn't work|did not work|failed|succeeded|was late|ran out of time)\b", l):
            success = None if re.search(r"\bok\b|fine", l) else not bool(
                re.search(r"badly|poorly|disaster|failure|didn't|did not|failed|late|ran out", l))
            hint = re.sub(r"\b(went|was|worked|didn't|did not|failed|succeeded).*$", "", l).strip(" .") or None
            out["outcomes"].append({"text": s.rstrip("."), "success": success, "decision_hint": hint})
            continue

        # preferences / habits
        if re.search(r"\bi (prefer|like|love|usually|always|tend to|normally|hate|dislike|don't like|avoid|work best)\b|"
                     r"^(usually|always|need)\b|\bmy (preference|habit)\b", l) or l.startswith(("prefer", "need ")):
            prep = None
            pm = re.search(r"(\d+|one|two|three|four|five|a couple of|a)\s+days?\s+(?:to|of)\s+prep", l)
            if pm:
                prep = int(pm.group(1)) if pm.group(1).isdigit() else _NUM.get(pm.group(1))
            cat = ("preparation" if prep or "prepar" in l else
                   "meetings" if "meeting" in l or "call" in l else
                   "focus" if re.search(r"focus|deep work|concentrat", l) else
                   "breaks" if "break" in l else
                   "work_hours" if re.search(r"work (from|until|till)|start work|finish work", l) else "other")
            text = re.sub(r"^(and\s+)?", "", s).rstrip(".")
            if not text.lower().startswith("i "):
                text = "I " + text[0].lower() + text[1:]
            out["preferences"].append({"category": cat, "text": text,
                                       "time_of_day": _tod(l), "prep_days": prep})
            continue

        # tasks
        tm = re.match(r"^(?:i need to|i have to|i must|i should|todo:?|task:?|remind me to|don't forget to)\s+(.+)$", s, re.I)
        if tm and out["intent"] == "remember":
            body = tm.group(1)
            out["tasks"].append({"title": _cap(_clean_title(re.split(r"\bby\b", body, flags=re.I)[0])),
                                 "due_date": _date_in(body, today),
                                 "priority": "high" if re.search(r"urgent|important|asap|critical", l) else "normal"})
            continue

        # standalone commitments: "I have a client meeting on Wednesday at 10am"
        if out["intent"] == "remember":
            ev = _event_from(s, today)
            if ev:
                out["commitments"].append(ev)

    return out
