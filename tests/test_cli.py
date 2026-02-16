"""
CLI tests using Typer CliRunner.
Every test uses temp dir via AGENTDBG_DATA_DIR (fixture restores env).
Covers: list (empty dir exit 0), export (missing run exit 2), list --json (valid JSON with spec_version, runs).
"""
import json

import pytest
from typer.testing import CliRunner

from agentdbg.cli import app

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


def test_list_json_outputs_valid_json_spec_version_and_runs(empty_data_dir):
    """agentdbg list --json outputs valid JSON with keys spec_version and runs."""
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "spec_version" in data
    assert "runs" in data
    assert data["spec_version"] == "0.1"
    assert isinstance(data["runs"], list)
