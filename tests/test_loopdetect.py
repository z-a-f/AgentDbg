"""
Loop detection tests: synthetic events with repeated tail pattern, detect_loop payload shape and stability.
No I/O; uses in-memory events. pattern_key stability and calling detect_loop again yields same payload.
"""
import pytest

from agentdbg.loopdetect import detect_loop, pattern_key


def _make_event(event_id: str, event_type: str, payload: dict) -> dict:
    """Minimal event dict for loop detection (signature comes from event_type + payload)."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "payload": payload,
    }


def test_detect_loop_repeated_tail_payload_shape_and_evidence_count():
    """Synthetic events with repeated tail; payload has pattern, repetitions, window_size, evidence_event_ids."""
    # Pattern [TOOL_CALL:foo, LLM_CALL:gpt] repeated 3 times -> 6 events in tail
    ids = [f"id-{i}" for i in range(6)]
    events = [
        _make_event(ids[0], "TOOL_CALL", {"tool_name": "foo"}),
        _make_event(ids[1], "LLM_CALL", {"model": "gpt"}),
        _make_event(ids[2], "TOOL_CALL", {"tool_name": "foo"}),
        _make_event(ids[3], "LLM_CALL", {"model": "gpt"}),
        _make_event(ids[4], "TOOL_CALL", {"tool_name": "foo"}),
        _make_event(ids[5], "LLM_CALL", {"model": "gpt"}),
    ]
    window = 10
    repetitions = 3
    payload = detect_loop(events, window=window, repetitions=repetitions)
    assert payload is not None
    assert "pattern" in payload
    assert "repetitions" in payload
    assert "window_size" in payload
    assert "evidence_event_ids" in payload

    pattern_len = 2  # TOOL_CALL:foo, LLM_CALL:gpt
    assert len(payload["evidence_event_ids"]) == pattern_len * repetitions

    assert payload["pattern"] == "TOOL_CALL:foo -> LLM_CALL:gpt"
    assert pattern_key(payload) == "TOOL_CALL:foo -> LLM_CALL:gpt|3"


def test_detect_loop_called_again_yields_same_payload():
    """Calling detect_loop again yields same payload (no dedupe inside detect_loop)."""
    events = []
    for i in range(6):
        events.append(
            _make_event(
                f"e-{i}",
                "TOOL_CALL" if i % 2 == 0 else "LLM_CALL",
                {"tool_name": "x"} if i % 2 == 0 else {"model": "y"},
            )
        )
    payload1 = detect_loop(events, window=10, repetitions=3)
    payload2 = detect_loop(events, window=10, repetitions=3)
    assert payload1 is not None
    assert payload2 is not None
    assert payload1["pattern"] == payload2["pattern"]
    assert payload1["evidence_event_ids"] == payload2["evidence_event_ids"]
    assert pattern_key(payload1) == pattern_key(payload2)


def test_detect_loop_smallest_m_chosen():
    """When multiple pattern lengths could match, the smallest m is chosen."""
    # 12 events: (TOOL_CALL:foo, LLM_CALL:gpt) x 6. Both m=2 (block x3) and m=4 (block x3) could match.
    # Algorithm iterates m from 2; it should return m=2, so pattern "TOOL_CALL:foo -> LLM_CALL:gpt".
    events = []
    for i in range(12):
        events.append(
            _make_event(
                f"id-{i}",
                "TOOL_CALL" if i % 2 == 0 else "LLM_CALL",
                {"tool_name": "foo"} if i % 2 == 0 else {"model": "gpt"},
            )
        )
    payload = detect_loop(events, window=12, repetitions=3)
    assert payload is not None
    assert payload["pattern"] == "TOOL_CALL:foo -> LLM_CALL:gpt"
    assert len(payload["evidence_event_ids"]) == 2 * 3  # m=2, not 4*3


def test_detect_loop_no_loop_returns_none():
    """When the tail does not contain a consecutively repeating pattern, returns None."""
    # All different signatures: no repeated block.
    events = [
        _make_event("a", "TOOL_CALL", {"tool_name": "one"}),
        _make_event("b", "TOOL_CALL", {"tool_name": "two"}),
        _make_event("c", "TOOL_CALL", {"tool_name": "three"}),
        _make_event("d", "LLM_CALL", {"model": "m1"}),
        _make_event("e", "LLM_CALL", {"model": "m2"}),
    ]
    assert detect_loop(events, window=10, repetitions=3) is None
