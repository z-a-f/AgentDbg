# SDK

The AgentDbg Python SDK exposes a decorator and three recording functions. All recording attaches to the current active run (thread-local). If there is no active run, recorders no-op unless implicit runs are enabled.

---

## `@trace`

Decorator to turn a function into a traced run.

```python
from agentdbg import trace

@trace
def run_agent():
    ...
```

**Behavior:**

- When the function is called **and no run is active:** creates a new run, emits `RUN_START`, runs the function, then emits `RUN_END`. On exception, emits `ERROR` then `RUN_END` with status `error` and re-raises.
- When called **inside an already active run:** runs the function without creating a new run or extra run events. All `record_*` calls inside still attach to that run.

---

## `record_llm_call`

Record an LLM call event.

```python
from agentdbg import record_llm_call

record_llm_call(
    model="gpt-4",
    prompt="...",
    response="...",
    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    meta=None,
    provider="unknown",
    temperature=None,
    stop_reason=None,
)
```

- **model** (required): Model name.
- **prompt / response / usage**: Optional; `usage` is normalized to `prompt_tokens`, `completion_tokens`, `total_tokens`.
- **meta**: Optional freeform dict (e.g. labels).
- **provider / temperature / stop_reason**: Optional metadata.

Payload and meta are redacted and truncated according to config before storage.

---

## `record_tool_call`

Record a tool call event.

```python
from agentdbg import record_tool_call

record_tool_call(
    name="search_db",
    args={"query": "x"},
    result={"count": 2},
    meta=None,
    status="ok",
    error=None,
)
```

- **name** (required): Tool name.
- **args / result**: Optional (object or string).
- **status**: `"ok"` or `"error"`; **error**: optional message when status is error.

Payload and meta are redacted and truncated.

---

## `record_state`

Record a state-update event (e.g. agent state snapshot).

```python
from agentdbg import record_state

record_state(state={"step": 1, "messages": [...]}, meta=None, diff=None)
```

- **state**: Optional object or string.
- **diff**: Optional; if provided, stored alongside state.
- **meta**: Optional freeform dict.

Redaction and truncation apply. Does not increment LLM/tool counts; used for timeline context.

---

## Implicit runs (`AGENTDBG_IMPLICIT_RUN=1`)

By default, if you call `record_llm_call` / `record_tool_call` / `record_state` **outside** a `@trace`-decorated function, they do nothing.

If you set:

```bash
export AGENTDBG_IMPLICIT_RUN=1
```

then the first recorder call in the process with no active run will create a single **implicit run**. All subsequent recorder calls in that process (until that implicit run is finalized) attach to it. The run is finalized at process exit (atexit). Use this for scripts that don’t have a single top-level `@trace` function.

---

## Redaction and truncation

- **Redaction:** Dict keys matching configured redact keys (e.g. `api_key`, `token`, `password`) are replaced with `__REDACTED__`. Applied recursively (with a depth limit).
- **Truncation:** Strings and large values are truncated to `AGENTDBG_MAX_FIELD_BYTES` (default 20000) and suffixed with `__TRUNCATED__`.

**Config precedence (highest first):**

1. Environment variables (`AGENTDBG_REDACT`, `AGENTDBG_REDACT_KEYS`, `AGENTDBG_MAX_FIELD_BYTES`)
2. `.agentdbg/config.yaml` in project root
3. `~/.agentdbg/config.yaml`

See [Getting started](getting-started.md) for env var names and defaults.
