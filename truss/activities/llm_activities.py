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
from typing import List, Dict, Any

import anyio
import redis.asyncio as redis
from temporalio import activity
from anyio import to_thread

from truss.core.llm_client import stream_completion
from truss.core.storage import PostgresStorage
from truss.data_models import AgentConfig, Message, ToolCall
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
) -> Message:  # noqa: D401 – imperative docstring handled by module
    """Stream assistant response and publish each raw chunk to Redis.

    This *Temporal activity* performs the following high-level steps:

    1. Derive LiteLLM parameters from the supplied *agent_config* and send a
       streaming chat-completion request using :func:`stream_completion`.
    2. For every chunk returned by the provider, immediately publish the raw
       JSON data to Redis channel ``stream:{session_id}`` for consumption by
       real-time clients.

    This implementation **extends** the previous streaming-only version by
    *accumulating* the provider deltas into a **complete** :class:`Message`
    instance which is returned to the workflow after streaming finishes.  The
    atomic persistence step will be introduced in the next sub-task.
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
        full_content: List[str] = []  # collect assistant text fragments

        # Track partial tool call construction:
        #   map tool_call_id -> {"name": str, "arguments": List[str]}
        _tool_buffers: Dict[str, Dict[str, Any]] = {}
        _tool_call_order: List[str] = []  # preserve order of first appearance

        # The final Message we'll return; initialised later to satisfy mypy.
        final_message: Message | None = None

        async for chunk in chunk_stream:  # type: Dict[str, Any]
            # Publish raw chunk for real-time UI
            await redis_client.publish(channel, json.dumps(chunk))

            # ------------------------------------------------------------------
            # Accumulate textual deltas for the final assistant message
            # ------------------------------------------------------------------
            try:
                delta = chunk["choices"][0]["delta"]
            except (KeyError, IndexError, TypeError):  # pragma: no cover – guard against provider shape changes
                activity.logger.warning("Unexpected chunk shape encountered while accumulating content: %s", chunk)
                continue

            # LiteLLM normalises OpenAI-style streaming payloads where text is
            # provided in the ``content`` field.
            if (content_piece := delta.get("content")):
                full_content.append(content_piece)

            # NOTE: Tool/function call accumulation will be handled in a future
            # sub-task.  We add support for OpenAI-compatible streaming tool
            # calls where the assistant emits "tool_calls": [ { id, type, function: { name, arguments } } ]

            if (tool_calls_delta := delta.get("tool_calls")):
                for tc in tool_calls_delta:  # each partial object
                    tc_id: str = tc.get("id")  # should always be present
                    if tc_id is None:  # pragma: no cover – guard
                        continue

                    if tc_id not in _tool_buffers:
                        _tool_buffers[tc_id] = {"name": None, "arguments": []}
                        _tool_call_order.append(tc_id)

                    buf = _tool_buffers[tc_id]

                    if func := tc.get("function"):
                        # Name might be sent in the first chunk, but may repeat – ensure we keep first non-null
                        if func.get("name"):
                            buf["name"] = func["name"]

                        # The arguments property may arrive in incremental chunks – append if present
                        if (args_part := func.get("arguments")) is not None:
                            buf["arguments"].append(args_part)

            # Emit a heartbeat so Temporal knows this activity is healthy even
            # during long-running streams.
            try:
                activity.heartbeat()
            except RuntimeError:
                # When running outside an activity context (e.g. plain unit
                # tests) heartbeat() raises – safely ignore so local tests can
                # exercise the logic without Temporal worker.
                pass

        # ------------------------------------------------------------------
        # Build the final assistant Message once streaming completed
        # ------------------------------------------------------------------
        tool_calls_final: List[ToolCall] | None = None
        if _tool_buffers:
            from json import loads  # local import to avoid top-level cost

            tool_calls_final = []
            for tid in _tool_call_order:
                buf = _tool_buffers[tid]
                raw_args = "".join(buf["arguments"])
                try:
                    parsed_args = loads(raw_args) if raw_args else {}
                except Exception:  # pragma: no cover – leave raw string if malformed
                    parsed_args = {"raw": raw_args}

                tool_calls_final.append(ToolCall(id=tid, name=buf["name"], arguments=parsed_args))

        final_message = Message(
            role="assistant",
            content="".join(full_content) if full_content else None,
            tool_calls=tool_calls_final,
        )

        # ------------------------------------------------------------------
        # ATOMIC DURABILITY: Persist the *complete* message before returning
        # ------------------------------------------------------------------
        storage = PostgresStorage.from_database_url(get_settings().database_url)

        # Off-load the blocking DB write to a worker thread so we don't block
        # the event-loop inside the activity runtime.
        await to_thread.run_sync(
            storage.create_run_step_from_message,
            run_id,
            final_message,
            cancellable=True,
        )

    finally:
        # Ensure the connection is closed even if streaming raises.
        with anyio.CancelScope(shield=True):
            # Best-effort close; swallow exceptions so Temporal retries aren't
            # masked by connection teardown issues.
            try:
                await redis_client.aclose()
            except Exception:  # pragma: no cover
                activity.logger.warning("Failed to close Redis client", exc_info=True)

    # Even if streaming raised an exception the finally block above will have
    # executed – but ``final_message`` may still be *None*.  In that case we
    # re-raise to let Temporal handle retries.  Otherwise we can safely return
    # the accumulated response.

    if final_message is None:
        raise RuntimeError("LLM streaming did not yield any chunks – cannot build assistant message")

    return final_message 
