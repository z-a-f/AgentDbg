"""
Deterministic tests for the OpenAI Agents SDK integration.

The real `openai-agents` package is optional. These tests install a fake
`agents.tracing` surface in `sys.modules`, then assert the adapter registers on
import and translates spans into AgentDbg events.
"""

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agentdbg.integrations._error import MissingOptionalDependencyError


def _drop_openai_agents_integration_modules() -> None:
    sys.modules.pop("agentdbg.integrations.openai_agents", None)
    sys.modules.pop("agentdbg.integrations", None)


def _make_fake_agents_modules() -> dict[str, ModuleType]:
    agents_module = ModuleType("agents")
    agents_module.__path__ = []  # type: ignore[attr-defined]

    tracing_module = ModuleType("agents.tracing")
    span_data_module = ModuleType("agents.tracing.span_data")
    processor_module = ModuleType("agents.tracing.processor_interface")

    class TracingProcessor:
        def on_trace_start(self, trace):
            return None

        def on_trace_end(self, trace):
            return None

        def on_span_start(self, span):
            return None

        def on_span_end(self, span):
            return None

        def shutdown(self):
            return None

        def force_flush(self):
            return None

    class GenerationSpanData:
        def __init__(
            self,
            input=None,
            output=None,
            model=None,
            model_config=None,
            usage=None,
        ):
            self.input = input
            self.output = output
            self.model = model
            self.model_config = model_config
            self.usage = usage

    class FunctionSpanData:
        def __init__(self, name, input=None, output=None, mcp_data=None):
            self.name = name
            self.input = input
            self.output = output
            self.mcp_data = mcp_data

    class HandoffSpanData:
        def __init__(self, from_agent=None, to_agent=None):
            self.from_agent = from_agent
            self.to_agent = to_agent

    tracing_module._processors = []

    def add_trace_processor(processor):
        tracing_module._processors.append(processor)

    def emit_span(span):
        for processor in list(tracing_module._processors):
            processor.on_span_end(span)

    tracing_module.add_trace_processor = add_trace_processor
    tracing_module.emit_span = emit_span
    tracing_module.TracingProcessor = TracingProcessor

    span_data_module.GenerationSpanData = GenerationSpanData
    span_data_module.FunctionSpanData = FunctionSpanData
    span_data_module.HandoffSpanData = HandoffSpanData
    processor_module.TracingProcessor = TracingProcessor

    agents_module.tracing = tracing_module

    return {
        "agents": agents_module,
        "agents.tracing": tracing_module,
        "agents.tracing.span_data": span_data_module,
        "agents.tracing.processor_interface": processor_module,
    }


def _fake_span(span_data, *, error=None, parent_id=None):
    return SimpleNamespace(
        span_data=span_data,
        error=error,
        trace_id="trace_1234567890abcdef1234567890abcd",
        span_id="span_123",
        parent_id=parent_id,
        trace_metadata={"source": "test"},
        started_at="2026-03-08T12:00:00.000Z",
        ended_at="2026-03-08T12:00:00.100Z",
    )


@pytest.fixture(autouse=True)
def clear_openai_integration_imports():
    _drop_openai_agents_integration_modules()
    yield
    _drop_openai_agents_integration_modules()


@pytest.fixture
def openai_agents_module():
    fake_modules = _make_fake_agents_modules()
    with patch.dict(sys.modules, fake_modules):
        import agentdbg.integrations.openai_agents as openai_agents

        yield (
            openai_agents,
            fake_modules["agents.tracing"],
            fake_modules["agents.tracing.span_data"],
        )


def test_import_without_optional_dependency_raises_clear_error():
    to_restore = {}
    for key in list(sys.modules.keys()):
        if key == "agents" or key.startswith("agents."):
            to_restore[key] = sys.modules.pop(key, None)

    fake_agents = ModuleType("agents")

    try:
        with patch.dict(sys.modules, {"agents": fake_agents}, clear=False):
            with pytest.raises(MissingOptionalDependencyError) as exc_info:
                import agentdbg.integrations.openai_agents  # noqa: F401
    finally:
        sys.modules.pop("agents", None)
        for key, value in to_restore.items():
            if value is not None:
                sys.modules[key] = value

    assert "OpenAI Agents" in str(exc_info.value)
    assert "agentdbg[openai-agents]" in str(exc_info.value)


def test_openai_integration_does_not_break_core_import():
    """Core agentdbg import must not crash when OpenAI Agents deps are missing."""
    agents_module = ModuleType("agents")

    with patch.dict(sys.modules, {"agents": agents_module}, clear=False):
        import agentdbg

    assert agentdbg.__version__


def test_import_registers_processor_once(openai_agents_module):
    openai_agents, tracing_module, _ = openai_agents_module

    assert len(tracing_module._processors) == 1

    importlib.reload(openai_agents)

    assert len(tracing_module._processors) == 1


def test_generation_span_is_ignored_without_active_run(openai_agents_module):
    openai_agents, tracing_module, span_data = openai_agents_module
    span = _fake_span(
        span_data.GenerationSpanData(
            input=[{"role": "user", "content": "hello"}],
            output=[{"role": "assistant", "content": "hi"}],
            model="gpt-4o-mini",
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        )
    )

    with patch.object(openai_agents, "record_llm_call", MagicMock()) as record_llm:
        tracing_module.emit_span(span)

    record_llm.assert_not_called()


def test_generation_span_records_llm_call_event(openai_agents_module):
    openai_agents, tracing_module, span_data = openai_agents_module

    span = _fake_span(
        span_data.GenerationSpanData(
            input=[{"role": "user", "content": "Summarize this"}],
            output=[{"role": "assistant", "content": "Summary"}],
            model="gpt-4o-mini",
            model_config={"temperature": 0.2},
            usage={
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        )
    )

    with patch.object(openai_agents, "has_active_run", return_value=True):
        with patch.object(openai_agents, "record_llm_call", MagicMock()) as record_llm:
            tracing_module.emit_span(span)

    record_llm.assert_called_once()
    kw = record_llm.call_args.kwargs
    assert kw["model"] == "gpt-4o-mini"
    assert kw["prompt"] == [{"role": "user", "content": "Summarize this"}]
    assert kw["response"] == [{"role": "assistant", "content": "Summary"}]
    assert kw["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert kw["provider"] == "openai"
    assert kw["status"] == "ok"
    meta = kw["meta"]
    assert meta["framework"] == "openai_agents"
    assert meta["openai_agents"]["span_type"] == "generation"
    assert meta["openai_agents"]["model_config"] == {"temperature": 0.2}


def test_function_and_handoff_spans_record_tool_call_events(openai_agents_module):
    openai_agents, tracing_module, span_data = openai_agents_module

    function_span = _fake_span(
        span_data.FunctionSpanData(
            name="search_docs",
            input={"query": "agentdbg"},
            output={"hits": 2},
            mcp_data={"server": "docs"},
        ),
        parent_id="span_parent",
    )
    handoff_span = _fake_span(
        span_data.HandoffSpanData(from_agent="router_agent", to_agent="search_agent")
    )

    with patch.object(openai_agents, "has_active_run", return_value=True):
        with patch.object(
            openai_agents, "record_tool_call", MagicMock()
        ) as record_tool:
            tracing_module.emit_span(function_span)
            tracing_module.emit_span(handoff_span)

    assert record_tool.call_count == 2

    function_kw = record_tool.call_args_list[0].kwargs
    assert function_kw["name"] == "search_docs"
    assert function_kw["args"] == {"query": "agentdbg"}
    assert function_kw["result"] == {"hits": 2}
    assert function_kw["status"] == "ok"
    function_meta = function_kw["meta"]
    assert function_meta["framework"] == "openai_agents"
    assert function_meta["openai_agents"]["span_type"] == "function"
    assert function_meta["openai_agents"]["mcp_data"] == {"server": "docs"}
    assert function_meta["openai_agents"]["parent_id"] == "span_parent"

    handoff_kw = record_tool.call_args_list[1].kwargs
    assert handoff_kw["name"] == "handoff"
    assert handoff_kw["args"] is None
    assert handoff_kw["result"] is None
    assert handoff_kw["status"] == "ok"
    handoff_meta = handoff_kw["meta"]
    assert handoff_meta["openai_agents"]["span_type"] == "handoff"
    assert handoff_meta["openai_agents"]["handoff"] == {
        "from_agent": "router_agent",
        "to_agent": "search_agent",
    }


def test_generation_error_records_error_status(openai_agents_module):
    openai_agents, tracing_module, span_data = openai_agents_module

    span = _fake_span(
        span_data.GenerationSpanData(
            input=[{"role": "user", "content": "fail"}],
            output=None,
            model="gpt-4o-mini",
            usage=None,
        ),
        error={"message": "model failed", "data": {"code": "boom"}},
    )

    with patch.object(openai_agents, "has_active_run", return_value=True):
        with patch.object(openai_agents, "record_llm_call", MagicMock()) as record_llm:
            tracing_module.emit_span(span)

    record_llm.assert_called_once()
    kw = record_llm.call_args.kwargs
    assert kw["status"] == "error"
    assert kw["error"]["error_type"] == "OpenAIAgentsSpanError"
    assert kw["error"]["message"] == "model failed"
    assert kw["error"]["details"] == {"code": "boom"}


def test_no_run_created_when_only_sdk_span_is_emitted(openai_agents_module):
    openai_agents, tracing_module, span_data = openai_agents_module

    function_span = _fake_span(
        span_data.FunctionSpanData(
            name="search_docs",
            input={"query": "agentdbg"},
            output={"hits": 2},
        )
    )

    with patch.object(openai_agents, "has_active_run", return_value=False):
        with patch.object(
            openai_agents, "record_tool_call", MagicMock()
        ) as record_tool:
            tracing_module.emit_span(function_span)

    record_tool.assert_not_called()
