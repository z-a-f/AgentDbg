"""
Loop detection for agent runs: signature computation and repeated-pattern detection.

Stdlib only. Pure functions, no I/O. Used to emit LOOP_WARNING when the last N
events contain a consecutively repeating signature subsequence.
"""
# Sentinel for evidence_event_ids when an event has no event_id (better UX than "")
MISSING_EVENT_ID = "__MISSING__"


def compute_signature(event: dict) -> str:
    """
    Produce a stable string signature for an event for loop detection.

    - LLM_CALL: "LLM_CALL:" + model (or "UNKNOWN" if missing)
    - TOOL_CALL: "TOOL_CALL:" + tool_name (or "UNKNOWN" if missing)
    - Else: event_type (or empty string)
    """
    t = event.get("event_type")
    if t == "LLM_CALL":
        model = event.get("payload", {}).get("model", "") or "UNKNOWN"
        return "LLM_CALL:" + str(model)
    if t == "TOOL_CALL":
        tool_name = event.get("payload", {}).get("tool_name", "") or "UNKNOWN"
        return "TOOL_CALL:" + str(tool_name)
    return str(t or "")


def detect_loop(
    events: list[dict],
    window: int,
    repetitions: int,
) -> dict | None:
    """
    Detect a consecutively repeating signature subsequence near the end of the run.

    Only considers the last `window` events. Finds the smallest pattern length m (>= 1)
    such that the last m*repetitions signatures form the same m-length block repeated
    `repetitions` times. Returns a LOOP_WARNING payload or None.
    """
    if not events or repetitions < 2 or window < 2:
        return None

    events_window = events[-window:] if len(events) >= window else events
    n = len(events_window)
    sigs = [compute_signature(e) for e in events_window]

    # m * repetitions must fit in the window
    max_m = n // repetitions
    if max_m < 1:
        return None

    for m in range(1, max_m + 1):
        L = m * repetitions
        if L > n:
            continue
        tail = sigs[-L:]
        block = tail[:m]
        # Check tail == block repeated 'repetitions' times
        if all(tail[i * m : (i + 1) * m] == block for i in range(repetitions)):
            evidence_events = events_window[-L:]
            evidence_event_ids = [
                e.get("event_id") or MISSING_EVENT_ID for e in evidence_events
            ]
            pattern = " -> ".join(block)
            return {
                "pattern": pattern,
                "repetitions": repetitions,
                "window_size": len(events_window),
                "evidence_event_ids": evidence_event_ids,
            }
    return None


def pattern_key(payload: dict) -> str:
    """
    Stable key for deduplication from LOOP_WARNING payload.

    Derived only from pattern and repetitions (no timestamps).
    """
    return f"{payload.get('pattern', '')}|{payload.get('repetitions', 0)}"
