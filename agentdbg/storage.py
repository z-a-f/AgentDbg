"""
Local storage for AgentDbg runs: run metadata (run.json) and append-only events (events.jsonl).

~/.agentdbg/runs/<run_id>/ with required run.json and events.jsonl.
Uses config.data_dir (default ~/.agentdbg). Stdlib only.
"""
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agentdbg.config import AgentDbgConfig
from agentdbg.events import utc_now_iso_ms_z

SPEC_VERSION = "0.1"

RUN_JSON = "run.json"
EVENTS_JSONL = "events.jsonl"

# run_id MUST be UUIDv4. We enforce canonical form (lowercase with hyphens).
_RUN_ID_MAX_LEN = 36


def validate_run_id_format(run_id: str) -> str:
    """
    Validate that run_id is a canonical UUIDv4 string (no path segments, no traversal).
    Returns run_id unchanged. Raises ValueError("invalid run_id") otherwise.
    """
    if not run_id or not isinstance(run_id, str):
        raise ValueError("invalid run_id")
    run_id = run_id.strip()
    if len(run_id) > _RUN_ID_MAX_LEN or ".." in run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("invalid run_id")
    try:
        u = uuid.UUID(run_id)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid run_id")
    if u.version != 4:
        raise ValueError("invalid run_id")
    if str(u) != run_id:
        raise ValueError("invalid run_id")
    return run_id


def _runs_dir(config: AgentDbgConfig) -> Path:
    """Return the runs base directory: <data_dir>/runs."""
    return config.data_dir.expanduser() / "runs"


def _run_dir(run_id: str, config: AgentDbgConfig) -> Path:
    """
    Return the run directory: <data_dir>/runs/<run_id>/.
    Validates run_id format and ensures resolved path is under runs base (defense-in-depth).
    """
    validate_run_id_format(run_id)
    base = _runs_dir(config)
    path = base / run_id
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError("invalid run_id")
    except (ValueError, OSError):
        raise ValueError("invalid run_id")
    return path


def _run_json_path(run_id: str, config: AgentDbgConfig) -> Path:
    """Path to run.json for the given run_id."""
    return _run_dir(run_id, config) / RUN_JSON


def _events_path(run_id: str, config: AgentDbgConfig) -> Path:
    """Path to events.jsonl for the given run_id."""
    return _run_dir(run_id, config) / EVENTS_JSONL


def _default_counts() -> dict:
    """Default counts per SPEC run.json schema."""
    return {
        "llm_calls": 0,
        "tool_calls": 0,
        "errors": 0,
        "loop_warnings": 0,
    }


def create_run(run_name: str | None, config: AgentDbgConfig) -> dict:
    """
    Create a new run: generate run_id, create run dir, write initial run.json (status=running).

    Returns run metadata dict including run_id and paths (run_dir, run_json, events_jsonl).
    """
    run_id = str(uuid.uuid4())
    base = _run_dir(run_id, config)
    base.mkdir(parents=True, exist_ok=True)

    started_at = utc_now_iso_ms_z()
    meta = {
        "spec_version": SPEC_VERSION,
        "run_id": run_id,
        "run_name": run_name,
        "started_at": started_at,
        "ended_at": None,
        "duration_ms": None,
        "status": "running",
        "counts": _default_counts(),
        "last_event_ts": None,
    }

    run_json_path = _run_json_path(run_id, config)
    _atomic_write_json(run_json_path, meta)

    return {
        **meta,
        "paths": {
            "run_dir": str(base),
            "run_json": str(run_json_path),
            "events_jsonl": str(_events_path(run_id, config)),
        },
    }


def append_event(run_id: str, event: dict, config: AgentDbgConfig) -> None:
    """
    Append one event as a single JSON line to events.jsonl and flush.

    Does not create the run dir; call create_run first.
    """
    path = _events_path(run_id, config)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def finalize_run(
    run_id: str,
    status: str,
    counts: dict,
    config: AgentDbgConfig,
) -> None:
    """
    Update run.json with ended_at, duration_ms, status, and counts.

    started_at is read from existing run.json (written at create_run). Uses atomic
    write (temp file then replace). status must be "ok" or "error".
    """
    path = _run_json_path(run_id, config)
    if not path.is_file():
        raise FileNotFoundError(f"run.json not found for run_id={run_id}")

    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    ended_at = utc_now_iso_ms_z()
    started_at = meta.get("started_at") or ended_at
    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    duration_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))

    merged_counts = _default_counts()
    for k in merged_counts:
        if k in counts and isinstance(counts[k], (int, float)):
            merged_counts[k] = int(counts[k])

    meta["ended_at"] = ended_at
    meta["duration_ms"] = duration_ms
    meta["status"] = status
    meta["counts"] = merged_counts
    meta["last_event_ts"] = ended_at  # v0.1: set at finalize (last event is RUN_END)

    _atomic_write_json(path, meta)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to path atomically (temp file then rename)."""
    fd, tmp = tempfile.mkstemp(
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def resolve_run_id(prefix: str, config: AgentDbgConfig) -> str:
    """
    Resolve a run_id prefix (e.g. short "33be9ab2") to the full run_id (UUID).
    If prefix already matches a run directory name exactly, returns it.
    Otherwise finds run directories whose name starts with prefix; if exactly one
    match returns it, if multiple returns the most recent by started_at.
    Raises FileNotFoundError if no run matches. Rejects prefix with path traversal.
    """
    if not prefix or not prefix.strip():
        raise FileNotFoundError("Run ID is required")
    prefix = prefix.strip()
    if ".." in prefix or "/" in prefix or "\\" in prefix:
        raise FileNotFoundError("Run ID is required")
    runs_base = _runs_dir(config)
    if not runs_base.is_dir():
        raise FileNotFoundError(f"No runs directory at {runs_base}")

    candidates: list[tuple[datetime | None, str]] = []
    for entry in runs_base.iterdir():
        if not entry.is_dir():
            continue
        rid = entry.name
        try:
            validate_run_id_format(rid)
        except ValueError:
            continue
        if rid != prefix and not rid.startswith(prefix):
            continue
        run_json = entry / RUN_JSON
        if not run_json.is_file():
            continue
        try:
            with open(run_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        started_str = meta.get("started_at")
        started_dt = _parse_iso8601_utc(started_str) if started_str else None
        candidates.append((started_dt, rid))

    if not candidates:
        raise FileNotFoundError(f"No run found matching '{prefix}'")

    def sort_key(item: tuple[datetime | None, str]) -> tuple[bool, datetime]:
        dt, _ = item
        return (dt is None, dt or datetime.min.replace(tzinfo=timezone.utc))

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0][1]


def load_run_meta(run_id: str, config: AgentDbgConfig) -> dict:
    """
    Load run metadata from run.json. Raises FileNotFoundError if run or run.json missing.
    """
    path = _run_json_path(run_id, config)
    if not path.is_file():
        raise FileNotFoundError(f"No run found for run_id '{run_id}'")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_iso8601_utc(s: str) -> datetime | None:
    """Parse ISO8601 UTC timestamp (e.g. 2026-02-15T20:31:05.123Z). Returns None if invalid."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        # Accept both .123Z and Z-only
        normalized = s.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def list_runs(limit: int, config: AgentDbgConfig) -> list[dict]:
    """
    List most recent runs by started_at descending. Does not parse events.jsonl.

    Sort uses parsed datetime for started_at so ordering is correct even if formats
    differ (e.g. with/without milliseconds). Runs with missing/invalid started_at
    sort last. Returns list of run metadata dicts (from run.json only), up to limit.
    """
    runs_base = _runs_dir(config)
    if not runs_base.is_dir():
        return []

    candidates: list[tuple[datetime | None, dict]] = []
    for entry in runs_base.iterdir():
        if not entry.is_dir():
            continue
        run_json = entry / RUN_JSON
        if not run_json.is_file():
            continue
        try:
            with open(run_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        started_str = meta.get("started_at")
        started_dt = _parse_iso8601_utc(started_str) if started_str else None
        candidates.append((started_dt, meta))

    # None sorts before datetime in Python 3, so put (None, meta) last when desc
    def sort_key(item: tuple[datetime | None, dict]) -> tuple[bool, datetime]:
        dt, _ = item
        return (dt is None, dt or datetime.min.replace(tzinfo=timezone.utc))

    candidates.sort(key=sort_key, reverse=True)
    return [meta for _, meta in candidates[:limit]]


def load_events(run_id: str, config: AgentDbgConfig) -> list[dict]:
    """
    Read events.jsonl for the run and return a list of event dicts.

    Returns [] if the file is missing or empty.
    """
    path = _events_path(run_id, config)
    if not path.is_file():
        return []
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
