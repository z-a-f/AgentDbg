"""
Tracing tests: @trace success path (RUN_START + RUN_END, status ok), error path (ERROR, status error),
and loop detection integration (repeated pattern triggers LOOP_WARNING exactly once).
Uses temp dir via AGENTDBG_DATA_DIR; env restored by fixture.
"""
import pytest

from agentdbg import record_llm_call, record_state, record_tool_call, trace, traced_run
from agentdbg.config import load_config
from agentdbg.events import EventType
from agentdbg.storage import load_events, load_run_meta
from tests.conftest import get_latest_run_id


@trace
def _traced_ok():
    pass


@trace
def _traced_raises():
    raise ValueError("expected test error")


def test_trace_success_one_run_start_one_run_end_run_json_ok(temp_data_dir):
    """A @trace function writes exactly one RUN_START and one RUN_END; run.json status == 'ok'."""
    _traced_ok()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    run_starts = [e for e in events if e.get("event_type") == EventType.RUN_START.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(run_starts) == 1
    assert len(run_ends) == 1
    assert run_meta.get("status") == "ok"


def test_trace_error_one_error_run_json_error_counts(temp_data_dir):
    """A @trace function raising ValueError writes exactly one ERROR; run.json status == 'error'; errors == 1."""
    with pytest.raises(ValueError, match="expected test error"):
        _traced_raises()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(errors) == 1
    assert run_meta.get("status") == "error"
    assert run_meta.get("counts", {}).get("errors") == 1


@trace
def _traced_loop_pattern():
    """Emit (TOOL_CALL:foo, LLM_CALL:gpt) x 3 so loop detection fires once."""
    for _ in range(3):
        record_tool_call("foo", args={}, result=None)
        record_llm_call("gpt", prompt="p", response="r")


def test_loop_warning_emitted_once_for_repeated_pattern(temp_data_dir):
    """Repeated pattern (tool+llm x3) triggers exactly one LOOP_WARNING and counts.loop_warnings == 1."""
    _traced_loop_pattern()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    loop_warnings = [e for e in events if e.get("event_type") == EventType.LOOP_WARNING.value]
    assert len(loop_warnings) == 1
    assert run_meta.get("counts", {}).get("loop_warnings") == 1
    payload = loop_warnings[0].get("payload", {})
    assert "TOOL_CALL:foo" in payload.get("pattern", "")
    assert "LLM_CALL:gpt" in payload.get("pattern", "")
    assert payload.get("repetitions") == 3


def test_tool_call_records_error_status_and_error_object_on_exception(temp_data_dir):
    """Tool that raises records TOOL_CALL with status=error and error object (type, message)."""
    @trace
    def _run():
        try:
            def failing_tool():
                raise ValueError("boom")
            failing_tool()
        except ValueError as e:
            record_tool_call("failing_tool", args={}, result=None, status="error", error=e)

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]
    assert len(tool_events) >= 1
    payload = tool_events[0].get("payload", {})
    assert payload.get("status") == "error"
    err = payload.get("error")
    assert err is not None and isinstance(err, dict)
    assert err.get("error_type") == "ValueError"
    assert err.get("message") == "boom"


def test_llm_call_records_error_status_and_error_object_on_exception(temp_data_dir):
    """LLM call recorded with status=error and error=exception yields error object in payload."""
    @trace
    def _run():
        record_llm_call(
            model="gpt-4",
            prompt="test",
            response=None,
            status="error",
            error=RuntimeError("llm api failed"),
        )

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    llm_events = [e for e in events if e.get("event_type") == EventType.LLM_CALL.value]
    assert len(llm_events) >= 1
    payload = llm_events[0].get("payload", {})
    assert payload.get("status") == "error"
    err = payload.get("error")
    assert err is not None and isinstance(err, dict)
    assert err.get("error_type") == "RuntimeError"
    assert "llm api failed" in str(err.get("message", ""))


def test_success_calls_have_status_ok_and_no_error(temp_data_dir):
    """TOOL_CALL and LLM_CALL success paths have status=ok and error null/absent."""
    @trace
    def _run():
        record_tool_call("ok_tool", args={"x": 1}, result="done")
        record_llm_call("gpt", prompt="p", response="r")

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]
    llm_events = [e for e in events if e.get("event_type") == EventType.LLM_CALL.value]
    assert len(tool_events) >= 1
    assert len(llm_events) >= 1
    tool_payload = tool_events[0].get("payload", {})
    llm_payload = llm_events[0].get("payload", {})
    assert tool_payload.get("status") == "ok"
    assert llm_payload.get("status") == "ok"
    assert tool_payload.get("error") is None
    assert llm_payload.get("error") is None


def test_record_llm_call_accepts_float_token_counts(temp_data_dir, monkeypatch):
    """record_llm_call with usage containing float token counts normalizes to integers (e.g. 100.0 -> 100)."""
    monkeypatch.setenv("AGENTDBG_REDACT", "0")  # so usage.*_tokens keys are not redacted
    @trace
    def _run():
        record_llm_call(
            model="gpt-4",
            prompt="p",
            response="r",
            usage={
                "prompt_tokens": 10.0,
                "completion_tokens": 20.0,
                "total_tokens": 30.0,
            },
        )

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    llm_events = [e for e in events if e.get("event_type") == EventType.LLM_CALL.value]
    assert len(llm_events) >= 1
    usage = llm_events[0].get("payload", {}).get("usage")
    assert usage is not None
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert all(isinstance(v, int) for v in usage.values())


def test_normalize_usage_accepts_floats_and_mixed_types():
    """_normalize_usage accepts float token counts and casts to int; mixed int/float and None allowed."""
    from agentdbg.tracing import _normalize_usage

    # All floats (common from some LLM APIs)
    out = _normalize_usage({"prompt_tokens": 100.0, "completion_tokens": 50.0, "total_tokens": 150.0})
    assert out == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    # Mixed int and float
    out = _normalize_usage({"prompt_tokens": 10, "completion_tokens": 20.0, "total_tokens": 30})
    assert out == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    # Missing keys -> None; float truncated to int
    out = _normalize_usage({"prompt_tokens": 5.7, "completion_tokens": None, "total_tokens": 10})
    assert out["prompt_tokens"] == 5
    assert out["completion_tokens"] is None
    assert out["total_tokens"] == 10

    # Invalid types (e.g. string) -> None for that key
    out = _normalize_usage({"prompt_tokens": "100", "completion_tokens": 20.0, "total_tokens": 30})
    assert out["prompt_tokens"] is None
    assert out["completion_tokens"] == 20
    assert out["total_tokens"] == 30


def test_traced_run_success_one_run_start_one_run_end(temp_data_dir):
    """traced_run(name=...) writes exactly one RUN_START and one RUN_END; run.json status == 'ok'."""
    with traced_run(name="my_agent_run"):
        pass

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    run_starts = [e for e in events if e.get("event_type") == EventType.RUN_START.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(run_starts) == 1
    assert len(run_ends) == 1
    assert run_meta.get("status") == "ok"
    assert run_meta.get("run_name") == "my_agent_run"
    assert run_starts[0].get("payload", {}).get("run_name") == "my_agent_run"


def test_traced_run_error_one_error_run_json_error(temp_data_dir):
    """traced_run with raised exception writes ERROR, RUN_END status=error, and re-raises."""
    with pytest.raises(ValueError, match="traced_run error"):
        with traced_run(name="failing_run"):
            raise ValueError("traced_run error")

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(errors) == 1
    assert len(run_ends) == 1
    assert run_meta.get("status") == "error"
    assert run_meta.get("counts", {}).get("errors") == 1


def test_trace_system_exit_propagates_without_error_recorded(temp_data_dir):
    """SystemExit inside @trace propagates immediately; no ERROR event or RUN_END is written."""
    @trace(name="sys_exit_run")
    def _traced_sys_exit():
        raise SystemExit(42)

    with pytest.raises(SystemExit) as exc_info:
        _traced_sys_exit()
    assert exc_info.value.code == 42

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(errors) == 0, "SystemExit must not be recorded as ERROR"
    assert len(run_ends) == 0, "RUN_END must not be written on SystemExit (fast exit)"


def test_traced_run_keyboard_interrupt_propagates_without_error_recorded(temp_data_dir):
    """KeyboardInterrupt inside traced_run propagates immediately; no ERROR event is written."""
    with pytest.raises(KeyboardInterrupt):
        with traced_run(name="kbd_run"):
            raise KeyboardInterrupt()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(errors) == 0, "KeyboardInterrupt must not be recorded as ERROR"


def test_traced_run_nested_does_not_create_new_run(temp_data_dir):
    """Nested traced_run uses the outer run; only one RUN_START and one RUN_END."""
    with traced_run(name="outer"):
        with traced_run(name="inner"):
            record_tool_call("nested_tool", args={}, result="ok")

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_starts = [e for e in events if e.get("event_type") == EventType.RUN_START.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]

    assert len(run_starts) == 1
    assert len(run_ends) == 1
    assert run_starts[0].get("payload", {}).get("run_name") == "outer"
    assert len(tool_events) == 1
    assert tool_events[0].get("payload", {}).get("tool_name") == "nested_tool"


def test_trace_nested_decorated_uses_outer_run(temp_data_dir):
    """Nested @trace (inner decorated function called from outer) uses the outer run; only one RUN_START and one RUN_END."""
    @trace(name="outer_trace")
    def outer():
        record_tool_call("outer_tool", args={}, result="a")
        inner()
        record_tool_call("after_inner", args={}, result="b")

    @trace(name="inner_trace")
    def inner():
        record_tool_call("inner_tool", args={}, result="ok")

    outer()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_starts = [e for e in events if e.get("event_type") == EventType.RUN_START.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]
    tool_names = [e.get("payload", {}).get("tool_name") for e in tool_events]

    assert len(run_starts) == 1
    assert len(run_ends) == 1
    assert run_starts[0].get("payload", {}).get("run_name") == "outer_trace"
    assert tool_names == ["outer_tool", "inner_tool", "after_inner"]


def test_record_state_inside_trace_writes_state_update_event(temp_data_dir):
    """record_state inside @trace writes one STATE_UPDATE with state and meta to storage."""
    @trace
    def _run():
        record_state(state={"step": 1, "query": "hello"}, meta={"label": "after_search"})

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    state_events = [e for e in events if e.get("event_type") == EventType.STATE_UPDATE.value]
    assert len(state_events) == 1
    payload = state_events[0].get("payload", {})
    assert payload.get("state") == {"step": 1, "query": "hello"}
    assert state_events[0].get("meta", {}).get("label") == "after_search"
    assert state_events[0].get("name") == "state"


def test_record_state_with_diff(temp_data_dir):
    """record_state with state and diff stores both in payload."""
    @trace
    def _run():
        record_state(state={"count": 2}, diff={"count": 1})

    _run()
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    state_events = [e for e in events if e.get("event_type") == EventType.STATE_UPDATE.value]
    assert len(state_events) == 1
    payload = state_events[0].get("payload", {})
    assert payload.get("state") == {"count": 2}
    assert payload.get("diff") == {"count": 1}


def test_record_state_no_op_outside_trace(temp_data_dir):
    """record_state with no active run does not create a run or write events."""
    with traced_run(name="only_run"):
        pass
    record_state(state={"orphan": True})
    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    state_events = [e for e in events if e.get("event_type") == EventType.STATE_UPDATE.value]
    assert len(state_events) == 0
