"""
Internal integration run lifecycle registry.

Integrations register run_enter and run_exit callbacks; the outermost run boundary
invokes them at RUN_START and in the finally block (with exception info).
No plugin discovery or auto-loading; registration is explicit on integration import.
"""
from types import TracebackType
from typing import Callable

# Callbacks: run_enter() takes no args; run_exit(exc_type, exc_value, traceback).
_run_enter_callbacks: list[Callable[[], None]] = []
_run_exit_callbacks: list[
    Callable[
        [
            type[BaseException] | None,
            BaseException | None,
            TracebackType | None,
        ],
        None,
    ]
] = []


def register_run_enter(fn: Callable[[], None]) -> None:
    """Register a callback to run at outermost run start. Idempotent (same fn not added twice)."""
    if fn not in _run_enter_callbacks:
        _run_enter_callbacks.append(fn)


def register_run_exit(
    fn: Callable[
        [
            type[BaseException] | None,
            BaseException | None,
            TracebackType | None,
        ],
        None,
    ],
) -> None:
    """Register a callback to run at outermost run exit (finally). Receives exc_type, exc_value, traceback. Idempotent."""
    if fn not in _run_exit_callbacks:
        _run_exit_callbacks.append(fn)


def _invoke_run_enter() -> None:
    """Invoke all registered run_enter callbacks. One failure does not stop others."""
    for cb in _run_enter_callbacks:
        try:
            cb()
        except Exception:
            pass


def _invoke_run_exit(
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: TracebackType | None,
) -> None:
    """Invoke all registered run_exit callbacks with exception info. One failure does not stop others."""
    for cb in _run_exit_callbacks:
        try:
            cb(exc_type, exc_value, traceback)
        except Exception:
            pass


def _clear_test_run_lifecycle_registry() -> None:
    """Clear all registered callbacks. For tests only."""
    _run_enter_callbacks.clear()
    _run_exit_callbacks.clear()
