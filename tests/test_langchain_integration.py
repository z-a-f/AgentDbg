"""
Tests for LangChain integration. Skip if langchain is not installed.
Uses temp dir; no network calls. Asserts TOOL_CALL and LLM_CALL events.
"""
import sys

import pytest

from agentdbg.config import load_config
from agentdbg.events import EventType
from agentdbg.storage import load_events, load_run_meta
from tests.conftest import get_latest_run_id


def test_langchain_integration_raises_clear_error_when_deps_missing():
    """When optional deps are missing, integration raises a clear error (no None, no NoneType)."""
    # Simulate missing langchain_core: access to .callbacks raises ImportError
    class FakeLangChainCore:
        def __getattr__(self, name: str):
            raise ImportError("No module named 'langchain_core.callbacks'")

    to_restore = {}
    for key in list(sys.modules.keys()):
        if key == "langchain_core" or key.startswith("langchain_core."):
            to_restore[key] = sys.modules.pop(key, None)
    for key in ("agentdbg.integrations.langchain", "agentdbg.integrations"):
        if key in sys.modules:
            to_restore[key] = sys.modules.pop(key)

    try:
        sys.modules["langchain_core"] = FakeLangChainCore()
        with pytest.raises(ImportError) as exc_info:
            from agentdbg.integrations import AgentDbgLangChainCallbackHandler  # noqa: F401
        msg = str(exc_info.value)
        assert "langchain" in msg.lower(), f"message should mention langchain: {msg!r}"
        assert "pip install" in msg.lower(), f"message should mention pip install: {msg!r}"
        assert "[langchain]" in msg, f"message should mention extra [langchain]: {msg!r}"
    finally:
        for key in ("langchain_core", "agentdbg.integrations.langchain", "agentdbg.integrations"):
            sys.modules.pop(key, None)
        sys.modules.update(to_restore)


def test_langchain_integration_does_not_break_core_import():
    """Core agentdbg import must not crash when LangChain optional deps are missing."""
    class FakeLangChainCore:
        def __getattr__(self, name: str):
            raise ImportError("No module named 'langchain_core.callbacks'")

    to_restore = {}
    for key in list(sys.modules.keys()):
        if key == "langchain_core" or key.startswith("langchain_core."):
            to_restore[key] = sys.modules.pop(key, None)

    try:
        sys.modules["langchain_core"] = FakeLangChainCore()
        import agentdbg  # noqa: F401
        assert agentdbg.__version__
    finally:
        sys.modules.pop("langchain_core", None)
        for k, v in to_restore.items():
            if v is not None:
                sys.modules[k] = v


pytest.importorskip("langchain_core")

from agentdbg import trace
from agentdbg.integrations.langchain import AgentDbgLangChainCallbackHandler


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
    err = error_tools[0].get("payload", {}).get("error")
    assert err is not None and isinstance(err, dict), "error should be structured object"
    assert err.get("type") == "ValueError"
    assert "simulated failure" in str(err.get("message", ""))
