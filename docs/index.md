# AgentDbg

**AgentDbg** is a local-first debugger for AI agents. It captures structured traces (LLM calls, tool calls, state, errors) and gives you a timeline UI to inspect what happened—inputs, outputs, latency, and loop warnings.

**What it is:** A developer tool to instrument your agent, run it, and see a full event timeline locally. No cloud, no accounts.

**What it is not:** It is not observability or production monitoring. It does not do deterministic replay (planned for a later version), and it does not lock you into any framework.

---

## In 60 seconds

**1. Install (editable from repo):**

```bash
cd /path/to/AgentDbg
uv pip install -e .
# or: pip install -e .
```

**2. Add tracing and recorders to your code:**

```python
from agentdbg import trace, record_llm_call, record_tool_call

@trace
def run_agent():
    record_tool_call(name="search", args={"q": "x"}, result={"count": 1})
    record_llm_call(model="gpt-4", prompt="Summarize", response="Done.", usage={})
```

**3. Run your agent, then open the viewer:**

```bash
python your_agent_script.py
agentdbg view
```

The browser opens on the latest run. Data is stored under `~/.agentdbg/runs/<run_id>/`.

---

## Documentation

| Page | Description |
|------|-------------|
| [Getting started](getting-started.md) | Installation (uv/pip), quickstart, data dir, redaction |
| [CLI](cli.md) | `list`, `view`, `export` with options and exit codes |
| [SDK](sdk.md) | `@trace`, `record_llm_call`, `record_tool_call`, `record_state`, implicit runs |
| [Integrations](integrations.md) | Framework-agnostic core and adapter roadmap |
| [Architecture](architecture.md) | Event schema, storage layout, viewer API, loop detection |
