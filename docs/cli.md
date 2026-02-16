# CLI

The `agentdbg` CLI lists runs, starts the local viewer, and exports runs to JSON. Storage is under `~/.agentdbg/` by default (overridable with `AGENTDBG_DATA_DIR`).

---

## `agentdbg list`

Lists recent runs (by `started_at` descending).

**Usage:**

```bash
agentdbg list [--limit N] [--json]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--limit`, `-n` | 20 | Maximum number of runs to list |
| `--json` | — | Output machine-readable JSON |

**Examples:**

```bash
agentdbg list
agentdbg list --limit 5
agentdbg list --json
```

**Exit codes:** `0` success; `10` internal error.

**Text columns:** run_id (short), run_name, started_at, duration_ms, llm_calls, tool_calls, status.

---

## `agentdbg view`

Starts the local viewer server and optionally opens the browser. Default bind: `127.0.0.1:8712`.

**Usage:**

```bash
agentdbg view [RUN_ID] [--host HOST] [--port PORT] [--no-browser] [--json]
```

**Arguments / options:**

| Argument/Option | Default | Description |
|-----------------|---------|-------------|
| `RUN_ID` | (latest) | Run to view; can be a short prefix (e.g. first 8 chars of UUID) |
| `--host`, `-H` | 127.0.0.1 | Bind host |
| `--port`, `-p` | 8712 | Bind port |
| `--no-browser` | — | Do not open the browser; only start the server |
| `--json` | — | Print run_id, url, status as JSON, then start server |

**Examples:**

```bash
agentdbg view
agentdbg view a1b2c3d4
agentdbg view --port 9000 --no-browser
agentdbg view --json
```

**Exit codes:** `0` success; `2` run not found (or no runs); `10` internal error.

With `--json`, output shape: `{"spec_version":"0.1","run_id":"...","url":"http://127.0.0.1:8712/?run_id=...","status":"serving"}`.

---

## `agentdbg export`

Exports one run to a single JSON file (run metadata + events array).

**Usage:**

```bash
agentdbg export RUN_ID --out FILE
```

**Options:**

| Option | Description |
|--------|-------------|
| `--out`, `-o` | Output file path (JSON) |

**Examples:**

```bash
agentdbg export a1b2c3d4-1234-5678-90ab-cdef12345678 --out run.json
agentdbg export a1b2c3d4 -o ./exports/run.json
```

**Exit codes:** `0` success; `2` run not found; `10` internal error.

Output file contains: `spec_version`, `run` (run metadata), `events` (array of event objects).
