"""
CLI tests using Typer's CliRunner.

Covers: list (empty dir, --json), export (missing run → exit 2).
View is not tested (it blocks).
"""
import json

import pytest
from typer.testing import CliRunner

from agentdbg.cli import app

runner = CliRunner()


@pytest.fixture
def empty_data_dir(temp_data_dir):
    """Alias: temp_data_dir is already an empty runs dir when AGENTDBG_DATA_DIR is set."""
    return temp_data_dir


def test_list_empty_dir_exit_zero_and_header(empty_data_dir):
    """agentdbg list on empty dir returns exit 0 and prints table header."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "run_id" in result.output
    assert "run_name" in result.output
    assert "started_at" in result.output
    assert "status" in result.output


def test_export_missing_run_exit_two(empty_data_dir):
    """agentdbg export missing_run --out x.json returns exit code 2."""
    out_path = empty_data_dir / "x.json"
    result = runner.invoke(app, ["export", "missing_run", "--out", str(out_path)])
    assert result.exit_code == 2


def test_list_json_valid_spec_version_and_runs(empty_data_dir):
    """agentdbg list --json prints valid JSON with spec_version and runs."""
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data.get("spec_version") == "0.1"
    assert "runs" in data
    assert isinstance(data["runs"], list)
    assert len(data["runs"]) == 0
