"""Fixture-scoped offline benchmark for the completed CodeScope MVP."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Protocol, cast

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from codescope import __version__
from codescope.config import AppConfig, load_config
from codescope.engine import QueryEngine
from codescope.exceptions import CodeScopeError
from codescope.indexer import RepositoryIndexer

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "sample_python"
CONFIG_TEMPLATE: Final = REPOSITORY_ROOT / "codescope.toml"
_CONFIG_ROOT_LINE: Final = 'root = "."'
_ISOLATED_ROOT_LINE: Final = 'root = "repository"'
_SEMANTIC_QUERY: Final = "email validation"
_SYMBOL_QUERY: Final = "validate_email"
_SIMILAR_QUERY: Final = "def is_valid_email(email: str) -> bool: ..."
_MIN_ITERATIONS: Final = 1
_MAX_ITERATIONS: Final = 50
_MIN_WARMUP: Final = 1
_MAX_WARMUP: Final = 10
_MCP_TIMEOUT_SECONDS: Final = 120


class BenchmarkError(Exception):
    """Safe expected failure at the benchmark boundary."""

    def __init__(self, code: str, message: str, suggestion: str) -> None:
        self.code = code
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class _DemoReport(Protocol):
    recommendation: str
    source_unchanged: bool
    duplicate_avoided: bool


class _DemoModule(Protocol):
    async def run_demo(self) -> _DemoReport: ...


@dataclass(frozen=True, slots=True)
class LatencyStatistics:
    """Summary of repeated high-resolution latency observations."""

    samples: int
    median_ms: float
    minimum_ms: float
    maximum_ms: float

    @classmethod
    def from_nanoseconds(cls, values: Sequence[int]) -> LatencyStatistics:
        """Build a rounded latency summary from positive nanosecond observations."""
        if not values or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values
        ):
            raise ValueError("Latency observations must be nonnegative integers.")
        milliseconds = [value / 1_000_000 for value in values]
        return cls(
            samples=len(values),
            median_ms=round(float(statistics.median(milliseconds)), 3),
            minimum_ms=round(min(milliseconds), 3),
            maximum_ms=round(max(milliseconds), 3),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Sanitized machine-readable benchmark result."""

    schema_version: int
    environment: Mapping[str, object]
    fixture: Mapping[str, object]
    methodology: Mapping[str, object]
    indexing: Mapping[str, object]
    queries: Mapping[str, object]
    mcp: Mapping[str, object]
    demo: Mapping[str, object]
    cleanup: Mapping[str, object]
    total_duration_ms: float

    def to_dict(self) -> dict[str, object]:
        """Return the stable external JSON object contract."""
        return {
            "schema_version": self.schema_version,
            "environment": dict(self.environment),
            "fixture": dict(self.fixture),
            "methodology": dict(self.methodology),
            "indexing": dict(self.indexing),
            "queries": dict(self.queries),
            "mcp": dict(self.mcp),
            "demo": dict(self.demo),
            "cleanup": dict(self.cleanup),
            "total_duration_ms": self.total_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class _McpMeasurements:
    transport_startup_ms: float
    initialization_ms: float
    round_trip: LatencyStatistics
    tools: tuple[str, ...]


def _bounded_integer(*, minimum: int, maximum: int, label: str) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{label} must be an integer") from error
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"{label} must be between {minimum} and {maximum}")
        return parsed

    return parse


def _measure_operation[ResultT](
    operation: Callable[[], ResultT],
    *,
    warmup: int,
    iterations: int,
) -> tuple[LatencyStatistics, ResultT]:
    """Warm an operation, then return measured latency and the final result."""
    if not _MIN_WARMUP <= warmup <= _MAX_WARMUP:
        raise ValueError("Warm-up count is outside the supported range.")
    if not _MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS:
        raise ValueError("Iteration count is outside the supported range.")
    result: ResultT | None = None
    for _ in range(warmup):
        result = operation()
    observations: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = operation()
        observations.append(time.perf_counter_ns() - started)
    if result is None:
        raise RuntimeError("Benchmark operation made no progress.")
    return LatencyStatistics.from_nanoseconds(observations), result


def _safe_fixture_copy(destination: Path) -> None:
    try:
        fixture = SOURCE_FIXTURE.resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        if fixture == repository or not fixture.is_relative_to(repository):
            raise OSError("fixture escaped repository")
        for candidate in fixture.rglob("*"):
            if candidate.is_symlink() or candidate.is_junction():
                raise OSError("fixture contains a link")
            if candidate.is_file() and candidate.suffix not in {".py", ".pyi"}:
                raise OSError("fixture contains an unsupported file")
        shutil.copytree(fixture, destination)
    except OSError as error:
        raise BenchmarkError(
            "BENCHMARK_FIXTURE_FAILED",
            "The committed benchmark fixture could not be copied safely.",
            "Restore the committed sample fixture and retry.",
        ) from error


def _write_isolated_config(destination: Path) -> None:
    try:
        template = CONFIG_TEMPLATE.read_text(encoding="utf-8")
        if template.count(_CONFIG_ROOT_LINE) != 1:
            raise ValueError("configuration root contract changed")
        isolated = template.replace(_CONFIG_ROOT_LINE, _ISOLATED_ROOT_LINE, 1)
        destination.write_text(isolated, encoding="utf-8", newline="\n")
    except (OSError, UnicodeError, ValueError) as error:
        raise BenchmarkError(
            "BENCHMARK_CONFIG_FAILED",
            "The isolated benchmark configuration could not be prepared safely.",
            "Restore the committed configuration and retry.",
        ) from error


@contextmanager
def _offline_environment() -> Iterator[None]:
    cache_value = os.environ.get("CODESCOPE_MODEL_CACHE_DIR")
    try:
        if not cache_value:
            raise OSError("cache is not configured")
        cache = Path(cache_value).expanduser().resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        if not cache.is_dir() or cache == repository or cache.is_relative_to(repository):
            raise OSError("cache boundary is unsafe")
    except OSError as error:
        raise BenchmarkError(
            "BENCHMARK_MODEL_UNAVAILABLE",
            "The prepared external model cache is unavailable.",
            "Set CODESCOPE_MODEL_CACHE_DIR to the prepared external cache and retry offline.",
        ) from error
    names = (
        "HF_HOME",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_HUB_DISABLE_PROGRESS_BARS",
        "TQDM_DISABLE",
    )
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(
        {
            "HF_HOME": str(cache),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "TQDM_DISABLE": "1",
        }
    )
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _codescope_command() -> str:
    executable = Path(sys.executable).with_name("codescope.exe" if os.name == "nt" else "codescope")
    if executable.is_file():
        return str(executable)
    located = shutil.which("codescope")
    if located is None:
        raise BenchmarkError(
            "BENCHMARK_SERVER_UNAVAILABLE",
            "The CodeScope command is unavailable in the active environment.",
            "Run the benchmark through the locked uv environment.",
        )
    return located


async def _measure_mcp(workspace: Path, *, warmup: int, iterations: int) -> _McpMeasurements:
    command = _codescope_command()
    parameters = StdioServerParameters(
        command=command,
        args=["serve"],
        cwd=workspace,
        env=dict(os.environ),
    )
    expected_tools = (
        "search_code",
        "find_symbol",
        "find_similar",
        "list_indexed_files",
    )
    calls: tuple[tuple[str, dict[str, object]], ...] = (
        ("list_indexed_files", {"language": "python"}),
        ("search_code", {"query": _SEMANTIC_QUERY, "language": "python", "limit": 5}),
        ("find_symbol", {"name": _SYMBOL_QUERY, "kind": "function", "limit": 20}),
        (
            "find_similar",
            {"code_snippet": _SIMILAR_QUERY, "language": "python", "limit": 3},
        ),
    )
    transport_started = time.perf_counter_ns()
    with Path(os.devnull).open("w", encoding="utf-8") as diagnostics:
        async with asyncio.timeout(_MCP_TIMEOUT_SECONDS):
            async with stdio_client(parameters, errlog=diagnostics) as (read_stream, write_stream):
                transport_elapsed = time.perf_counter_ns() - transport_started
                async with ClientSession(read_stream, write_stream) as session:
                    initialization_started = time.perf_counter_ns()
                    await session.initialize()
                    initialization_elapsed = time.perf_counter_ns() - initialization_started
                    listed = await session.list_tools()
                    tool_names = tuple(tool.name for tool in listed.tools)
                    if tool_names != expected_tools:
                        raise BenchmarkError(
                            "BENCHMARK_MCP_FAILED",
                            "The MCP server did not expose the expected read-only tool set.",
                            "Verify the current CodeScope server and retry.",
                        )
                    for _ in range(warmup):
                        for name, arguments in calls:
                            result = await session.call_tool(name, arguments)
                            if result.isError:
                                raise BenchmarkError(
                                    "BENCHMARK_MCP_FAILED",
                                    "An MCP warm-up call failed safely.",
                                    "Verify the isolated index and retry.",
                                )
                    observations: list[int] = []
                    for _ in range(iterations):
                        for name, arguments in calls:
                            started = time.perf_counter_ns()
                            result = await session.call_tool(name, arguments)
                            observations.append(time.perf_counter_ns() - started)
                            if result.isError:
                                raise BenchmarkError(
                                    "BENCHMARK_MCP_FAILED",
                                    "A measured MCP call failed safely.",
                                    "Verify the isolated index and retry.",
                                )
    return _McpMeasurements(
        transport_startup_ms=round(transport_elapsed / 1_000_000, 3),
        initialization_ms=round(initialization_elapsed / 1_000_000, 3),
        round_trip=LatencyStatistics.from_nanoseconds(observations),
        tools=tool_names,
    )


def _load_demo_module() -> _DemoModule:
    path = REPOSITORY_ROOT / "scripts" / "demo.py"
    spec = importlib.util.spec_from_file_location("codescope_phase10_demo", path)
    if spec is None or spec.loader is None:
        raise BenchmarkError(
            "BENCHMARK_DEMO_FAILED",
            "The fixed demonstration module could not be loaded.",
            "Restore scripts/demo.py and retry.",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise BenchmarkError(
            "BENCHMARK_DEMO_FAILED",
            "The fixed demonstration module could not be loaded.",
            "Restore scripts/demo.py and retry.",
        ) from error
    return cast(_DemoModule, module)


def _run_fixed_demo() -> tuple[float, _DemoReport]:
    module = _load_demo_module()
    started = time.perf_counter_ns()
    try:
        report = asyncio.run(module.run_demo())
    except BenchmarkError:
        raise
    except Exception as error:
        raise BenchmarkError(
            "BENCHMARK_DEMO_FAILED",
            "The fixed duplication-prevention demo failed during measurement.",
            "Verify the prepared model cache and retry offline.",
        ) from error
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    if (
        report.recommendation != "REUSE"
        or report.source_unchanged is not True
        or report.duplicate_avoided is not True
    ):
        raise BenchmarkError(
            "BENCHMARK_DEMO_FAILED",
            "The fixed demonstration did not produce the required safe decision.",
            "Inspect the Phase 9 evidence path before retrying.",
        )
    return elapsed_ms, report


def _latency_dict(value: LatencyStatistics) -> dict[str, object]:
    return asdict(value)


def _query_measurements(
    config: AppConfig,
    *,
    warmup: int,
    iterations: int,
) -> dict[str, object]:
    engine = QueryEngine(config)
    status_stats, status = _measure_operation(
        engine.get_index_status,
        warmup=warmup,
        iterations=iterations,
    )
    semantic_stats, semantic = _measure_operation(
        lambda: engine.search_code(_SEMANTIC_QUERY, language="python", limit=5),
        warmup=warmup,
        iterations=iterations,
    )
    symbol_stats, symbols = _measure_operation(
        lambda: engine.find_symbol(_SYMBOL_QUERY, kind="function", limit=20),
        warmup=warmup,
        iterations=iterations,
    )
    similar_stats, similar = _measure_operation(
        lambda: engine.find_similar(_SIMILAR_QUERY, language="python", limit=3),
        warmup=warmup,
        iterations=iterations,
    )
    if not any(result.symbol == _SYMBOL_QUERY for result in semantic):
        raise BenchmarkError(
            "BENCHMARK_QUERY_FAILED",
            "Semantic search did not return the expected fixture evidence.",
            "Verify the prepared model and fixture before retrying.",
        )
    if not symbols or symbols[0].name != _SYMBOL_QUERY or not similar:
        raise BenchmarkError(
            "BENCHMARK_QUERY_FAILED",
            "A required fixture query did not return expected evidence.",
            "Verify the isolated index and retry.",
        )
    if not status.index_exists:
        raise BenchmarkError(
            "BENCHMARK_QUERY_FAILED",
            "The authoritative benchmark index status is unavailable.",
            "Rebuild the isolated fixture index and retry.",
        )
    return {
        "authoritative_status_ms": _latency_dict(status_stats),
        "semantic_search_ms": _latency_dict(semantic_stats),
        "exact_symbol_lookup_ms": _latency_dict(symbol_stats),
        "similar_code_lookup_ms": _latency_dict(similar_stats),
    }


def run_benchmark(*, iterations: int, warmup: int) -> BenchmarkReport:
    """Run the complete isolated cache-only fixture benchmark."""
    if not _MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS:
        raise BenchmarkError(
            "BENCHMARK_INVALID_ARGUMENT",
            "The measured iteration count is outside the supported range.",
            f"Use a value from {_MIN_ITERATIONS} through {_MAX_ITERATIONS}.",
        )
    if not _MIN_WARMUP <= warmup <= _MAX_WARMUP:
        raise BenchmarkError(
            "BENCHMARK_INVALID_ARGUMENT",
            "The warm-up count is outside the supported range.",
            f"Use a value from {_MIN_WARMUP} through {_MAX_WARMUP}.",
        )
    total_started = time.perf_counter_ns()
    workspace_removed = False
    runtime_removed = False
    fixture_unchanged = False
    fixture_data: Mapping[str, object] | None = None
    indexing_data: Mapping[str, object] | None = None
    query_data: Mapping[str, object] | None = None
    mcp_data: Mapping[str, object] | None = None
    demo_data: Mapping[str, object] | None = None
    with _offline_environment():
        temporary = tempfile.TemporaryDirectory(prefix="codescope-benchmark-")
        workspace = Path(temporary.name)
        try:
            fixture = workspace / "repository"
            _safe_fixture_copy(fixture)
            before_hashes = {
                path.relative_to(fixture).as_posix(): path.read_bytes()
                for path in sorted(fixture.rglob("*"))
                if path.is_file()
            }
            config_path = workspace / "codescope.toml"
            _write_isolated_config(config_path)
            config = load_config(config_path)
            indexing_started = time.perf_counter_ns()
            summary = RepositoryIndexer(config).rebuild(allow_model_download=False)
            indexing_ms = round((time.perf_counter_ns() - indexing_started) / 1_000_000, 3)
            queries = _query_measurements(config, warmup=warmup, iterations=iterations)
            mcp = asyncio.run(_measure_mcp(workspace, warmup=warmup, iterations=iterations))
            demo_ms, _demo_report = _run_fixed_demo()
            after_hashes = {
                path.relative_to(fixture).as_posix(): path.read_bytes()
                for path in sorted(fixture.rglob("*"))
                if path.is_file()
            }
            fixture_unchanged = before_hashes == after_hashes
            if not fixture_unchanged:
                raise BenchmarkError(
                    "BENCHMARK_FIXTURE_FAILED",
                    "The benchmark fixture changed during the read-only workflow.",
                    "Inspect the indexing and query boundaries before retrying.",
                )
            fixture_data = {
                "name": "committed sample_python fixture",
                "file_count": summary.total_files,
                "symbol_count": summary.total_symbols,
                "chunk_count": summary.total_chunks,
                "model": config.embeddings.model,
            }
            indexing_data = {
                "iterations": 1,
                "duration_ms": indexing_ms,
            }
            query_data = queries
            mcp_data = {
                "transport_startup_ms": mcp.transport_startup_ms,
                "initialization_ms": mcp.initialization_ms,
                "tool_round_trip_ms": _latency_dict(mcp.round_trip),
                "calls_per_iteration": 4,
                "tools": list(mcp.tools),
            }
            demo_data = {
                "iterations": 1,
                "duration_ms": demo_ms,
                "recommendation": "REUSE",
                "source_unchanged": True,
                "duplicate_avoided": True,
            }
        except CodeScopeError as error:
            raise BenchmarkError(
                error.code.value,
                error.message,
                error.suggestion,
            ) from error
        finally:
            runtime = workspace / ".codescope"
            temporary.cleanup()
            workspace_removed = not workspace.exists()
            runtime_removed = not runtime.exists()
    if any(
        value is None for value in (fixture_data, indexing_data, query_data, mcp_data, demo_data)
    ):
        raise BenchmarkError(
            "BENCHMARK_FAILED",
            "The benchmark did not produce a complete result.",
            "Review the local setup and retry.",
        )
    total_ms = round((time.perf_counter_ns() - total_started) / 1_000_000, 3)
    return BenchmarkReport(
        schema_version=1,
        environment={
            "python_version": platform.python_version(),
            "platform_family": platform.system() or "Unknown",
            "logical_cpu_count": os.cpu_count(),
            "codescope_version": __version__,
            "mcp_version": importlib.metadata.version("mcp"),
        },
        fixture=cast(Mapping[str, object], fixture_data),
        methodology={
            "timer": "time.perf_counter_ns",
            "query_warmup_iterations": warmup,
            "query_measured_iterations": iterations,
            "indexing_iterations": 1,
            "demo_iterations": 1,
            "network_during_model_use": False,
            "model_download_time_included": False,
        },
        indexing=cast(Mapping[str, object], indexing_data),
        queries=cast(Mapping[str, object], query_data),
        mcp=cast(Mapping[str, object], mcp_data),
        demo=cast(Mapping[str, object], demo_data),
        cleanup={
            "workspace_removed": workspace_removed,
            "runtime_removed": runtime_removed,
            "fixture_unchanged": fixture_unchanged,
        },
        total_duration_ms=total_ms,
    )


def _terminal_safe(value: str) -> str:
    return "".join(
        "�"
        if unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        else character
        for character in value
    )


def render_json(report: BenchmarkReport) -> str:
    """Render one deterministic JSON object with no path-bearing diagnostics."""
    return (
        json.dumps(
            report.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def render_human(report: BenchmarkReport) -> str:
    """Render a concise fixture-scoped benchmark summary."""
    query = report.queries
    semantic = query["semantic_search_ms"]
    symbol = query["exact_symbol_lookup_ms"]
    similar = query["similar_code_lookup_ms"]
    if not all(isinstance(value, Mapping) for value in (semantic, symbol, similar)):
        raise ValueError("Benchmark query statistics are invalid.")
    semantic_values = cast(Mapping[str, object], semantic)
    symbol_values = cast(Mapping[str, object], symbol)
    similar_values = cast(Mapping[str, object], similar)
    round_trip = report.mcp["tool_round_trip_ms"]
    if not isinstance(round_trip, Mapping):
        raise ValueError("Benchmark MCP statistics are invalid.")
    lines = [
        "CodeScope fixture benchmark",
        (
            "Fixture: "
            f"{report.fixture['file_count']} files, "
            f"{report.fixture['symbol_count']} symbols, "
            f"{report.fixture['chunk_count']} chunks"
        ),
        f"Indexing: {report.indexing['duration_ms']} ms",
        f"Semantic median: {semantic_values['median_ms']} ms",
        f"Symbol median: {symbol_values['median_ms']} ms",
        f"Similar-code median: {similar_values['median_ms']} ms",
        f"MCP initialization: {report.mcp['initialization_ms']} ms",
        f"MCP round-trip median: {round_trip['median_ms']} ms",
        f"Fixed demo: {report.demo['duration_ms']} ms (REUSE)",
        f"Total: {report.total_duration_ms} ms",
        "Scope: intentionally small fixture; model download excluded; no quality claim.",
    ]
    return "\n".join(_terminal_safe(line) for line in lines) + "\n"


def _error_json(error: BenchmarkError) -> str:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "error": True,
                "code": error.code,
                "message": error.message,
                "suggestion": error.suggestion,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure the existing CodeScope MVP on its committed fixture, offline."
    )
    parser.add_argument(
        "--iterations",
        type=_bounded_integer(
            minimum=_MIN_ITERATIONS,
            maximum=_MAX_ITERATIONS,
            label="iterations",
        ),
        default=5,
        help="measured query/MCP iterations (1-50; default: 5)",
    )
    parser.add_argument(
        "--warmup",
        type=_bounded_integer(minimum=_MIN_WARMUP, maximum=_MAX_WARMUP, label="warmup"),
        default=1,
        help="unmeasured query/MCP warm-up iterations (1-10; default: 1)",
    )
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the isolated benchmark with safe deterministic output."""
    arguments = _parser().parse_args(argv)
    try:
        report = run_benchmark(iterations=arguments.iterations, warmup=arguments.warmup)
    except BenchmarkError as error:
        if arguments.json:
            sys.stdout.write(_error_json(error))
        else:
            sys.stderr.write(
                f"Error [{_terminal_safe(error.code)}]: {_terminal_safe(error.message)}\n"
                f"Suggestion: {_terminal_safe(error.suggestion)}\n"
            )
        return 1
    except Exception as error:
        unexpected = BenchmarkError(
            "BENCHMARK_FAILED",
            "The fixture benchmark could not complete safely.",
            "Verify the locked environment and prepared model cache, then retry.",
        )
        unexpected.__cause__ = error
        if arguments.json:
            sys.stdout.write(_error_json(unexpected))
        else:
            sys.stderr.write(
                f"Error [{unexpected.code}]: {unexpected.message}\n"
                f"Suggestion: {unexpected.suggestion}\n"
            )
        return 1
    sys.stdout.write(render_json(report) if arguments.json else render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
