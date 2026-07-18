"""Security regression tests for Phase 10 release tooling."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]


def _load(name: str, relative: str) -> Any:
    path = REPOSITORY_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Phase 10 release module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load("codescope_phase10_benchmark_security", "scripts/benchmark.py")
verifier = _load("codescope_phase10_verifier_security", "scripts/verify_clean_setup.py")


def test_expected_release_errors_do_not_reflect_attacker_paths_or_environment() -> None:
    # Arrange
    attacker = "/home/private/Downloads/CodeScope\nPRIVATE_TOKEN"
    benchmark_error = benchmark.BenchmarkError(
        "BENCHMARK_FAILED",
        "The benchmark failed safely.",
        "Verify local prerequisites.",
    )
    setup_error = verifier.SetupVerificationError(
        "CLEAN_SETUP_FAILED",
        "The clean verification failed safely.",
        "Verify local prerequisites.",
    )

    # Act
    output = benchmark._error_json(benchmark_error) + verifier._error_json(setup_error)

    # Assert
    assert attacker not in output
    assert "/home/" not in output
    assert "Downloads/" not in output
    assert "PRIVATE_TOKEN" not in output
    for line in output.splitlines():
        json.loads(line)


def test_environment_sanitization_drops_common_secret_and_process_injection_variables(
    tmp_path: Path,
) -> None:
    # Arrange
    inherited = {
        "PATH": "/private/bin",
        "OPENAI_API_KEY": "PRIVATE",
        "GITHUB_TOKEN": "PRIVATE",
        "AWS_SESSION_TOKEN": "PRIVATE",
        "PYTHONPATH": "/private/python",
        "PYTHONSTARTUP": "/private/startup.py",
        "VIRTUAL_ENV": "/private/venv",
        "LD_PRELOAD": "/private/inject.so",
        "DYLD_INSERT_LIBRARIES": "/private/inject.dylib",
    }

    # Act
    result = verifier._sanitized_environment(
        inherited,
        workspace=tmp_path / "workspace",
        model_cache=tmp_path / "cache",
        uv_cache=tmp_path / "uv-cache",
        executables=(tmp_path / "bin" / "uv",),
    )

    # Assert
    serialized = json.dumps(result)
    assert "PRIVATE" not in serialized
    for name in (
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "AWS_SESSION_TOKEN",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "VIRTUAL_ENV",
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
    ):
        assert name not in result


def test_untracked_allowlist_excludes_runtime_cache_build_and_report_artifacts() -> None:
    # Arrange
    prohibited = {
        ".codescope/index.sqlite3",
        ".coverage",
        "dist/codescope.whl",
        "models/model.bin",
        "benchmark-output.json",
        "security-report/findings.json",
        "graphify-out/graph.json",
    }

    # Act / Assert
    assert prohibited.isdisjoint(verifier.AUTHORIZED_UNTRACKED_PATHS)
    for path in prohibited:
        with pytest.raises(verifier.SetupVerificationError) as raised:
            verifier._validate_untracked_paths([path])
        assert raised.value.code == "CLEAN_SETUP_UNEXPECTED_FILE"
        assert path not in raised.value.message + raised.value.suggestion


def test_benchmark_bounds_prevent_unbounded_iteration_work() -> None:
    # Arrange / Act / Assert
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.run_benchmark(iterations=10_000_000, warmup=1)
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.run_benchmark(iterations=1, warmup=10_000_000)


def test_terminal_controls_are_neutralized_in_human_release_output() -> None:
    # Arrange
    hostile = "safe\nforged\u202evalue\x1b[31m"

    # Act
    benchmark_safe = benchmark._terminal_safe(hostile)
    verifier_safe = verifier._terminal_safe(hostile)

    # Assert
    assert "\n" not in benchmark_safe + verifier_safe
    assert "\u202e" not in benchmark_safe + verifier_safe
    assert "\x1b" not in benchmark_safe + verifier_safe
    assert "�" in benchmark_safe and "�" in verifier_safe
