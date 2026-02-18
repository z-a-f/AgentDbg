"""
Typer CLI for AgentDbg (SPEC §9).

Commands: list, export, view. Entrypoint: main() for console script agentdbg.cli:main.
"""
import json
import socket
import threading
import time
import webbrowser
from pathlib import Path

import typer
from typer import Exit

import agentdbg.storage as storage
from agentdbg.config import load_config
from agentdbg.server import create_app

SPEC_VERSION = "0.1"
EXIT_NOT_FOUND = 2
EXIT_INTERNAL = 10

app = typer.Typer(help="AgentDbg CLI: list runs, export, or view in browser.")


def _wait_for_port(host: str, port: int, timeout_s: float = 5.0) -> bool:
    """Block until *host*:*port* accepts a TCP connection, or *timeout_s* elapses.

    Used to avoid opening the browser before the viewer server is reachable
    (race-condition prevention).  Pure-stdlib, no new dependencies.

    Returns ``True`` if the port became reachable, ``False`` on timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _run_table_rows(runs: list[dict]) -> list[list[str]]:
    """Build rows for text table: run_id (short), run_name, started_at, duration_ms, llm_calls, tool_calls, status."""
    rows = []
    for r in runs:
        run_id = (r.get("run_id") or "")[:8]
        run_name = r.get("run_name") or ""
        started_at = r.get("started_at") or ""
        duration_ms = r.get("duration_ms")
        duration_str = str(duration_ms) if duration_ms is not None else ""
        counts = r.get("counts") or {}
        llm = counts.get("llm_calls", 0)
        tool = counts.get("tool_calls", 0)
        status = r.get("status") or ""
        rows.append([run_id, run_name, started_at, duration_str, str(llm), str(tool), status])
    return rows


def _format_text_table(rows: list[list[str]], headers: list[str]) -> str:
    """Format rows as a simple text table (no external libs)."""
    if not rows:
        return "\n".join(["\t".join(headers), ""])
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    lines = []
    sep = "\t"
    lines.append(sep.join(h.ljust(col_widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        lines.append(sep.join(str(row[i]).ljust(col_widths[i]) for i in range(min(len(row), len(col_widths)))))
    return "\n".join(lines)


@app.command("list")
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Max runs to list"),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
) -> None:
    """List recent runs."""
    try:
        config = load_config()
        runs = storage.list_runs(limit=limit, config=config)
        if json_out:
            out = {"spec_version": SPEC_VERSION, "runs": runs}
            print(json.dumps(out, ensure_ascii=False))
        else:
            headers = ["run_id", "run_name", "started_at", "duration_ms", "llm_calls", "tool_calls", "status"]
            rows = _run_table_rows(runs)
            print(_format_text_table(rows, headers))
    except Exception as e:
        if not json_out:
            typer.echo(f"error: {e}", err=True)
        raise Exit(EXIT_INTERNAL)


@app.command("export")
def export_cmd(
    run_id: str = typer.Argument(..., help="Run ID or prefix to export"),
    out: Path = typer.Option(..., "--out", "-o", path_type=Path, help="Output JSON file path"),
) -> None:
    """Export a run to a single JSON file (run metadata + events array)."""
    try:
        config = load_config()
        try:
            run_id = storage.resolve_run_id(run_id, config)
        except FileNotFoundError:
            raise Exit(EXIT_NOT_FOUND)
        try:
            run_meta = storage.load_run_meta(run_id, config)
        except (ValueError, FileNotFoundError):
            raise Exit(EXIT_NOT_FOUND)
        events = storage.load_events(run_id, config)
        payload = {"spec_version": SPEC_VERSION, "run": run_meta, "events": events}
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exit:
        raise
    except Exception as e:
        typer.echo(f"error: {e}", err=True)
        raise Exit(EXIT_INTERNAL)


@app.command("view")
def view_cmd(
    run_id: str | None = typer.Argument(None, help="Run ID to view (default: latest)"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind host"),
    port: int = typer.Option(8712, "--port", "-p", help="Bind port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser"),
    json_out: bool = typer.Option(False, "--json", help="Print run_id, url, status as JSON then start server"),
) -> None:
    """Start local viewer server and optionally open browser."""
    try:
        config = load_config()
        if run_id is None:
            runs = storage.list_runs(limit=1, config=config)
            if not runs:
                if not json_out:
                    typer.echo("No runs found. Record a traced run first.", err=True)
                raise Exit(EXIT_NOT_FOUND)
            run_id = runs[0].get("run_id") or ""
        if not run_id:
            if not json_out:
                typer.echo("Run ID is required.", err=True)
            raise Exit(EXIT_NOT_FOUND)
        try:
            run_id = storage.resolve_run_id(run_id, config)
        except FileNotFoundError as e:
            if not json_out:
                typer.echo(f"Run not found: {e}", err=True)
            raise Exit(EXIT_NOT_FOUND)
        try:
            storage.load_run_meta(run_id, config)
        except (ValueError, FileNotFoundError) as e:
            if not json_out:
                typer.echo(f"Run not found: {e}", err=True)
            raise Exit(EXIT_NOT_FOUND)

        url = f"http://{host}:{port}/?run_id={run_id}"
        if json_out:
            out = {
                "spec_version": SPEC_VERSION,
                "run_id": run_id,
                "url": url,
                "status": "serving",
            }
            print(json.dumps(out, ensure_ascii=False))

        import uvicorn

        fastapi_app = create_app()
        log_level = "warning" if json_out else "info"

        # Start the server in a daemon thread so we can gate the browser
        # open on actual TCP readiness (prevents "connection refused" race).
        server_thread = threading.Thread(
            target=uvicorn.run,
            kwargs=dict(app=fastapi_app, host=host, port=port, log_level=log_level),
            daemon=True,
        )
        server_thread.start()

        if not no_browser:
            if _wait_for_port(host, port):
                webbrowser.open(url)
            else:
                typer.echo(
                    f"Server did not become ready in time. Open manually: {url}",
                    err=True,
                )

        # Block the main thread until the server exits or the user interrupts.
        server_thread.join()
    except Exit:
        raise
    except KeyboardInterrupt:
        if not json_out:
            typer.echo("Stopped.", err=True)
        raise Exit(0)
    except Exception as e:
        if not json_out:
            typer.echo(f"error: {e}", err=True)
        raise Exit(EXIT_INTERNAL)


def main() -> None:
    """CLI entrypoint (console script agentdbg.cli:main)."""
    app()


if __name__ == "__main__":
    main()
