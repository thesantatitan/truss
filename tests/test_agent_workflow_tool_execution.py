from uuid import uuid4

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio import worker as _worker
from temporalio import activity

from truss.data_models import (
    AgentWorkflowInput,
    Message,
    AgentMemory,
    ToolCall,
    ToolCallResult,
)
from truss.workflows import TemporalAgentExecutionWorkflow


@pytest.mark.asyncio
async def test_workflow_executes_tools_and_completes():
    """Workflow should call ExecuteTool and persist tool results before completing."""

    # In-memory trackers ------------------------------------------------------
    created_steps: list[Message] = []
    execute_tool_called: list[str] = []
    finalized: list[str] = []

    # ------------------------------------------------------------------
    # Activity stubs
    # ------------------------------------------------------------------
    @activity.defn(name="CreateRun")
    async def fake_create_run(session_id):
        return str(uuid4())

    @activity.defn(name="CreateRunStep")
    async def fake_create_run_step(run_id, message):
        created_steps.append(message)
        return str(uuid4())

    @activity.defn(name="GetRunMemory")
    async def fake_get_run_memory(session_id):
        # Return empty memory for simplicity – the workflow doesn't depend on
        # previous steps for this test scenario.
        return AgentMemory(messages=[])

    # Provide two-phase LLM behaviour: first call returns tool_calls, second none
    _llm_call_counter = {"count": 0}

    @activity.defn(name="LLMStreamPublish")
    async def fake_llm_stream_publish(agent_config, messages, session_id, run_id):
        _llm_call_counter["count"] += 1
        if _llm_call_counter["count"] == 1:
            # First iteration – ask to execute a tool
            tool_call = ToolCall(name="web_search", arguments={"query": "hi"})
            return Message(role="assistant", content=None, tool_calls=[tool_call])
        # Second iteration – final assistant response with no tool calls
        return Message(role="assistant", content="done", tool_calls=None)

    @activity.defn(name="ExecuteTool")
    async def fake_execute_tool(tool_call: ToolCall):
        execute_tool_called.append(tool_call.name)
        return ToolCallResult(tool_call_id=tool_call.id, content="result")

    @activity.defn(name="FinalizeRun")
    async def fake_finalize_run(run_id, status, error_msg):  # noqa: D401
        finalized.append(status)

    # ------------------------------------------------------------------
    env = await WorkflowEnvironment.start_time_skipping()
    worker = _worker.Worker(
        env.client,
        task_queue="test-tool-queue",
        workflows=[TemporalAgentExecutionWorkflow],
        activities=[
            fake_create_run,
            fake_create_run_step,
            fake_get_run_memory,
            fake_llm_stream_publish,
            fake_execute_tool,
            fake_finalize_run,
        ],
    )

    async with worker:
        input_payload = AgentWorkflowInput(
            session_id=str(uuid4()),
            user_message=Message(role="user", content="Hello"),
        )
        handle = await env.client.start_workflow(
            TemporalAgentExecutionWorkflow.execute,
            input_payload,
            id=f"wf-{uuid4()}",
            task_queue="test-tool-queue",
        )
        result = await handle.result()

    # Assertions --------------------------------------------------------------
    assert result.status == "completed"
    # ExecuteTool called exactly once
    assert execute_tool_called == ["web_search"]

    # A tool result message should have been persisted
    assert any(m.role == "tool" for m in created_steps)

    assert finalized == ["completed"]

    await env.shutdown() 
