"""Regression tests for the model-router fallback chain.

Guards the fix that keeps AI chat working on credit-less OpenRouter accounts:
when the primary model fails with a provider-side error (402 no credits /
429 rate-limit / 5xx), the router must move to the next configured model
instead of surfacing ``ModelRouterError``.
"""
import pytest
from app.ai import model_router
from app.ai.model_router import ModelRouterError


def test_complete_falls_back_on_retryable_error(monkeypatch):
    calls = []

    def fake_one(model, messages, temperature):
        calls.append(model)
        if model == "first":
            raise ModelRouterError("402 no credits", status_code=402)
        return "ok"

    monkeypatch.setattr(model_router, "_complete_one", fake_one)
    monkeypatch.setattr(model_router.settings, "AI_MODEL_FALLBACKS", "second,third")

    result = model_router.complete([{"role": "user", "content": "hi"}], model="first")

    assert result == "ok"
    assert calls == ["first", "second"]


def test_complete_with_tools_falls_back(monkeypatch):
    calls = []

    def fake_one(messages, tools, model, temperature, tool_choice, max_tokens):
        calls.append(model)
        if model == "primary":
            raise ModelRouterError("429 rate limited", status_code=429)
        return {"content": "done", "tool_calls": []}

    monkeypatch.setattr(model_router, "_complete_with_tools_one", fake_one)
    monkeypatch.setattr(model_router.settings, "AI_MODEL_FALLBACKS", "backup")

    result = model_router.complete_with_tools(
        [{"role": "user", "content": "hi"}], tools=[], model="primary"
    )

    assert result["content"] == "done"
    assert calls == ["primary", "backup"]


def test_complete_does_not_retry_config_errors(monkeypatch):
    calls = []

    def fake_one(model, messages, temperature):
        calls.append(model)
        raise ModelRouterError("OPENROUTER_API_KEY is not configured")

    monkeypatch.setattr(model_router, "_complete_one", fake_one)
    monkeypatch.setattr(model_router.settings, "AI_MODEL_FALLBACKS", "backup")

    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="first")
    except ModelRouterError:
        pass
    else:
        raise AssertionError("expected ModelRouterError")

    # A missing-key error (no status_code) must NOT retry other models.
    assert calls == ["first"]


def test_model_chain_dedupes(monkeypatch):
    monkeypatch.setattr(model_router.settings, "AI_MODEL_FALLBACKS", "b, c, a")
    chain = model_router._model_chain("a")
    assert chain == ["a", "b", "c"]


def test_complete_falls_back_on_model_not_found(monkeypatch):
    """An unknown model id (400/404 "model not found") must move to the next
    fallback instead of killing the whole chain."""
    calls = []

    def fake_one(model, messages, temperature):
        calls.append(model)
        if model == "ghost-model":
            raise ModelRouterError("404 model 'ghost-model' not found", status_code=404)
        return "ok"

    monkeypatch.setattr(model_router, "_complete_one", fake_one)
    monkeypatch.setattr(model_router.settings, "AI_MODEL_FALLBACKS", "gemini-2.5-pro")

    result = model_router.complete(
        [{"role": "user", "content": "hi"}], model="ghost-model"
    )

    assert result == "ok"
    assert calls == ["ghost-model", "gemini-2.5-pro"]


def test_auto_fallback_routes_missing_direct_keys_to_openrouter(monkeypatch):
    """When OPENROUTER_AUTO_FALLBACK is on and only OPENROUTER_API_KEY is set,
    OpenAI/Anthropic/Google model calls should be treated as OpenRouter calls:
    the provider label becomes "openrouter" and the OpenRouter httpx path is used
    instead of raising a missing-key error."""
    monkeypatch.setattr(model_router.settings, "OPENROUTER_API_KEY", "sk-or-v1-x")
    monkeypatch.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", True)
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", None)

    # OpenAI/Anthropic/Google model ids are routed to OpenRouter when the
    # matching direct key is missing but AUTO_FALLBACK is on.
    assert model_router._effective_provider("gpt-4o-mini", model_router._provider_for("gpt-4o-mini")) == "openrouter"
    assert model_router._effective_provider("claude-3-5-sonnet-20241022", model_router._provider_for("claude-3-5-sonnet-20241022")) == "openrouter"
    assert model_router._effective_provider("gemini-2.5-flash", model_router._provider_for("gemini-2.5-flash")) == "openrouter"

    # _has_working_direct_key reflects that there is no usable direct key.
    assert model_router._has_working_direct_key("openai") is False
    assert model_router._has_working_direct_key("anthropic") is False
    assert model_router._has_working_direct_key("google") is False


def test_has_working_direct_key_rejects_missing_keys(monkeypatch):
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", None)

    assert model_router._has_working_direct_key("openai") is False
    assert model_router._has_working_direct_key("anthropic") is False
    assert model_router._has_working_direct_key("google") is False


def test_has_working_direct_key_accepts_real_keys(monkeypatch):
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", "AIzaSy-x")

    assert model_router._has_working_direct_key("openai") is True
    assert model_router._has_working_direct_key("anthropic") is True
    assert model_router._has_working_direct_key("google") is True


def test_has_working_direct_key_rejects_bogus_google_key(monkeypatch):
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", "not-a-key")

    assert model_router._has_working_direct_key("google") is False


def test_auto_fallback_keeps_direct_key_when_present(monkeypatch):
    """A configured direct key should still take precedence even when
    OPENROUTER_AUTO_FALLBACK is on."""
    monkeypatch.setattr(model_router.settings, "OPENROUTER_API_KEY", "sk-or-v1-x")
    monkeypatch.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", True)
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", "AIzaSy-x")

    assert model_router._effective_provider("gpt-4o-mini", model_router._provider_for("gpt-4o-mini")) == "openai"
    assert model_router._effective_provider("claude-3-5-sonnet-20241022", model_router._provider_for("claude-3-5-sonnet-20241022")) == "anthropic"
    assert model_router._effective_provider("gemini-2.5-flash", model_router._provider_for("gemini-2.5-flash")) == "google"


def test_auto_fallback_off_still_fails_missing_keys(monkeypatch):
    """With OPENROUTER_AUTO_FALLBACK off, missing direct keys still cause the
    expected missing-key errors (no silent OpenRouter retry)."""
    monkeypatch.setattr(model_router.settings, "OPENROUTER_API_KEY", "sk-or-v1-x")
    monkeypatch.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", False)
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "GOOGLE_AI_KEY", None)

    # OpenAI model without key still raises missing-key error
    raised = False
    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="gpt-4o-mini")
    except ModelRouterError as e:
        raised = True
        assert "OPENAI_API_KEY is not configured" in str(e)
    assert raised

    # Anthropic model without key still raises missing-key error
    raised = False
    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="claude-3-5-sonnet-20241022")
    except ModelRouterError as e:
        raised = True
        assert "ANTHROPIC_API_KEY is not configured" in str(e)
    assert raised

    # Google model without key still raises missing-key error
    raised = False
    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="gemini-2.5-flash")
    except ModelRouterError as e:
        raised = True
        assert "GOOGLE_AI_KEY is not configured" in str(e)
    assert raised


def test_auto_fallback_still_raises_when_openrouter_key_missing(monkeypatch):
    """If even OPENROUTER_API_KEY is missing, the openai/anthropic model call
    should still raise the missing-key error for that provider; AUTO_FALLBACK
    alone is not enough without an OpenRouter key to fall back to."""
    monkeypatch.setattr(model_router.settings, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", True)
    monkeypatch.setattr(model_router.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(model_router.settings, "ANTHROPIC_API_KEY", None)

    # OpenAI model without any key at all should raise a missing-key error.
    raised = False
    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="gpt-4o-mini")
    except ModelRouterError as e:
        raised = True
        msg = str(e)
        assert "OPENAI_API_KEY is not configured" in msg
    assert raised

    # Anthropic model without any key at all should raise a missing-key error.
    raised = False
    try:
        model_router.complete([{"role": "user", "content": "hi"}], model="claude-3-5-sonnet-20241022")
    except ModelRouterError as e:
        raised = True
        msg = str(e)
        assert "ANTHROPIC_API_KEY is not configured" in msg
    assert raised


def test_auto_fallback_sends_openai_model_via_openrouter(monkeypatch):
    """When only OPENROUTER_API_KEY is set and AUTO_FALLBACK is on, an
    OpenAI-native model id (gpt-4o-mini) should actually be sent to
    OpenRouter's chat/completions endpoint and return the OpenAI-format body."""
    with pytest.MonkeyPatch().context() as m:
        m.setattr(model_router.settings, "OPENROUTER_API_KEY", "sk-or-v1-test")
        m.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", True)
        m.setattr(model_router.settings, "OPENAI_API_KEY", None)
        m.setattr(model_router.settings, "ANTHROPIC_API_KEY", None)
        m.setattr(model_router.settings, "GOOGLE_AI_KEY", None)

        import httpx
        sent = {}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def post(self, url, headers, json):
                sent.update(url=url, headers=headers, json=json)
                return FakeResponse()

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "reply from openrouter",
                                "tool_calls": [],
                            }
                        }
                    ]
                }

        m.setattr(httpx, "Client", FakeClient)

        result = model_router.complete(
            [{"role": "user", "content": "hi"}], model="gpt-4o-mini"
        )

        assert result == "reply from openrouter"
        assert sent["url"].endswith("/chat/completions")
        assert sent["headers"]["Authorization"] == "Bearer sk-or-v1-test"
        assert sent["json"]["model"] == "gpt-4o-mini"
        assert sent["json"]["messages"] == [{"role": "user", "content": "hi"}]


def test_auto_fallback_sends_google_model_via_openrouter(monkeypatch):
    """Same idea for a Google model id: with only OPENROUTER_API_KEY set and
    AUTO_FALLBACK on, gemini-2.5-flash should be sent to OpenRouter, not to the
    Gemini REST API."""
    with pytest.MonkeyPatch().context() as m:
        m.setattr(model_router.settings, "OPENROUTER_API_KEY", "sk-or-v1-test")
        m.setattr(model_router.settings, "OPENROUTER_AUTO_FALLBACK", True)
        m.setattr(model_router.settings, "GOOGLE_AI_KEY", None)

        import httpx
        sent = {}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def post(self, url, headers, json):
                sent.update(url=url, headers=headers, json=json)
                return FakeResponse()

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "reply from openrouter via gemini model id",
                            }
                        }
                    ]
                }

        m.setattr(httpx, "Client", FakeClient)

        result = model_router.complete(
            [{"role": "user", "content": "hi"}], model="gemini-2.5-flash"
        )

        assert result == "reply from openrouter via gemini model id"
        assert sent["url"].endswith("/chat/completions")
        assert sent["headers"]["Authorization"] == "Bearer sk-or-v1-test"
        assert sent["json"]["model"] == "gemini-2.5-flash"
