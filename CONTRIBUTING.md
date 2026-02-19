# Contributing to AgentDbg

Thanks for your interest in AgentDbg. This document covers dev setup, tests, lint/format, and how to add integrations.

---

## Dev setup

1. **Clone and install with uv (recommended):**

   ```bash
   git clone https://github.com/zt-9/AgentDbg.git
   cd AgentDbg
   uv venv && uv sync && uv pip install -e .
   ```

   This creates a venv, installs dependencies (including dev), and installs the package in editable mode.

2. **Optional dependencies (e.g. LangChain integration):**

   ```bash
   uv pip install -e ".[langchain]"
   ```

---

## Running tests

```bash
uv run pytest
```

Run a specific file or test:

```bash
uv run pytest tests/test_tracing.py
uv run pytest tests/test_tracing.py -k "test_trace_creates_run"
```

---

## Lint and format

- **Ruff** is used for linting and formatting. Dev dependencies include `ruff` and `pre-commit`.
- Format and lint:

  ```bash
  uv run ruff check .
  uv run ruff format .
  ```

- **Pre-commit:** If you use pre-commit, install hooks with `uv run pre-commit install`. The project does not require pre-commit for contributions; running ruff before pushing is sufficient.

---

## Adding integrations / adapters

AgentDbg is **framework-agnostic** at the core. Integrations are optional adapters that map framework callbacks to AgentDbg's recording API.

If you want to add or extend an integration (e.g. another framework):

1. **Optional dependencies only.** The integration must live under `agentdbg.integrations.*` and depend on the framework via optional extras (e.g. `[langchain]` in `pyproject.toml`). The core package must not depend on the framework.
2. **Keep the core framework-agnostic.** All recording goes through the public API: `record_llm_call`, `record_tool_call`, `record_state`. The integration's job is to translate framework events into those calls.
3. **Deterministic tests, no network.** Tests for the integration should be deterministic and not perform real LLM or network calls. Use mocks or in-memory stubs.
4. **Map callbacks to record_*.** Implement the framework's callback/hook interface and call the appropriate `record_*` functions so that events attach to the current run (or an implicit run if `AGENTDBG_IMPLICIT_RUN=1`).

New integrations should be documented in [docs/integrations.md](docs/integrations.md) with usage and install instructions.

---

## Example folders

Examples live under `examples/` and must stay runnable from the repo root:

- **`examples/minimal_agent/`** – minimal pure-Python agent (no extra deps).
- **`examples/langchain/minimal/`** – minimal LangChain chain; requires `[langchain]` extra.
- **`examples/langchain/customer_support/`** – advanced LangChain/LangGraph demo; requires `[langchain-examples]` and API keys (see its README).
- **`examples/demo/`** – short demo scripts (`pure_python.py`, `langchain.py`).

When changing directory layout or run commands, update README, [docs/index.md](docs/index.md) (Demos section), and this list.

---

## Documentation

- **User docs** live in `docs/`: [getting started](docs/getting-started.md), [CLI](docs/cli.md), [SDK](docs/sdk.md), [integrations](docs/integrations.md), [architecture](docs/architecture.md).
- **Reference docs** (public contracts) are in `docs/reference/`:
  - [Trace format](docs/reference/trace-format.md) - event schema, run.json, payloads.
  - [Configuration](docs/reference/config.md) - env vars, YAML precedence, redaction, loop detection.

When you change behavior that affects the trace format or configuration, update the relevant reference doc and any linked pages.

---

## Summary

- **Setup:** `uv venv && uv sync && uv pip install -e .`
- **Tests:** `uv run pytest`
- **Lint/format:** `uv run ruff check .` and `uv run ruff format .`
- **Integrations:** Optional deps, map framework callbacks -> `record_*`, deterministic tests, document in `docs/integrations.md`.
