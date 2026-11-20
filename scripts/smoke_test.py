"""End-to-end smoke test for a running Garuda Purana RAG bot.

Assumes `python app.py` is already serving on http://127.0.0.1:5000.

Usage:
    python scripts/smoke_test.py                       # default questions
    python scripts/smoke_test.py "Can girls perform shraddha?"
    set BOT_BASE_URL=http://127.0.0.1:8000 && python scripts/smoke_test.py

A local LLM can be slow, so every request uses a generous timeout (300s by
default, override with BOT_TIMEOUT seconds). Exit code 0 = all checks passed.
"""

import json
import os
import sys
import time
from urllib import error, parse, request

BASE_URL = os.getenv("BOT_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT = float(os.getenv("BOT_TIMEOUT", "300"))

DEFAULT_QUESTIONS = [
    "What are the duties of a son when a parent is on their death bed?",
    "When does a person become an ant in the next life?",
    "What material are the pinds used in shraddha rituals made of?",
]

CANNED_REFUSAL_HINT = "does not seem to contain specific details"

passed = 0
failed = 0


def call(method, path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + parse.urlencode(params)
    req = request.Request(url, method=method)
    started = time.time()
    try:
        with request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, time.time() - started
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, time.time() - started
    except error.URLError as exc:
        print(f"[FAIL] {method} {url} -> cannot reach server: {exc.reason}")
        print("       Is `python app.py` running? Is BOT_BASE_URL correct?")
        sys.exit(2)


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"[PASS] {label}" + (f" -> {detail}" if detail else ""))
    else:
        failed += 1
        print(f"[FAIL] {label}" + (f" -> {detail}" if detail else ""))


def main():
    print(f"--- Smoke test against {BASE_URL} ---")

    # 1. Health probe
    status, body, elapsed = call("GET", "/health")
    print(f"\nGET /health -> HTTP {status} in {elapsed:.1f}s")
    print(body[:800])
    check("/health reachable", status in (200, 503), f"HTTP {status}")
    try:
        health = json.loads(body)
    except ValueError:
        health = {}
    check(
        "/health reports database up",
        health.get("database") == "up",
        str(health.get("database")),
    )
    check(
        "/health reports indexed chunks",
        isinstance(health.get("chunks"), int) and health.get("chunks", 0) > 0,
        f"{health.get('chunks')} chunks",
    )
    check("/health reports ollama up", health.get("ollama") == "up", str(health.get("ollama")))

    # 2. Input validation
    status, body, _ = call("GET", "/api/chatbot")
    check("missing question returns 400", status == 400, f"HTTP {status} {body.strip()[:120]}")

    # 3. Real questions
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    for question in questions:
        status, body, elapsed = call("GET", "/api/chatbot", {"question": question})
        print(f'\nGET /api/chatbot?question="{question}" -> HTTP {status} in {elapsed:.1f}s')
        check(f"answered: {question}", status == 200, f"HTTP {status}")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}

        answer = payload.get("data", "")
        print(f"Answer ({len(answer)} chars): {answer[:500]}")
        sources = payload.get("sources") or []
        if sources:
            for source in sources:
                print(f"  source: {source.get('citation')} (score {source.get('similarity')})")
        check(f"answer not empty: {question}", bool(answer.strip()))
        check(f"citations returned: {question}", bool(sources))
        if answer and CANNED_REFUSAL_HINT not in answer:
            print("  note: answer is grounded in retrieved context")

    print("\n--- Summary ---")
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
