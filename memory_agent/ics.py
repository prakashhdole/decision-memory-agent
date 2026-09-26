"""Turn a week plan into an .ics calendar file (works with Google Calendar, Outlook, Apple)."""
from datetime import datetime, timedelta, timezone


def _esc(t):
    return (t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def plan_to_ics(result):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Decision Memory Agent//EN", "CALSCALE:GREGORIAN"]
    n = 0
    for day in result.get("days", []):
        for it in day.get("items", []):
            try:
                start = datetime.fromisoformat(f"{day['date']}T{it.get('time') or '09:00'}")
            except ValueError:
                continue
            title = it.get("title", "Plan item")
            # prep/focus blocks get 2h, everything else 1h
            dur = 2 if any(k in title for k in ("Prepare", "Continue", "🛠️", "✅")) else 1
            n += 1
            lines += ["BEGIN:VEVENT", f"UID:dma-{day['date']}-{n}@decision-memory-agent", f"DTSTAMP:{stamp}",
                      f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{start + timedelta(hours=dur):%Y%m%dT%H%M%S}",
                      f"SUMMARY:{_esc(title)}", f"DESCRIPTION:{_esc(it.get('why'))}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
