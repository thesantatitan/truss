from __future__ import annotations

"""Temporal workflow orchestrating durable agent execution.

Skeleton implementation for subtask 7.1 – establishes workflow class
structure, signal/query handlers, and state variables.  Functional logic
will be implemented in subsequent subtasks.
"""

from typing import Optional

from temporalio import workflow
from temporalio.exceptions import ApplicationError

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
        """Entry-point for Temporal – to be implemented in later subtasks."""

        # Skeleton placeholder – update status, then raise to indicate
        # incomplete implementation (this will be replaced soon).
        self.current_status = "not_implemented"

        # Raise a non-retryable error so workers surface missing implementation
        raise ApplicationError(
            "TemporalAgentExecutionWorkflow.execute is not yet implemented",
            type="NotImplemented",
            non_retryable=True,
        ) 
