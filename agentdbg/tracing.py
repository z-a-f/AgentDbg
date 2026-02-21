"""
Tracing context, @trace decorator, and manual recorders for AgentDbg.

Re-export shim: public API lives in agentdbg._tracing.
"""
from agentdbg._tracing import (
    record_llm_call,
    record_tool_call,
    record_state,
    trace,
    traced_run,
)

__all__ = [
    "trace",
    "traced_run",
    "record_llm_call",
    "record_tool_call",
    "record_state",
]
