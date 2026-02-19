# AgentDbg

**AgentDbg** is a local-first debugger for AI agents. It captures structured traces (LLM calls, tool calls, state, errors) and gives you a timeline UI to inspect what happened-inputs, outputs, latency, and loop warnings.

**What it is:** A developer tool to instrument your agent, run it, and see a full event timeline locally. No cloud, no accounts.

**What it is not:** It is not observability or production monitoring. It does not do deterministic replay (planned for a later version), and it does not lock you into any framework.

---

## In 60 seconds

**1. Install:**

```bash
git clone https://github.com/zt-9/AgentDbg.git
cd AgentDbg
uv venv && uv sync && uv pip install -e .
```

**2. Run the example agent:**

```bash
python examples/minimal/simple_agent.py
```

**3. Open the timeline viewer:**

```bash
agentdbg view
```

A browser tab opens showing every event in the run - tool calls, LLM calls, timing. Data is stored locally under `~/.agentdbg/runs/<run_id>/`.

---

## Demos and examples

| Example | Path | How to run |
|--------|------|------------|
| **Minimal agent** (pure Python) | `examples/minimal/` | `python examples/minimal/simple_agent.py` |
| **LangChain minimal** | `examples/langchain/minimal.py` | `uv run --extra langchain python examples/langchain/minimal.py` |
| **LangChain customer support** (advanced) | `examples/langchain/` | Set API keys, then `cd examples/langchain && uv run --extra langchain-examples python customer_support.py` |
| **Demos** (short scripts) | `examples/demo/` | `python examples/demo/pure_python.py` or `python examples/demo/langchain.py` |

After any run, open the timeline with `agentdbg view`.

---

## Documentation

| Page | Description |
|------|-------------|
| [Getting started](getting-started.md) | Installation (uv/pip), quickstart, data dir, redaction |
| [CLI](cli.md) | `list`, `view`, `export` with options and exit codes |
| [SDK](sdk.md) | `@trace`, `traced_run`, `record_llm_call`, `record_tool_call`, `record_state` |
| [Integrations](integrations.md) | LangChain handler (available) and planned adapters |
| [Architecture](architecture.md) | Event schema, storage layout, viewer API, loop detection |
| **Reference** | |
| [Trace format](reference/trace-format.md) | Event envelope, event types, payload schemas, run.json (public contract) |
| [Configuration](reference/config.md) | Env vars, YAML precedence, redaction, truncation, loop detection |
