"""Turn words like 'Monday' or 'tomorrow' into real dates."""
import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAY_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r"|today|tomorrow)\b", re.I)


def resolve_day(word, today):
    """'Monday' -> the next Monday on/after today. Returns a date or None."""
    if not word:
        return None
    w = word.lower().strip()
    if w == "today":
        return today
    if w == "tomorrow":
        return today + timedelta(days=1)
    if w in WEEKDAYS:
        return today + timedelta(days=(WEEKDAYS.index(w) - today.weekday()) % 7)
    try:
        return date.fromisoformat(w[:10])
    except ValueError:
        return None


def find_days(text):
    """All day words in text, in order."""
    return [m.group(1) for m in _DAY_RE.finditer(text)]


def planning_week(today):
    """Working days to plan: rest of this week (Mon-Fri), or next week if it's the weekend."""
    start = today if today.weekday() < 5 else today + timedelta(days=7 - today.weekday())
    monday = start - timedelta(days=start.weekday())
    return [d for d in (monday + timedelta(days=i) for i in range(5)) if d >= start]


def week_table(today):
    """Text like 'Monday=2026-09-28, ...' to help the LLM resolve dates."""
    return ", ".join(f"{WEEKDAYS[resolve_day(w, today).weekday()].title()}="
                     f"{resolve_day(w, today).isoformat()}" for w in WEEKDAYS)
