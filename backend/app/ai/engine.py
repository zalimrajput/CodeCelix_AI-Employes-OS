"""Agent execution engine: turns a user message into a tool-calling loop.

Primary path uses the provider's native tool-calling protocol (OpenAI-style
``tools``/``tool_choice``), which OpenRouter exposes for all models in active
use.  A backward-compatible envelope fallback (``{{to_call: {...}}}``) is kept
for providers without native tool support and for models that refuse to emit
tool calls; ``extract_tool_call`` handles it defensively.
"""
import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai import executor
from app.ai import model_router
from app.ai.model_router import ModelRouterError, _is_retryable
from app.ai.tools import get_tool

logger = logging.getLogger("app.ai.engine")

MAX_STEPS = 6

_TOOL_PROTOCOL = """\
Use the provided functions whenever you need data from the workspace (leads,
customers, invoices, tasks, knowledge base, etc). Call tools yourself — do not
ask the user to fetch data. Never invent data that a tool did not return; if a
tool returns an error or no rows, say so honestly and suggest next steps.
"""


def extract_tool_call(reply: str) -> dict[str, Any] | None:
    """Extract the tool-call envelope, or None when the reply is an answer."""
    marker = reply.find("to_call")
    if marker == -1:
        return None
    start = reply.find("{", marker)
    if start == -1:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(reply[start:])
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    if not isinstance(name, str):
        return None
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    return {"name": name, "arguments": arguments}


def build_messages(
    *,
    employee_name: str,
    role: str,
    agent,
    allowed_tools: list[str] | None,
    org_name: str | None = None,
    memory: list[str] | None = None,
    context: list[dict] | None = None,
    user_message: str,
    images: list[dict] | None = None,
) -> list[dict]:
    """Assemble the chat history: system + memory + prior turns + user message.

    When ``images`` (OpenAI-style ``{"type": "image_url", "image_url": {"url":
    "data:image/...;base64,..."}}`` parts) are provided, the user message becomes
    a multimodal content list so vision-capable models can analyze screenshots.
    """
    tools = [t for t in (allowed_tools or []) if get_tool(t) is not None]
    system = agent.build_system_prompt(org_name=org_name)
    tools_block = ", ".join(sorted(tools)) if tools else "none"
    system = f"{system}\n\nYou have access to these tools: {tools_block}.\n{_TOOL_PROTOCOL}"

    if memory:
        system = f"{system}\n\nRelevant workspace context:\n" + "\n\n".join(memory)

    messages: list[dict] = [{"role": "system", "content": system}]
    if context:
        messages.extend(context)

    if images:
        content: Any = [{"type": "text", "text": user_message}]
        for img in images:
            url = img.get("image_url") if isinstance(img, dict) else img
            if isinstance(url, dict):
                url = url.get("url")
            if url:
                content.append({"type": "image_url", "image_url": {"url": url}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


def _openai_tools(allowed_tools: list[str]) -> list[dict]:
    """OpenAI-style function definitions for the tools an agent may use."""
    definitions = []
    for name in sorted(allowed_tools or []):
        spec = get_tool(name)
        if spec is None:
            continue
        definitions.append(
            {"type": "function", "function": spec.to_definition()}
        )
    return definitions


def run_agent(
    db: Session,
    *,
    organization_id,
    user_id: Optional[str],
    agent,
    user_message: str,
    memory: list[str] | None = None,
    context: list[dict] | None = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    images: list[dict] | None = None,
) -> str:
    """Execute a single user turn and return the final text answer."""
    messages = build_messages(
        agent=agent,
        employee_name=agent.display_name,
        role=agent.role,
        allowed_tools=agent.allowed_tools,
        memory=memory,
        context=context,
        user_message=user_message,
        images=images,
    )
    tools = _openai_tools(agent.allowed_tools)
    native = True
    retried_steps: set[int] = set()
    retry_budget = 1  # one transient-retry per step; refilled by every success

    for step in range(MAX_STEPS):
        if step:
            messages.append({"role": "user", "content": "Please continue."})
        try:
            if native:
                result = model_router.complete_with_tools(
                    messages, tools=tools, model=model, temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                reply = model_router.complete(
                    messages, model=model, temperature=temperature
                )
                result = {"content": reply, "tool_calls": []}
        except Exception as exc:  # noqa: BLE001 - model-facing failures
            if native and isinstance(exc, ModelRouterError):
                logger.warning(
                    "native tool calling unavailable (%s); falling back to envelope",
                    exc,
                )
                native = False
                continue
            if isinstance(exc, ModelRouterError) and exc.status_code == 402:
                logger.warning(
                    "model_router OpenRouter 402 on step %s; refilling retry budget and retrying",
                    step,
                )
                retry_budget = 1
                retried_steps.add(step)
                continue
            if isinstance(exc, ModelRouterError) and not _is_retryable(exc):
                logger.warning(
                    "model_router non-retryable failure on step %s: %s",
                    step, exc, exc_info=True,
                )
                detail = str(exc).strip() or exc.__class__.__name__
                return (
                    "Sorry, the language model is temporarily unavailable "
                    f"({exc.__class__.__name__}: {detail[:160]}). "
                    "Please try again in a moment."
                )

            # Transient provider-side failures (429 / 5xx / in-fight budget 
            # exhaustion) are worth one retry per step so a single hiccup 
            # does not kill the whole turn. The per-step retry budget is 
            # refilled by every successful step, so a permanently failing 
            # model still returns the apology quickly.
            if retry_budget > 0:
                retried_steps.add(step)
                retry_budget -= 1
                logger.warning(
                    "model_router transient failure on step %s: %s",
                    step, exc, exc_info=True,
                )
                continue
            logger.warning("model_router failure: %s", exc, exc_info=True)
            # Include the real detail — a bare class name made incidents like
            # an invalid model key impossible to diagnose from chat alone.
            #
            # OpenAI / Anthropic / Google errors are description-only (no status_code).
            # We only surface the raw detail for those so the user sees which provider
            # / model broke. OpenRouter errors (those that reach here with a status_code)
            # are already formatted in ModelRouterError with the upstream detail embedded,
            # so we keep the existing short template instead of re-printing the full JSON.
            detail = str(exc).strip() or exc.__class__.__name__
            return (
                "Sorry, the language model is temporarily unavailable "
                f"({exc.__class__.__name__}: {detail[:160]}). "
                "Please try again in a moment."
            )
            if retry_budget > 0:
                retried_steps.add(step)
                retry_budget -= 1
                logger.warning(
                    "model_router transient failure on step %s: %s",
                    step, exc, exc_info=True,
                )
                continue
            logger.warning("model_router failure: %s", exc, exc_info=True)
            # Include the real detail — a bare class name made incidents like
            # an invalid model key impossible to diagnose from chat alone.
            detail = str(exc).strip() or exc.__class__.__name__
            return (
                "Sorry, the language model is temporarily unavailable "
                f"({exc.__class__.__name__}: {detail[:160]}). "
                "Please try again in a moment."
            )

        retry_budget = 1

        call = None
        if result.get("tool_calls"):
            call = result["tool_calls"][0]
        if call is None and not native:
            call = extract_tool_call(result.get("content") or "")

        if call is None:
            text = (result.get("content") or "").strip()
            if text:
                return text
            # Some models emit an empty turn after a tool result; keep looping
            # (MAX_STEPS bounds this) instead of returning an empty reply.
            continue

        messages.append(
            {
                "role": "assistant",
                "content": result.get("content"),
                "tool_calls": [
                    {
                        "id": call.get("id", f"call_{step}"),
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("arguments") or {}, default=str),
                        },
                    }
                ],
            }
        )
        tool_result = executor.run(
            db,
            call["name"],
            organization_id,
            user_id,
            call.get("arguments") or {},
            allowed_tools=agent.allowed_tools,
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", f"call_{step}"),
                "content": json.dumps(tool_result, default=str),
            }
        )

    return (
        "I've reached the step limit for this request. "
        "Please rephrase or split your request into smaller parts."
    )


__all__ = ["run_agent", "build_messages", "extract_tool_call", "MAX_STEPS"]