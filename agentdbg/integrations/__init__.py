"""
Optional framework integrations. No heavy imports at package load.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentdbg.integrations.langchain import AgentDbgLangChainCallbackHandler


def __getattr__(name: str):
    """Lazy load LangChain handler so langchain is not required at import time."""
    if name == "AgentDbgLangChainCallbackHandler":
        from agentdbg.integrations.langchain import AgentDbgLangChainCallbackHandler
        return AgentDbgLangChainCallbackHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
