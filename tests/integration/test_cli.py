"""Explicit offline real-model integration test for the Phase 7 CLI workflow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codescope.cli import app

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "sample_python"
runner = CliRunner()


def _fixture_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_offline_real_model_cli_index_status_search_json_and_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    if os.environ.get("CODESCOPE_RUN_REAL_MODEL") != "1":
        pytest.skip("explicit real-model validation is not enabled")
    cache_value = os.environ.get("CODESCOPE_MODEL_CACHE_DIR")
    if not cache_value:
        pytest.fail("CODESCOPE_MODEL_CACHE_DIR must identify the external validation cache")
    cache = Path(cache_value).resolve()
    repository = REPOSITORY_ROOT.resolve()
    if cache == repository or cache.is_relative_to(repository):
        pytest.fail("the real-model cache must remain outside the repository")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = workspace / "sample_python"
    shutil.copytree(FIXTURE_ROOT, fixture)
    shutil.copy2(REPOSITORY_ROOT / "codescope.toml", workspace / "codescope.toml")
    before = _fixture_hashes(fixture)
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("HF_HOME", str(cache))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    # Act
    indexed = runner.invoke(app, ["index", "sample_python"])
    status = runner.invoke(app, ["status"])
    human = runner.invoke(app, ["search", "email validation"])
    machine = runner.invoke(app, ["search", "email validation", "--json"])
    reset = runner.invoke(app, ["reset", "--yes"])
    after_reset = runner.invoke(app, ["status"])

    # Assert
    assert indexed.exit_code == 0, indexed.stderr
    assert "Accepted files" in indexed.stdout and "4" in indexed.stdout
    assert "Symbols" in indexed.stdout and "11" in indexed.stdout
    assert status.exit_code == 0, status.stderr
    assert all(field in status.stdout for field in ("Ready", "Files", "Symbols", "Chunks"))
    assert human.exit_code == 0, human.stderr
    assert "validators.py:6-9" in human.stdout
    assert "validate_email" in human.stdout
    assert machine.exit_code == 0, machine.stderr
    payload = json.loads(machine.stdout)
    validator = next(item for item in payload if item["symbol"] == "validate_email")
    assert validator["file"] == "validators.py"
    assert (validator["start_line"], validator["end_line"]) == (6, 9)
    assert reset.exit_code == 0, reset.stderr
    assert not (workspace / ".codescope").exists()
    assert _fixture_hashes(fixture) == before
    assert after_reset.exit_code == 1
    assert "INDEX_NOT_FOUND" in after_reset.stderr
