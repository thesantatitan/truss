"""Temporal activity handling LLM streaming with real-time UI updates.

This module exposes :func:`llm_activity` which streams assistant responses
from LiteLLM **and** publishes every raw chunk to Redis so the frontend can
render incremental updates.  Actual accumulation of chunks, persistence and
heartbeat logic are implemented in follow-up subtasks – this iteration
focuses solely on the *Redis publishing* requirement (Task 5.2).
"""

from __future__ import annotations

import json
from uuid import UUID
from typing import List

import anyio
import redis.asyncio as redis
from temporalio import activity

from truss.core.llm_client import stream_completion
from truss.data_models import AgentConfig, Message
from truss.settings import get_settings

__all__ = [
    "llm_activity",
]


async def _get_redis_client() -> "redis.Redis":
    """Return an *async* Redis client built from application settings."""

    settings = get_settings()
    # The Python Redis library automatically derives TLS/DB options from the
    # URL so we can simply forward it.
    return redis.from_url(settings.redis_url, decode_responses=False)


@activity.defn(name="LLMStreamPublish")
async def llm_activity(
    agent_config: AgentConfig,
    messages: List[Message],
    session_id: UUID,
    run_id: UUID,  # noqa: D401 – part of stable signature, unused for now
) -> None:  # noqa: D401 – imperative docstring handled by module
    """Stream assistant response and publish each raw chunk to Redis.

    This *Temporal activity* performs the following high-level steps:

    1. Derive LiteLLM parameters from the supplied *agent_config* and send a
       streaming chat-completion request using :func:`stream_completion`.
    2. For every chunk returned by the provider, immediately publish the raw
       JSON data to Redis channel ``stream:{session_id}`` for consumption by
       real-time clients.

    Down-stream improvements (accumulation, persistence, heartbeats) will be
    addressed by subsequent subtasks – keeping commits small and focused.
    """

    # ------------------------------------------------------------------
    # Acquire resources
    # ------------------------------------------------------------------
    redis_client = await _get_redis_client()

    try:
        # ------------------------------------------------------------------
        # Initiate streaming LLM request
        # ------------------------------------------------------------------
        chunk_stream = await stream_completion(agent_config=agent_config, conversation=messages)

        # ------------------------------------------------------------------
        # Forward chunks to Redis in *real time*
        # ------------------------------------------------------------------
        channel = f"stream:{session_id}"
        async for chunk in chunk_stream:  # type: Dict[str, Any]
            # Publish the provider chunk as a JSON-encoded string so clients can
            # parse it easily irrespective of Redis serialization.
            await redis_client.publish(channel, json.dumps(chunk))

    finally:
        # Ensure the connection is closed even if streaming raises.
        with anyio.CancelScope(shield=True):
            # Best-effort close; swallow exceptions so Temporal retries aren't
            # masked by connection teardown issues.
            try:
                await redis_client.aclose()
            except Exception:  # pragma: no cover
                activity.logger.warning("Failed to close Redis client", exc_info=True) 
