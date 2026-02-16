"""
Tracing tests: @trace success path (RUN_START + RUN_END, status ok), error path (ERROR, status error),
and loop detection integration (repeated pattern triggers LOOP_WARNING exactly once).
Uses temp dir via AGENTDBG_DATA_DIR; env restored by fixture.
"""
import pytest

from agentdbg import record_llm_call, record_tool_call, trace
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
