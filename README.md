# AgentDbg — local-first debugger for AI agents

AgentDbg is a **local-only** developer tool that captures structured traces of agent runs (LLM calls, tool calls, state updates, errors) and provides a **minimal timeline UI** to inspect what happened.

**Positioning:** *Debugger for AI agents* (not “observability”).
**Scope:** Python SDK + local viewer. No cloud, no accounts.


## Why AgentDbg

When agents misbehave, logs aren't enough. AgentDbg gives you a timeline with:
- LLM prompts/responses (redacted by default)
- tool calls + results
- errors + stack traces
- loop warnings (v0.1: detection module exists; integration may vary by version)

**Goal:** instrument an agent in <10 minutes and immediately see a full run timeline.


## Install (local dev)

This repo is `uv`-managed.

```bash
uv venv
uv sync
uv pip install -e .
```

(If you don't use `uv`, a standard editable install works too.)


## Quickstart

Get a full run timeline in a few minutes: instrument one function, run it, then open the viewer.

### 1. Instrument your agent

Wrap your agent entrypoint with `@trace` and record LLM and tool activity:

```python
from agentdbg import trace, record_tool_call, record_llm_call

@trace
def run_agent():
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

run_agent()
```

Traces are written under `~/.agentdbg/runs/<run_id>/` (or `AGENTDBG_DATA_DIR`).

### 2. View the timeline

```bash
agentdbg view
```

Starts a local server (default `127.0.0.1:8712`) and opens the UI. Use **List runs** and **View a specific run** below to pick a run.

### Try the example

From the repo root (after `uv sync` and `uv pip install -e .`):

```bash
python examples/minimal_agent/main.py
agentdbg view
```


## CLI

### List runs

```bash
agentdbg list
agentdbg list --limit 50
agentdbg list --json
```

### View a specific run

```bash
agentdbg view <RUN_ID>
agentdbg view --host 127.0.0.1 --port 8712
agentdbg view --no-browser
agentdbg view --json
```

### Export a run

```bash
agentdbg export <RUN_ID> --out run.json
```


## Storage layout

AgentDbg writes traces locally:

* Default data dir: `~/.agentdbg/`
* Runs live under: `~/.agentdbg/runs/<run_id>/`

  * `run.json` (metadata)
  * `events.jsonl` (append-only events)

Override the location:

```bash
export AGENTDBG_DATA_DIR=/path/to/agentdbg-data
```


## Redaction & privacy

Redaction is **ON by default** (`AGENTDBG_REDACT=1`).

AgentDbg redacts values for payload keys that match configured substrings (case-insensitive) and truncates very large fields.

Key env vars:

```bash
export AGENTDBG_REDACT=1
export AGENTDBG_REDACT_KEYS="api_key,token,authorization,cookie,secret,password"
export AGENTDBG_MAX_FIELD_BYTES=20000
```


## Development

Run tests:

```bash
uv run pytest
```

Run the example:

```bash
python examples/minimal_agent/main.py
agentdbg view
```


## Roadmap (v0.2+)

* deterministic replay / tool mocking
* framework adapters (LangChain/LangGraph/OpenAI Agents SDK)
* eval + regression CI support
* optional hosted trace store

**Framework Integrations (OSS)**: optional adapters for LangGraph/LangChain, Agno, OpenAI Agents SDK, etc. Implemented as thin translation layers that emit AgentDbg events without locking users into any framework.

## License

TBD
