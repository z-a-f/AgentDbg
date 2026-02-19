"""
Tests for redaction: sensitive keys in payloads are replaced with __REDACTED__.
Uses AGENTDBG_REDACT_KEYS and temp dir via AGENTDBG_DATA_DIR.
"""
import os
import pytest

from agentdbg.constants import REDACTED_MARKER, TRUNCATED_MARKER
from agentdbg.config import load_config
from agentdbg.events import EventType
from agentdbg.tracing import record_tool_call, trace
from agentdbg.storage import load_events, list_runs


def test_redaction_constants_unchanged():
    """Guards against accidental refactors."""
    assert REDACTED_MARKER == "__REDACTED__"
    assert TRUNCATED_MARKER == "__TRUNCATED__"


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
