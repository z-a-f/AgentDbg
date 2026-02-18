"""
CLI tests using Typer CliRunner.
Every test uses temp dir via AGENTDBG_DATA_DIR (fixture restores env).
Covers: list (empty dir exit 0), export (missing run exit 2), list --json (valid JSON with spec_version, runs),
        _wait_for_port readiness probe, and browser-open ordering for `view`.
"""
import json
import socket
import threading
import time

import pytest
from typer.testing import CliRunner

from agentdbg.cli import _wait_for_port, app

runner = CliRunner()


@pytest.fixture
def empty_data_dir(temp_data_dir):
    """Empty data dir with AGENTDBG_DATA_DIR set (env restored after test)."""
    return temp_data_dir


def test_list_empty_dir_exit_zero(empty_data_dir):
    """agentdbg list on empty dir exits code 0."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_export_missing_run_exit_two(empty_data_dir):
    """agentdbg export missing_run --out <tmpfile> exits code 2."""
    tmpfile = empty_data_dir / "out.json"
    result = runner.invoke(app, ["export", "missing_run", "--out", str(tmpfile)])
    assert result.exit_code == 2


def test_export_accepts_run_id_prefix(empty_data_dir):
    """agentdbg export with run_id prefix resolves to full run and writes correct JSON."""
    from agentdbg.config import load_config

    config = load_config()
    run_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    run_dir = config.data_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({
        "spec_version": "0.1",
        "run_id": run_id,
        "run_name": "prefix_test",
        "started_at": "2026-01-01T00:00:00.000Z",
        "ended_at": None,
        "duration_ms": 0,
        "status": "ok",
        "counts": {"llm_calls": 0, "tool_calls": 0, "errors": 0, "loop_warnings": 0},
        "last_event_ts": None,
    }))
    (run_dir / "events.jsonl").write_text("")

    prefix = run_id[:8]
    tmpfile = empty_data_dir / "exported.json"
    result = runner.invoke(app, ["export", prefix, "--out", str(tmpfile)])
    assert result.exit_code == 0
    data = json.loads(tmpfile.read_text())
    assert data["run"]["run_id"] == run_id
    assert data["run"]["run_name"] == "prefix_test"
    assert "events" in data


def test_list_json_outputs_valid_json_spec_version_and_runs(empty_data_dir):
    """agentdbg list --json outputs valid JSON with keys spec_version and runs."""
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "spec_version" in data
    assert "runs" in data
    assert data["spec_version"] == "0.1"
    assert isinstance(data["runs"], list)


# ---------------------------------------------------------------------------
# _wait_for_port readiness-probe tests
# ---------------------------------------------------------------------------


def test_wait_for_port_returns_true_when_port_opens():
    """_wait_for_port returns True once a TCP listener appears on the port."""
    # Bind to an ephemeral port but don't accept yet.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    # Start listening after a short delay (simulates server startup lag).
    def _delayed_listen() -> None:
        time.sleep(0.15)
        srv.listen(1)

    t = threading.Thread(target=_delayed_listen, daemon=True)
    t.start()

    try:
        assert _wait_for_port("127.0.0.1", port, timeout_s=3.0) is True
    finally:
        srv.close()
        t.join(timeout=2)


def test_wait_for_port_returns_false_on_timeout():
    """_wait_for_port returns False when no listener appears before timeout."""
    # Grab an ephemeral port number, then close it so nothing listens.
    tmp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tmp.bind(("127.0.0.1", 0))
    port = tmp.getsockname()[1]
    tmp.close()

    assert _wait_for_port("127.0.0.1", port, timeout_s=0.3) is False


def test_view_opens_browser_only_after_wait_succeeds(monkeypatch, empty_data_dir):
    """webbrowser.open is called only after _wait_for_port returns True."""
    # Track call ordering.
    call_log: list[str] = []

    def fake_wait_for_port(host: str, port: int, timeout_s: float = 5.0) -> bool:
        call_log.append("wait")
        return True

    def fake_webbrowser_open(url: str, *a, **kw) -> None:
        # At the moment the browser is opened, 'wait' must already be logged.
        assert "wait" in call_log, "webbrowser.open called before readiness wait"
        call_log.append("browser")

    # Patch _wait_for_port at the module level so view_cmd picks it up.
    monkeypatch.setattr("agentdbg.cli._wait_for_port", fake_wait_for_port)
    monkeypatch.setattr("agentdbg.cli.webbrowser.open", fake_webbrowser_open)

    # Patch uvicorn.run so no real server starts; make it block briefly.
    def fake_uvicorn_run(**kwargs) -> None:
        time.sleep(0.1)

    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    # Create a minimal run so the view command doesn't exit with "not found".
    # Use a valid UUIDv4 (SPEC §5.1) so run_id validation accepts it.
    import agentdbg.storage as storage
    from agentdbg.config import load_config

    config = load_config()
    run_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    run_dir = config.data_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({
        "spec_version": "0.1",
        "run_id": run_id,
        "run_name": "test",
        "started_at": "2026-01-01T00:00:00.000Z",
        "ended_at": None,
        "duration_ms": 0,
        "status": "ok",
        "counts": {"llm_calls": 0, "tool_calls": 0, "errors": 0, "loop_warnings": 0},
        "last_event_ts": None,
    }))
    (run_dir / "events.jsonl").write_text("")

    result = runner.invoke(app, ["view", run_id])
    assert result.exit_code == 0
    assert call_log == ["wait", "browser"]
