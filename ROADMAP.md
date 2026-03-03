# Roadmap and version history

## v0.2 (planned)
- Deterministic replay / tool mocking
- OpenAI Agents SDK adapter
- Eval + regression CI
- Optional hosted trace store


## v0.1 (released 2026-02-28)
- `@trace` decorator + `record_llm_call` / `record_tool_call` / `record_state`
- Local JSONL storage with automatic redaction
- `agentdbg list`, `agentdbg view` (timeline UI), `agentdbg export`
- Loop detection (`LOOP_WARNING` events)
- LangChain/LangGraph callback handler
