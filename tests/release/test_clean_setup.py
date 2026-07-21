"""Release tests for isolated candidate-clone setup verification."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]


def _load_verifier() -> Any:
    path = REPOSITORY_ROOT / "scripts" / "verify_clean_setup.py"
    spec = importlib.util.spec_from_file_location("codescope_phase10_clean_setup_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("clean-setup verifier could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _git(cwd: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _test_environment(tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def test_import_is_side_effect_free(tmp_path: Path) -> None:
    # Arrange
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)

    # Act
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.verify_clean_setup"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_sanitized_environment_keeps_only_documented_values(tmp_path: Path) -> None:
    # Arrange
    workspace = tmp_path / "workspace"
    cache = tmp_path / "model-cache"
    executable = tmp_path / "bin" / "uv"
    inherited = {
        "PATH": "/private/bin",
        "LANG": "C.UTF-8",
        "API_TOKEN": "PRIVATE",
        "PYTHONPATH": "/private/source",
        "VIRTUAL_ENV": "/private/venv",
        "AWS_SECRET_ACCESS_KEY": "PRIVATE",
    }

    # Act
    result = verifier._sanitized_environment(
        inherited,
        workspace=workspace,
        model_cache=cache,
        uv_cache=tmp_path / "uv-cache",
        executables=(executable,),
    )

    # Assert
    assert "API_TOKEN" not in result
    assert "PYTHONPATH" not in result
    assert "VIRTUAL_ENV" not in result
    assert "AWS_SECRET_ACCESS_KEY" not in result
    assert result["HF_HUB_OFFLINE"] == "1"
    assert result["TRANSFORMERS_OFFLINE"] == "1"
    assert result["UV_CACHE_DIR"] == str(tmp_path / "uv-cache")
    assert result[verifier.REAL_VERIFICATION_VARIABLE] == "1"
    assert "PRIVATE" not in json.dumps(result)


def test_untracked_allowlist_is_exact_and_rejects_unsafe_or_unexpected_values() -> None:
    # Arrange
    authorized = ["scripts/benchmark.py", "docs/SECURITY.md"]

    # Act
    result = verifier._validate_untracked_paths(authorized)

    # Assert
    assert result == ("docs/SECURITY.md", "scripts/benchmark.py")
    for invalid in ("../private", "/absolute", "C:\\private", ".codescope/data"):
        with pytest.raises(verifier.SetupVerificationError):
            verifier._validate_untracked_paths([invalid])


def test_small_candidate_patch_is_materialized_copies_allowlisted_and_preserves_source(
    tmp_path: Path,
) -> None:
    # Arrange
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "CodeScope Test")
    _git(source, "config", "user.email", "codescope@example.invalid")
    (source / "README.md").write_text("before\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-m", "test baseline")
    (source / "README.md").write_text("after\n", encoding="utf-8")
    script = source / "scripts" / "benchmark.py"
    script.parent.mkdir()
    script.write_text("VALUE = 1\n", encoding="utf-8")
    status_before = _git(source, "status", "--porcelain=v1")
    runner = verifier.SubprocessRunner()
    git_path = Path(shutil_which_or_fail("git"))
    environment = _test_environment(tmp_path)
    clone = tmp_path / "clone"
    patch = _git(source, "diff", "--binary", "--no-ext-diff", "HEAD", "--")

    # Act
    _head, copied = verifier._materialize_candidate(
        runner,
        git_path,
        source_root=source,
        clone_root=clone,
        environment=environment,
        timeout_seconds=30,
    )

    # Assert
    assert len(patch.encode("utf-8")) <= verifier._MAX_OUTPUT_BYTES
    assert copied == 1
    assert (clone / "README.md").read_text(encoding="utf-8") == "after\n"
    assert (clone / "scripts" / "benchmark.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _git(source, "status", "--porcelain=v1") == status_before


def _staged_binary_candidate(tmp_path: Path, *, payload_size: int) -> tuple[Path, bytes]:
    """Create a repository with one staged binary candidate file."""
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "CodeScope Test")
    _git(source, "config", "user.email", "codescope@example.invalid")
    (source / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-m", "test baseline")
    payload = os.urandom(payload_size)
    (source / "candidate.bin").write_bytes(payload)
    _git(source, "add", "candidate.bin")
    return source, payload


def test_binary_candidate_above_generic_cap_below_patch_cap_is_materialized(
    tmp_path: Path,
) -> None:
    # Arrange
    source, payload = _staged_binary_candidate(
        tmp_path,
        payload_size=2 * 1024 * 1024,
    )
    patch = _git(source, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    clone = tmp_path / "clone"

    # Act
    _head, copied = verifier._materialize_candidate(
        verifier.SubprocessRunner(),
        Path(shutil_which_or_fail("git")),
        source_root=source,
        clone_root=clone,
        environment=_test_environment(tmp_path),
        timeout_seconds=30,
    )

    # Assert
    assert verifier._MAX_OUTPUT_BYTES < len(patch.encode("utf-8")) <= verifier._MAX_PATCH_BYTES
    assert copied == 0
    assert (clone / "candidate.bin").read_bytes() == payload


def test_binary_candidate_above_patch_cap_is_rejected_before_clone(tmp_path: Path) -> None:
    # Arrange
    source, _payload = _staged_binary_candidate(
        tmp_path,
        payload_size=verifier._MAX_PATCH_BYTES,
    )
    patch = _git(source, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    clone = tmp_path / "clone"

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier._materialize_candidate(
            verifier.SubprocessRunner(),
            Path(shutil_which_or_fail("git")),
            source_root=source,
            clone_root=clone,
            environment=_test_environment(tmp_path),
            timeout_seconds=30,
        )

    # Assert
    assert len(patch.encode("utf-8")) > verifier._MAX_PATCH_BYTES
    assert raised.value.code == "CLEAN_SETUP_OUTPUT_FAILED"
    assert not clone.exists()


def shutil_which_or_fail(name: str) -> str:
    import shutil

    located = shutil.which(name)
    if located is None:
        pytest.fail(f"required test executable unavailable: {name}")
    return located


def test_materialize_candidate_rejects_unexpected_untracked_file_before_clone(
    tmp_path: Path,
) -> None:
    # Arrange
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "CodeScope Test")
    _git(source, "config", "user.email", "codescope@example.invalid")
    (source / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-m", "test baseline")
    (source / "private.tmp").write_text("PRIVATE\n", encoding="utf-8")

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier._materialize_candidate(
            verifier.SubprocessRunner(),
            Path(shutil_which_or_fail("git")),
            source_root=source,
            clone_root=tmp_path / "clone",
            environment=_test_environment(tmp_path),
            timeout_seconds=30,
        )

    # Assert
    assert raised.value.code == "CLEAN_SETUP_UNEXPECTED_FILE"
    assert not (tmp_path / "clone").exists()
    assert "private.tmp" not in raised.value.message + raised.value.suggestion


def test_authorized_untracked_symlink_is_rejected_without_copying_target(tmp_path: Path) -> None:
    # Arrange
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    external = tmp_path / "external.py"
    external.write_text("PRIVATE = True\n", encoding="utf-8")
    try:
        (source / "scripts" / "benchmark.py").symlink_to(external)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier._candidate_file(source, "scripts/benchmark.py")

    # Assert
    assert raised.value.code == "CLEAN_SETUP_CANDIDATE_FAILED"
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_subprocess_timeout_terminates_descendant_before_it_can_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    marker = tmp_path / "leaked-child"
    child = (
        f"import pathlib,time; time.sleep(2); pathlib.Path({str(marker)!r}).write_text('leaked')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    )
    monkeypatch.setattr(verifier, "_MIN_TIMEOUT_SECONDS", 1)

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier.SubprocessRunner().run(
            [sys.executable, "-c", parent],
            cwd=tmp_path,
            environment=_test_environment(tmp_path),
            timeout_seconds=1,
        )
    time.sleep(2.2)

    # Assert
    assert raised.value.code == "CLEAN_SETUP_TIMEOUT"
    assert not marker.exists()


def test_subprocess_output_is_bounded_and_utf8(tmp_path: Path) -> None:
    # Arrange / Act
    result = verifier.SubprocessRunner().run(
        [sys.executable, "-c", "print('safe output')"],
        cwd=tmp_path,
        environment=_test_environment(tmp_path),
        timeout_seconds=30,
    )

    # Assert
    assert result.returncode == 0
    assert result.stdout == "safe output\n"
    assert result.stderr == ""
    assert result.duration_ns >= 0


def test_ordinary_subprocess_output_above_generic_cap_is_rejected(tmp_path: Path) -> None:
    # Arrange
    command = [
        sys.executable,
        "-c",
        f"import sys; sys.stdout.write('x' * {verifier._MAX_OUTPUT_BYTES + 1})",
    ]

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier.SubprocessRunner().run(
            command,
            cwd=tmp_path,
            environment=_test_environment(tmp_path),
            timeout_seconds=30,
        )

    # Assert
    assert raised.value.code == "CLEAN_SETUP_OUTPUT_FAILED"


def test_candidate_patch_capture_rejects_any_non_candidate_command(tmp_path: Path) -> None:
    # Arrange
    command = [sys.executable, "-c", "print('not a candidate patch')"]

    # Act
    with pytest.raises(verifier.SetupVerificationError) as raised:
        verifier.SubprocessRunner().run_candidate_patch(
            command,
            cwd=tmp_path,
            environment=_test_environment(tmp_path),
            timeout_seconds=30,
        )

    # Assert
    assert raised.value.code == "CLEAN_SETUP_COMMAND_FAILED"


def test_report_json_and_human_output_are_path_private() -> None:
    # Arrange
    report = verifier.CleanSetupReport(
        schema_version=1,
        candidate={
            "base_revision": "a" * 40,
            "tracked_patch_applied": True,
            "authorized_untracked_files": 12,
        },
        commands=("uv sync --locked",),
        checks={
            "python_fixture_files": 4,
            "expected_email_validator_found": True,
            "mcp_tools": list(verifier._EXPECTED_TOOLS),
            "demo_recommendation": "REUSE",
            "source_repository_unchanged": True,
            "model_download_included": False,
        },
        timing=verifier.VerificationTiming(1.0, 2.0, 3.0, 4.0),
        cleanup={
            "clone_removed": True,
            "runtime_removed": True,
            "source_repository_unchanged": True,
        },
    )

    # Act
    encoded = verifier.render_json(report)
    human = verifier.render_human(report)

    # Assert
    assert json.loads(encoded)["checks"]["demo_recommendation"] == "REUSE"
    assert "Setup to demo: 3.0 ms" in human
    assert str(REPOSITORY_ROOT) not in encoded + human
    assert "/tmp/" not in encoded + human
    assert "model-cache" not in encoded + human


def test_real_candidate_clone_when_explicitly_enabled() -> None:
    # Arrange
    if os.environ.get(verifier.REAL_VERIFICATION_VARIABLE) != "1":
        pytest.skip(
            f"set {verifier.REAL_VERIFICATION_VARIABLE}=1 to run the real clean-candidate test"
        )

    # Act
    report = verifier.verify_clean_setup(timeout_seconds=300)

    # Assert
    assert report.timing.setup_to_demo_ms < 300_000
    assert report.checks["demo_recommendation"] == "REUSE"
    assert report.checks["source_repository_unchanged"] is True
    assert all(report.cleanup.values())
