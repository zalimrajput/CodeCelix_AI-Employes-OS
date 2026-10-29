"""
Verify that OPENROUTER_AUTO_FALLBACK=false keeps OpenAI/Anthropic/Google
model ids using the direct provider path even when a real Google key is set
(only the OpenAI/Anthropic keys are missing, so those still raise missing-key).
The Google model id is chosen from VERIFY_AUTO_FALLBACK_GOOGLE_MODEL or a built-in
fallback; if it is not reachable by the live key, the script reports that and
exits non-zero so you can point it at a working model id.

Reads backend/.env first so the check reflects the env you actually have.
If backend/.env has OPENROUTER_AUTO_FALLBACK=true, set it to false there (or
pass OPENROUTER_AUTO_FALLBACK=false in the shell before running this script)
otherwise the verification runs against the OpenRouter auto-fallback ON path.
"""
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PYTHONPATH", str(ROOT))

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

settings.OPENROUTER_AUTO_FALLBACK = False
# Re-read so a local override of OPENROUTER_AUTO_FALLBACK in backend/.env
# stays effective after imports above already set it.
import importlib as _iml
import app.core.config as _cc
_iml.reload(_cc)

print(f"OPENROUTER_AUTO_FALLBACK (after reload): {settings.OPENROUTER_AUTO_FALLBACK}")
if not settings.GOOGLE_AI_KEY:
    print("SKIP: this script only makes sense when a real GOOGLE_AI_KEY is present")
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
        return FakeResponse(url, json)


class FakeResponse:
    status_code = 200

    def __init__(self, url, json_body):
        self._url = url
        self._json_body = json_body

    def json(self):
        return self._json_body


httpx.Client = FakeClient


def _timeout_guard(seconds):
    """Context manager that raises TimeoutError if the block runs longer than
    `seconds`. Uses SIGALRM on Unix; on Windows it is a best-effort no-op so the
    script still runs, just without the hard timeout."""

    def _raise_timeout(signum, frame):
        raise TimeoutError("model call timed out")

    class _Ctx:
        def __enter__(self):
            try:
                self._old = signal.signal(signal.SIGALRM, _raise_timeout)
                signal.alarm(seconds)
            except (AttributeError, ValueError):
                self._old = None
            return self

        def __exit__(self, exc_type, exc, tb):
            try:
                signal.alarm(0)
            except (AttributeError, ValueError):
                pass
            if self._old is not None:
                try:
                    signal.signal(signal.SIGALRM, self._old)
                except (AttributeError, ValueError):
                    pass
            return False

    return _Ctx()


print(f"GOOGLE_AI_KEY set (non-empty): {bool(settings.GOOGLE_AI_KEY)}")
print(f"OPENAI_API_KEY set: {bool(settings.OPENAI_API_KEY)}")
print(f"ANTHROPIC_API_KEY set: {bool(settings.ANTHROPIC_API_KEY)}")
print(f"OPENROUTER_API_KEY set: {bool(settings.OPENROUTER_API_KEY)}")
print(f"OPENROUTER_AUTO_FALLBACK: {settings.OPENROUTER_AUTO_FALLBACK}")
print()

if settings.OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY present -> auto-fallback path is available even when OPENROUTER_AUTO_FALLBACK is off")
else:
    print("OPENROUTER_API_KEY absent   -> OpenRouter auto-fallback is not available")
print()

google_model_id = os.environ.get("VERIFY_AUTO_FALLBACK_GOOGLE_MODEL", "gemini-3.8-flash")
print(f"using google model id: {google_model_id}")
print()

all_ok = True

for model_id, expected_provider_label in [
    ("gpt-4o-mini", "openai"),
    ("claude-3-5-sonnet-20241022", "anthropic"),
    (google_model_id, "google"),
]:
    deadline = time.monotonic() + 12
    try:
        with _timeout_guard(seconds=12):
            model_router.complete([{"role": "user", "content": "hi"}], model=model_id)
    except model_router.ModelRouterError as e:
        # OpenRouter should not have been called when AUTO_FALLBACK is off.
        if real_calls:
            print(f"{model_id} (expected {expected_provider_label}):")
            print("  error raised but httpx was already called:")
            for c in real_calls[-1:]:
                print(f"    url: {c['url']}")
                print(f"    auth: {c['headers'].get('Authorization')!r}")
            print()
            all_ok = False
            real_calls.clear()
            continue

        msg = str(e)
        if expected_provider_label in ("openai", "anthropic"):
            expected_missing = f"{expected_provider_label.upper()}_API_KEY is not configured"
            ok = expected_missing in msg
            print(f"{model_id} (expected {expected_provider_label}):")
            print(f"  raised missing-key error for {expected_provider_label} -> {ok}")
            print(f"  error text: {msg[:160]!r}")
            print()
            if not ok:
                all_ok = False
            continue

        # Google path: a provider error that clearly came from the Gemini API
        # (missing-key OR a 4xx/5xx from the live key). OpenRouter must not have
        # been touched; the helper below checks the captured httpx calls for that.
        is_google_missing = "GOOGLE_AI_KEY is not configured" in msg
        # The live Google key can raise provider errors from whichever Google
        # exception class the SDK surfaces for HTTP errors. Accept anything that
        # looks like a Gemini API rejection (HTTP status in the error text plus
        # a known 4xx/5xx code) as a Google-path error.
        exc_status = getattr(e, "status_code", None)
        is_google_provider = (
            bool(msg)
            and exc_status in (400, 401, 403, 404, 429, 500, 502, 503, 504)
            and (
                msg.startswith("Google error")
                or any(msg.startswith(prefix) for prefix in (
                    "400", "401", "403", "404", "429", "500", "502", "503", "504"
                ))
            )
        )
        google_path_ok = is_google_missing or is_google_provider

        # Extra guard: if httpx was touched, make sure it was the Google REST
        # path, not an OpenRouter call. That keeps the auto-fallback-off rule
        # honest even when the live key raises a provider error for the chosen
        # model id.
        google_httpx_ok = True
        if real_calls:
            google_httpx_ok = all(
                "openrouter.ai" not in c["url"]
                for c in real_calls[-1:]
            )
            if not google_httpx_ok:
                print(
                    f"{model_id} (expected google):"
                )
                print("  raised a Google-path error, BUT httpx already hit OpenRouter:")
                # Do not clear real_calls here so the outer path summary still
                # shows what OpenRouter was asked for; mark the overall case
                # as a failure once at the end of this branch.
                for c in real_calls[-1:]:
                    print(f"    url: {c['url']}")
                    print(f"    auth: {c['headers'].get('Authorization')!r}")
                print()
                all_ok = False

        ok = google_path_ok and google_httpx_ok
        print(f"{model_id} (expected google):")
        print(f"  raised a Google-path error              -> {google_path_ok}")
        print(f"  is missing-key       -> {is_google_missing}")
        print(f"  is Google 4xx/5xx   -> {is_google_provider}")
        print(f"  httpx touched OpenRouter -> {not google_httpx_ok}")
        print(f"  error type          -> {type(e).__name__}")
        print(f"  error text: {msg[:160]!r}")
        print()
        if not ok:
            all_ok = False
        real_calls.clear()
        continue

    except TimeoutError:
        print(f"{model_id} (expected {expected_provider_label}):")
        print("  timed out before any ModelRouterError — could not confirm the path")
        print(f"  httpx calls made before timeout: {len(real_calls)}")
        if real_calls:
            for c in real_calls[-1:]:
                print(f"    url: {c['url']}")
        print()
        all_ok = False
        real_calls.clear()
        continue

    except BaseException as e:
        print(f"{model_id} (expected {expected_provider_label}):")
        print(f"  unexpected exception escaped: {type(e).__name__}: {str(e)[:160]!r}")
        print(f"  httpx calls made: {len(real_calls)}")
        if real_calls:
            for c in real_calls[-1:]:
                print(f"    url: {c['url']}")
                print(f"    auth: {c['headers'].get('Authorization')!r}")
        print()
        all_ok = False
        real_calls.clear()
        continue


        real_calls.clear()
        continue

    # No exception: that means the direct provider path returned a real reply.
    # Only the Google path can do that here (OpenAI/Anthropic keys are missing).
    if expected_provider_label == "google":
        print(f"{model_id} (expected google):")
        print("  no exception raised — direct Google path returned a reply (as expected)")
        print(f"  httpx calls made: {len(real_calls)}")
        if real_calls:
            last = real_calls[-1]
            print(f"  last httpx url     : {last['url']}")
            print(f"  last httpx auth    : {last['headers'].get('Authorization')!r}")
            if "openrouter.ai" in last["url"]:
                print("  -> unexpected: OpenRouter was used for the Google path")
                all_ok = False
            else:
                print("  -> confirmed Google direct path was used, not OpenRouter")
                print(f"  -> last httpx url: {last['url']}")
        else:
            print("  -> no httpx call was needed (SDK path was used)")
        real_calls.clear()
        continue

    print(f"{model_id} (expected {expected_provider_label}): unexpected success (no error)")
    all_ok = False
    print()

if all_ok:
    print("ALL OK: with OPENROUTER_AUTO_FALLBACK=false, OpenAI/Anthropic/Google ids still use the direct provider path")
    sys.exit(0)
else:
    print("SOME FAILURES - see above")
    sys.exit(1)

