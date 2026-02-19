"""
Event types and factory for AgentDebugger trace events.

All events are JSON-serializable dicts conforming to SPEC v0.1.
Pure functions, stdlib only, unit-testable.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SPEC_VERSION = "0.1"

# TODO: This is a serialization guardrail, not a security feature
# We should decide what to do:
# - Option A: keep it as is, but export as a constant
# - Option B: remove max depth here and enforce it in redaction
#             logic instead
_MAX_JSON_DEPTH = 10


class EventType(str, Enum):
    """Event type enum."""

    RUN_START = "RUN_START"
    RUN_END = "RUN_END"
    LLM_CALL = "LLM_CALL"
    TOOL_CALL = "TOOL_CALL"
    STATE_UPDATE = "STATE_UPDATE"
    ERROR = "ERROR"
    LOOP_WARNING = "LOOP_WARNING"


def utc_now_iso_ms_z() -> str:
    """Return current UTC time as ISO8601 with milliseconds and trailing Z."""
    now = datetime.now(timezone.utc)
    # Format: 2026-02-15T20:31:05.123Z
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _json_safe_value(value: Any, depth: int) -> Any:
    """Convert value to a JSON-serializable form; non-serializable types become str."""
    if depth > _MAX_JSON_DEPTH:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item, depth + 1) for item in value]
    return str(value)


def _ensure_json_safe(obj: Any) -> Any:
    """Ensure object is JSON-serializable; mutates only by building new structures."""
    return _json_safe_value(obj, 0)


def new_event(
    event_type: EventType | str,
    run_id: str,
    name: str,
    payload: Any,
    parent_id: str | None = None,
    duration_ms: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build an event dict with required fields.

    All events are JSON-serializable. payload and meta are normalized so that
    non-serializable values are converted to strings.

    Args:
        event_type: Event type (enum or string).
        run_id: Run UUID string.
        name: Label (e.g. tool name, model name).
        payload: Event payload; made JSON-safe if needed.
        parent_id: Optional parent event UUID.
        duration_ms: Optional duration in milliseconds.
        meta: Optional freeform meta dict; made JSON-safe if needed.

    Returns:
        Event dict with spec_version, event_id, run_id, parent_id, event_type,
        ts, duration_ms, name, payload, meta.
    """
    type_str = event_type.value if isinstance(event_type, EventType) else str(event_type)
    event_id = str(uuid.uuid4())
    ts = utc_now_iso_ms_z()
    # TODO: safe_payload defaults to {} if payload is None
    # However, for some event types it might be meaningful
    # to preserve `None`
    safe_payload = _ensure_json_safe(payload) if payload is not None else {}
    if not isinstance(safe_payload, dict):
        safe_payload = {"value": safe_payload}
    safe_meta = _ensure_json_safe(meta) if meta is not None else {}
    if not isinstance(safe_meta, dict):
        safe_meta = {"value": safe_meta}

    return {
        "spec_version": SPEC_VERSION,
        "event_id": event_id,
        "run_id": run_id,
        "parent_id": parent_id,
        "event_type": type_str,
        "ts": ts,
        "duration_ms": duration_ms,
        "name": str(name),
        "payload": safe_payload,
        "meta": safe_meta,
    }
