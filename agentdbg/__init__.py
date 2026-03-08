"""AgentDbg: local-first agent debugging (trace, record_llm_call, record_tool_call, record_state)."""

from agentdbg.exceptions import AgentDbgGuardrailExceeded, AgentDbgLoopAbort
from agentdbg.tracing import (
    record_llm_call,
    record_state,
    record_tool_call,
    trace,
    traced_run,
)
from agentdbg._version import version as __version__

__all__ = [
    "AgentDbgGuardrailExceeded",
    "AgentDbgLoopAbort",
    "trace",
    "traced_run",
    "record_llm_call",
    "record_tool_call",
    "record_state",
    "__version__",
]
