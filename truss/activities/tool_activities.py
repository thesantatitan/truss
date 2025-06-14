from __future__ import annotations

"""Temporal activity module that routes LLM *ToolCall*s to concrete tool implementations.

At this stage only the registry and generic *execute_tool_activity* router are
implemented.  Individual tools will be fleshed-out in subsequent subtasks but
minimal stub functions are provided to allow the activity to run and to keep
unit-tests simple.
"""

import json
from typing import Any, Awaitable, Callable, Dict, Mapping

from temporalio import activity
from temporalio.exceptions import ApplicationError

from truss.data_models import ToolCall, ToolCallResult


# ---------------------------------------------------------------------------
# Tool implementation stubs
# ---------------------------------------------------------------------------
async def _execute_web_search(query: str) -> Dict[str, Any]:  # noqa: D401 – imperative
    """Dummy implementation that will call a real search API in later tasks."""

    # In a future subtask we will call Serper/Google here.  Returning a static
    # payload keeps the API contract intact for now.
    return {"results": []}


async def _execute_get_stock_price(ticker_symbol: str) -> Dict[str, Any]:  # noqa: D401
    """Dummy financial lookup – returns a placeholder price until implemented."""

    return {"ticker": ticker_symbol.upper(), "price": None}


# ---------------------------------------------------------------------------
# Registry mapping – maps function names (as referenced by the LLM) to callables
# ---------------------------------------------------------------------------
ToolCallable = Callable[..., Awaitable[Dict[str, Any] | str]]

TOOL_REGISTRY: Mapping[str, ToolCallable] = {
    "web_search": _execute_web_search,
    "get_stock_price": _execute_get_stock_price,
}


# ---------------------------------------------------------------------------
# Activity router
# ---------------------------------------------------------------------------
@activity.defn(name="ExecuteTool")
async def execute_tool_activity(tool_call: ToolCall) -> ToolCallResult:  # noqa: D401 – imperative
    """Route the *tool_call* to the registered implementation and wrap the result.

    Steps
    -----
    1. Resolve the ``tool_call.name`` in :data:`TOOL_REGISTRY`.
    2. Parse the JSON *arguments* payload into keyword arguments.
    3. Await the tool coroutine with those arguments.
    4. Return the value packaged as :class:`ToolCallResult`.

    Raises
    ------
    ApplicationError
        If the *function* referenced in *tool_call* is not present in the
        registry or if the target callable raises an exception.  Temporal will
        treat this as a *non-retryable* failure unless explicitly configured
        otherwise by callers.
    """

    function_name = tool_call.name

    # ------------------------------------------------------------------
    # Resolve tool implementation
    # ------------------------------------------------------------------
    if function_name not in TOOL_REGISTRY:
        raise ApplicationError(f"Tool '{function_name}' is not registered.")

    tool_fn: ToolCallable = TOOL_REGISTRY[function_name]  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Parse arguments – they may arrive as a dict already or a JSON string.
    # ------------------------------------------------------------------
    try:
        raw_args = tool_call.arguments
        if isinstance(raw_args, str):
            kwargs: Dict[str, Any] = json.loads(raw_args)
        else:
            kwargs = dict(raw_args)  # shallow copy / normalise to plain dict
    except (TypeError, json.JSONDecodeError) as exc:  # pragma: no cover – arg errors
        raise ApplicationError("Invalid JSON arguments for tool call") from exc

    # ------------------------------------------------------------------
    # Execute – delegate to the actual tool implementation.
    # ------------------------------------------------------------------
    try:
        result = await tool_fn(**kwargs)
    except Exception as exc:  # noqa: BLE001 – surface as Temporal app error
        raise ApplicationError(f"Tool '{function_name}' execution failed: {exc}") from exc

    # Serialise the result payload so it can be stored in the DB as text if needed.
    if isinstance(result, (dict, list)):
        result_content: str | Dict[str, Any] = json.dumps(result)
    else:
        result_content = str(result)

    return ToolCallResult(tool_call_id=tool_call.id, content=result_content) 
