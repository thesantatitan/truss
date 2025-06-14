from __future__ import annotations

"""Pydantic data models used throughout the Truss runtime.

Only skeleton class definitions are included in this first iteration.  Subsequent
subtasks will flesh out the individual models.
"""


from pydantic import BaseModel

__all__ = [
    "Message",
    "ToolCall",
    "ToolCallResult",
    "AgentMemory",
    "LLMConfig",
    "AgentConfig",
    "AgentWorkflowInput",
    "AgentWorkflowOutput",
]


class Message(BaseModel):
    """Placeholder for Message model – to be implemented in subtask 1.2."""

    # TODO: add fields `role`, `content`, `tool_calls`, `tool_call_id` etc.
    ...


class ToolCall(BaseModel):
    """Placeholder for ToolCall model – to be implemented in subtask 1.2."""

    # TODO: define name, arguments schema, etc.
    ...


class ToolCallResult(BaseModel):
    """Placeholder for ToolCallResult model – to be implemented in subtask 1.2."""

    # TODO: define status, result, error, etc.
    ...


class AgentMemory(BaseModel):
    """Placeholder for AgentMemory model – to be implemented in subtask 1.3."""

    # TODO: include messages: List[Message]
    ...


class LLMConfig(BaseModel):
    """Placeholder for LLMConfig model – to be implemented in subtask 1.4."""

    # TODO: include model_name, temperature, max_tokens, etc.
    ...


class AgentConfig(BaseModel):
    """Placeholder for AgentConfig model – to be implemented in subtask 1.4."""

    # TODO: include id, name, system_prompt, llm_config, tools
    ...


class AgentWorkflowInput(BaseModel):
    """Placeholder for AgentWorkflowInput model – to be implemented in subtask 1.5."""

    # TODO: include session_id, user_message, run_id, etc.
    ...


class AgentWorkflowOutput(BaseModel):
    """Placeholder for AgentWorkflowOutput model – to be implemented in subtask 1.5."""

    # TODO: include status, final_message etc.
    ... 
