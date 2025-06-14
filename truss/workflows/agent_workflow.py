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

from truss.data_models import AgentWorkflowInput, AgentWorkflowOutput  # placeholders until full impl


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

        # For now, mark status and short-circuit further processing.
        self.current_status = "initialised"

        # Workflow not fully implemented – raise to stop execution without retry
        raise ApplicationError(
            "TemporalAgentExecutionWorkflow.execute – reasoning loop not yet implemented",
            type="NotImplemented",
            non_retryable=True,
        ) 
