# 🧠 Personal Productivity & Decision Memory Agent

An AI agent that remembers your preferences, tasks, commitments, decisions and their outcomes
in a Neo4j knowledge graph, then uses that memory to plan your week and support decisions.
Every recommendation says which memory it came from.

## Run it
```powershell
python -m streamlit run app.py      # opens http://localhost:8501
python demo_cli.py                  # same scenario in the terminal (backup demo)
```
Optional smarter language: paste a Gemini or OpenAI key into `llm_keys.txt`.
Without a key, the built-in rule engine handles everything.

## The 5-step flow
| Step | What happens | Code |
|---|---|---|
| 1. Interaction | User types a preference, task or decision | `app.py` |
| 2. Memory creation | Message becomes Preference / Commitment / Task / Decision / Outcome nodes in Neo4j | `memory_agent/extract.py`, `graph.store` |
| 3. New interaction | "Help me plan my week" / "Should I…?" / "What do you remember?" | `extract` detects intent |
| 4. Memory retrieval | Graph query pulls active preferences, this week's commitments, open tasks, decisions and their outcomes | `graph.retrieve` |
| 5. Recommendation | Week plan with a "why" for every item, conflict warnings and memories used | `memory_agent/planner.py` |

## Advanced features
- **Revisit decisions**: "Why did I decide to prepare on Monday?" returns the reason, the linked event,
  whether it fits your habits, the outcome and a lesson.
- **Learns from failure**: after "The presentation went badly, I ran out of time", future plans add a
  🛟 rehearsal buffer before important events.
- **Task completion**: "I sent the invoice to Acme" marks the matching task done.
- **Calendar export**: download any week plan as `.ics` (Google Calendar / Outlook / Apple).
- **Decision track record**: memory count, decisions, % that worked out, tasks done.
- **Secure**: login with PBKDF2-hashed passwords, lockout after 5 failed tries, private memory per user,
  secrets kept out of git.

## Graph model
```
(:User)-[:HAS_PREFERENCE]->(:Preference {category, timeOfDay, prepDays, active})
(:User)-[:HAS_COMMITMENT]->(:Commitment {title, date, time, kind, importance})
(:User)-[:HAS_TASK]->(:Task {title, dueDate, priority})
(:User)-[:MADE_DECISION]->(:Decision {text, action, date, reason, status})-[:FOR]->(:Commitment)
(:Outcome {text, success})-[:RESULT_OF]->(:Decision)
(:Preference)-[:SUPERSEDES]->(:Preference)        # preferences change over time
(any memory)-[:LEARNED_FROM]->(:Interaction {text, at})   # provenance
```

## 2-minute demo script
1. Click **Load example scenario**. It stores the morning-meetings preference, the 2-day prep habit,
   the "prepare on Monday" decision, an invoice task and a Thursday 3pm team sync.
2. Open the **Graph** tab to see the memory graph (decision → FOR → client meeting).
3. Click **Help me plan my week**:
   - Mon: prepare presentation (your decision); Tue: continue prep (2-day habit)
   - Wed 09:30: client meeting (placed in the morning, as you prefer)
   - ⚠️ Thursday 3pm team sync conflicts with your morning preference
   - ✔️ Monday start satisfies your 2-day prep rule
4. Type **"The client presentation went badly, I ran out of time."** It gets linked to the decision.
   Plan again and the agent warns you to leave extra buffer.
5. Type **"I prefer meetings in the afternoon."** The old preference is superseded and the plan adapts.
