"""Async wrapper around LiteLLM for streaming chat completions.

The helper exposed here converts our internal Pydantic data models to the
JSON shape expected by `litellm.acompletion` and forwards configurable
parameters extracted from :class:`truss.data_models.AgentConfig`.

The public coroutine :func:`stream_completion` deliberately returns the
_async generator_ produced by `litellm.acompletion` unchanged so callers
can iterate over the provider's tokens/chunks directly.
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, Any, List

import litellm

from truss.data_models import AgentConfig, Message

__all__ = [
    "stream_completion",
]


def _build_messages_payload(messages: List[Message]) -> List[Dict[str, Any]]:
    """Convert internal :class:`Message` objects to LiteLLM JSON payload.

    LiteLLM expects a list of dictionaries with at minimum the keys
    ``role`` and ``content``.  We currently ignore tool call fields here –
    they will be handled at a higher level once we implement tool calling
    support in the streaming activity.
    """

    payload: List[Dict[str, Any]] = []
    for msg in messages:
        payload.append({
            "role": msg.role,
            "content": msg.content or "",
        })
    return payload


async def stream_completion(
    *,
    agent_config: AgentConfig,
    conversation: List[Message],
) -> AsyncIterator[Dict[str, Any]]:
    """Return an async iterator yielding streaming completion chunks.

    Parameters
    ----------
    agent_config
        The agent configuration containing LLM parameters to forward.
    conversation
        Ordered list of user/assistant/system messages to include in the
        completion request.
    """

    llm_conf = agent_config.llm_config

    # Build parameter dict conditionally so we don't send ``None`` values
    # for optional parameters which some providers reject.
    params: Dict[str, Any] = {
        "model": llm_conf.model_name,
        "temperature": llm_conf.temperature,
        "top_p": llm_conf.top_p,
        "frequency_penalty": llm_conf.frequency_penalty,
        "presence_penalty": llm_conf.presence_penalty,
        "stream": True,
        # Messages converted to provider format
        "messages": _build_messages_payload(conversation),
    }
    if llm_conf.max_tokens is not None:
        params["max_tokens"] = llm_conf.max_tokens

    # Delegate the heavy lifting to LiteLLM – it returns an *async generator*
    # when ``stream=True`` so we simply forward that upstream.
    # Any network exceptions are allowed to propagate so Temporal retry
    # policies can handle them at the activity layer.
    return await litellm.acompletion(**params) 
