# Architecture

How AgentDbg works: event schema, storage, viewer API, UI, and loop detection. For the full public contract (envelope, event types, payload schemas, run.json), see the [Trace format](reference/trace-format.md) reference.

---

## Event schema

Every event is a JSON object with a common set of top-level fields:

| Field | Type | Description |
|---|---|---|
| `spec_version` | `"0.1"` | Schema version |
| `event_id` | UUID string | Unique event identifier |
| `run_id` | UUID string | Run this event belongs to |
| `parent_id` | UUID string or `null` | Parent event (for nesting) |
| `event_type` | string | One of the types below |
| `ts` | ISO8601 UTC (`2026-02-15T20:31:05.123Z`) | Timestamp with milliseconds |
| `duration_ms` | integer or `null` | Duration if applicable |
| `name` | string | Label (tool name, model name, etc.) |
| `payload` | object | Event-type-specific data |
| `meta` | object | Freeform user-defined metadata |

### Event types

| Type | Emitted by | Payload highlights |
|---|---|---|
| `RUN_START` | `@trace` / `traced_run` | `run_name`, `python_version`, `platform`, `cwd`, `argv` |
| `RUN_END` | `@trace` / `traced_run` | `status` (`ok` / `error`), `summary` (counts + duration) |
| `LLM_CALL` | `record_llm_call()` | `model`, `prompt`, `response`, `usage`, `provider`, `status`, `error` |
| `TOOL_CALL` | `record_tool_call()` | `tool_name`, `args`, `result`, `status`, `error` |
| `STATE_UPDATE` | `record_state()` | `state`, `diff` |
| `ERROR` | `@trace` (on exception) | `error_type`, `message`, `stack` |
| `LOOP_WARNING` | Automatic detection | `pattern`, `repetitions`, `window_size`, `evidence_event_ids` |

Events are written as one JSON object per line (JSONL) and flushed after each write.

---

## Storage layout

- **Base directory:** `~/.agentdbg/` (or `AGENTDBG_DATA_DIR`).
- **Per run:** `runs/<run_id>/`
  - **run.json** - Run metadata: `run_id`, `run_name`, `started_at`, `ended_at`, `duration_ms`, `status`, `counts` (llm_calls, tool_calls, errors, loop_warnings), `last_event_ts`.
  - **events.jsonl** - Append-only; one event per line.

`run.json` is created at run start (status `running`) and updated at run end (status `ok` or `error`, counts, ended_at, duration_ms).

---

## Viewer API

The local server (FastAPI) exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /api/runs` | List recent runs (metadata only). |
| `GET /api/runs/{run_id}` | Run metadata (run.json). |
| `GET /api/runs/{run_id}/events` | Events array for the run. |
| `GET /` | Static UI (`agentdbg/ui_static/index.html`). |

Default bind: `127.0.0.1:8712`. The UI fetches runs and events from these endpoints and renders a timeline.

---

## UI overview

- **Multi-file static UI** (HTML, JS, CSS); no build step. Served from `agentdbg/ui_static/`.
- Loads run list from `/api/runs`; when a run is selected (or `run_id` in query), loads `/api/runs/{run_id}/events`.
- **Flat timeline:** events are shown in chronological order (write order / `ts`). Each event is expandable with payload shown as formatted JSON. Nesting by `parent_id` is not required.
- `LOOP_WARNING` events are displayed prominently.

---

## Loop detection

- **Input:** A sliding window of the last N events (default N=12; `AGENTDBG_LOOP_WINDOW`).
- **Signature:** Each event is reduced to a string: for `LLM_CALL` -> `"LLM_CALL:"+model`, for `TOOL_CALL` -> `"TOOL_CALL:"+tool_name`, else `event_type`.
- **Rule:** Look for a contiguous block of signatures that repeats K times (default K=3; `AGENTDBG_LOOP_REPETITIONS`) at the end of the window. If found, emit one `LOOP_WARNING` per distinct pattern per run (deduplicated by pattern + repetitions).
- **Payload:** `pattern` (e.g. "LLM_CALL:gpt-4 -> TOOL_CALL:search"), `repetitions`, `window_size`, `evidence_event_ids`.

No ML; purely pattern-based on event type and name to give quick feedback on repetitive agent behavior.
