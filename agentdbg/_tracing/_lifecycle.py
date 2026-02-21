"""
Run lifecycle: _run_context context manager, trace decorator, traced_run.
Depends: agentdbg.config, agentdbg.events, agentdbg.storage, _redact, _context.
"""
import sys
import traceback
from types import TracebackType
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Generator, ParamSpec, TypeVar

from agentdbg.config import load_config
from agentdbg.constants import default_counts
from agentdbg.events import EventType, new_event
from agentdbg.storage import append_event, create_run, finalize_run

from agentdbg._tracing._context import (
    _config_var,
    _counts_var,
    _event_window_var,
    _loop_emitted_var,
    _resolve_run_name,
    _run_end_payload,
    _run_id_var,
    _run_start_payload_for_event,
)
from agentdbg._tracing._redact import _redact_and_truncate
from agentdbg._integration_utils import _invoke_run_enter, _invoke_run_exit


P = ParamSpec("P")
R = TypeVar("R")


def _error_payload(exc: BaseException) -> dict[str, Any]:
    """Build ERROR payload."""
    return {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "stack": traceback.format_exc(),
    }


@contextmanager
def _run_context(
    name: str | None = None,
    func: Callable[..., Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager that factors the common run lifecycle.
    If a run is already active, yields without creating a new run.
    Otherwise: load config, create run, set context vars, emit RUN_START,
    then on success emit RUN_END "ok" and finalize; on exception emit ERROR,
    RUN_END "error", finalize, and reraise. Reset context vars in finally.
    """
    existing_run_id = _run_id_var.get()
    if existing_run_id is not None:
        yield
        return

    config = load_config()
    run_name = _resolve_run_name(name, func)
    meta = create_run(run_name, config)
    run_id = meta["run_id"]
    started_at = meta["started_at"]
    counts = default_counts()

    token_run = _run_id_var.set(run_id)
    token_counts = _counts_var.set(counts)
    token_config = _config_var.set(config)
    token_window = _event_window_var.set([])
    token_emitted = _loop_emitted_var.set(set())
    exc_info: tuple[type[BaseException] | None, BaseException | None, TracebackType | None] = (
        None,
        None,
        None,
    )

    def _finish_run(status: str) -> None:
        _invoke_run_exit(*exc_info)
        payload_end = _run_end_payload(status, counts, started_at)
        ev_end = new_event(EventType.RUN_END, run_id, "run_end", payload_end)
        append_event(run_id, ev_end, config)
        finalize_run(run_id, status, counts, config)

    try:
        payload = _run_start_payload_for_event(run_name, config)
        ev = new_event(EventType.RUN_START, run_id, run_name, payload)
        append_event(run_id, ev, config)
        _invoke_run_enter()
        yield
    except Exception as e:
        exc_info = sys.exc_info()
        err_payload = _redact_and_truncate(_error_payload(e), config)
        err_ev = new_event(EventType.ERROR, run_id, type(e).__name__, err_payload)
        append_event(run_id, err_ev, config)
        counts["errors"] = counts.get("errors", 0) + 1
        _finish_run("error")
        raise
    else:
        _finish_run("ok")
    finally:
        _run_id_var.reset(token_run)
        _counts_var.reset(token_counts)
        _config_var.reset(token_config)
        _event_window_var.reset(token_window)
        _loop_emitted_var.reset(token_emitted)


def trace(
    f: Callable[P, R] | str | None = None,
    *,
    name: str | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator that starts a new run (RUN_START / RUN_END, ERROR on exception)
    when no run is active; otherwise runs the function in the existing run without
    creating a new run or emitting extra run events.

    Usage: @trace, @trace(), @trace("run name"), @trace(name="run name").
    Run name precedence: AGENTDBG_RUN_NAME env, then explicit name, then default (entrypoint - timestamp).
    """

    def decorator(func: Callable[P, R], explicit: str | None = None) -> Callable[P, R]:
        _name = explicit if explicit is not None else name

        @wraps(func)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            with _run_context(name=_name, func=func):
                return func(*args, **kwargs)

        return inner

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
    with _run_context(name=name, func=None):
        yield
