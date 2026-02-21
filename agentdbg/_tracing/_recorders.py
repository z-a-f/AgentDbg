"""
Recorders: record_llm_call, record_tool_call, record_state.
Depends: agentdbg.events, agentdbg.storage, agentdbg.loopdetect, _redact, _context.
"""
from typing import Any

from agentdbg.config import AgentDbgConfig
from agentdbg.events import EventType, new_event
from agentdbg.loopdetect import detect_loop, pattern_key as loop_pattern_key
from agentdbg.storage import append_event

from agentdbg._tracing._context import _ensure_run
from agentdbg._tracing._redact import (
    _apply_redaction_truncation,
    _build_error_payload,
    _normalize_usage,
)


def _maybe_emit_loop_warning(
    run_id: str,
    counts: dict[str, int],
    config: AgentDbgConfig,
    window: list[dict],
    emitted: set[str],
) -> None:
    """
    If the last N events contain a repeating pattern not yet emitted, emit LOOP_WARNING,
    increment counts["loop_warnings"], and add the pattern key to emitted.
    """
    payload = detect_loop(window, config.loop_window, config.loop_repetitions)
    if payload is None:
        return
    key = loop_pattern_key(payload)
    if key in emitted:
        return
    pattern = payload.get("pattern", "loop_warning")
    max_name_len = 80
    name = pattern if len(pattern) <= max_name_len else pattern[: max_name_len - 1] + "..."
    ev = new_event(EventType.LOOP_WARNING, run_id, name, payload)
    append_event(run_id, ev, config)
    counts["loop_warnings"] = counts.get("loop_warnings", 0) + 1
    emitted.add(key)


def record_llm_call(
    model: str,
    prompt: Any = None,
    response: Any = None,
    usage: Any = None,
    meta: dict[str, Any] | None = None,
    provider: str = "unknown",
    temperature: Any = None,
    stop_reason: str | None = None,
    status: str = "ok",
    error: str | BaseException | dict[str, Any] | None = None,
) -> None:
    """
    Record an LLM call event. No-op if no active run (unless AGENTDBG_IMPLICIT_RUN=1).
    Applies redaction and truncation from config, appends event, increments llm_calls.
    When status is "error", error may be an exception, string, or dict (type, message, details?, stack?).
    """
    ctx = _ensure_run()
    if ctx is None:
        return
    run_id, counts, config, window, emitted = ctx
    status_val = "ok" if status not in ("ok", "error") else status
    error_obj: dict[str, Any] | None = None
    if status_val == "error" and error is not None:
        error_obj = _build_error_payload(error, config, include_stack=True)
    payload = {
        "model": model,
        "prompt": prompt,
        "response": response,
        "usage": _normalize_usage(usage),
        "provider": provider,
        "temperature": temperature,
        "stop_reason": stop_reason,
        "status": status_val,
        "error": error_obj,
    }
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.LLM_CALL, run_id, model, payload, meta=safe_meta)
    append_event(run_id, ev, config)
    counts["llm_calls"] = counts.get("llm_calls", 0) + 1
    window.append(ev)
    if len(window) > config.loop_window:
        window[:] = window[-config.loop_window:]
    _maybe_emit_loop_warning(run_id, counts, config, window, emitted)


def record_tool_call(
    name: str,
    args: Any = None,
    result: Any = None,
    meta: dict[str, Any] | None = None,
    status: str = "ok",
    error: str | BaseException | dict[str, Any] | None = None,
) -> None:
    """
    Record a tool call event. No-op if no active run (unless AGENTDBG_IMPLICIT_RUN=1).
    Applies redaction and truncation, appends event, increments tool_calls.
    When status is "error", error may be an exception, string, or dict (type, message, details?, stack?).
    """
    ctx = _ensure_run()
    if ctx is None:
        return
    run_id, counts, config, window, emitted = ctx
    status_val = "ok" if status not in ("ok", "error") else status
    error_obj: dict[str, Any] | None = None
    if status_val == "error" and error is not None:
        error_obj = _build_error_payload(error, config, include_stack=True)
    payload = {
        "tool_name": name,
        "args": args,
        "result": result,
        "status": status_val,
        "error": error_obj,
    }
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.TOOL_CALL, run_id, name, payload, meta=safe_meta)
    append_event(run_id, ev, config)
    counts["tool_calls"] = counts.get("tool_calls", 0) + 1
    window.append(ev)
    if len(window) > config.loop_window:
        window[:] = window[-config.loop_window:]
    _maybe_emit_loop_warning(run_id, counts, config, window, emitted)


def record_state(
    state: Any = None,
    meta: dict[str, Any] | None = None,
    diff: Any = None,
) -> None:
    """
    Record a state update event. No-op if no active run (unless AGENTDBG_IMPLICIT_RUN=1).
    Applies redaction and truncation; does not increment any count.
    """
    ctx = _ensure_run()
    if ctx is None:
        return
    run_id, counts, config, window, emitted = ctx
    payload = {"state": state, "diff": diff}
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.STATE_UPDATE, run_id, "state", payload, meta=safe_meta)
    append_event(run_id, ev, config)
    window.append(ev)
    if len(window) > config.loop_window:
        window[:] = window[-config.loop_window:]
    _maybe_emit_loop_warning(run_id, counts, config, window, emitted)
