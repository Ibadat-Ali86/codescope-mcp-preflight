"""Deterministic release tests for the Phase 10 benchmark boundary."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]


def _load_benchmark() -> Any:
    path = REPOSITORY_ROOT / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("codescope_phase10_benchmark_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("benchmark module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load_benchmark()


def _report() -> Any:
    latency = {"samples": 3, "median_ms": 2.0, "minimum_ms": 1.0, "maximum_ms": 3.0}
    return benchmark.BenchmarkReport(
        schema_version=1,
        environment={
            "python_version": "3.12.13",
            "platform_family": "Linux",
            "logical_cpu_count": 4,
            "codescope_version": "0.1.0",
            "mcp_version": "1.28.1",
        },
        fixture={
            "name": "committed sample_python fixture",
            "file_count": 4,
            "symbol_count": 11,
            "chunk_count": 16,
            "model": "sentence-transformers/all-MiniLM-L6-v2",
        },
        methodology={
            "timer": "time.perf_counter_ns",
            "query_warmup_iterations": 1,
            "query_measured_iterations": 3,
            "indexing_iterations": 1,
            "demo_iterations": 1,
            "network_during_model_use": False,
            "model_download_time_included": False,
        },
        indexing={"iterations": 1, "duration_ms": 10.0},
        queries={
            "authoritative_status_ms": latency,
            "semantic_search_ms": latency,
            "exact_symbol_lookup_ms": latency,
            "similar_code_lookup_ms": latency,
        },
        mcp={
            "transport_startup_ms": 1.0,
            "initialization_ms": 2.0,
            "tool_round_trip_ms": latency,
            "calls_per_iteration": 4,
            "tools": [
                "search_code",
                "find_symbol",
                "find_similar",
                "list_indexed_files",
            ],
        },
        demo={
            "iterations": 1,
            "duration_ms": 12.0,
            "recommendation": "REUSE",
            "source_unchanged": True,
            "duplicate_avoided": True,
        },
        cleanup={
            "workspace_removed": True,
            "runtime_removed": True,
            "fixture_unchanged": True,
        },
        total_duration_ms=30.0,
    )


def test_import_is_side_effect_free(tmp_path: Path) -> None:
    # Arrange
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)

    # Act
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.benchmark"],
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
    assert not (REPOSITORY_ROOT / ".codescope").exists()


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        (["--iterations", "0"], "between 1 and 50"),
        (["--iterations", "51"], "between 1 and 50"),
        (["--warmup", "0"], "between 1 and 10"),
        (["--warmup", "11"], "between 1 and 10"),
    ],
)
def test_argument_bounds_fail_before_benchmark_execution(
    arguments: list[str],
    fragment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange / Act
    with pytest.raises(SystemExit) as raised:
        benchmark._parser().parse_args(arguments)
    captured = capsys.readouterr()

    # Assert
    assert raised.value.code == 2
    assert fragment in captured.err


def test_latency_statistics_are_deterministic_and_nonnegative() -> None:
    # Arrange
    observations = [3_000_000, 1_000_000, 2_000_000]

    # Act
    result = benchmark.LatencyStatistics.from_nanoseconds(observations)

    # Assert
    assert result.samples == 3
    assert result.median_ms == 2.0
    assert result.minimum_ms == 1.0
    assert result.maximum_ms == 3.0


@pytest.mark.parametrize("observations", [[], [-1], [True]])
def test_latency_statistics_reject_invalid_observations(observations: list[Any]) -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="nonnegative integers"):
        benchmark.LatencyStatistics.from_nanoseconds(observations)


def test_measure_operation_uses_exact_warmup_and_iteration_counts() -> None:
    # Arrange
    calls = 0

    def operation() -> int:
        nonlocal calls
        calls += 1
        return calls

    # Act
    statistics, result = benchmark._measure_operation(operation, warmup=2, iterations=4)

    # Assert
    assert calls == 6
    assert result == 6
    assert statistics.samples == 4


def test_report_json_is_parseable_source_free_and_path_private() -> None:
    # Arrange
    report = _report()

    # Act
    rendered = benchmark.render_json(report)
    payload = json.loads(rendered)

    # Assert
    assert payload["schema_version"] == 1
    assert payload["demo"]["recommendation"] == "REUSE"
    assert payload["cleanup"]["workspace_removed"] is True
    assert "snippet" not in rendered
    assert "embedding" not in rendered
    assert str(REPOSITORY_ROOT) not in rendered
    assert "/tmp/" not in rendered


def test_human_report_is_concise_and_fixture_scoped() -> None:
    # Arrange / Act
    rendered = benchmark.render_human(_report())

    # Assert
    assert "4 files, 11 symbols, 16 chunks" in rendered
    assert "Fixed demo: 12.0 ms (REUSE)" in rendered
    assert "intentionally small fixture" in rendered
    assert "no quality claim" in rendered


def test_run_benchmark_rejects_invalid_bounds_without_loading_model() -> None:
    # Arrange / Act / Assert
    with pytest.raises(benchmark.BenchmarkError) as raised:
        benchmark.run_benchmark(iterations=0, warmup=1)
    assert raised.value.code == "BENCHMARK_INVALID_ARGUMENT"


def test_error_json_is_fixed_and_does_not_reflect_private_values() -> None:
    # Arrange
    error = benchmark.BenchmarkError(
        "BENCHMARK_FAILED",
        "The benchmark failed safely.",
        "Verify the local prerequisites.",
    )

    # Act
    rendered = benchmark._error_json(error)

    # Assert
    assert json.loads(rendered)["code"] == "BENCHMARK_FAILED"
    assert "/home/" not in rendered
    assert "PRIVATE" not in rendered


def test_fixture_copy_rejects_link_content_when_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    external = tmp_path / "external.py"
    external.write_text("PRIVATE = True\n", encoding="utf-8")
    try:
        (fixture / "linked.py").symlink_to(external)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")
    monkeypatch.setattr(benchmark, "SOURCE_FIXTURE", fixture)

    # Act
    with pytest.raises(benchmark.BenchmarkError) as raised:
        benchmark._safe_fixture_copy(tmp_path / "copy")

    # Assert
    assert raised.value.code == "BENCHMARK_FIXTURE_FAILED"
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion
