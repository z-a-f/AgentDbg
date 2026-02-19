"""
Tests for redaction: sensitive keys in payloads are replaced with __REDACTED__.
Uses AGENTDBG_REDACT_KEYS and temp dir via AGENTDBG_DATA_DIR.
"""
import os
from unittest.mock import patch

import pytest

from pathlib import Path

from agentdbg.constants import REDACTED_MARKER, TRUNCATED_MARKER
from agentdbg.config import load_config, AgentDbgConfig
from agentdbg.events import EventType
from agentdbg.tracing import record_tool_call, _redact_and_truncate, trace, traced_run
from agentdbg.storage import load_events, list_runs


def test_redaction_constants_unchanged():
    """Guards against accidental refactors."""
    assert REDACTED_MARKER == "__REDACTED__"
    assert TRUNCATED_MARKER == "__TRUNCATED__"


def test_max_field_truncation():
    """Strings over AGENTDBG_MAX_FIELD_BYTES are truncated and suffixed with __TRUNCATED__."""
    max_bytes = 100
    cfg = AgentDbgConfig(
        redact=True,
        redact_keys=["token"],
        max_field_bytes=max_bytes,
        loop_window=12,
        loop_repetitions=3,
        data_dir=Path("."),
    )
    short = "under limit"
    assert len(short.encode("utf-8")) <= max_bytes
    assert _redact_and_truncate(short, cfg) == short

    long_str = "x" * (max_bytes + 1)
    result = _redact_and_truncate(long_str, cfg)
    assert result.endswith(TRUNCATED_MARKER)
    assert len(result.encode("utf-8")) <= max_bytes

    # Nested dict: long value in payload is truncated
    payload = {"prompt": "a" * (max_bytes + 10), "other": "short"}
    out = _redact_and_truncate(payload, cfg)
    assert out["prompt"].endswith(TRUNCATED_MARKER)
    assert len(out["prompt"].encode("utf-8")) <= max_bytes
    assert out["other"] == "short"


@pytest.fixture
def redact_token_env():
    """Set AGENTDBG_REDACT_KEYS=token for the test."""
    old = os.environ.get("AGENTDBG_REDACT_KEYS")
    try:
        os.environ["AGENTDBG_REDACT_KEYS"] = "token"
        yield
    finally:
        if old is not None:
            os.environ["AGENTDBG_REDACT_KEYS"] = old
        elif "AGENTDBG_REDACT_KEYS" in os.environ:
            os.environ.pop("AGENTDBG_REDACT_KEYS")


@pytest.fixture
def redact_message_and_stack_env():
    """Set AGENTDBG_REDACT_KEYS=message,stack so ERROR payload message/stack are redacted."""
    old = os.environ.get("AGENTDBG_REDACT_KEYS")
    try:
        os.environ["AGENTDBG_REDACT_KEYS"] = "message,stack"
        yield
    finally:
        if old is not None:
            os.environ["AGENTDBG_REDACT_KEYS"] = old
        elif "AGENTDBG_REDACT_KEYS" in os.environ:
            os.environ.pop("AGENTDBG_REDACT_KEYS")


def test_record_tool_call_redacts_args_with_token_key(temp_data_dir, redact_token_env):
    """record_tool_call with args containing 'token' key -> value is __REDACTED__."""
    @trace
    def run_with_tool():
        record_tool_call("my_tool", args={"token": "secret-api-key", "query": "hello"})

    run_with_tool()

    config = load_config()
    runs = list_runs(limit=1, config=config)
    assert runs
    run_id = runs[0]["run_id"]
    events = load_events(run_id, config)

    tool_events = [e for e in events if e.get("event_type") == EventType.TOOL_CALL.value]
    assert len(tool_events) == 1
    payload = tool_events[0]["payload"]
    args = payload.get("args")
    assert isinstance(args, dict)
    assert args.get("token") == REDACTED_MARKER
    assert args.get("query") == "hello"


def test_error_event_payload_redacted_decorator(temp_data_dir, redact_message_and_stack_env):
    """ERROR from @trace has message and stack redacted when redact_keys include message,stack."""
    @trace
    def run_that_raises():
        raise ValueError("API key sk-abc123 is invalid")

    with pytest.raises(ValueError, match="API key sk-abc123 is invalid"):
        run_that_raises()

    config = load_config()
    runs = list_runs(limit=1, config=config)
    assert runs
    run_id = runs[0]["run_id"]
    events = load_events(run_id, config)

    error_events = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(error_events) == 1
    payload = error_events[0]["payload"]
    assert payload.get("message") == REDACTED_MARKER
    assert payload.get("stack") == REDACTED_MARKER
    assert payload.get("error_type") == "ValueError"


def test_error_event_payload_redacted_context_manager(temp_data_dir, redact_message_and_stack_env):
    """ERROR from traced_run() has message and stack redacted when redact_keys include message,stack."""
    with pytest.raises(ValueError, match="secret in context"):
        with traced_run(name="failing_run"):
            raise ValueError("secret in context")

    config = load_config()
    runs = list_runs(limit=1, config=config)
    assert runs
    run_id = runs[0]["run_id"]
    events = load_events(run_id, config)

    error_events = [e for e in events if e.get("event_type") == EventType.ERROR.value]
    assert len(error_events) == 1
    payload = error_events[0]["payload"]
    assert payload.get("message") == REDACTED_MARKER
    assert payload.get("stack") == REDACTED_MARKER


def test_run_start_argv_redacted(temp_data_dir):
    """RUN_START keeps argv but redacts only sensitive option values, e.g. --api-key=secret -> --api-key=__REDACTED__."""
    with patch("sys.argv", ["test_script.py", "--api-key=sk-secret-1234", "--verbose"]):
        @trace
        def run_quiet():
            pass

        run_quiet()

    config = load_config()
    runs = list_runs(limit=1, config=config)
    assert runs
    run_id = runs[0]["run_id"]
    events = load_events(run_id, config)

    run_start_events = [e for e in events if e.get("event_type") == EventType.RUN_START.value]
    assert len(run_start_events) == 1
    payload = run_start_events[0]["payload"]
    argv = payload.get("argv")
    assert isinstance(argv, list)
    assert argv == ["test_script.py", f"--api-key={REDACTED_MARKER}", "--verbose"]
