# Architecture

Short overview of how AgentDbg works: event schema, storage, viewer API, UI, and loop detection.

---

## Event schema (high-level)

Events are JSON objects with a common shape:

- **Required fields:** `spec_version` ("0.1"), `event_id` (UUID), `run_id`, `parent_id`, `event_type`, `ts` (ISO8601 UTC), `duration_ms`, `name`, `payload`, `meta`.
- **Event types:** `RUN_START`, `RUN_END`, `LLM_CALL`, `TOOL_CALL`, `STATE_UPDATE`, `ERROR`, `LOOP_WARNING`.

Payloads are type-specific (e.g. `LLM_CALL` has `model`, `prompt`, `response`, `usage`; `TOOL_CALL` has `tool_name`, `args`, `result`, `status`). Full schema is in SPEC §5.

Events are written as one JSON object per line (JSONL) and flushed after each write.

---

## Storage layout

- **Base directory:** `~/.agentdbg/` (or `AGENTDBG_DATA_DIR`).
- **Per run:** `runs/<run_id>/`
  - **run.json** — Run metadata: `run_id`, `run_name`, `started_at`, `ended_at`, `duration_ms`, `status`, `counts` (llm_calls, tool_calls, errors, loop_warnings), `last_event_ts`.
  - **events.jsonl** — Append-only; one event per line.

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

- Single static HTML/JS file; no build step.
- Loads run list from `/api/runs`; when a run is selected (or `run_id` in query), loads `/api/runs/{run_id}/events`.
- Timeline: events in order; each event expandable with payload shown as formatted JSON.
- `LOOP_WARNING` events are displayed prominently.

---

## Loop detection

- **Input:** A sliding window of the last N events (default N=12; `AGENTDBG_LOOP_WINDOW`).
- **Signature:** Each event is reduced to a string: for `LLM_CALL` → `"LLM_CALL:"+model`, for `TOOL_CALL` → `"TOOL_CALL:"+tool_name`, else `event_type`.
- **Rule:** Look for a contiguous block of signatures that repeats K times (default K=3; `AGENTDBG_LOOP_REPETITIONS`) at the end of the window. If found, emit one `LOOP_WARNING` per distinct pattern per run (deduplicated by pattern + repetitions).
- **Payload:** `pattern` (e.g. "LLM_CALL:gpt-4 -> TOOL_CALL:search"), `repetitions`, `window_size`, `evidence_event_ids`.

No ML; purely pattern-based on event type and name to give quick feedback on repetitive agent behavior.
