# Integrations

## Philosophy

AgentDbg is **framework-agnostic** at the core. The SDK is a thin layer: you call `@trace` and `record_llm_call` / `record_tool_call` / `record_state` from any Python code. No required dependency on LangChain, OpenAI Agents SDK, or others.

**Adapters** (planned or future) are thin translation layers: they hook into a framework’s callbacks or execution and emit AgentDbg events. They do not lock you into that framework for the rest of your app.

---

## Roadmap

Planned framework adapters (order is indicative, not guaranteed):

1. **LangChain / LangGraph** — first target; instrument runs and tool calls.
2. **OpenAI Agents SDK** — instrument agent steps and tool use.
3. **Agno** — optional adapter for Agno-based agents.
4. Others as needed (e.g. AutoGen, CrewAI, custom loops).

These are **not implemented yet**. When an adapter exists, it will be documented here and in the repo.

---

## LangChain adapter

**Status: planned.** There is no LangChain or LangGraph adapter in the current repo. When added, it will live in the repo as an optional integration and will be documented in this section with usage and installation notes.

Until then, use the core SDK: wrap your LangChain/LangGraph entrypoint with `@trace` and call `record_llm_call` / `record_tool_call` (and optionally `record_state`) from your callbacks or run loop.
