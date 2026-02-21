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
from agentdbg._tracing._lifecycle import trace, traced_run
from agentdbg._tracing._recorders import record_llm_call, record_tool_call, record_state

__all__ = [
    "trace",
    "traced_run",
    "record_llm_call",
    "record_tool_call",
    "record_state",
]
