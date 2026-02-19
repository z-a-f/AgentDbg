# Integrations

## Philosophy

AgentDbg is **framework-agnostic** at the core. The SDK is a thin layer: you call `@trace` and `record_llm_call` / `record_tool_call` / `record_state` from any Python code. No required dependency on LangChain, OpenAI Agents SDK, or others.

**Adapters** are thin translation layers: they hook into a framework's callbacks and emit AgentDbg events. They do not lock you into that framework for the rest of your app.

---

## Available in v0.1

### LangChain / LangGraph callback handler

**Status: available.** An optional callback handler lives at `agentdbg.integrations.langchain`. It records LLM calls and tool calls to the active AgentDbg run automatically.

**Requirements:** `langchain-core` must be installed. Install the optional dependency group:

```bash
pip install -e ".[langchain]"
```

If `langchain-core` is not installed, importing the integration raises a clear `ImportError` with install instructions. The integration is optional; the core package does not depend on it.

**Usage:**

```python
from agentdbg import trace
from agentdbg.integrations import AgentDbgLangChainCallbackHandler

@trace
def run_agent():
    handler = AgentDbgLangChainCallbackHandler()
    config = {"callbacks": [handler]}

    # Use config with any LangChain chain, LLM, or tool:
    result = my_chain.invoke(input_data, config=config)
    return result
```

The handler captures:

- **LLM calls** (`on_llm_start` / `on_chat_model_start` -> `on_llm_end`): records model name, prompt, response, and token usage via `record_llm_call`.
- **Tool calls** (`on_tool_start` -> `on_tool_end` / `on_tool_error`): records tool name, args, result, and error status via `record_tool_call`.

See `examples/langchain/minimal.py` for a runnable example:

```bash
uv run --extra langchain python examples/langchain/minimal.py
agentdbg view
```

**Notes:**

- The handler requires an active AgentDbg run - wrap your entrypoint with `@trace` or set `AGENTDBG_IMPLICIT_RUN=1`.
- Tool errors are recorded as `TOOL_CALL` events with `status="error"` and include the error message.
- LLM errors are recorded as `LLM_CALL` events with `status="error"` (not as separate `ERROR` events).

---

## Planned

Planned framework adapters (not yet implemented):

1. **OpenAI Agents SDK** - instrument agent steps and tool use.
2. **Agno** - optional adapter for Agno-based agents.
3. Others as needed (e.g. AutoGen, CrewAI, custom loops).

When an adapter is added, it will be documented here with usage and installation notes.

Until then, use the core SDK: wrap your entrypoint with `@trace` and call `record_llm_call` / `record_tool_call` (and optionally `record_state`) from your own callbacks or run loop.

For guidance on adding new integrations (optional deps, mapping callbacks to `record_*`, tests), see [CONTRIBUTING.md](../CONTRIBUTING.md#adding-integrations--adapters) in the repo root.
