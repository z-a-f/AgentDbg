"""
Storage tests: create_run, append_event/load_events, finalize_run.
Uses temp dir via AGENTDBG_DATA_DIR; env restored by fixture.
"""
import json

import pytest

from agentdbg.config import load_config
from agentdbg.events import EventType, new_event
from agentdbg.storage import (
    append_event,
    create_run,
    finalize_run,
    load_events,
    load_run_meta,
)


def test_create_run_writes_run_json_with_status_running(temp_data_dir):
    """create_run writes run.json with status 'running'."""
    config = load_config()
    meta = create_run("test_run", config)
    run_id = meta["run_id"]
    path = meta["paths"]["run_json"]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("status") == "running"
    assert data.get("run_id") == run_id


def test_append_event_writes_events_jsonl_load_events_reads_back(temp_data_dir):
    """append_event writes to events.jsonl and load_events reads it back."""
    config = load_config()
    meta = create_run("test_run", config)
    run_id = meta["run_id"]
    ev = new_event(EventType.TOOL_CALL, run_id, "tool1", {"tool_name": "tool1", "args": {}})
    append_event(run_id, ev, config)
    loaded = load_events(run_id, config)
    assert len(loaded) == 1
    assert loaded[0].get("event_type") == EventType.TOOL_CALL.value
    assert loaded[0].get("payload", {}).get("tool_name") == "tool1"


def test_finalize_run_sets_status_ok_ended_at_duration_ms(temp_data_dir):
    """finalize_run sets status 'ok' and sets ended_at and duration_ms not None."""
    config = load_config()
    meta = create_run("test_run", config)
    run_id = meta["run_id"]
    counts = {"llm_calls": 0, "tool_calls": 0, "errors": 0, "loop_warnings": 0}
    finalize_run(run_id, "ok", counts, config)
    run_meta = load_run_meta(run_id, config)
    assert run_meta.get("status") == "ok"
    assert run_meta.get("ended_at") is not None
    assert run_meta.get("duration_ms") is not None
