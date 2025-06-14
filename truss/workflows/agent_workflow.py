from __future__ import annotations

"""Temporal workflow orchestrating durable agent execution.

Skeleton implementation for subtask 7.1 – establishes workflow class
structure, signal/query handlers, and state variables.  Functional logic
will be implemented in subsequent subtasks.
"""

from typing import Optional
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.exceptions import ApplicationError
from temporalio.common import RetryPolicy

from truss.data_models import AgentWorkflowInput, AgentWorkflowOutput, Message  # placeholders until full impl


@workflow.defn
class TemporalAgentExecutionWorkflow:  # noqa: WPS110 – name specified in HLD/LLD
    """Durable agent execution workflow (skeleton)."""

    # ---------------------------------------------------------------------
    # Lifecycle helpers
    # ---------------------------------------------------------------------
    def __init__(self) -> None:  # noqa: D401 – imperative
        # Signal/query exposed state
        self.cancellation_requested: bool = False
        self.current_status: str = "initialising"

        # Internal trackers – populated during execution
        self._run_id: Optional[str] = None  # Will be populated when run created

    # ------------------------------------------------------------------
    # Signal handlers (mutate workflow state)
    # ------------------------------------------------------------------
    @workflow.signal
    def request_cancellation(self) -> None:  # noqa: D401 – imperative
        """External signal requesting graceful cancellation."""

        self.cancellation_requested = True

    # ------------------------------------------------------------------
    # Query handlers (read-only access)
    # ------------------------------------------------------------------
    @workflow.query
    def get_status(self) -> str:  # noqa: D401 – imperative
        """Return current workflow status for observers."""

        return self.current_status

    # ------------------------------------------------------------------
    # Main workflow run method – *not* yet implemented
    # ------------------------------------------------------------------
    @workflow.run
    async def execute(self, input: AgentWorkflowInput) -> AgentWorkflowOutput:  # type: ignore[override]
        """Initialise run row and first user message using StorageActivities.

        Only the *initialisation* responsibilities of the workflow are handled
        in this subtask – the reasoning loop and finalisation logic will be
        implemented in subsequent work.
        """

        # ------------------------------------------------------------------
        # 1. Sanity-check & local state
        # ------------------------------------------------------------------
        self.current_status = "initialising"

        # Convert session_id (str) to UUID if required – Temporal signals/inputs
        # prefer simple JSON-serialisable types, so PRD uses strings.
        try:
            session_uuid = UUID(str(input.session_id))
        except ValueError as exc:  # pragma: no cover – invalid caller payload
            raise ApplicationError("Invalid session_id UUID string", non_retryable=True) from exc

        default_retry = RetryPolicy(maximum_attempts=3)

        # ------------------------------------------------------------------
        # 2. Persist new *Run* row
        # ------------------------------------------------------------------
        run_id = await workflow.execute_activity(
            "CreateRun",
            args=[session_uuid],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=default_retry,
        )

        # ------------------------------------------------------------------
        # 3. Persist initial user message as *RunStep*
        # ------------------------------------------------------------------
        await workflow.execute_activity(
            "CreateRunStep",
            args=[run_id, input.user_message],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=default_retry,
        )

        # Store run identifier for later workflow steps
        self._run_id = str(run_id)

        # ------------------------------------------------------------------
        # 4. Main reasoning loop – delegate heavy lifting to activities
        # ------------------------------------------------------------------
        # NOTE: For now we do **not** load the AgentConfig because the session ->
        # agent mapping activity has not yet been implemented (future sub-task).
        # We simply forward ``None`` which is accepted by the stubbed
        # ``LLMStreamPublish`` activity used in unit-tests.  A real implementation
        # will supply the actual AgentConfig instance.
        agent_config = None  # type: ignore[assignment]

        self.current_status = "thinking"

        while True:
            # --------------------------------------------------------------
            # Cancellation check – honour external signal requests
            # --------------------------------------------------------------
            if self.cancellation_requested:
                raise ApplicationError("Workflow cancelled via signal", non_retryable=True)

            # --------------------------------------------------------------
            # 4.1 Fetch conversation memory for this session
            # --------------------------------------------------------------
            memory = await workflow.execute_activity(
                "GetRunMemory",
                args=[session_uuid],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=default_retry,
            )

            # Construct prompt – prepend system prompt if we have one
            messages_for_llm: list[Message] = []
            if agent_config is not None and getattr(agent_config, "system_prompt", None):
                messages_for_llm.append(
                    Message(role="system", content=getattr(agent_config, "system_prompt"))
                )
            messages_for_llm.extend(memory.messages)  # type: ignore[arg-type]

            # --------------------------------------------------------------
            # 4.2 Invoke LLM activity with streaming & durability guarantees
            # --------------------------------------------------------------
            assistant_response = await workflow.execute_activity(
                "LLMStreamPublish",
                args=[agent_config, messages_for_llm, session_uuid, run_id],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

            # --------------------------------------------------------------
            # 4.3 Decision – final response vs tool delegation
            # --------------------------------------------------------------
            if not assistant_response.tool_calls:
                # No tool calls requested → finished.
                self.current_status = "completed"
                return AgentWorkflowOutput(
                    run_id=run_id,
                    status="completed",
                    final_message=assistant_response,
                )

            # The assistant requested tool execution – this will be implemented
            # in the next sub-task.  For now we abort with a non-retryable error
            # so the workflow can be resumed after the feature lands.
            raise ApplicationError(
                "Tool call execution not yet implemented",
                type="NotImplemented",
                non_retryable=True,
            )

        # This line is unreachable but keeps the type-checker happy.
        # pragma: no cover
        return AgentWorkflowOutput(run_id=run_id, status="failed") 
