"""Pydantic data models used throughout the Truss runtime.

Only skeleton class definitions are included in this first iteration.  Subsequent
subtasks will flesh out the individual models.
"""


from __future__ import annotations
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
    """Input payload supplied when starting an Agent execution workflow.

    Attributes
    ----------
    session_id: str
        Unique identifier of the conversation session the run belongs to (UUID string).
    user_message: Message
        The latest user message that triggered this workflow execution.
    run_id: str | None
        Optional identifier of the run/Workflow execution. A UUID will be generated
        client-side where appropriate (e.g. by the API server) and forwarded so the
        Temporal workflow can adopt the same identifier.  Keeping the field optional
        allows callers that do not care about controlling the ID to omit it and let
        the system generate one downstream.
    """

    session_id: str = Field(..., description="Conversation session identifier (UUID string)")
    user_message: Message = Field(..., description="Latest user message to process")
    run_id: Optional[str] = Field(
        default=None,
        description="Optional identifier for the run/workflow. If omitted one will be generated downstream.",
    )


class AgentWorkflowOutput(BaseModel):
    """Represents the final or intermediate result returned by an Agent workflow.

    Attributes
    ----------
    run_id: str
        Identifier of the run/workflow this output relates to.
    status: Literal["running", "completed", "errored", "cancelled"]
        Current status of the workflow execution.
    final_message: Message | None
        If the workflow finished successfully, the assistant's final message.
    error: str | None
        Human-readable error string when *status* is "errored".
    """

    run_id: str = Field(..., description="Identifier of the run/workflow")
    status: Literal["running", "completed", "errored", "cancelled"] = Field(
        ..., description="Execution status of the workflow"
    )
    final_message: Optional[Message] = Field(
        default=None,
        description="Assistant's final message when execution succeeded (None until completed)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if status == 'errored'",
    ) 
