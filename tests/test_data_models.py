import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from truss.data_models import Message, ToolCall, ToolCallResult, LLMConfig, AgentConfig


def test_message_serialization_roundtrip():
    msg = Message(role="user", content="Hello world")
    json_str = msg.model_dump_json()
    parsed = Message.model_validate_json(json_str)
    assert parsed == msg


def test_tool_call_roundtrip():
    tool_call = ToolCall(name="add_numbers", arguments={"a": 1, "b": 2})
    json_str = tool_call.model_dump_json()
    parsed = ToolCall.model_validate_json(json_str)
    assert parsed == tool_call


def test_tool_call_result_roundtrip():
    tool_call = ToolCall(name="fake", arguments={})
    result = ToolCallResult(tool_call_id=tool_call.id, content={"ok": True})
    json_str = result.model_dump_json()
    parsed = ToolCallResult.model_validate_json(json_str)
    assert parsed == result


def test_invalid_role_raises_validation_error():
    with pytest.raises(ValueError):
        Message(role="invalid", content="oops")


def test_llm_config_roundtrip():
    cfg = LLMConfig(model_name="gpt-4o", temperature=0.5, max_tokens=256)
    json_str = cfg.model_dump_json()
    parsed = LLMConfig.model_validate_json(json_str)
    assert parsed == cfg


def test_agent_config_roundtrip():
    cfg = AgentConfig(
        name="Test Agent",
        system_prompt="You are a helpful assistant",
        llm_config=LLMConfig(model_name="gpt-3.5-turbo"),
        tools=["calculator", "search"],
    )
    json_str = cfg.model_dump_json()
    parsed = AgentConfig.model_validate_json(json_str)
    assert parsed == cfg


def test_invalid_llm_temperature_raises():
    with pytest.raises(ValueError):
        LLMConfig(model_name="gpt-4", temperature=3.0) 
