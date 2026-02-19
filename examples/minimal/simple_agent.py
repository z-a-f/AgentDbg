"""
Minimal runnable example: traced function with one record_tool_call and one record_llm_call.
Run with: python examples/minimal/simple_agent.py (from repo root).
"""
from agentdbg import record_llm_call, record_tool_call, trace


@trace(name="minimal agent")
def run_agent():
    """Simulate a minimal agent: one tool call, one LLM call."""
    record_tool_call(
        name="search_db",
        args={"query": "find users"},
        result={"count": 2},
    )
    record_llm_call(
        model="gpt-4",
        prompt="Summarize the results.",
        response="Found 2 users.",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


if __name__ == "__main__":
    run_agent()
    # Run data is under ~/.agentdbg/runs/<run_id>/ (or AGENTDBG_DATA_DIR)
    print("Run data is under ~/.agentdbg/runs/<run_id>/ (or AGENTDBG_DATA_DIR)")
