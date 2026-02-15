"""
Tracing context, @trace decorator, and manual recorders for AgentDbg.

Uses contextvars for run_id, counts, and config. Recorders no-op when no active run,
or create an implicit run when AGENTDBG_IMPLICIT_RUN=1.
Dependencies: stdlib + agentdbg.config + agentdbg.events + agentdbg.storage.
"""
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

from agentdbg.config import AgentDbgConfig, load_config
from agentdbg.events import EventType, new_event, utc_now_iso_ms_z
from agentdbg.storage import append_event, create_run, finalize_run

_RECURSION_LIMIT = 10

_run_id_var: ContextVar[str | None] = ContextVar("agentdbg_run_id", default=None)
_counts_var: ContextVar[dict | None] = ContextVar("agentdbg_counts", default=None)
_config_var: ContextVar[AgentDbgConfig | None] = ContextVar("agentdbg_config", default=None)


def _default_counts() -> dict[str, int]:
    """Default counts dict; keys match SPEC run.json and RUN_END summary."""
    # TODO: when loop detection is implemented, increment counts["loop_warnings"] when emitting LOOP_WARNING
    return {
        "llm_calls": 0,
        "tool_calls": 0,
        "errors": 0,
        "loop_warnings": 0,
    }


def _key_matches_redact(key: str, redact_keys: list[str]) -> bool:
    """True if key matches any redact key (case-insensitive substring)."""
    k = key.lower()
    return any(rk.lower() in k for rk in redact_keys)


_TRUNCATED_MARKER = "__TRUNCATED__"


def _truncate_string(s: str, max_bytes: int) -> str:
    """Truncate string so result (including __TRUNCATED__ marker) fits in max_bytes. max_bytes <= 0 means no truncation."""
    if max_bytes <= 0:
        return s
    enc = "utf-8"
    marker_bytes = len(_TRUNCATED_MARKER.encode(enc))
    if len(s.encode(enc)) <= max_bytes:
        return s
    limit = max(0, max_bytes - marker_bytes)
    b = s.encode(enc)
    while len(b) > limit and len(s) > 0:
        s = s[: len(s) - 1]
        b = s.encode(enc)
    return (s or "") + _TRUNCATED_MARKER


def _redact_and_truncate(
    obj: Any,
    config: AgentDbgConfig,
    depth: int = 0,
) -> Any:
    """
    Recursively redact keys matching config.redact_keys and truncate large strings.
    Limit recursion to _RECURSION_LIMIT. Returns a new structure; does not mutate input.
    """
    if depth > _RECURSION_LIMIT:
        return "__TRUNCATED__"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _truncate_string(obj, config.max_field_bytes)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key_str = str(k)
            if config.redact and _key_matches_redact(key_str, config.redact_keys):
                out[key_str] = "__REDACTED__"
            else:
                out[key_str] = _redact_and_truncate(v, config, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact_and_truncate(item, config, depth + 1) for item in obj]
    s = str(obj)
    return _truncate_string(s, config.max_field_bytes) if len(s.encode("utf-8")) > config.max_field_bytes else s


def _normalize_usage(usage: Any) -> dict[str, int | None] | None:
    """Normalize LLM usage to SPEC shape: prompt_tokens, completion_tokens, total_tokens (null if unknown)."""
    if usage is None:
        return None
    if not isinstance(usage, dict):
        return None

    def _token_val(key: str) -> int | None:
        v = usage.get(key)
        return v if isinstance(v, (int, type(None))) else None

    return {
        "prompt_tokens": _token_val("prompt_tokens"),
        "completion_tokens": _token_val("completion_tokens"),
        "total_tokens": _token_val("total_tokens"),
    }


def _apply_redaction_truncation(payload: Any, meta: Any, config: AgentDbgConfig) -> tuple[Any, Any]:
    """Apply redaction and truncation to payload and meta; returns (payload, meta)."""
    return (
        _redact_and_truncate(payload, config),
        _redact_and_truncate(meta, config) if meta is not None else {},
    )


def _ensure_run() -> tuple[str, dict, AgentDbgConfig] | None:
    """
    Return (run_id, counts, config) for the current run, or None if no run.
    If AGENTDBG_IMPLICIT_RUN=1 and no run is active, create an implicit run and return it.
    """
    run_id = _run_id_var.get()
    if run_id is not None:
        counts = _counts_var.get()
        config = _config_var.get()
        if counts is not None and config is not None:
            return (run_id, counts, config)
    if os.environ.get("AGENTDBG_IMPLICIT_RUN", "").strip() == "1":
        config = load_config()
        meta = create_run("implicit", config)
        run_id = meta["run_id"]
        counts = _default_counts()
        _run_id_var.set(run_id)
        _counts_var.set(counts)
        _config_var.set(config)
        payload = {
            "run_name": "implicit",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "cwd": os.getcwd(),
            "argv": list(sys.argv),
        }
        ev = new_event(EventType.RUN_START, run_id, "implicit", payload)
        append_event(run_id, ev, config)
        return (run_id, counts, config)
    return None


def _run_start_payload(run_name: str | None) -> dict[str, Any]:
    """Build RUN_START payload per SPEC §5.3."""
    return {
        "run_name": run_name,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "argv": list(sys.argv),
    }


def _run_end_payload(status: str, counts: dict, started_at: str) -> dict[str, Any]:
    """Build RUN_END payload per SPEC §5.3; duration_ms from started_at to now."""
    now = utc_now_iso_ms_z()
    try:
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        duration_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
    except (ValueError, TypeError):
        duration_ms = 0
    return {
        "status": status,
        "summary": {
            "llm_calls": counts.get("llm_calls", 0),
            "tool_calls": counts.get("tool_calls", 0),
            "errors": counts.get("errors", 0),
            "duration_ms": duration_ms,
        },
    }


def _error_payload(exc: BaseException) -> dict[str, Any]:
    """Build ERROR payload per SPEC §5.3."""
    return {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "stack": traceback.format_exc(),
    }


F = TypeVar("F", bound=Callable[..., Any])


def trace(f: F) -> F:
    """
    Decorator that starts a new run (RUN_START / RUN_END, ERROR on exception)
    when no run is active; otherwise runs the function in the existing run without
    creating a new run or emitting extra run events.
    """

    @wraps(f)
    def inner(*args: Any, **kwargs: Any) -> Any:
        existing_run_id = _run_id_var.get()
        if existing_run_id is not None:
            return f(*args, **kwargs)

        config = load_config()
        run_name = getattr(f, "__name__", None) or None
        meta = create_run(run_name, config)
        run_id = meta["run_id"]
        started_at = meta["started_at"]
        counts = _default_counts()

        token_run = _run_id_var.set(run_id)
        token_counts = _counts_var.set(counts)
        token_config = _config_var.set(config)
        try:
            payload = _run_start_payload(run_name)
            ev = new_event(EventType.RUN_START, run_id, run_name or "run", payload)
            append_event(run_id, ev, config)

            result = f(*args, **kwargs)

            payload_end = _run_end_payload("ok", counts, started_at)
            ev_end = new_event(EventType.RUN_END, run_id, "run_end", payload_end)
            append_event(run_id, ev_end, config)
            finalize_run(run_id, "ok", counts, config)
            return result
        except BaseException as e:
            err_payload = _error_payload(e)
            err_ev = new_event(EventType.ERROR, run_id, type(e).__name__, err_payload)
            append_event(run_id, err_ev, config)
            counts["errors"] = counts.get("errors", 0) + 1

            payload_end = _run_end_payload("error", counts, started_at)
            ev_end = new_event(EventType.RUN_END, run_id, "run_end", payload_end)
            append_event(run_id, ev_end, config)
            finalize_run(run_id, "error", counts, config)
            raise
        finally:
            _run_id_var.reset(token_run)
            _counts_var.reset(token_counts)
            _config_var.reset(token_config)

    return inner  # type: ignore[return-value]


def record_llm_call(
    model: str,
    prompt: Any = None,
    response: Any = None,
    usage: Any = None,
    meta: dict[str, Any] | None = None,
    provider: str = "unknown",
    temperature: Any = None,
    stop_reason: str | None = None,
) -> None:
    """
    Record an LLM call event. No-op if no active run (unless AGENTDBG_IMPLICIT_RUN=1).
    Applies redaction and truncation from config, appends event, increments llm_calls.
    """
    ctx = _ensure_run()
    if ctx is None:
        return
    run_id, counts, config = ctx
    payload = {
        "model": model,
        "prompt": prompt,
        "response": response,
        "usage": _normalize_usage(usage),
        "provider": provider,
        "temperature": temperature,
        "stop_reason": stop_reason,
    }
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.LLM_CALL, run_id, model, payload, meta=safe_meta)
    append_event(run_id, ev, config)
    counts["llm_calls"] = counts.get("llm_calls", 0) + 1


def record_tool_call(
    name: str,
    args: Any = None,
    result: Any = None,
    meta: dict[str, Any] | None = None,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """
    Record a tool call event. No-op if no active run (unless AGENTDBG_IMPLICIT_RUN=1).
    Applies redaction and truncation, appends event, increments tool_calls.
    """
    ctx = _ensure_run()
    if ctx is None:
        return
    run_id, counts, config = ctx
    payload = {
        "tool_name": name,
        "args": args,
        "result": result,
        "status": status,
        "error": error,
    }
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.TOOL_CALL, run_id, name, payload, meta=safe_meta)
    append_event(run_id, ev, config)
    counts["tool_calls"] = counts.get("tool_calls", 0) + 1


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
    run_id, counts, config = ctx
    payload = {"state": state, "diff": diff}
    payload, safe_meta = _apply_redaction_truncation(payload, meta or {}, config)
    ev = new_event(EventType.STATE_UPDATE, run_id, "state", payload, meta=safe_meta)
    append_event(run_id, ev, config)
