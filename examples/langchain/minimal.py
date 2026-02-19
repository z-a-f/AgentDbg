"""
Minimal LangChain example: @trace plus a chain that triggers one LLM and one tool callback.
Uses fake LLM (no network). Run from repo root:
  uv run --extra langchain python examples/langchain/minimal.py
Then: agentdbg view
"""
from agentdbg import trace
from agentdbg.integrations import AgentDbgLangChainCallbackHandler

# Optional: only import LangChain when running this example
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.tools import tool


@tool
def lookup(query: str) -> str:
    """Look up something (stub tool for demo)."""
    return f"result for: {query}"


@trace(name="langchain minimal example")
def run_agent():
    """Run a minimal chain: one tool call, one LLM call; both traced via AgentDbg handler."""
    handler = AgentDbgLangChainCallbackHandler()
    config = {"callbacks": [handler]}

    llm = FakeListLLM(responses=["Traced LLM response."])
    result = lookup.invoke({"query": "demo"}, config=config)
    _ = llm.invoke("Summarize.", config=config)
    return result


if __name__ == "__main__":
    run_agent()
    print("Run complete. View with: agentdbg view")
