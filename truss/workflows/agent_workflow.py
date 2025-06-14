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

from truss.data_models import AgentWorkflowInput, AgentWorkflowOutput, Message, ToolCallResult  # placeholders until full impl


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

        # We wrap the *entire* execution flow in a try/except/finally so we can
        # guarantee a *FinalizeRun* activity executes exactly once regardless
        # of success, explicit cancellation, or runtime failure.

        run_id = None  # will be assigned after CreateRun succeeds
        final_status: str = "errored"  # pessimistic default
        error_message: str | None = None

        try:
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
                    final_status = "completed"
                    return AgentWorkflowOutput(
                        run_id=run_id,
                        status="completed",
                        final_message=assistant_response,
                    )

                # --------------------------------------------------------------
                # 4.4 Execute requested tools in *parallel*
                # --------------------------------------------------------------
                import asyncio  # local import to keep top-level clean & deterministic

                if assistant_response.tool_calls is None:  # pragma: no cover – safety guard
                    # Should not happen due to check above, but keep workflow safe.
                    continue

                self.current_status = f"executing {len(assistant_response.tool_calls)} tools"

                tool_tasks = [
                    workflow.execute_activity(
                        "ExecuteTool",
                        args=[tool_call],
                        start_to_close_timeout=timedelta(minutes=1),
                        retry_policy=default_retry,
                    )
                    for tool_call in assistant_response.tool_calls
                ]

                tool_results: list[ToolCallResult] = list(await asyncio.gather(*tool_tasks))

                # --------------------------------------------------------------
                # 4.5 Persist tool results as *tool* role RunSteps
                # --------------------------------------------------------------
                for res in tool_results:
                    tool_msg = Message(role="tool", content=res.content, tool_call_id=res.tool_call_id)

                    await workflow.execute_activity(
                        "CreateRunStep",
                        args=[run_id, tool_msg],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=default_retry,
                    )

                # Loop continues – with new memory containing tool results added

        except ApplicationError as exc:
            # Includes our custom cancellation exception and non-retryable errors
            error_message = str(exc)
            final_status = "cancelled" if "cancelled" in error_message.lower() else "errored"
            raise  # surface to caller so Temporal records failure/cancellation

        except Exception as exc:  # noqa: BLE001 – catch-all to record status
            error_message = str(exc)
            final_status = "errored"
            raise

        finally:
            # Ensure we attempt to finalise run *once* if run_id is available.
            if run_id is not None:
                try:
                    await workflow.execute_activity(
                        "FinalizeRun",
                        args=[run_id, final_status, error_message],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=10),
                    )
                except Exception:  # pragma: no cover – log but do not mask
                    # We cannot call activity.logger from workflow context; instead rely on Temporal stack trace.
                    pass

        # This line is only reached if the *return* path above was executed.
        # For mypy completeness.
        # pragma: no cover
        assert run_id is not None
        return AgentWorkflowOutput(run_id=run_id, status=final_status, error=error_message) 
