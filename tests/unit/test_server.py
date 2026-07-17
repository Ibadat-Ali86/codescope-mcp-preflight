"""Unit tests for the lazy read-only MCP adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

import codescope.server as server_module
from codescope.config import AppConfig
from codescope.exceptions import IndexNotFoundError, InvalidQueryError
from codescope.models import ErrorResponse, IndexStatus, SearchResult, SymbolResult
from codescope.server import (
    SERVER_INSTRUCTIONS,
    QueryEngineBoundary,
    create_server,
    run_stdio_server,
)


def _search_result(*, file: str = "src/example.py", score: float = 0.75) -> SearchResult:
    return SearchResult(
        file=file,
        start_line=3,
        end_line=7,
        symbol="validate_email",
        qualified_name="validate_email",
        language="python",
        snippet="def validate_email(value: str) -> bool:\n    return '@' in value\n",
        relevance_score=score,
    )


def _symbol_result() -> SymbolResult:
    return SymbolResult(
        name="validate_email",
        qualified_name="validate_email",
        kind="function",
        file="src/example.py",
        start_line=3,
        end_line=7,
        signature="def validate_email(value: str) -> bool:",
        docstring="Validate an email address.",
    )


def _status() -> IndexStatus:
    return IndexStatus(
        index_exists=True,
        index_root=".",
        total_files=4,
        total_chunks=16,
        total_symbols=11,
        languages={"python": 4},
        last_indexed="2026-07-16T00:00:00+00:00",
        index_size_bytes=2048,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )


class FakeEngine(QueryEngineBoundary):
    """Deterministic query boundary with observable delegation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.search_results = [_search_result(score=0.9), _search_result(score=0.4)]
        self.symbol_results = [_symbol_result()]
        self.similar_results = [_search_result(score=0.8)]
        self.status = _status()
        self.failures: dict[str, BaseException] = {}

    def _record(self, operation: str, *arguments: object) -> None:
        self.calls.append((operation, arguments))
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure

    def search_code(
        self,
        query: str,
        language: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        self._record("search_code", query, language, limit)
        return self.search_results

    def find_symbol(
        self,
        name: str,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[SymbolResult]:
        self._record("find_symbol", name, kind, limit)
        return self.symbol_results

    def find_similar(
        self,
        code_snippet: str,
        language: str | None = None,
        limit: int = 3,
    ) -> list[SearchResult]:
        self._record("find_similar", code_snippet, language, limit)
        return self.similar_results

    def get_index_status(self) -> IndexStatus:
        self._record("get_index_status")
        return self.status


def _server(app_config: AppConfig, engine: QueryEngineBoundary) -> FastMCP:
    return create_server(
        config_loader=lambda: app_config,
        engine_factory=lambda _config: engine,
    )


async def _call(server: FastMCP, name: str, arguments: dict[str, Any]) -> object:
    return await server._tool_manager.call_tool(name, arguments)


def test_import_has_no_runtime_or_repository_side_effect(tmp_path: Path) -> None:
    # Arrange
    command = [sys.executable, "-c", "import codescope.server"]

    # Act
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)

    # Assert
    assert result.returncode == 0
    assert result.stdout == ""
    assert not (tmp_path / ".codescope").exists()
    assert list(tmp_path.iterdir()) == []


def test_construction_is_lazy_and_succeeds_without_index(app_config: AppConfig) -> None:
    # Arrange
    calls: list[str] = []

    def load() -> AppConfig:
        calls.append("config")
        return app_config

    def build(_config: AppConfig) -> QueryEngineBoundary:
        calls.append("engine")
        return FakeEngine()

    # Act
    server = create_server(config_loader=load, engine_factory=build)

    # Assert
    assert isinstance(server, FastMCP)
    assert calls == []
    assert not app_config.storage.path.exists()


@pytest.mark.asyncio
async def test_default_server_loads_config_and_engine_only_on_first_call() -> None:
    # Arrange
    server = create_server()

    # Act
    result = await _call(server, "list_indexed_files", {})

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "INDEX_NOT_FOUND"


def test_stdio_runner_uses_only_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    transports: list[str] = []

    class Runner:
        def run(self, transport: str) -> None:
            transports.append(transport)

    monkeypatch.setattr(server_module, "create_server", Runner)

    # Act
    run_stdio_server()

    # Assert
    assert transports == ["stdio"]


@pytest.mark.asyncio
async def test_exact_public_tools_schemas_instructions_and_annotations(
    app_config: AppConfig,
) -> None:
    # Arrange
    server = _server(app_config, FakeEngine())

    # Act
    tools = await server.list_tools()

    # Assert
    assert [tool.name for tool in tools] == [
        "search_code",
        "find_symbol",
        "find_similar",
        "list_indexed_files",
    ]
    assert not {"index", "reset", "read_file", "write_file"}.intersection(
        tool.name for tool in tools
    )
    first_policy = SERVER_INSTRUCTIONS[:512]
    assert "At the start of a coding task" in first_policy
    assert "list_indexed_files" in first_policy
    assert "search_code" in first_policy
    assert "find_similar" in first_policy
    assert "find_symbol" in first_policy
    assert "Never assume similarity proves equivalence" in first_policy
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False
        assert tool.outputSchema is not None
        assert "result" in tool.outputSchema["properties"]
    descriptions = " ".join(tool.description or "" for tool in tools)
    assert "untrusted" in descriptions
    assert "not instructions" in descriptions
    similar = next(tool for tool in tools if tool.name == "find_similar")
    assert "does not prove" in (similar.description or "")


@pytest.mark.asyncio
async def test_search_code_delegates_exactly_and_preserves_typed_order(
    app_config: AppConfig,
) -> None:
    # Arrange
    engine = FakeEngine()
    server = _server(app_config, engine)

    # Act
    result = await _call(
        server,
        "search_code",
        {"query": "email validation", "language": "python", "limit": 7},
    )

    # Assert
    assert result == engine.search_results
    assert engine.calls == [("search_code", ("email validation", "python", 7))]
    assert isinstance(result, list)
    assert [item.relevance_score for item in result] == [0.9, 0.4]
    dumped = [item.model_dump(mode="json") for item in result]
    assert dumped[0] == {
        "start_line": 3,
        "end_line": 7,
        "file": "src/example.py",
        "symbol": "validate_email",
        "qualified_name": "validate_email",
        "language": "python",
        "snippet": "def validate_email(value: str) -> bool:\n    return '@' in value\n",
        "relevance_score": 0.9,
    }
    assert "embedding" not in dumped[0]


@pytest.mark.asyncio
async def test_empty_search_results_are_a_valid_success(app_config: AppConfig) -> None:
    # Arrange
    engine = FakeEngine()
    engine.search_results = []

    # Act
    result = await _call(_server(app_config, engine), "search_code", {"query": "nothing"})

    # Assert
    assert result == []


@pytest.mark.asyncio
async def test_search_expected_failure_preserves_stable_error_without_input_leak(
    app_config: AppConfig,
    capfd: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    raw_query = "PRIVATE-QUERY-CONTENT"
    engine = FakeEngine()
    engine.failures["search_code"] = InvalidQueryError("The query is safely invalid.")

    # Act
    result = await _call(_server(app_config, engine), "search_code", {"query": raw_query})
    captured = capfd.readouterr()

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "INVALID_QUERY"
    assert result.message == "The query is safely invalid."
    assert raw_query not in result.model_dump_json()
    assert raw_query not in captured.out
    assert raw_query not in captured.err


@pytest.mark.asyncio
async def test_unexpected_failure_becomes_generic_query_error_without_details(
    app_config: AppConfig,
    capfd: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    secret = "/tmp/private/source.py PRIVATE-SNIPPET"
    engine = FakeEngine()
    engine.failures["find_similar"] = RuntimeError(secret)

    # Act
    result = await _call(
        _server(app_config, engine),
        "find_similar",
        {"code_snippet": secret},
    )
    captured = capfd.readouterr()

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "QUERY_FAILED"
    assert secret not in result.model_dump_json()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.asyncio
async def test_find_symbol_delegates_and_preserves_ranked_metadata(
    app_config: AppConfig,
) -> None:
    # Arrange
    engine = FakeEngine()

    # Act
    result = await _call(
        _server(app_config, engine),
        "find_symbol",
        {"name": "validate_email", "kind": "function", "limit": 12},
    )

    # Assert
    assert result == engine.symbol_results
    assert engine.calls == [("find_symbol", ("validate_email", "function", 12))]
    assert isinstance(result, list)
    symbol = result[0]
    assert symbol.file == "src/example.py"
    assert (symbol.start_line, symbol.end_line) == (3, 7)


@pytest.mark.asyncio
async def test_find_similar_delegates_exact_snippet_and_language(app_config: AppConfig) -> None:
    # Arrange
    engine = FakeEngine()
    snippet = "def candidate(value: str) -> bool:\n    return '@' in value"

    # Act
    result = await _call(
        _server(app_config, engine),
        "find_similar",
        {"code_snippet": snippet, "language": "python", "limit": 2},
    )

    # Assert
    assert result == engine.similar_results
    assert engine.calls == [("find_similar", (snippet, "python", 2))]


@pytest.mark.asyncio
async def test_inventory_validates_language_and_delegates_authoritative_status(
    app_config: AppConfig,
) -> None:
    # Arrange
    engine = FakeEngine()
    server = _server(app_config, engine)

    # Act
    result = await _call(server, "list_indexed_files", {"language": " Python "})

    # Assert
    assert result == engine.status
    assert engine.calls == [("get_index_status", ())]
    assert isinstance(result, IndexStatus)
    assert result.index_root == "."


@pytest.mark.asyncio
async def test_inventory_rejects_language_before_constructing_engine(
    app_config: AppConfig,
) -> None:
    # Arrange
    build_calls = 0

    def build(_config: AppConfig) -> QueryEngineBoundary:
        nonlocal build_calls
        build_calls += 1
        return FakeEngine()

    server = create_server(config_loader=lambda: app_config, engine_factory=build)

    # Act
    result = await _call(server, "list_indexed_files", {"language": "typescript"})

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "INVALID_LANGUAGE"
    assert build_calls == 0
    assert not app_config.storage.path.exists()


@pytest.mark.asyncio
async def test_missing_inventory_is_structured_and_creates_no_runtime(
    app_config: AppConfig,
) -> None:
    # Arrange
    engine = FakeEngine()
    engine.failures["get_index_status"] = IndexNotFoundError("No complete usable index exists.")

    # Act
    result = await _call(_server(app_config, engine), "list_indexed_files", {})

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "INDEX_NOT_FOUND"
    assert not app_config.storage.path.exists()


@pytest.mark.asyncio
async def test_shared_engine_is_reused_but_status_is_revalidated_each_call(
    app_config: AppConfig,
) -> None:
    # Arrange
    engine = FakeEngine()
    factory_calls = 0

    def build(_config: AppConfig) -> QueryEngineBoundary:
        nonlocal factory_calls
        factory_calls += 1
        return engine

    server = create_server(config_loader=lambda: app_config, engine_factory=build)

    # Act
    first = await _call(server, "list_indexed_files", {})
    second = await _call(server, "list_indexed_files", {})
    tools_after_calls = await server.list_tools()

    # Assert
    assert first == second == engine.status
    assert factory_calls == 1
    assert engine.calls == [("get_index_status", ()), ("get_index_status", ())]
    assert len(tools_after_calls) == 4


@pytest.mark.asyncio
async def test_direct_successful_tool_execution_writes_nothing(
    app_config: AppConfig,
    capfd: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    server = _server(app_config, FakeEngine())

    # Act
    await _call(server, "search_code", {"query": "email validation"})
    captured = capfd.readouterr()

    # Assert
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    ("operation", "arguments", "failure"),
    [
        ("find_symbol", {"name": "secret-name"}, InvalidQueryError("Safe failure.")),
        ("find_similar", {"code_snippet": "secret-code"}, InvalidQueryError("Safe failure.")),
    ],
)
@pytest.mark.asyncio
async def test_expected_failures_are_typed_for_all_query_tools(
    app_config: AppConfig,
    operation: str,
    arguments: dict[str, Any],
    failure: BaseException,
) -> None:
    # Arrange
    engine = FakeEngine()
    engine.failures[operation] = failure

    # Act
    result = await _call(_server(app_config, engine), operation, arguments)

    # Assert
    assert isinstance(result, ErrorResponse)
    assert result.code == "INVALID_QUERY"
