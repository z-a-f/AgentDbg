# Trace format (public contract)

This page describes the **public trace format** for AgentDbg v0.1. Traces are stored locally as **JSONL events** plus a **run metadata file** (`run.json`). The format is a public contract: consumers can rely on it for tooling and integrations.

**Versioning:** The trace format is versioned via `spec_version` (currently `"0.1"`). Additive changes (new optional fields, new event types) may be introduced without a version bump. Breaking changes will result in a new spec version.

---

## Overview

- **Per run:** One directory `runs/<run_id>/` containing:
  - **events.jsonl** - append-only; one JSON object per line (one event per line).
  - **run.json** - run metadata; written at run start and updated at run end.
- **Ordering:** Events in `events.jsonl` are in write order; when timestamps tie, this order is authoritative.
- **Flushing:** Events are flushed after every write so that crashes do not lose the last event.

**Redaction and truncation:** All payloads (and meta) written to disk pass through redaction and truncation before being written. This includes **ERROR** payloads and **RUN_START.argv** (option values matching redact keys are redacted). See the configuration reference for `redact`, `redact_keys`, and `max_field_bytes`.

---

## Event envelope (all events)

Every event is a single JSON object with these **required top-level fields**:

| Field | Type | Description |
|-------|------|-------------|
| `spec_version` | string | Schema version, e.g. `"0.1"` |
| `event_id` | string | UUIDv4, unique per event |
| `run_id` | string | UUIDv4, run this event belongs to |
| `parent_id` | string \| null | UUIDv4 of parent event, or `null` |
| `event_type` | string | One of the event types below |
| `ts` | string | UTC ISO8601 with milliseconds and trailing `Z`, e.g. `2026-02-15T20:31:05.123Z` |
| `duration_ms` | integer \| null | Duration in milliseconds if applicable |
| `name` | string | Label (e.g. tool name, model name, run name) |
| `payload` | object | Event-type-specific data (see below) |
| `meta` | object | Freeform metadata (tags, user-defined) |

### Timestamp and ID rules

- **Timestamps:** `ts` MUST be UTC ISO8601 with millisecond precision and trailing `Z`.
- **IDs:** `run_id` and `event_id` MUST be UUIDv4 strings (canonical form with hyphens).

---

## Event types

| Type | Description |
|------|-------------|
| `RUN_START` | Run started (emitted by `@trace` / `traced_run`) |
| `RUN_END` | Run finished (ok or error) |
| `LLM_CALL` | One LLM invocation (model, prompt, response, usage) |
| `TOOL_CALL` | One tool invocation (name, args, result, status) |
| `STATE_UPDATE` | State snapshot or diff (e.g. between steps) |
| `ERROR` | Exception captured (type, message, stack) |
| `LOOP_WARNING` | Loop detection: repeated pattern in recent events |

---

## Payload schemas by event type

### RUN_START

```json
{
  "run_name": "optional string or null",
  "python_version": "3.11.7",
  "platform": "darwin | linux | win32",
  "cwd": "/path/to/cwd",
  "argv": ["script.py", "arg1"]
}
```

- **run_name** is set from: `AGENTDBG_RUN_NAME` (env), explicit `@trace("...")` / `@trace(name="...")` or `traced_run(name="...")`, or default `path:function - YYYY-MM-DD HH:MM`. See [configuration reference](config.md#run-name-env-only).
- **argv** may contain secrets; values for options matching redact keys are redacted before write.

### RUN_END

```json
{
  "status": "ok | error",
  "summary": {
    "llm_calls": 3,
    "tool_calls": 5,
    "errors": 0,
    "duration_ms": 1234
  }
}
```

### LLM_CALL

```json
{
  "model": "string",
  "prompt": "string | object | null",
  "response": "string | object | null",
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "provider": "openai | anthropic | local | unknown",
  "temperature": 0.0,
  "stop_reason": "string | null",
  "status": "ok | error",
  "error": "object | null"
}
```

- `usage` fields may be `null` if unknown.
- `prompt` and `response` may be redacted or truncated by config.
- When `status` is `"error"`, `error` is an object with `error_type`, `message`, optional `details`, optional `stack` (same shape as ERROR event payload).

### TOOL_CALL

```json
{
  "tool_name": "string",
  "args": "object | string | null",
  "result": "object | string | null",
  "status": "ok | error",
  "error": "object | null"
}
```

- When `status` is `"error"`, `error` is an object with `error_type`, `message`, optional `details`, optional `stack` (same shape as ERROR event payload).

### STATE_UPDATE

```json
{
  "state": "object | string | null",
  "diff": "object | string | null"
}
```

- `diff` is optional; may be omitted if not computed.

### ERROR

Error payloads use a consistent shape (same for standalone ERROR events and nested `error` in LLM_CALL/TOOL_CALL):

```json
{
  "error_type": "ExceptionClassName",
  "message": "string",
  "stack": "string | null",
  "details": "optional, any"
}
```

- Use **`error_type`** (not `type`) for the exception class name.

### LOOP_WARNING

```json
{
  "pattern": "string",
  "repetitions": 3,
  "window_size": 6,
  "evidence_event_ids": ["event_uuid_1", "event_uuid_2"]
}
```

- Emitted at most once per run per distinct pattern (deduplicated).

---

## run.json schema

Each run has a `run.json` file in its directory. It is created at run start and updated at run end.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `spec_version` | string | `"0.1"` |
| `run_id` | string | UUIDv4 |
| `run_name` | string \| null | Optional run label |
| `started_at` | string | UTC ISO8601 with ms and `Z` |
| `ended_at` | string \| null | Set when run finishes; `null` while running |
| `duration_ms` | integer \| null | Total run duration in ms; `null` while running |
| `status` | string | `"running"` \| `"ok"` \| `"error"` |
| `counts` | object | See below |
| `last_event_ts` | string \| null | Timestamp of last event; set at finalize |

**counts** object:

```json
{
  "llm_calls": 0,
  "tool_calls": 0,
  "errors": 0,
  "loop_warnings": 0
}
```

### Lifecycle semantics

- **On run start:** `run.json` is written with `status: "running"`, `ended_at: null`, `duration_ms: null` (or 0), and zero counts.
- **On run end:** `run.json` is updated with `status: "ok"` or `"error"`, `ended_at`, `duration_ms`, final `counts`, and `last_event_ts`.

---

## Versioning note

The trace format is a **public contract** for v0.1. Additive changes (e.g. new optional fields, new event types) are allowed without a version bump. Breaking changes (removing fields, changing types or semantics) will be accompanied by a new `spec_version`. The markdown reference on this page is **canonical**; JSON schemas in the repo root `schemas/` folder (`run.schema.json`, `event.schema.json`) are best-effort for tooling.
