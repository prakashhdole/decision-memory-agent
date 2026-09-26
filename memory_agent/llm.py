"""Optional LLM access (Gemini or OpenAI) using only the standard library.

Put ONE key in llm_keys.txt (project root), e.g.
    GEMINI_API_KEY=your-key
or  OPENAI_API_KEY=your-key
If no key is set (or the call fails), the agent falls back to its built-in
rule-based logic, so the demo always works.
"""
import json
import os
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEYS = os.path.join(_ROOT, "llm_keys.txt")
if os.path.exists(_KEYS):
    with open(_KEYS, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
last_error = None


def provider():
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _call(system, user, want_json):
    global last_error
    p = provider()
    if not p:
        return None
    try:
        if p == "gemini":
            cfg = {"temperature": 0.2}
            if want_json:
                cfg["responseMimeType"] = "application/json"
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{GEMINI_MODEL}:generateContent")
            resp = _post(url, {
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": cfg,
            }, {"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
        else:
            body = {"model": OPENAI_MODEL, "temperature": 0.2,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            if want_json:
                body["response_format"] = {"type": "json_object"}
            resp = _post("https://api.openai.com/v1/chat/completions", body,
                         {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
            text = resp["choices"][0]["message"]["content"]
        last_error = None
        return text
    except urllib.error.HTTPError as e:
        last_error = f"{p} HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:  # network, parsing, quota...
        last_error = f"{p} error: {type(e).__name__}: {e}"
    return None


def chat_json(system, user):
    """Return a dict from the LLM, or None if unavailable/invalid."""
    global last_error
    text = _call(system, user, want_json=True)
    if text is None:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except ValueError:
        last_error = "LLM returned invalid JSON"
        return None
