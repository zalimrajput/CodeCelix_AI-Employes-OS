"""
Verify that OPENROUTER_AUTO_FALLBACK=false keeps OpenAI/Anthropic/Google
model ids using the direct provider path (and therefore still raises the
missing-key error when no direct key is set).
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
from app.core.config import settings

# Force the toggle off, regardless of .env.
settings.OPENROUTER_AUTO_FALLBACK = False
# Force a reload so any local override of OPENROUTER_AUTO_FALLBACK in
# backend/.env keeps working after imports above have already set it.
import importlib as _iml
import app.core.config as _cc
_iml.reload(_cc)

print(f"OPENROUTER_AUTO_FALLBACK (after reload): {settings.OPENROUTER_AUTO_FALLBACK}")
if not settings.OPENROUTER_API_KEY:
    print("SKIP: this script only makes sense when OPENROUTER_API_KEY is present")
    sys.exit(0)

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
        # Return one fake response per model id so each test gets its own
        # expected reply.
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
                    }
                }
            ]
        }


httpx.Client = FakeClient

print(f"OPENROUTER_API_KEY set: {bool(settings.OPENROUTER_API_KEY)}")
print(f"OPENAI_API_KEY set: {bool(settings.OPENAI_API_KEY)}")
print(f"OPENROUTER_AUTO_FALLBACK: {settings.OPENROUTER_AUTO_FALLBACK}")
print()

if settings.OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY present -> auto-fallback path is available even when OPENROUTER_AUTO_FALLBACK is off")
else:
    print("OPENROUTER_API_KEY absent   -> OpenRouter auto-fallback is not available")
print()

cases = [
    ("gpt-4o-mini (OpenAI-native id)"),
    ("claude-3-5-sonnet-20241022 (Anthropic-native id)"),
    ("gemini-2.5-flash (Google-native id)"),
]

all_ok = True
for label in cases:
    model_id = label.split()[0]
    try:
        # Each call should hit the direct provider path and raise a missing-key
        # error before httpx is even used (no OpenRouter retry).
        model_router.complete([{"role": "user", "content": "hi"}], model=model_id)
    except Exception as e:
        # With AUTO_FALLBACK off, we expect a provider-side error before any
        # OpenRouter httpx call. For OpenAI/Anthropic that is the missing-key
        # error; for Google it may be a 4xx/5xx from the Gemini API (missing key
        # or rejected model id). In either case, no OpenRouter call should have
        # been made.
        provider_error = isinstance(e, model_router.ModelRouterError)
        is_expected = provider_error and (
            "OPENAI_API_KEY is not configured" in str(e)
            or "ANTHROPIC_API_KEY is not configured" in str(e)
            or "GOOGLE_AI_KEY is not configured" in str(e)
            or (
                str(e).startswith("Google error")
                and getattr(e, "status_code", None) in (400, 403, 404, 429, 500, 502, 503, 504)
            )
        )
        print(f"{label}:")
        print(f"  raised a provider-side error            -> {provider_error}")
        print(f"  looks like expected missing-key/4xx     -> {is_expected}")
        print(f"  error text: {str(e)[:200]!r}")
        print()
        if not is_expected:
            all_ok = False
            continue
        # No httpx call should have been made.
        if real_calls:
            print("  unexpected httpx call:")
            for c in real_calls[-1:]:
                print(f"    url: {c['url']}")
                print(f"    auth: {c['headers'].get('Authorization')!r}")
            print()
            all_ok = False
        real_calls.clear()
        continue

    # If we get here, no error was raised at all; that can only happen if a
    # direct key was somehow used (which we do not have here).
    print(f"{label}: unexpected success (no error raised)")
    all_ok = False

if all_ok:
    print("ALL OK: with OPENROUTER_AUTO_FALLBACK=false, OpenAI/Anthropic/Google ids still use the direct provider path")
    sys.exit(0)
else:
    print("SOME FAILURES - see above")
    sys.exit(1)
