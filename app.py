"""Personal Productivity & Decision Memory Agent: Streamlit web app.

Run locally:  run_local.cmd   (or: python -m streamlit run app.py --server.address localhost)
Logins come from [users] in .streamlit/secrets.toml (see make_user.py).
"""
import os
from datetime import date

import streamlit as st

st.set_page_config(page_title="Decision Memory Agent", page_icon="🧠", layout="wide")

# Copy root-level secrets (NEO4J_*, GEMINI_API_KEY, ...) into env vars BEFORE db/llm load them
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)):
            os.environ.setdefault(_k, str(_v))
    USERS = {k.lower(): v for k, v in st.secrets.get("users", {}).items()}
except Exception:  # no secrets file configured
    USERS = {}

from db import get_driver  # noqa: E402
from memory_agent import graph, llm  # noqa: E402
from memory_agent.agent import handle  # noqa: E402
from memory_agent.auth import LoginGuard, check_login  # noqa: E402
from memory_agent.ics import plan_to_ics  # noqa: E402


@st.cache_resource
def login_guard():
    return LoginGuard()  # shared by all visitors, so refreshing the page doesn't reset lockouts


# ---------------------------------------------------------------- login gate
if not st.session_state.get("user"):
    st.title("🧠 Decision Memory Agent")
    if not USERS:
        st.error("No logins are configured. Add a [users] section to the app's secrets (see make_user.py).")
        st.stop()
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            ok, msg = check_login(USERS, login_guard(), u, p)
            if ok:
                st.session_state.user = u.strip().lower()
                st.session_state.chat = []
                st.rerun()
            st.error(msg)
    st.stop()

EXAMPLE = [
    "I prefer meetings in the morning and usually need two days to prepare for important client presentations.",
    "I'll prepare the presentation on Monday because the client meeting is on Wednesday.",
    "I need to send the invoice to Acme by Friday.",
    "I have a team sync on Thursday at 3pm.",
]
QUICK = ["Help me plan my week.", "What do you remember about me?",
         "Why did I decide to prepare on Monday?", "Should I take on the extra project this week?",
         "I sent the invoice to Acme.", "The client presentation went badly, I ran out of time."]


@st.cache_resource
def driver():
    d = get_driver()
    graph.ensure_schema(d)
    return d


def run(msg):
    res = handle(driver(), st.session_state.user, msg, date.today())
    st.session_state.chat.append({"role": "user", "content": msg})
    st.session_state.chat.append({"role": "assistant", "res": res})


# ---------------------------------------------------------------- sidebar
st.session_state.setdefault("chat", [])
with st.sidebar:
    st.title("🧠 Memory Agent")
    st.markdown(f"Logged in as **{st.session_state.user}**. Your memory is private to you.")
    if st.button("Log out", width="stretch"):
        st.session_state.clear()
        st.rerun()
    p = llm.provider()
    st.caption(f"Reasoning: **{p.title() + ' LLM' if p else 'built-in rules'}** · Memory: **Neo4j Aura**")
    if llm.last_error:
        st.warning("The AI model was unavailable, so built-in rules were used.")

    st.subheader("Demo")
    if st.button("▶️ Load example scenario", width="stretch"):
        for m in EXAMPLE:
            run(m)
        st.rerun()
    st.caption("Then try:")
    for q in QUICK:
        if st.button(q, width="stretch"):
            run(q)
            st.rerun()
    st.divider()
    if st.button("🗑️ Clear my memory", width="stretch"):
        graph.reset(driver(), st.session_state.user)
        st.session_state.chat = []
        st.rerun()

prompt = st.chat_input("Tell me a preference, task or decision… or ask me to plan your week",
                       max_chars=1000)
if prompt:
    run(prompt)

# ---------------------------------------------------------------- layout
left, right = st.columns([3, 2], gap="large")


def render_result(res, idx):
    for label, text in res["saved"]:
        icon = "✔️ Updated in Neo4j" if label == "Completed" else "💾 Stored in Neo4j"
        st.caption(f"{icon} → **{label}**: {text}")
    r = res["result"]
    if not r:
        if not res["saved"]:
            st.markdown("I didn't find a preference, task or decision in that. Try something like "
                        "*“I prefer deep work before lunch”* or ask *“Help me plan my week.”*")
        else:
            st.markdown("Got it, I'll remember that. ✅")
        return
    st.caption(f"① understood intent **{res['intent']}** → ② saved → ④ retrieved "
               f"**{len(r['memories_used'])}** relevant memories → ⑤ recommendation ({r['source']})")
    st.markdown(r["summary"])
    for d in r.get("days", []):
        with st.container(border=True):
            st.markdown(f"**{d['weekday']}** · {d['date']}")
            if not d["items"]:
                st.caption("Free, nothing planned")
            for it in d["items"]:
                st.markdown(f"`{it['time']}` {it['title']}  \n<span style='color:gray;font-size:0.85em'>"
                            f"↳ {it['why']}</span>", unsafe_allow_html=True)
    for n in r.get("notes", []):
        st.markdown(n)
    if r.get("days") and any(d["items"] for d in r["days"]):
        st.download_button("📅 Add this plan to my calendar (.ics)", plan_to_ics(r),
                           file_name="my-week-plan.ics", mime="text/calendar", key=f"ics-{idx}")
    if r["memories_used"]:
        with st.expander(f"🔎 Memories used ({len(r['memories_used'])})"):
            for m in r["memories_used"]:
                st.markdown(f"- {m}")


with left:
    st.header("Chat")
    if not st.session_state.chat:
        st.info("**Try it:** click **Load example scenario** in the sidebar, then **Help me plan my week**. "
                "Or type your own preferences, tasks and decisions below.")
    for i, m in enumerate(st.session_state.chat):
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                render_result(m["res"], i)


def dot(triples):
    colors = {"User": "#6c5ce7", "Preference": "#00b894", "Commitment": "#0984e3", "Task": "#fdcb6e",
              "Decision": "#e17055", "Outcome": "#d63031"}
    nodes, edges = {}, []
    for t in triples:
        for lab, name in ((t["fl"], t["fn"]), (t["tl"], t["tn"])):
            key = f"{lab}:{name}"
            if key not in nodes:
                short = (name or "")[:38] + ("…" if name and len(name) > 38 else "")
                nodes[key] = (len(nodes), lab, short.replace('"', "'"))
        edges.append((nodes[f"{t['fl']}:{t['fn']}"][0], nodes[f"{t['tl']}:{t['tn']}"][0], t["rel"]))
    lines = ['digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", '
             'fontcolor=white, fontsize=10]; edge [fontsize=8, color=gray50, fontcolor=gray40];']
    for _, (i, lab, name) in nodes.items():
        lines.append(f'n{i} [label="{lab}\\n{name}", fillcolor="{colors.get(lab, "#636e72")}"];')
    for a, b, rel in edges:
        lines.append(f'n{a} -> n{b} [label="{rel}"];')
    return "\n".join(lines) + "}"


with right:
    st.header("What I remember")
    mem = graph.retrieve(driver(), st.session_state.user)
    tr = graph.track_record(driver(), st.session_state.user)
    judged = tr["succeeded"] + tr["failed"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Memories", sum(len(v) for v in mem.values()))
    c2.metric("Decisions", tr["decisions"])
    c3.metric("Worked out", f"{round(100 * tr['succeeded'] / judged)}%" if judged else "–",
              help="Share of decisions with a recorded outcome that went well")
    c4.metric("Tasks done", f"{tr['tasksDone']}/{tr['tasksDone'] + tr['tasksOpen']}")
    tab_list, tab_graph = st.tabs(["📋 Memories", "🕸️ Graph"])
    with tab_list:
        sections = [
            ("⭐ Preferences", mem["preferences"], lambda x: x["text"]),
            ("📅 Commitments", mem["commitments"],
             lambda x: f"{x['title']}: {x.get('date') or 'no date'} {x.get('time') or ''}"),
            ("📝 Tasks", mem["tasks"], lambda x: f"{x['title']} (due {x.get('dueDate') or 'anytime'})"),
            ("✅ Decisions", mem["decisions"],
             lambda x: x["text"] + (f"  \n↳ for **{x['relatedTo']}**" if x.get("relatedTo") else "") +
             (f"  \n↳ outcome: {x['outcome']}" if x.get("outcome") else "")),
            ("📊 Outcomes", mem["outcomes"], lambda x: x["text"]),
        ]
        empty = True
        for title, items, fmt in sections:
            if items:
                empty = False
                st.markdown(f"**{title}**")
                for x in items:
                    st.markdown(f"- {fmt(x)}")
        if empty:
            st.caption("Nothing yet. Tell me about your preferences, tasks and decisions.")
    with tab_graph:
        triples = graph.graph_triples(driver(), st.session_state.user)
        if triples:
            st.graphviz_chart(dot(triples), width="stretch")
        else:
            st.caption("The memory graph appears here once I've stored something.")
