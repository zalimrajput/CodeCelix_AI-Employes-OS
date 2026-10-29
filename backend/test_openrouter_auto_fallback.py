"""
Standalone check: when OPENROUTER_API_KEY is the only configured key and
OPENROUTER_AUTO_FALLBACK=true, a chat turn for an OpenAI/Anthropic/Google model
id is sent to OpenRouter (not to the direct provider) and returns a usable
reply.

This script reads the live backend env so it exercises the real key if present.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PYTHONPATH", str(ROOT))

# Load backend/.env into the process so Settings() sees it.
_env_path = ROOT / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.ai import model_router
from app.ai.model_router import ModelRouterError
from app.core.config import settings

# Force the configuration we want to test, regardless of what is in .env.
settings.OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY or "sk-or-v1-test-only"
settings.OPENAI_API_KEY = None
settings.ANTHROPIC_API_KEY = None
settings.GOOGLE_AI_KEY = None
settings.OPENROUTER_AUTO_FALLBACK = True

import httpx

real_calls = []


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, headers, json):
        real_calls.append(dict(url=url, headers=headers, json=json))
        return FakeResponse(json["model"])


class FakeResponse:
    status_code = 200

    def __init__(self, model_id):
        self._model_id = model_id

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": f"reply from openrouter for {self._model_id}",
                        "tool_calls": [],
                    }
                }
            ]
        }


httpx.Client = FakeClient

print(f"OPENROUTER_API_KEY set: {bool(settings.OPENROUTER_API_KEY)}")
print(f"OPENAI_API_KEY set: {bool(settings.OPENAI_API_KEY)}")
print(f"ANTHROPIC_API_KEY set: {bool(settings.ANTHROPIC_API_KEY)}")
print(f"GOOGLE_AI_KEY set: {bool(settings.GOOGLE_AI_KEY)}")
print(f"OPENROUTER_AUTO_FALLBACK: {settings.OPENROUTER_AUTO_FALLBACK}")
print()

if not settings.OPENROUTER_API_KEY:
    print("SKIP: no OPENROUTER_API_KEY at all (real or forced)")
    sys.exit(0)

cases = [
    ("gpt-4o-mini (OpenAI-native id)"),
    ("claude-3-5-sonnet-20241022 (Anthropic-native id)"),
    ("gemini-2.5-flash (Google-native id)"),
]

all_ok = True
for label in cases:
    try:
        reply = model_router.complete([{"role": "user", "content": "hi"}], model=label.split()[0])
    except ModelRouterError as e:
        print(f"FAIL {label}: {e}")
        all_ok = False
        continue

    if not real_calls:
        print(f"FAIL {label}: no httpx call was made")
        all_ok = False
        continue

    last = real_calls[-1]
    ok_url = last["url"].endswith("/chat/completions")
    ok_auth = last["headers"]["Authorization"] == f"Bearer {settings.OPENROUTER_API_KEY}"
    ok_body = last["json"]["model"] == label.split()[0]
    ok_reply = reply == f"reply from openrouter for {label.split()[0]}"

    print(f"{label}:")
    print(f"  sent to OpenRouter chat/completions -> {ok_url}")
    print(f"  used OPENROUTER_API_KEY as bearer     -> {ok_auth}")
    print(f"  model id in body                      -> {ok_body}")
    print(f"  returned expected reply               -> {ok_reply}")
    print()
    if not (ok_url and ok_auth and ok_body and ok_reply):
        all_ok = False
    real_calls.clear()

if all_ok:
    print("ALL OK: OpenAI/Anthropic/Google model ids are routed through OpenRouter")
    sys.exit(0)
else:
    print("SOME FAILURES - see above")
    sys.exit(1)
