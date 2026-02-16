"""
Tests for LangChain integration. Skip if langchain is not installed.
Uses temp dir; no network calls. Asserts TOOL_CALL and LLM_CALL events.
"""
import pytest

pytest.importorskip("langchain_core")

from agentdbg import trace
from agentdbg.config import load_config
from agentdbg.events import EventType
from agentdbg.integrations.langchain import AgentDbgLangChainCallbackHandler
from agentdbg.storage import load_events, load_run_meta
from tests.conftest import get_latest_run_id


@trace
def _traced_with_handler():
    """Run one tool and one LLM via handler so events are recorded."""
    handler = AgentDbgLangChainCallbackHandler()
    config = {"callbacks": [handler]}

    from langchain_core.language_models.fake import FakeListLLM
    from langchain_core.tools import tool

    @tool
    def test_tool(x: str) -> str:
        """Test tool for integration."""
        return f"ok:{x}"

    llm = FakeListLLM(responses=["fake response"])
    test_tool.invoke({"x": "hello"}, config=config)
    llm.invoke("prompt", config=config)


def test_langchain_handler_emits_tool_call_and_llm_call(temp_data_dir):
    """With langchain installed, traced run with handler produces TOOL_CALL and LLM_CALL."""
    _traced_with_handler()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)

    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]
    llm_events = [e for e in events if e.get("event_type") == EventType.LLM_CALL.value]

    assert len(tool_events) >= 1, "expected at least one TOOL_CALL"
    assert len(llm_events) >= 1, "expected at least one LLM_CALL"

    tool_payload = tool_events[0].get("payload", {})
    assert tool_payload.get("tool_name"), "TOOL_CALL should have tool_name"
    assert tool_payload.get("status") == "ok"

    llm_payload = llm_events[0].get("payload", {})
    assert llm_payload.get("model") is not None or "model" in llm_payload, "LLM_CALL should have model"


def test_langchain_handler_tool_error_emits_error_status(temp_data_dir):
    """Simulate tool error callback; record_tool_call is called with status=error."""
    handler = AgentDbgLangChainCallbackHandler()

    @trace
    def _run():
        handler.on_tool_start(
            {"name": "failing_tool"},
            '{"key": "value"}',
            run_id="00000000-0000-0000-0000-000000000001",
        )
        handler.on_tool_error(
            ValueError("simulated failure"),
            run_id="00000000-0000-0000-0000-000000000001",
        )

    _run()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    error_tools = [
        e for e in events
        if e.get("event_type") == EventType.TOOL_CALL.value
        and (e.get("payload") or {}).get("status") == "error"
    ]

    assert len(error_tools) >= 1, "expected at least one TOOL_CALL with status=error"
    assert "simulated failure" in str(error_tools[0].get("payload", {}).get("error", ""))
