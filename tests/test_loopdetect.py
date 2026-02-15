"""
Tests for loop detection: compute_signature, detect_loop, pattern_key.
"""
import pytest

from agentdbg.loopdetect import detect_loop, pattern_key


def _event(event_id: str, event_type: str, payload: dict | None = None) -> dict:
    """Build a minimal event with event_id, event_type, payload."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "payload": payload or {},
    }


def test_loop_triggers_for_repeated_tail_pattern():
    """Repeated tail (TOOL_CALL:A, LLM_CALL:M) x3 → payload with evidence length m*repetitions."""
    # Pattern A, M repeated 3 times = 6 events
    events = [
        _event("e1", "TOOL_CALL", {"tool_name": "A"}),
        _event("e2", "LLM_CALL", {"model": "M"}),
        _event("e3", "TOOL_CALL", {"tool_name": "A"}),
        _event("e4", "LLM_CALL", {"model": "M"}),
        _event("e5", "TOOL_CALL", {"tool_name": "A"}),
        _event("e6", "LLM_CALL", {"model": "M"}),
    ]
    result = detect_loop(events, window=12, repetitions=3)
    assert result is not None
    assert result["pattern"] == "TOOL_CALL:A -> LLM_CALL:M"
    assert result["repetitions"] == 3
    assert result["window_size"] == 6
    m = 2
    assert len(result["evidence_event_ids"]) == m * 3
    assert result["evidence_event_ids"] == ["e1", "e2", "e3", "e4", "e5", "e6"]


def test_no_loop_when_not_repeated():
    """Tail does not form a repeated block → None."""
    events = [
        _event("e1", "TOOL_CALL", {"tool_name": "A"}),
        _event("e2", "LLM_CALL", {"model": "M"}),
        _event("e3", "TOOL_CALL", {"tool_name": "A"}),
        _event("e4", "LLM_CALL", {"model": "M"}),
        _event("e5", "TOOL_CALL", {"tool_name": "B"}),  # breaks A,M repeat
    ]
    result = detect_loop(events, window=12, repetitions=3)
    assert result is None


def test_smallest_m_chosen():
    """Signatures [A,B,A,B,A,B] with repetitions=3 → smallest m=2 (A,B), not m=6."""
    events = [
        _event("e1", "STATE_UPDATE"),  # different signature so we get A,B in window
        _event("e2", "STATE_UPDATE"),
        _event("e3", "TOOL_CALL", {"tool_name": "X"}),  # A
        _event("e4", "TOOL_CALL", {"tool_name": "Y"}),  # B
        _event("e5", "TOOL_CALL", {"tool_name": "X"}),  # A
        _event("e6", "TOOL_CALL", {"tool_name": "Y"}),  # B
        _event("e7", "TOOL_CALL", {"tool_name": "X"}),  # A
        _event("e8", "TOOL_CALL", {"tool_name": "Y"}),  # B
    ]
    # Signatures: STATE_UPDATE, STATE_UPDATE, TOOL_CALL:X, TOOL_CALL:Y (x3) = A,B repeated 3 times
    result = detect_loop(events, window=8, repetitions=3)
    assert result is not None
    assert result["pattern"] == "TOOL_CALL:X -> TOOL_CALL:Y"
    assert result["repetitions"] == 3
    assert len(result["evidence_event_ids"]) == 2 * 3  # m=2


def test_window_limits_detection():
    """Loop exists earlier in run; last `window` events do not contain it → None."""
    # 6 events: A,M,A,M,A,M (loop). Then 4 other events. window=4 → last 4 are not a loop.
    events = [
        _event("e1", "TOOL_CALL", {"tool_name": "A"}),
        _event("e2", "LLM_CALL", {"model": "M"}),
        _event("e3", "TOOL_CALL", {"tool_name": "A"}),
        _event("e4", "LLM_CALL", {"model": "M"}),
        _event("e5", "TOOL_CALL", {"tool_name": "A"}),
        _event("e6", "LLM_CALL", {"model": "M"}),
        _event("e7", "RUN_END"),
        _event("e8", "STATE_UPDATE"),
        _event("e9", "STATE_UPDATE"),
        _event("e10", "RUN_END"),
    ]
    result = detect_loop(events, window=4, repetitions=3)
    assert result is None
