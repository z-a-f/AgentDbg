# Getting started

## Installation

Requires Python 3.10+.

**With uv (recommended):**

```bash
git clone https://github.com/AgentDbg/AgentDbg.git
cd AgentDbg
uv venv && uv sync && uv pip install -e .
```

**With pip:**

```bash
git clone https://github.com/AgentDbg/AgentDbg.git
cd AgentDbg
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

---

## Quickstart

**1. Decorate your entrypoint with `@trace`** so each invocation becomes a run (RUN_START / RUN_END, ERROR on exception).

**2. Call the recorders** inside that function so events attach to the current run:

```python
from agentdbg import trace, record_llm_call, record_tool_call, record_state

@trace
def run_agent():
    record_tool_call(name="search_db", args={"query": "x"}, result={"count": 2})
    record_llm_call(
        model="gpt-4",
        prompt="Summarize",
        response="Done.",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    record_state(state={"step": 1}, meta={"label": "after_search"})

if __name__ == "__main__":
    run_agent()
```

**3. Run the script, then open the UI:**

```bash
python your_script.py
agentdbg view
```

The viewer starts a local server (default `127.0.0.1:8712`) and opens the latest run in your browser.

---

## Where data is stored

- **Default:** `~/.agentdbg/runs/<run_id>/`
  - `run.json` - run metadata (status, counts, started_at, ended_at)
  - `events.jsonl` - one JSON object per line (append-only)

---

## Overriding the data directory

Set the data directory so runs are stored somewhere else (e.g. project-local):

```bash
export AGENTDBG_DATA_DIR=/path/to/my/data
```

Config can also be set in `~/.agentdbg/config.yaml` or `.agentdbg/config.yaml` in the project root; environment variables take precedence. See the [configuration reference](reference/config.md) for the full list of options and precedence.

---

## Redaction (defaults and config)

- **Redaction is on by default.** Payloads are scanned for sensitive keys (e.g. `api_key`, `token`, `authorization`, `password`); matching values are replaced with `__REDACTED__`.
- **Large values** are truncated to a maximum size (default 20_000 bytes) and suffixed with `__TRUNCATED__`.

**Environment variables (override config files):**

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTDBG_REDACT` | `1` | `1`/`true`/`yes` to enable redaction |
| `AGENTDBG_REDACT_KEYS` | `api_key,token,authorization,cookie,secret,password` | Comma-separated keys (case-insensitive substring match) |
| `AGENTDBG_MAX_FIELD_BYTES` | `20000` | Max size for string/field before truncation |

Example: disable redaction (e.g. for local debugging):

```bash
export AGENTDBG_REDACT=0
```

For full details (precedence, YAML keys, redaction/truncation behavior), see the [configuration reference](reference/config.md).
