from __future__ import annotations

"""Pydantic data models used throughout the Truss runtime.

Only skeleton class definitions are included in this first iteration.  Subsequent
subtasks will flesh out the individual models.
"""


from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4
from pydantic import Field

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
    """A single chat message, optionally associated with tool calls or their results."""

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = Field(
        default=None,
        description="If this message is a tool response, reference to the originating tool call",
    )


class ToolCall(BaseModel):
    """Represents a single tool invocation request coming from the LLM."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier of the tool call within the assistant turn")
    name: str = Field(..., description="Registered name of the tool/function to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Raw JSON arguments payload passed to the tool")


class ToolCallResult(BaseModel):
    """Result payload returned by a tool execution."""

    tool_call_id: str = Field(..., description="Identifier linking this result to the originating ToolCall.id")
    content: str | Dict[str, Any] = Field(..., description="Serialized result or message produced by the tool")


class AgentMemory(BaseModel):
    """Represents an ordered collection of chat messages that make up an agent's conversation memory."""

    messages: List[Message] = Field(
        ...,
        min_length=1,
        description="Ordered list of messages constituting the conversation memory (must contain at least one message)",
    )

    def add_message(self, message: Message) -> None:
        """Append a new message to the memory preserving order."""

        self.messages.append(message)


class LLMConfig(BaseModel):
    """Configuration options for the Large Language Model used by an agent."""

    model_name: str = Field(..., description="Identifier for the underlying LLM model, e.g. 'gpt-4o' or 'anthropic/claude-3'")
    temperature: float = Field(
        0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature; higher values produce more diverse output",
    )
    max_tokens: Optional[int] = Field(
        None,
        gt=0,
        description="Maximum number of tokens to generate in the completion (None means provider default)",
    )
    top_p: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter; consider tokens with cumulative probability <= top_p",
    )
    frequency_penalty: float = Field(
        0.0,
        ge=0.0,
        description="Penalises new tokens based on their existing frequency in text so far",
    )
    presence_penalty: float = Field(
        0.0,
        ge=0.0,
        description="Penalises new tokens based on whether they appear in the text so far",
    )

    class Config:
        frozen = True  # treat config as immutable so it can be hashed/cached


class AgentConfig(BaseModel):
    """High-level configuration describing an autonomous agent instance."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the agent configuration",
    )
    name: str = Field(..., min_length=1, description="Human-readable name for the agent")
    system_prompt: str = Field(
        ...,
        description="System prompt that will be prepended to every conversation with this agent",
    )
    llm_config: LLMConfig = Field(..., description="Parameters controlling the underlying LLM")
    tools: Optional[List[str]] = Field(
        default=None,
        description="List of tool names the agent is allowed to invoke (None means no tool calls)",
    )


class AgentWorkflowInput(BaseModel):
    """Placeholder for AgentWorkflowInput model – to be implemented in subtask 1.5."""

    # TODO: include session_id, user_message, run_id, etc.
    ...


class AgentWorkflowOutput(BaseModel):
    """Placeholder for AgentWorkflowOutput model – to be implemented in subtask 1.5."""

    # TODO: include status, final_message etc.
    ... 
