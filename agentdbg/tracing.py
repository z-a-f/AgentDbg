"""
Tracing context, @trace decorator, and manual recorders for AgentDbg.

Uses contextvars for run_id, counts, and config. Recorders no-op when no active run,
or create an implicit run when AGENTDBG_IMPLICIT_RUN=1.
Dependencies: stdlib + agentdbg.config + agentdbg.constants + agentdbg.events + agentdbg.storage.

TODO(concurrency): Safe for single-threaded agent loops. If tools run concurrently
(e.g. thread pool), context does not propagate to worker threads and the event window
ordering can be non-deterministic. For v0.2+: propagate context into workers
(contextvars.copy_context().run(...)) and use a thread-safe window (e.g. lock around
appends) with a well-defined ordering rule so loop detection remains meaningful.
"""
import atexit
import os
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Generator, TypeVar

from agentdbg.config import AgentDbgConfig, load_config
from agentdbg.constants import REDACTED_MARKER, TRUNCATED_MARKER
from agentdbg.events import EventType, new_event, utc_now_iso_ms_z
from agentdbg.loopdetect import detect_loop, pattern_key as loop_pattern_key
from agentdbg.storage import append_event, create_run, finalize_run

_RECURSION_LIMIT = 10

_run_id_var: ContextVar[str | None] = ContextVar("agentdbg_run_id", default=None)
_counts_var: ContextVar[dict | None] = ContextVar("agentdbg_counts", default=None)
_config_var: ContextVar[AgentDbgConfig | None] = ContextVar("agentdbg_config", default=None)
_event_window_var: ContextVar[list[dict] | None] = ContextVar("agentdbg_event_window", default=None)
_loop_emitted_var: ContextVar[set[str] | None] = ContextVar("agentdbg_loop_emitted", default=None)

# Implicit run: stored so atexit can finalize (RUN_END + run.json status).
_implicit_run_id: str | None = None
_implicit_counts: dict | None = None
_implicit_config: AgentDbgConfig | None = None
_implicit_started_at: str | None = None
_implicit_event_window: list[dict] = []
_implicit_loop_emitted: set[str] = set()


def _entrypoint(func: Callable[..., Any]) -> str:
    """Human-friendly entrypoint string: path/to/file.py:function_name (relative to cwd when possible)."""
    try:
        code = getattr(func, "__code__", None)
        filename = code.co_filename if code else None
        if filename:
            try:
                rel = os.path.relpath(filename, os.getcwd())
            except (ValueError, OSError):
                rel = filename
            return f"{rel}:{func.__name__}"
    except Exception:
        pass
    return getattr(func, "__name__", None) or "run"


def _default_run_name_timestamp() -> str:
    """Local timestamp for default run names, e.g. 2025-02-18 14:12."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _resolve_run_name(
    explicit_name: str | None,
    func: Callable[..., Any] | None,
) -> str:
    """
    Resolve run name by precedence: AGENTDBG_RUN_NAME env, explicit name, default (entrypoint + timestamp).
    """
    env_name = os.environ.get("AGENTDBG_RUN_NAME", "").strip()
    if env_name:
        return env_name
    if explicit_name:
        return explicit_name
    if func is not None:
        return f"{_entrypoint(func)} - {_default_run_name_timestamp()}"
    return f"run - {_default_run_name_timestamp()}"


def _default_counts() -> dict[str, int]:
    """Default counts dict; keys match SPEC run.json and RUN_END summary."""
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


def _truncate_string(s: str, max_bytes: int) -> str:
    """Truncate string so result (including TRUNCATED_MARKER) fits in max_bytes. O(n), single encode/decode."""
    if max_bytes <= 0:
        return s
    enc = "utf-8"
    b = s.encode(enc)
    if len(b) <= max_bytes:
        return s
    marker_bytes = len(TRUNCATED_MARKER.encode(enc))
    limit = max(0, max_bytes - marker_bytes)
    b_trunc = b[:limit]
    return b_trunc.decode(enc, errors="ignore") + TRUNCATED_MARKER


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
        return TRUNCATED_MARKER
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _truncate_string(obj, config.max_field_bytes)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key_str = str(k)
            if config.redact and _key_matches_redact(key_str, config.redact_keys):
                out[key_str] = REDACTED_MARKER
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


def _build_error_payload(
    exc_or_message: BaseException | str | dict[str, Any] | None,
    config: AgentDbgConfig,
    include_stack: bool = True,
) -> dict[str, Any] | None:
    """
    Build a consistent error object for TOOL_CALL/LLM_CALL payloads.
    Returns None if exc_or_message is None; otherwise dict with type, message, optional details, optional stack.
    Result is redacted/truncated per config.
    """
    if exc_or_message is None:
        return None
    if isinstance(exc_or_message, BaseException):
        err = {
            "type": type(exc_or_message).__name__,
            "message": str(exc_or_message),
            "details": None,
            "stack": traceback.format_exc() if include_stack else None,
        }
    elif isinstance(exc_or_message, str):
        err = {
            "type": "Error",
            "message": exc_or_message,
            "details": None,
            "stack": None,
        }
    elif isinstance(exc_or_message, dict):
        err = {
            "type": exc_or_message.get("type", "Error"),
            "message": exc_or_message.get("message", ""),
            "details": exc_or_message.get("details"),
            "stack": exc_or_message.get("stack") if include_stack else None,
        }
    else:
        err = {"type": "Error", "message": str(exc_or_message), "details": None, "stack": None}
    return _redact_and_truncate(err, config)


def _finalize_implicit_run() -> None:
    """Atexit hook: write RUN_END and finalize run.json for the implicit run, if any."""
    global _implicit_run_id, _implicit_counts, _implicit_config, _implicit_started_at
    global _implicit_event_window, _implicit_loop_emitted
    if _implicit_run_id is None or _implicit_config is None or _implicit_started_at is None:
        return
    run_id = _implicit_run_id
    counts = _implicit_counts or _default_counts()
    config = _implicit_config
    started_at = _implicit_started_at
    _implicit_run_id = None
    _implicit_counts = None
    _implicit_config = None
    _implicit_started_at = None
    _implicit_event_window = []
    _implicit_loop_emitted = set()
    try:
        payload = _run_end_payload("ok", counts, started_at)
        ev = new_event(EventType.RUN_END, run_id, "run_end", payload)
        append_event(run_id, ev, config)
        finalize_run(run_id, "ok", counts, config)
    except Exception:
        pass


atexit.register(_finalize_implicit_run)


def _ensure_run() -> tuple[str, dict, AgentDbgConfig, list[dict], set[str]] | None:
    """
    Return (run_id, counts, config, event_window, loop_emitted) for the current run, or None if no run.
    If AGENTDBG_IMPLICIT_RUN=1 and no run is active, create an implicit run (once per process)
    and return it. Implicit run never sets contextvars, so it does not hijack subsequent
    traced runs or leave a "current run" for the rest of the process.
    """
    global _implicit_run_id, _implicit_counts, _implicit_config, _implicit_started_at
    global _implicit_event_window, _implicit_loop_emitted
    run_id = _run_id_var.get()
    if run_id is not None:
        counts = _counts_var.get()
        config = _config_var.get()
        if counts is not None and config is not None:
            window = _event_window_var.get()
            emitted = _loop_emitted_var.get()
            return (run_id, counts, config, window if window is not None else [], emitted if emitted is not None else set())
    if os.environ.get("AGENTDBG_IMPLICIT_RUN", "").strip() == "1":
        if _implicit_run_id is not None and _implicit_counts is not None and _implicit_config is not None:
            return (_implicit_run_id, _implicit_counts, _implicit_config, _implicit_event_window, _implicit_loop_emitted)
        config = load_config()
        run_name = _resolve_run_name("implicit", None)
        meta = create_run(run_name, config)
        run_id = meta["run_id"]
        counts = _default_counts()
        started_at = meta["started_at"]
        _implicit_run_id = run_id
        _implicit_counts = counts
        _implicit_config = config
        _implicit_started_at = started_at
        _implicit_event_window = []
        _implicit_loop_emitted = set()
        payload = {
            "run_name": run_name,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "cwd": os.getcwd(),
            "argv": list(sys.argv),
        }
        ev = new_event(EventType.RUN_START, run_id, run_name, payload)
        append_event(run_id, ev, config)
        return (run_id, counts, config, _implicit_event_window, _implicit_loop_emitted)
    return None


def _run_start_payload(run_name: str | None) -> dict[str, Any]:
    """Build RUN_START payload."""
    return {
        "run_name": run_name,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "argv": list(sys.argv),
    }


def _run_end_payload(status: str, counts: dict, started_at: str) -> dict[str, Any]:
    """Build RUN_END payload; duration_ms from started_at to now."""
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
    """Build ERROR payload."""
    return {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "stack": traceback.format_exc(),
    }


F = TypeVar("F", bound=Callable[..., Any])


def trace(
    f: F | str | None = None,
    *,
    name: str | None = None,
) -> F | Callable[[F], F]:
    """
    Decorator that starts a new run (RUN_START / RUN_END, ERROR on exception)
    when no run is active; otherwise runs the function in the existing run without
    creating a new run or emitting extra run events.

    Usage: @trace, @trace(), @trace("run name"), @trace(name="run name").
    Run name precedence: AGENTDBG_RUN_NAME env, then explicit name, then default (entrypoint - timestamp).
    """

    def decorator(func: F, explicit: str | None = None) -> F:
        _name = explicit if explicit is not None else name

        @wraps(func)
        def inner(*args: Any, **kwargs: Any) -> Any:
            existing_run_id = _run_id_var.get()
            if existing_run_id is not None:
                return func(*args, **kwargs)

            config = load_config()
            run_name = _resolve_run_name(_name, func)
            meta = create_run(run_name, config)
            run_id = meta["run_id"]
            started_at = meta["started_at"]
            counts = _default_counts()

            token_run = _run_id_var.set(run_id)
            token_counts = _counts_var.set(counts)
            token_config = _config_var.set(config)
            token_window = _event_window_var.set([])
            token_emitted = _loop_emitted_var.set(set())
            try:
                payload = _run_start_payload(run_name)
                ev = new_event(EventType.RUN_START, run_id, run_name, payload)
                append_event(run_id, ev, config)

                result = func(*args, **kwargs)

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
                _event_window_var.reset(token_window)
                _loop_emitted_var.reset(token_emitted)

        return inner  # type: ignore[return-value]

    if f is not None and not callable(f):
        # @trace("name") -> f is the name string
        return lambda func: decorator(func, explicit=str(f))  # type: ignore[return-value]
    if f is None:
        return decorator  # type: ignore[return-value]
    return decorator(f)  # type: ignore[return-value]


@contextmanager
def traced_run(name: str | None = None) -> Generator[None, None, None]:
    """
    Context manager that starts a new run (RUN_START / RUN_END, ERROR on exception)
    when no run is active; otherwise runs the block in the existing run without
    creating a new run. Run name precedence: AGENTDBG_RUN_NAME env, then name, then default.
    """
    existing_run_id = _run_id_var.get()
    if existing_run_id is not None:
        yield
        return

    config = load_config()
    run_name = _resolve_run_name(name, None)
    meta = create_run(run_name, config)
    run_id = meta["run_id"]
    started_at = meta["started_at"]
    counts = _default_counts()

    token_run = _run_id_var.set(run_id)
    token_counts = _counts_var.set(counts)
    token_config = _config_var.set(config)
    token_window = _event_window_var.set([])
    token_emitted = _loop_emitted_var.set(set())
    try:
        payload = _run_start_payload(run_name)
        ev = new_event(EventType.RUN_START, run_id, run_name, payload)
        append_event(run_id, ev, config)

        yield
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
    else:
        payload_end = _run_end_payload("ok", counts, started_at)
        ev_end = new_event(EventType.RUN_END, run_id, "run_end", payload_end)
        append_event(run_id, ev_end, config)
        finalize_run(run_id, "ok", counts, config)
    finally:
        _run_id_var.reset(token_run)
        _counts_var.reset(token_counts)
        _config_var.reset(token_config)
        _event_window_var.reset(token_window)
        _loop_emitted_var.reset(token_emitted)


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
