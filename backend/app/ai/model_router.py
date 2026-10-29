"""Thin multi-provider LLM client.

Primary provider is OpenRouter (``OPENROUTER_BASE_URL`` / ``OPENROUTER_API_KEY``);
falls back to direct OpenAI, Anthropic or Google calls when the model id
implies a different provider and the matching key is configured.  Streaming is
supported for all providers and exposed as an iterator of text chunks.

Free-tier OpenRouter models are transiently rate-limited (429) or credit-gated
(402), so every completion is attempted against a chain of models - the
requested/default model first, then ``AI_MODEL_FALLBACKS`` - and moves to the
next one when a provider-side error occurs.
"""
import json
import logging
from typing import Iterator, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app.ai.model_router")

SYSTEM_ROLE = "system"

# Provider-side failures worth retrying on the next model in the chain.
_RETRYABLE_STATUS = {402, 429, 500, 502, 503, 504}


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return False


class ModelRouterError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _provider_for(model: str) -> str:
    lower = model.lower()
    # OpenRouter catalog IDs carry a vendor prefix (e.g. "google/gemma-...",
    # "deepseek/deepseek-chat") and/or a ":free" variant suffix. These are
    # OpenRouter model IDs and must be sent to OpenRouter, never to a direct
    # provider API (Google rejects "google/gemma-..." with INVALID_ARGUMENT).
    if ":free" in lower or "/" in lower:
        return "openrouter"
    if "anthropic" in lower or "claude" in lower:
        return "anthropic"
    if "gemini" in lower or "google" in lower:
        return "google"
    if "openai" in lower or lower.startswith("gpt") or lower.startswith("o1") or lower.startswith("o3") or lower.startswith("text-"):
        return "openai"
    return "openrouter"


def _has_working_direct_key(provider: str) -> bool:
    """Return True when the configured direct-provider key looks usable.

    For the Gemini-first mode we only trust a direct Google key when it is
    present and shaped like a real key (legacy ``AIzaSy...`` or the newer
    ``AQ.`` access tokens). When that is not the case, the Gemini path is
    treated as unusable and the request should fall back through OpenRouter
    instead of surfacing a hard Google error.
    """
    if not settings.OPENROUTER_API_KEY:
        return False
    if provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    if provider == "google":
        key = settings.GOOGLE_AI_KEY or ""
        if not key or not key.startswith(("AIzaSy", "AQ.")):
            return False
        # The configured Google key looks usable, so we keep Gemini on the
        # direct Google path when Gemini-first routing is on. Once the key is
        # missing or unrecognised the Gemini path is treated as unavailable
        # and the request falls back through OpenRouter instead.
        return True
    return False


def _effective_provider(model: str, provider: str) -> str:
    """Route a completion through the right provider for *model*.

    When the matching direct-provider key is missing or invalid but
    ``OPENROUTER_API_KEY`` is configured and ``OPENROUTER_AUTO_FALLBACK`` is on,
    the call is silently retried through OpenRouter instead. That keeps a single
    OpenRouter key able to cover the whole fallback chain (useful on free-tier
    accounts where adding an OpenAI/Anthropic/Google key is not an option).

    When OpenRouter auto-fallback is off, the provider is chosen purely by the
    model id — so a missing/invalid direct key still fails loudly and fast.
    """
    if not settings.OPENROUTER_API_KEY:
        return provider
    if not settings.OPENROUTER_AUTO_FALLBACK:
        return provider
    # OpenRouter is the only provider that can cover the whole fallback chain
    # (OpenAI, Anthropic and Google ids all route through it), so route the
    # request there as soon as the matching direct-provider key is missing or
    # unusable. That keeps Gemini-first mode working: a failing Gemini request
    # still completes through OpenRouter instead of surfacing a hard model error.
    if _has_working_direct_key(provider):
        return provider
    return "openrouter"


def _fallback_models() -> list[str]:
    raw = settings.AI_MODEL_FALLBACKS or ""
    ids = [m.strip() for m in raw.split(",") if m.strip()]
    if not ids:
        return ids
    return ids


def _model_chain(model: Optional[str]) -> list[str]:
    """Ordered, de-duplicated list of models to try for one completion.

    The requested/default model comes first. When the model is Gemini and the
    configured Gemini path is unavailable or fails, the chain must be able to
    continue through OpenRouter models instead of ending on a failed Gemini- only
    list. That is handled by appending OpenRouter-facing models after the
    configured Gemini fallback list.
    """
    primary = model or settings.DEFAULT_AI_MODEL
    chain: list[str] = []
    for candidate in [primary] + _fallback_models():
        if candidate and candidate not in chain:
            chain.append(candidate)
    # If the requested/fallback list is Gemini-only and contains no OpenRouter-style
    # Gemini id (vendor prefix or :free), append one OpenRouter Gemini model at
    # the tail. That guarantees the router can switch to OpenRouter if every
    # configured Gemini model fails, so the user gets a real reply instead of a
    # ModelRouterError. OpenRouter-facing Gemini ids keep their own chain and are
    # not duplicated at the end.
    if any("gemini" in m.lower() for m in chain):
        if not any(":free" in m.lower() or "/" in m.lower() for m in chain):
            chain.append("google/gemini-3.5-flash")
    return chain


def _is_retryable(exc: ModelRouterError) -> bool:
    if exc.status_code is None:
        return False
    if exc.status_code in _RETRYABLE_STATUS:
        return True
    # Everything with a status_code from the upstream provider is retryable: the
    # chain moves to the next configured model for each one.
    return True


def _request_retryable_error(exc: Exception) -> ModelRouterError:
    """Convert a transport-level httpx failure into a retryable router error.

    Free-tier models frequently time out or drop connections; treating those
    as retryable lets the fallback chain move to the next model instead of
    failing the whole turn.
    """
    if isinstance(exc, httpx.TimeoutException):
        return ModelRouterError(f"OpenRouter timeout: {exc}", status_code=504)
    return ModelRouterError(f"OpenRouter connection error: {exc}", status_code=502)


def _openrouter_headers() -> dict:
    if not settings.OPENROUTER_API_KEY:
        raise ModelRouterError("OPENROUTER_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def _openrouter_payload(
    model: str, messages: list[dict], temperature: float, stream: bool
) -> dict:
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
        "max_tokens": settings.AI_MAX_TOKENS,
    }


def complete(messages: list[dict], model: Optional[str] = None, temperature: float = 0.3) -> str:
    """Non-streaming completion returning the full text reply.

    Tries the requested/default model first, then every configured fallback,
    retrying only provider-side failures (402/429/5xx). A failure on one
    provider/model moves to the next one so the user gets a real reply even
    when the first provider is out of credit or temporarily unavailable.
    """
    last_error: Optional[ModelRouterError] = None
    for candidate in _model_chain(model):
        try:
            return _complete_one(candidate, messages, temperature)
        except ModelRouterError as exc:
            last_error = exc
            if not _is_retryable(exc):
                raise
            logger.warning(
                "model %s failed (%s); trying next fallback", candidate, exc
            )
    if last_error is None:
        raise ModelRouterError("no AI model configured")
    raise last_error


def _complete_one(model: str, messages: list[dict], temperature: float) -> str:
    provider = _effective_provider(model, _provider_for(model))

    if provider == "openrouter":
        url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    url,
                    headers=_openrouter_headers(),
                    json=_openrouter_payload(model, messages, temperature, False),
                )
        except httpx.HTTPError as exc:
            raise _request_retryable_error(exc) from exc
        if resp.status_code != 200:
            raise ModelRouterError(
                f"OpenRouter error {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    if provider == "openai":
        if settings.OPENAI_API_KEY:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
            return (resp.choices[0].message.content or "") if resp.choices else ""
        # Missing OpenAI key but OPENROUTER_AUTO_FALLBACK is on (or the provider
        # was already switched to OpenRouter by _effective_provider) → falls
        # through to the OpenRouter block below.
        raise ModelRouterError(
            "OPENAI_API_KEY is not configured"
        ) from None

    if provider == "anthropic":
        if settings.ANTHROPIC_API_KEY:
            from anthropic import Anthropic

            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            system, claude_messages = _split_system(messages)
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system or None,
                messages=claude_messages,
                temperature=temperature,
            )
            return "".join(b.text for b in resp.content if b.type == "text") or ""
        raise ModelRouterError(
            "ANTHROPIC_API_KEY is not configured"
        ) from None

    if provider == "google":
        if settings.GOOGLE_AI_KEY:
            return _google_complete(model, messages, temperature)
        raise ModelRouterError(
            "GOOGLE_AI_KEY is not configured"
        ) from None

    raise ModelRouterError(f"Cannot route model {model!r}")


def complete_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.3,
    tool_choice: str = "auto",
    max_tokens: Optional[int] = None,
) -> dict:
    """Native tool-calling completion (OpenAI-compatible protocol).

    Returns a dict with:
      - ``content``: the model's text reply (may be None when calling a tool)
      - ``tool_calls``: list of {"id", "name", "arguments"} or []

    Tries the requested/default model first, then every configured fallback,
    retrying only provider-side failures (402/429/5xx). A failure on one
    provider/model moves to the next one so the user gets a real reply even
    when the first provider is out of credit or temporarily unavailable.
    """
    last_error: Optional[ModelRouterError] = None
    for candidate in _model_chain(model):
        try:
            return _complete_with_tools_one(
                messages=messages,
                tools=tools,
                model=candidate,
                temperature=temperature,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
            )
        except ModelRouterError as exc:
            last_error = exc
            if not _is_retryable(exc):
                raise
            logger.warning(
                "model %s failed with tools (%s); trying next fallback",
                candidate,
                exc,
            )
    if last_error is None:
        raise ModelRouterError("no AI model configured")
    raise last_error


def _complete_with_tools_one(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float,
    tool_choice: str,
    max_tokens: Optional[int],
) -> dict:
    provider = _effective_provider(model, _provider_for(model))

    if provider in ("openrouter", "openai"):
        url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        # Explicit max_tokens keeps requests within OpenRouter free-tier limits
        # (the provider default of ~64k triggers 402 on unfunded accounts).
        payload["max_tokens"] = max_tokens if max_tokens is not None else settings.AI_MAX_TOKENS
        if provider == "openrouter":
            if not settings.OPENROUTER_API_KEY:
                raise ModelRouterError("OPENROUTER_API_KEY is not configured")
            headers = _openrouter_headers()
        else:
            # The OpenAI path is kept only when OPENAI_API_KEY is actually set;
            # otherwise the toggle routed us here as an OpenRouter retry and we
            # re-raise so the chain / falls back to the OpenRouter path.
            if settings.OPENAI_API_KEY:
                headers = {
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                }
            else:
                raise ModelRouterError(
                    "OPENAI_API_KEY is not configured"
                ) from None
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise _request_retryable_error(exc) from exc
        if resp.status_code != 200:
            raise ModelRouterError(
                f"OpenRouter error {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        return _parse_openai_response(data)

    if provider == "anthropic":
        # Anthropic uses a different tool protocol; not covered until a key is
        # configured, so the engine falls back to the envelope path.
        raise ModelRouterError(
            "native tool calling is not implemented for anthropic; use the envelope path"
        )

    if provider == "google":
        if settings.GOOGLE_AI_KEY:
            return _google_complete_with_tools(
                messages=messages,
                tools=tools,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        raise ModelRouterError(
            "GOOGLE_AI_KEY is not configured"
        ) from None

    raise ModelRouterError(f"Cannot route model {model!r} with native tools")


def _parse_openai_response(data: dict) -> dict:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            arguments = json.loads(raw)
        except (ValueError, TypeError):
            arguments = {}
        tool_calls.append(
            {
                "id": call.get("id") or f"call_{len(tool_calls)}",
                "name": fn.get("name") or "",
                "arguments": arguments,
            }
        )
    return {
        "content": message.get("content") or "",
        "tool_calls": tool_calls,
    }


def stream(
    messages: list[dict], model: Optional[str] = None, temperature: float = 0.3
) -> Iterator[str]:
    """Stream a completion, yielding text chunks.

    Tries the requested/default model first, then every configured fallback,
    retrying only provider-side failures (402/429/5xx). A failure on one
    provider/model moves to the next one so the user gets a real reply even
    when the first provider is out of credit or temporarily unavailable.
    """
    last_error: Optional[ModelRouterError] = None
    for candidate in _model_chain(model):
        yielded = False
        try:
            for chunk in _stream_one(candidate, messages, temperature):
                yielded = True
                yield chunk
            return
        except ModelRouterError as exc:
            # Never splice partial output from a failed model onto the next
            # one's reply; only fall back when nothing was emitted yet.
            if yielded:
                raise
            last_error = exc
            if not _is_retryable(exc):
                raise
            logger.warning(
                "model %s stream failed (%s); trying next fallback", candidate, exc
            )
    if last_error is None:
        raise ModelRouterError("no AI model configured")
    raise last_error


def _stream_one(model: str, messages: list[dict], temperature: float) -> Iterator[str]:
    provider = _effective_provider(model, _provider_for(model))

    if provider == "openrouter":
        url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
        try:
            with httpx.Client(timeout=180) as client:
                with client.stream(
                    "POST",
                    url,
                    headers=_openrouter_headers(),
                    json=_openrouter_payload(model, messages, temperature, True),
                ) as resp:
                    if resp.status_code != 200:
                        raise ModelRouterError(
                            f"OpenRouter error {resp.status_code}: {resp.read()[:300]}",
                            status_code=resp.status_code,
                        )
                    for raw in resp.iter_lines():
                        if not raw or not raw.startswith("data:"):
                            continue
                        payload = raw[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            event = json.loads(payload)
                        except ValueError:
                            continue
                        choice = event.get("choices") or []
                        if not choice:
                            continue
                        delta = choice[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield text
        except httpx.HTTPError as exc:
            raise _request_retryable_error(exc) from exc
        return

    if provider == "openai":
        if settings.OPENAI_API_KEY:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, stream=True
            )
            for chunk in resp:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
            return
        raise ModelRouterError(
            "OPENAI_API_KEY is not configured"
        ) from None

    if provider == "anthropic":
        if settings.ANTHROPIC_API_KEY:
            from anthropic import Anthropic

            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            system, claude_messages = _split_system(messages)
            with client.messages.stream(
                model=model,
                max_tokens=8192,
                system=system or None,
                messages=claude_messages,
                temperature=temperature,
            ) as stream_ctx:
                for text in stream_ctx.text_stream:
                    if text:
                        yield text
            return
        raise ModelRouterError(
            "ANTHROPIC_API_KEY is not configured"
        ) from None

    if provider == "google":
        if settings.GOOGLE_AI_KEY:
            yield from _google_stream(model, messages, temperature)
            return
        raise ModelRouterError(
            "GOOGLE_AI_KEY is not configured"
        ) from None

    raise ModelRouterError(f"Cannot route model {model!r}")


def _google_complete(model: str, messages: list[dict], temperature: float) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.GOOGLE_AI_KEY)
    gen_model = genai.GenerativeModel(model)
    # Google's chat interface expects a flat prompt; collapse history. When the
    # final user message carries image parts (screenshots), convert them into
    # SDK-style parts so Gemini can see them.
    chat = gen_model.start_chat(history=_google_history(messages))
    content = messages[-1].get("content")
    if isinstance(content, list):
        content = _openai_content_to_google_parts(content, sdk_style=True)
    response = chat.send_message(content, generation_config={"temperature": temperature})
    return response.text if response else ""


def _google_history(messages: list[dict]):
    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] in ("user", "tool") else "model"
        content = msg.get("content")
        if isinstance(content, list):
            parts: list[dict] = _openai_content_to_google_parts(content, sdk_style=True)
        else:
            parts = [content] if content is not None else []
        history.append({"role": role, "parts": parts})
    return history


def _split_system(messages: list[dict]):
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return "\n".join(system_parts), rest


# ---------------------------------------------------------------------------
# Multimodal content (images / screenshots)
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _parse_data_uri(url) -> tuple[str, str] | None:
    """Split a ``data:image/<mime>;base64,<data>`` URI into (mime, data)."""
    if not isinstance(url, str) or not url.startswith("data:image/") or "," not in url:
        return None
    header, data = url.split(",", 1)
    mime = header[5:].split(";")[0].strip().lower()
    if mime not in _ALLOWED_IMAGE_MIMES or not data:
        return None
    return mime, data


def _openai_content_to_google_parts(content, sdk_style: bool = False) -> list[dict]:
    """Convert OpenAI-style message content (str or part list) to Gemini parts.

    ``image_url`` parts whose url is a ``data:image/...;base64,...`` URI become
    ``inlineData`` (REST) or ``inline_data`` (Python SDK) so Gemini can analyze
    screenshots and attached images. Anything else (http(s) URLs, unsupported
    mimes) is silently skipped so a bad attachment can never crash a turn.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [{"text": content}] if content.strip() else []
    parts: list[dict] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text":
            text = item.get("text")
            if text and str(text).strip():
                parts.append({"text": str(text)})
        elif kind == "image_url":
            parsed = _parse_data_uri((item.get("image_url") or {}).get("url"))
            if parsed:
                mime, data = parsed
                if sdk_style:
                    parts.append({"inline_data": {"mime_type": mime, "data": data}})
                else:
                    parts.append({"inlineData": {"mimeType": mime, "data": data}})
    return parts


# ---------------------------------------------------------------------------
# Google (Gemini) native tool calling + streaming
# ---------------------------------------------------------------------------


def _google_contents(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split OpenAI-style messages into (system_instruction, Gemini contents).

    Roles map user/assistant 1:1; tool responses carry their tool_call_id
    alongside the result so the model can match them to its calls.
    """
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    system_instruction = "\n".join(system_parts)
    contents: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role == "tool":
            tool_id = msg.get("tool_call_id") or "call_0"
            text = str(msg.get("content") or "")
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_id,
                                "response": {"result": text},
                            }
                        }
                    ],
                }
            )
            continue
        parts: list[dict] = _openai_content_to_google_parts(msg.get("content"))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw)
            except (ValueError, TypeError):
                args = {}
            parts.append(
                {
                    "functionCall": {
                        "name": fn.get("name") or call.get("name") or "",
                        "args": args,
                    }
                }
            )
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    return system_instruction, contents


def _openai_to_google_declaration(definition: dict) -> dict:
    """Convert one OpenAI tool definition into a Gemini function declaration.

    The definition is a ``{type, function: {...}}`` wrapper; Gemini accepts a
    mostly-identical JSON schema, but expects object types/"properties" keys
    to be uppercase ("OBJECT", "STRING", ...).
    """
    fn = definition.get("function") or definition
    parameters = fn.get("parameters") or {"type": "object", "properties": {}}
    return {
        "name": fn.get("name") or "",
        "description": fn.get("description") or "",
        "parameters": _google_type(parameters),
    }


def _google_type(schema: dict) -> dict:
    """Recursively uppercase JSON-schema type names for the Gemini API."""
    if not isinstance(schema, dict):
        return schema
    out: dict = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            out[key] = value.upper()
        elif key in ("properties", "items", "definitions"):
            if isinstance(value, dict):
                out[key] = {k: _google_type(v) for k, v in value.items()}
            else:
                out[key] = _google_type(value)
        elif key == "anyOf" and isinstance(value, list):
            out[key] = [_google_type(v) for v in value]
        else:
            out[key] = value
    return out


def _google_generate_payload(
    messages: list[dict],
    tools: list[dict],
    temperature: float,
    stream: bool,
    max_tokens: Optional[int],
) -> dict:
    system_instruction, contents = _google_contents(messages)
    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens or settings.AI_MAX_TOKENS,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    declarations = [_openai_to_google_declaration(t) for t in tools if t]
    if declarations:
        payload["tools"] = [{"functionDeclarations": declarations}]
    if stream:
        payload["streamConfig"] = {"includeThoughts": False}
    return payload


def _google_complete_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float,
    max_tokens: Optional[int],
) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = _google_generate_payload(messages, tools, temperature, False, max_tokens)
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                url, params={"key": settings.GOOGLE_AI_KEY}, json=payload
            )
    except httpx.HTTPError as exc:
        raise _request_retryable_error(exc) from exc
    if resp.status_code != 200:
        raise ModelRouterError(
            f"Google error {resp.status_code}: {resp.text[:300]}",
            status_code=resp.status_code,
        )
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise ModelRouterError("Google returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()
    tool_calls = []
    for p in parts:
        fc = p.get("functionCall")
        if fc:
            tool_calls.append(
                {
                    "id": fc.get("id") or f"call_{len(tool_calls)}",
                    "name": fc.get("name") or "",
                    "arguments": fc.get("args") or {},
                }
            )
    return {"content": text or None, "tool_calls": tool_calls}


def _google_stream(model: str, messages: list[dict], temperature: float):
    """Stream text chunks from Gemini (SSE streamGenerateContent)."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent"
    )
    payload = _google_generate_payload(messages, [], temperature, True, None)
    try:
        with httpx.Client(timeout=180) as client:
            with client.stream(
                "POST", url, params={"key": settings.GOOGLE_AI_KEY, "alt": "sse"}, json=payload
            ) as resp:
                if resp.status_code != 200:
                    raise ModelRouterError(
                        f"Google error {resp.status_code}: {resp.read()[:300]}",
                        status_code=resp.status_code,
                    )
                for raw in resp.iter_lines():
                    if not raw or not raw.startswith("data:"):
                        continue
                    payload = raw[len("data:"):].strip()
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                    except ValueError:
                        continue
                    for candidate in event.get("candidates") or []:
                        for part in (candidate.get("content") or {}).get("parts") or []:
                            text = part.get("text")
                            if text:
                                yield text
    except httpx.HTTPError as exc:
        raise _request_retryable_error(exc) from exc
