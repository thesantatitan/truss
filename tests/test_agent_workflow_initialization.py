from uuid import uuid4

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio import worker as _worker  # local import to avoid global deps
from temporalio import activity

from truss.data_models import AgentWorkflowInput, Message, AgentMemory
from truss.workflows import TemporalAgentExecutionWorkflow


@pytest.mark.asyncio
async def test_workflow_initialisation_creates_run_and_step():
    """Workflow should invoke CreateRun and CreateRunStep once each during init."""

    # --- Fake activity implementations -------------------------------------------------
    created_run_ids: list[str] = []
    created_steps: list[tuple[str, Message]] = []

    @activity.defn(name="CreateRun")
    async def fake_create_run(session_id):  # noqa: D401 – test stub
        run_id = uuid4()
        created_run_ids.append(str(run_id))
        return str(run_id)

    @activity.defn(name="CreateRunStep")
    async def fake_create_run_step(run_id, message):  # noqa: D401 – test stub
        created_steps.append((str(run_id), message))
        return str(uuid4())

    # Additional activities required by reasoning loop ----------------------

    @activity.defn(name="GetRunMemory")
    async def fake_get_run_memory(session_id):  # noqa: D401 – test stub
        # Return empty memory so the workflow treats next LLM call as first turn.
        return AgentMemory(messages=[])

    @activity.defn(name="LLMStreamPublish")
    async def fake_llm_stream_publish(agent_config, messages, session_id, run_id):  # noqa: D401
        # Always return a simple assistant Message with *no* tool calls so the
        # workflow exits the reasoning loop after a single iteration.
        return Message(role="assistant", content="Hi", tool_calls=None)

    # -----------------------------------------------------------------------------------
    env = await WorkflowEnvironment.start_time_skipping()

    worker = _worker.Worker(
        env.client,
        task_queue="test-queue",
        workflows=[TemporalAgentExecutionWorkflow],
        activities=[
            fake_create_run,
            fake_create_run_step,
            fake_get_run_memory,
            fake_llm_stream_publish,
        ],
    )

    # Run worker in background context
    async with worker:
        input_payload = AgentWorkflowInput(
            session_id=str(uuid4()),
            user_message=Message(role="user", content="hello"),
        )

        handle = await env.client.start_workflow(
            TemporalAgentExecutionWorkflow.execute,
            input_payload,
            id=f"wf-{uuid4()}",
            task_queue="test-queue",
        )

        result = await handle.result()

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    assert result.status == "completed"

    # Ensure our fake activities were called as expected
    assert len(created_run_ids) == 1
    assert len(created_steps) == 1
    assert created_steps[0][0] == created_run_ids[0]

    await env.shutdown() 
 