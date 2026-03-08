"""
Guardrails tests: stop_on_loop, max_llm_calls, max_tool_calls, max_events, max_duration_s.

Deterministic: no network, no randomness. Uses temp_data_dir; max_duration_s tests
use patched time.
"""

import pytest

from agentdbg import record_llm_call, record_tool_call, record_state, trace, traced_run
from agentdbg.config import load_config
from agentdbg.events import EventType
from agentdbg.exceptions import AgentDbgGuardrailExceeded, AgentDbgLoopAbort
from agentdbg.storage import load_events, load_run_meta
from tests.conftest import get_latest_run_id


# ---------------------------------------------------------------------------
# stop_on_loop
# ---------------------------------------------------------------------------


@trace(stop_on_loop=True, stop_on_loop_min_repetitions=3)
def _run_loop_pattern():
    """Emit (TOOL_CALL:foo, LLM_CALL:gpt) x 3 so loop detection fires and guardrail aborts."""
    for _ in range(3):
        record_tool_call("foo", args={}, result=None)
        record_llm_call("gpt", prompt="p", response="r")


def test_stop_on_loop_enabled_and_threshold_crossed_aborts(temp_data_dir):
    """When stop_on_loop=True and loop detection fires with repetitions >= threshold, abort."""
    with pytest.raises(AgentDbgLoopAbort):
        _run_loop_pattern()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(errors) == 1
    assert len(run_ends) == 1
    assert run_meta.get("status") == "error"
    payload = errors[0].get("payload", {})
    assert payload.get("guardrail") == "stop_on_loop"
    assert payload.get("threshold") == 3
    assert payload.get("actual") == 3


@trace(stop_on_loop=False)
def _run_loop_pattern_no_stop():
    for _ in range(3):
        record_tool_call("x", args={}, result=None)
        record_llm_call("y", prompt="p", response="r")


def test_stop_on_loop_disabled_no_abort(temp_data_dir):
    """When stop_on_loop=False, loop warning is emitted but no abort."""
    _run_loop_pattern_no_stop()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    loop_warnings = [
        e for e in events if e.get("event_type") == EventType.LOOP_WARNING.value
    ]
    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(loop_warnings) == 1
    assert len(errors) == 0
    assert run_meta.get("status") == "ok"


def test_stop_on_loop_below_threshold_no_abort(temp_data_dir):
    """When repetitions (2) < stop_on_loop_min_repetitions (3), no abort."""

    @trace(stop_on_loop=True, stop_on_loop_min_repetitions=3)
    def run_two():
        record_tool_call("a", args={}, result=None)
        record_llm_call("b", prompt="p", response="r")
        record_tool_call("a", args={}, result=None)
        record_llm_call("b", prompt="p", response="r")

    run_two()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(errors) == 0
    assert run_meta.get("status") == "ok"


# ---------------------------------------------------------------------------
# max_llm_calls
# ---------------------------------------------------------------------------


def test_max_llm_calls_triggers_at_n_plus_one(temp_data_dir):
    """max_llm_calls=50 allows 50 calls; 51st triggers abort."""

    @trace(max_llm_calls=2)
    def run_three_llm():
        record_llm_call("m", prompt="p", response="r")
        record_llm_call("m", prompt="p", response="r")
        record_llm_call("m", prompt="p", response="r")

    with pytest.raises(AgentDbgGuardrailExceeded) as exc_info:
        run_three_llm()

    assert exc_info.value.guardrail == "max_llm_calls"
    assert exc_info.value.threshold == 2
    assert exc_info.value.actual == 3

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)
    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(errors) == 1
    assert errors[0]["payload"]["guardrail"] == "max_llm_calls"
    assert run_meta.get("status") == "error"


def test_max_llm_calls_at_limit_does_not_trigger(temp_data_dir):
    """Exactly 2 LLM calls when max_llm_calls=2 completes ok."""

    @trace(max_llm_calls=2)
    def run_two_llm():
        record_llm_call("m", prompt="p", response="r")
        record_llm_call("m", prompt="p", response="r")

    run_two_llm()

    config = load_config()
    run_id = get_latest_run_id(config)
    run_meta = load_run_meta(run_id, config)
    assert run_meta.get("status") == "ok"
    assert run_meta.get("counts", {}).get("llm_calls") == 2


# ---------------------------------------------------------------------------
# max_tool_calls
# ---------------------------------------------------------------------------


def test_max_tool_calls_triggers_at_n_plus_one(temp_data_dir):
    """max_tool_calls=2 allows 2; 3rd triggers abort."""

    @trace(max_tool_calls=2)
    def run_three_tool():
        record_tool_call("t", args={}, result=None)
        record_tool_call("t", args={}, result=None)
        record_tool_call("t", args={}, result=None)

    with pytest.raises(AgentDbgGuardrailExceeded) as exc_info:
        run_three_tool()

    assert exc_info.value.guardrail == "max_tool_calls"
    assert exc_info.value.threshold == 2
    assert exc_info.value.actual == 3


# ---------------------------------------------------------------------------
# max_events
# ---------------------------------------------------------------------------


def test_max_events_triggers_at_threshold(temp_data_dir):
    """max_events=5 aborts when total events exceeds 5 (e.g. after 6th event)."""

    @trace(max_events=5)
    def run_many_events():
        record_llm_call("m", prompt="p", response="r")
        record_tool_call("t", args={}, result=None)
        record_state(state={})
        record_llm_call("m", prompt="p", response="r")
        record_tool_call("t", args={}, result=None)

    with pytest.raises(AgentDbgGuardrailExceeded) as exc_info:
        run_many_events()

    assert exc_info.value.guardrail == "max_events"
    assert exc_info.value.threshold == 5
    assert exc_info.value.actual > 5


# ---------------------------------------------------------------------------
# max_duration_s (deterministic via patched time)
# ---------------------------------------------------------------------------


def test_max_duration_s_triggers_after_timeout(temp_data_dir, monkeypatch):
    """max_duration_s triggers when elapsed time >= limit; use patched time for determinism."""
    from agentdbg import guardrails as guardrails_mod
    from agentdbg import storage as storage_mod

    start_ts = "2026-01-01T12:00:00.000Z"
    end_ts = "2026-01-01T12:01:40.000Z"  # 100s later

    monkeypatch.setattr(storage_mod, "utc_now_iso_ms_z", lambda: start_ts)
    monkeypatch.setattr(guardrails_mod, "utc_now_iso_ms_z", lambda: end_ts)

    with pytest.raises(AgentDbgGuardrailExceeded) as exc_info:
        with traced_run(max_duration_s=60):
            record_llm_call("m", prompt="p", response="r")

    assert exc_info.value.guardrail == "max_duration_s"
    assert exc_info.value.threshold == 60
    assert exc_info.value.actual >= 60


# ---------------------------------------------------------------------------
# Lifecycle: ERROR + RUN_END and re-raise
# ---------------------------------------------------------------------------


def test_guardrail_abort_records_error_and_run_end(temp_data_dir):
    """Guardrail abort produces exactly one ERROR and RUN_END(status=error)."""

    @trace(max_llm_calls=0)
    def run_one_llm():
        record_llm_call("m", prompt="p", response="r")

    with pytest.raises(AgentDbgGuardrailExceeded):
        run_one_llm()

    config = load_config()
    run_id = get_latest_run_id(config)
    events = load_events(run_id, config)
    run_meta = load_run_meta(run_id, config)

    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    run_ends = [e for e in events if e.get("event_type") == EventType.RUN_END.value]
    assert len(errors) == 1
    assert len(run_ends) == 1
    assert run_ends[0].get("payload", {}).get("status") == "error"
    assert run_meta.get("status") == "error"
    assert run_meta.get("counts", {}).get("errors") == 1


def test_guardrail_exception_re_raised(temp_data_dir):
    """Caller can catch AgentDbgGuardrailExceeded."""

    @trace(max_llm_calls=0)
    def run_one():
        record_llm_call("m", prompt="p", response="r")

    caught = None
    try:
        run_one()
    except AgentDbgGuardrailExceeded as e:
        caught = e

    assert caught is not None
    assert caught.guardrail == "max_llm_calls"


# ---------------------------------------------------------------------------
# Defaults unchanged
# ---------------------------------------------------------------------------


@trace
def _traced_no_guardrails():
    for _ in range(4):
        record_llm_call("m", prompt="p", response="r")
        record_tool_call("t", args={}, result=None)


def test_default_behavior_unchanged(temp_data_dir):
    """With no guardrail params (defaults), run completes normally."""
    _traced_no_guardrails()

    config = load_config()
    run_id = get_latest_run_id(config)
    run_meta = load_run_meta(run_id, config)
    events = load_events(run_id, config)

    assert run_meta.get("status") == "ok"
    assert run_meta.get("counts", {}).get("llm_calls") == 4
    assert run_meta.get("counts", {}).get("tool_calls") == 4
    errors = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(errors) == 0


# ---------------------------------------------------------------------------
# Precedence: function args > env
# ---------------------------------------------------------------------------


def test_precedence_function_arg_over_env(temp_data_dir, monkeypatch):
    """@trace(max_llm_calls=2) overrides AGENTDBG_MAX_LLM_CALLS=10."""
    monkeypatch.setenv("AGENTDBG_MAX_LLM_CALLS", "10")

    @trace(max_llm_calls=2)
    def run_three():
        record_llm_call("m", prompt="p", response="r")
        record_llm_call("m", prompt="p", response="r")
        record_llm_call("m", prompt="p", response="r")

    with pytest.raises(AgentDbgGuardrailExceeded) as exc_info:
        run_three()

    assert exc_info.value.threshold == 2


# ---------------------------------------------------------------------------
# traced_run with guardrails
# ---------------------------------------------------------------------------


def test_traced_run_with_guardrails(temp_data_dir):
    """traced_run(max_llm_calls=N) enforces limit."""
    with pytest.raises(AgentDbgGuardrailExceeded):
        with traced_run(max_llm_calls=1):
            record_llm_call("a", prompt="p", response="r")
            record_llm_call("b", prompt="p", response="r")

    config = load_config()
    run_id = get_latest_run_id(config)
    run_meta = load_run_meta(run_id, config)
    assert run_meta.get("status") == "error"
