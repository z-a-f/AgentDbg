# AgentDebugger — SPEC v0.1

Status: Implementable (v0.1)
Language: Python 3.10+
Primary goal: Zero-friction agent debugging (local-only)
Positioning: "Debugger for AI agents" (NOT observability)
Scope: SDK + local viewer, framework-agnostic

---

## 1. Overview

AgentDebugger is a local-first developer tool that captures structured traces of agent runs:
- LLM calls
- tool calls
- errors
- (optional) state updates
and provides a local UI to inspect a timeline of events.

Core promise:
> In <10 minutes, a developer can instrument an agent and see a full timeline of what happened, with inputs/outputs, latency, and loop warnings.

Non-goals (v0.1):
- No cloud, accounts, multi-user
- No enterprise features (SSO, RBAC, compliance)
- No full deterministic replay (planned v0.2+)
- No framework lock-in (LangChain/OpenAI SDK specific integrations are optional later)
- No OS sandboxing, security policy engines

---

## 2. Repository Structure (reference implementation)

```
AgentDbg/
├── agentdbg/
│   ├── __init__.py
│   ├── version.py
│   ├── config.py
│   ├── tracing.py
│   ├── events.py
│   ├── storage.py
│   ├── loopdetect.py
│   ├── cli.py
│   ├── server.py
│   └── ui_static/              # bundled minimal UI assets (optional)
├── docs/
├── examples/
│   └── minimal_agent/
│       └── main.py
├── tests/
│   ├── test_tracing.py
│   ├── test_storage.py
│   ├── test_loopdetect.py
│   └── test_cli.py
├── pyproject.toml
├── README.md
└── SPEC.md
```

---

## 3. Core Concepts

### 3.1 Run
A single invocation of an agent function (or top-level workflow).

### 3.2 Event
A structured record with:
- event_type
- timestamps
- payload (inputs/outputs/metadata)
- identifiers (run_id, event_id, parent_id)
- tags (tool name, model name, etc.)

### 3.3 Timeline View
UI displays events ordered by timestamp and nested by parent span when available.

---

## 4. Minimum Public API (Python SDK)

### 4.1 Decorator: trace
Primary entrypoint.

```python
from agentdbg import trace

@trace
def run_agent(...):
    ...
```

Behavior:

* Starts a new run
* Records `RUN_START` and `RUN_END` events
* Records `ERROR` on exception (then re-raises)
* Nested tracing: if a `@trace` function is called inside an active run, it MUST NOT create a new run. It MAY optionally emit a `STATE_UPDATE` event with meta `{"span": "<function_name>"}` but nested spans are NOT required for v0.1. The priority is that all `record_*` events attach to the correct active run.

### 4.2 Manual recording helpers (stable API)

Must exist in v0.1:

```python
from agentdbg import record_llm_call, record_tool_call, record_state

record_llm_call(model="gpt-4.1", prompt=..., response=..., usage=..., meta=...)
record_tool_call(name="search_db", args=..., result=..., meta=...)
record_state(state=..., meta=...)
```

Notes:

* These functions should attach to the current active run automatically (thread-local/contextvar).
* If called outside a traced run, they should no-op (default) or create an implicit run if `AGENTDBG_IMPLICIT_RUN=1` (optional flag).

### 4.3 Context manager (optional but recommended)

```python
from agentdbg import traced_run

with traced_run(name="my_agent_run"):
    ...
```

---

## 5. Trace Event Schema (v0.1)

All events are JSON-serializable dicts. Store as JSONL.

### 5.1 Required top-level fields (all events)

* `spec_version`: "0.1"
* `event_id`: UUID string
* `run_id`: UUID string
* `parent_id`: UUID string or null
* `event_type`: string enum
* `ts`: ISO8601 UTC timestamp (e.g., "2026-02-15T20:31:05.123Z")
* `duration_ms`: integer or null
* `name`: string (e.g., tool name, model name, or label)
* `payload`: object (event-type-specific)
* `meta`: object (freeform; tags, user-defined)

Timestamp format:
* `ts` MUST be UTC ISO8601 with milliseconds and trailing `Z`.
* Example: `2026-02-15T20:31:05.123Z`
* Implementation guidance: `datetime.now(timezone.utc)` with milliseconds.

IDs:
* `run_id` and `event_id` MUST be UUIDv4 strings.

### 5.2 Event Types (enum)

* `RUN_START`
* `RUN_END`
* `LLM_CALL`
* `TOOL_CALL`
* `STATE_UPDATE`
* `ERROR`
* `LOOP_WARNING`

### 5.3 Payloads

#### `RUN_START` payload

```json
{
  "run_name": "optional string",
  "python_version": "3.11.7",
  "platform": "darwin|linux|win32",
  "cwd": "/path",
  "argv": ["..."]
}
```

#### `RUN_END` payload

```json
{
  "status": "ok|error",
  "summary": {
    "llm_calls": 3,
    "tool_calls": 5,
    "errors": 0,
    "duration_ms": 1234
  }
}
```

#### `LLM_CALL` payload (minimum)

```json
{
  "model": "string",
  "prompt": "string|object|null",
  "response": "string|object|null",
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "provider": "openai|anthropic|local|unknown",
  "temperature": 0.0,
  "stop_reason": "string|null"
}
```

Rules:

* usage fields may be null if unknown
* prompt/response may be redacted by config (see redaction)

#### `TOOL_CALL` payload (minimum)

```json
{
  "tool_name": "string",
  "args": "object|string|null",
  "result": "object|string|null",
  "status": "ok|error",
  "error": "string|null"
}
```

#### `STATE_UPDATE` payload

```json
{
  "state": "object|string|null",
  "diff": "object|string|null"
}
```

Notes:

* diff is optional in v0.1; compute diff only if easy (simple dict diff).

#### `ERROR` payload

```json
{
  "error_type": "ExceptionClassName",
  "message": "string",
  "stack": "string"
}
```

#### `LOOP_WARNING` payload

```json
{
  "pattern": "string",
  "repetitions": 3,
  "window_size": 6,
  "evidence_event_ids": ["..."]
}
```

---

## 6. Storage (Local-only)

### 6.1 Default directory

* `~/.agentdbg/`
* Runs stored under `~/.agentdbg/runs/<run_id>/`
  - `events.jsonl` (append-only)
  - `run.json` (run metadata; written at start and finalized at end)

### 6.2 `run.json` schema (required)

`run.json` must exist for every run, and contain:

```json
{
  "spec_version": "0.1",
  "run_id": "<uuid>",
  "run_name": "string|null",
  "started_at": "ISO8601Z",
  "ended_at": "ISO8601Z|null",
  "duration_ms": 1234,
  "status": "ok|error|running",
  "counts": {"llm_calls": 0, "tool_calls": 0, "errors": 0, "loop_warnings": 0},
  "last_event_ts": "ISO8601Z|null"
}
```

Rules:

* On run start: write `status=running`, `ended_at=null`, duration_ms null/0.
* On run end: update status + ended_at + duration_ms + counts.

### 6.3 Event file rules

* `events.jsonl` is append-only.
* Each line is a single JSON object event.
* Flush after every event write (v0.1 requirement).
* Preserve write order (treat as authoritative ordering when timestamps tie).

---

## 7. Redaction & Privacy (must exist in v0.1)

Configurable redaction to avoid leaking secrets into traces.

### 7.1 Config sources (precedence)

1. environment variables
2. `.agentdbg/config.yaml` in project root (optional)
3. `~/.agentdbg/config.yaml`

### 7.2 Redaction settings (minimum)

* `AGENTDBG_REDACT=1` default ON
* `AGENTDBG_REDACT_KEYS="api_key,token,authorization,cookie,secret,password"`
* `AGENTDBG_MAX_FIELD_BYTES=20000` default

  Behavior:
* If payload includes dict keys matching redact keys (case-insensitive substring), replace value with `"__REDACTED__"`.
* Truncate very large strings/objects to limit size, append `"__TRUNCATED__"` marker.

Redaction must apply recursively to nested dict/list structures.
- Traverse dict keys and list elements.
- If a dict key matches (case-insensitive substring) any redact key, replace the value with `"__REDACTED__"` (do not recurse into the value).
- Limit recursion depth to 10 to avoid pathological objects.

---

## 8. Loop Detection (v0.1)

Goal: Provide immediate "intelligence" without heavy ML.

Algorithm (simple):

* Consider last N events (default N=12)
* Build a signature sequence from event types + tool_name/model (for `TOOL_CALL`/`LLM_CALL`)
* If a subsequence repeats K times consecutively (default K>=3), emit LOOP_WARNING
* Do not emit more than once per run per identical pattern (dedupe)

CLI/config knobs:

* `AGENTDBG_LOOP_WINDOW=12`
* `AGENTDBG_LOOP_REPETITIONS=3`

---

## 9. CLI (must exist in v0.1)

Use `typer` for CLI.

Commands:

### 9.1 `agentdbg list`

Lists recent runs.

Output columns (text):

* run_id (short)
* run_name
* started_at
* duration_ms
* llm_calls
* tool_calls
* status

Flags:

* `--limit N` default 20
* `--json` outputs machine JSON

Exit codes:

* 0 success
* 10 internal error

Output format for `agentdbg list --json`:

```json
{
  "spec_version": "0.1",
  "runs": [
    {
      "run_id": "...",
      "run_name": null,
      "started_at": "...",
      "duration_ms": 123,
      "status": "ok",
      "counts": {"llm_calls": 1, "tool_calls": 2, "errors": 0, "loop_warnings": 0}
    }
  ]
}
```

### 9.2 `agentdbg view [RUN_ID]`

Starts local server and opens UI (or prints URL).

* If RUN_ID omitted, open latest run
* Server binds default `127.0.0.1:8712`

Flags:

* `--host`, `--port`
* `--no-browser` (do not auto-open)
* `--json` (prints selected run metadata + URL)

Exit codes:

* 0 success
* 2 run not found
* 10 internal error

Output format for `agentdbg view --json`:

```json
{
  "spec_version": "0.1",
  "run_id": "...",
  "url": "http://127.0.0.1:8712/",
  "status": "serving"
}
```

### 9.3 `agentdbg export RUN_ID --out file.json`

Exports a run to a single JSON file (events array + metadata).

Exit codes:

* 0 success
* 2 run not found
* 10 internal error

---

## 10. Local Viewer Server (v0.1)

Implement a minimal local HTTP server using FastAPI (recommended) or Flask.

Endpoints (required):

* `GET /api/runs` -> list runs
* `GET /api/runs/{run_id}` -> run metadata
* `GET /api/runs/{run_id}/events` -> events (array)
* `GET /` -> UI (static HTML/JS) OR minimal rendered page

UI requirements (v0.1):

* show run list
* show timeline view (chronological list)
* expand/collapse each event
* show payload JSON with formatting
* display `LOOP_WARNING` prominently

UI implementation approach:

* v0.1 may be a single static HTML file with vanilla JS fetching from API
* no React requirement
* no build tool requirement preferred (maximize velocity)

UI assets:
* Provide `agentdbg/ui_static/index.html` (required).
* Server MUST serve this file at `/`.
* UI MUST:
  * fetch `/api/runs` and display run list
  * when a run is selected, fetch `/api/runs/{run_id}/events`
  * display a timeline list; each event expandable
  * render JSON payload with pretty formatting (`JSON.stringify(x, null, 2)`)

No build step, no bundler.

---

## 11. Testing Requirements (v0.1)

Use pytest.

Must include tests:

* tracing:

  * `@trace` creates `RUN_START` + RUN_END
  * exception creates `ERROR` + `RUN_END`(status=error)
* storage:

  * events appended and loadable
* redaction:

  * sensitive keys redacted
  * max field truncation
* loop detection:

  * repeated pattern triggers `LOOP_WARNING` exactly once
* cli:

  * list works on empty dir
  * export fails on missing run_id with exit code 2

---

## 12. Packaging and Distribution

* Project is uv-managed
* Provide `pyproject.toml` for pip install
* Entry point console script: `agentdbg = agentdbg.cli:main`
* Do not place CLI main() in `__init__.py`
* Do not move to src-layout
* Minimal dependencies:
* Avoid heavy frontend toolchains.

---

## 13. Out of Scope but Planned (v0.2+)

* deterministic replay
* tool mocking
* adapters for specific frameworks (LangChain/LangGraph/OpenAI Agents SDK)
* eval CI (regression testing)
* hosted multi-user trace store

---

## 14. Codegen Prompt (copy/paste)

Implement AgentDebugger exactly per SPEC v0.1.

Constraints:

* Python-only
* Local-first (no cloud)
* Framework-agnostic
* Focus on the "magic feature": timeline UI + structured events
* Keep UI minimal: static HTML + JS is enough
* Implement loop detection and redaction as required
* Provide examples and pytest tests
* Do not implement v0.2 features (replay, CI, hosted)

Deliver files in the repository structure specified, file-by-file.
