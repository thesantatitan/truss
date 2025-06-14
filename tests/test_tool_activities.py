import json
import pytest

from temporalio.exceptions import ApplicationError

from truss.data_models import ToolCall
from truss.activities.tool_activities import execute_tool_activity


@pytest.mark.asyncio
async def test_execute_tool_activity_known_tool():
    """Router should dispatch to registered tool and wrap response in ToolCallResult."""

    call = ToolCall(name="web_search", arguments={"query": "python"})

    result = await execute_tool_activity(call)

    assert result.tool_call_id == call.id
    # the stub returns JSON string – parse to verify structure
    payload = json.loads(result.content)
    assert "results" in payload


@pytest.mark.asyncio
async def test_execute_tool_activity_unknown_tool():
    """Router must raise :class:`ApplicationError` for unregistered tools."""

    call = ToolCall(name="does_not_exist", arguments={})

    with pytest.raises(ApplicationError):
        await execute_tool_activity(call) 
