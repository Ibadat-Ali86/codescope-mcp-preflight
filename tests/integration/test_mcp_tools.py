"""MCP client integration tests for the four CodeScope tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

from codescope.config import AppConfig, IndexConfig, StorageConfig
from codescope.engine import QueryEngine
from codescope.indexer import RepositoryIndexer
from codescope.models import IndexStatus, SearchResult, SymbolResult
from codescope.server import QueryEngineBoundary, create_server

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "sample_python"
PUBLIC_TOOLS = ["search_code", "find_symbol", "find_similar", "list_indexed_files"]


def _payload(result: CallToolResult) -> object:
    structured = result.structuredContent
    assert isinstance(structured, dict)
    assert set(structured) == {"result"}
    return structured["result"]


class StaticEngine(QueryEngineBoundary):
    """Small deterministic engine used to exercise MCP serialization."""

    def search_code(
        self,
        query: str,
        language: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        del query, language, limit
        return [
            SearchResult(
                file="validators.py",
                start_line=6,
                end_line=9,
                symbol="validate_email",
                qualified_name="validate_email",
                language="python",
                snippet="def validate_email(value: str) -> bool:\n    return '@' in value\n",
                relevance_score=0.9,
            )
        ]

    def find_symbol(
        self,
        name: str,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[SymbolResult]:
        del name, kind, limit
        return [
            SymbolResult(
                name="validate_email",
                qualified_name="validate_email",
                kind="function",
                file="validators.py",
                start_line=6,
                end_line=9,
                signature="def validate_email(value: str) -> bool:",
                docstring="Validate an email address.",
            )
        ]

    def find_similar(
        self,
        code_snippet: str,
        language: str | None = None,
        limit: int = 3,
    ) -> list[SearchResult]:
        del code_snippet, language, limit
        return self.search_code("similar")

    def get_index_status(self) -> IndexStatus:
        return IndexStatus(
            index_exists=True,
            index_root=".",
            total_files=4,
            total_chunks=16,
            total_symbols=11,
            languages={"python": 4},
            last_indexed="2026-07-16T00:00:00+00:00",
            index_size_bytes=4096,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )


@pytest.mark.asyncio
async def test_in_memory_client_lists_exact_schemas_and_serializes_all_tools(
    app_config: AppConfig,
) -> None:
    # Arrange
    server = create_server(
        config_loader=lambda: app_config,
        engine_factory=lambda _config: StaticEngine(),
    )

    # Act
    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
        search = await session.call_tool(
            "search_code",
            {"query": "email validation", "language": "python", "limit": 5},
        )
        symbol = await session.call_tool(
            "find_symbol",
            {"name": "validate_email", "kind": "function", "limit": 20},
        )
        similar = await session.call_tool(
            "find_similar",
            {"code_snippet": "def validate(value): ...", "language": "python", "limit": 3},
        )
        status = await session.call_tool("list_indexed_files", {"language": "python"})

    # Assert
    assert [tool.name for tool in listed.tools] == PUBLIC_TOOLS
    schemas = {tool.name: tool.inputSchema for tool in listed.tools}
    assert set(schemas["search_code"]["properties"]) == {"query", "language", "limit"}
    assert schemas["search_code"]["properties"]["limit"]["default"] == 5
    assert set(schemas["find_symbol"]["properties"]) == {"name", "kind", "limit"}
    assert schemas["find_symbol"]["properties"]["limit"]["default"] == 20
    assert set(schemas["find_similar"]["properties"]) == {
        "code_snippet",
        "language",
        "limit",
    }
    assert schemas["find_similar"]["properties"]["limit"]["default"] == 3
    assert set(schemas["list_indexed_files"]["properties"]) == {"language"}
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in listed.tools)

    search_payload = _payload(search)
    symbol_payload = _payload(symbol)
    similar_payload = _payload(similar)
    status_payload = _payload(status)
    assert isinstance(search_payload, list)
    assert search_payload[0]["file"] == "validators.py"
    assert search_payload[0]["start_line"] == 6
    assert search_payload[0]["end_line"] == 9
    assert "embedding" not in search_payload[0]
    assert isinstance(symbol_payload, list)
    assert symbol_payload[0]["name"] == "validate_email"
    assert isinstance(similar_payload, list)
    assert "equivalent" not in similar_payload[0]
    assert isinstance(status_payload, dict)
    assert status_payload["total_files"] == 4
    assert status_payload["total_symbols"] == 11
    assert status_payload["total_chunks"] == 16


@pytest.mark.asyncio
async def test_missing_index_initializes_and_returns_actionable_structured_errors(
    app_config: AppConfig,
) -> None:
    # Arrange
    server = create_server(
        config_loader=lambda: app_config,
        engine_factory=lambda config: QueryEngine(config),
    )

    # Act
    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
        missing = await session.call_tool("list_indexed_files", {})
        search = await session.call_tool("search_code", {"query": "email validation"})

    # Assert
    assert [tool.name for tool in listed.tools] == PUBLIC_TOOLS
    for result in (missing, search):
        payload = _payload(result)
        assert isinstance(payload, dict)
        assert payload["error"] is True
        assert payload["code"] == "INDEX_NOT_FOUND"
        assert payload["suggestion"]
    assert not app_config.storage.path.exists()


@pytest.mark.asyncio
async def test_committed_cli_stdio_is_protocol_only_and_recovers_after_failed_call(
    tmp_path: Path,
) -> None:
    # Arrange
    runtime = REPOSITORY_ROOT / ".codescope"
    assert not runtime.exists(), "stdio safety test requires the repository runtime to be absent"
    stderr_path = tmp_path / "server-stderr.log"
    parameters = StdioServerParameters(
        command="uv",
        args=["run", "codescope", "serve"],
        cwd=REPOSITORY_ROOT,
    )

    # Act
    with stderr_path.open("w+", encoding="utf-8") as stderr:
        async with stdio_client(parameters, errlog=stderr) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                listed = await session.list_tools()
                invalid = await session.call_tool(
                    "list_indexed_files",
                    {"language": "typescript"},
                )
                malformed = await session.call_tool(
                    "search_code",
                    {"query": "safe", "limit": {"private": "DO-NOT-ECHO"}},
                )
                valid_after_failure = await session.call_tool("list_indexed_files", {})
        stderr.seek(0)
        diagnostics = stderr.read()

    # Assert
    assert initialized.serverInfo.name == "codescope"
    assert [tool.name for tool in listed.tools] == PUBLIC_TOOLS
    invalid_payload = _payload(invalid)
    assert isinstance(invalid_payload, dict)
    assert invalid_payload["code"] == "INVALID_LANGUAGE"
    malformed_payload = _payload(malformed)
    assert isinstance(malformed_payload, dict)
    assert malformed_payload["code"] == "INVALID_LIMIT"
    assert "DO-NOT-ECHO" not in str(malformed_payload)
    missing_payload = _payload(valid_after_failure)
    assert isinstance(missing_payload, dict)
    assert missing_payload["code"] == "INDEX_NOT_FOUND"
    assert "email validation" not in diagnostics
    assert "DO-NOT-ECHO" not in diagnostics
    assert "Traceback" not in diagnostics
    assert str(REPOSITORY_ROOT) not in diagnostics
    assert not runtime.exists()


@pytest.mark.asyncio
async def test_real_cached_fixture_index_is_queryable_when_explicitly_enabled(
    app_config: AppConfig,
    tmp_path: Path,
) -> None:
    # Arrange
    if os.environ.get("CODESCOPE_RUN_REAL_MODEL") != "1":
        pytest.skip("set CODESCOPE_RUN_REAL_MODEL=1 to run the cache-only model integration")
    fixture = tmp_path / "sample_python"
    shutil.copytree(FIXTURE_ROOT, fixture)
    index_config = IndexConfig.model_validate({**app_config.index.model_dump(), "root": fixture})
    storage_config = StorageConfig(
        path=tmp_path / ".codescope",
        collection=app_config.storage.collection,
    )
    config = AppConfig(
        server=app_config.server,
        index=index_config,
        embeddings=app_config.embeddings,
        storage=storage_config,
        search=app_config.search,
    )
    summary = RepositoryIndexer(config).rebuild(allow_model_download=False)
    server = create_server(
        config_loader=lambda: config,
        engine_factory=lambda loaded: QueryEngine(loaded),
    )

    # Act
    async with create_connected_server_and_client_session(server) as session:
        status = _payload(await session.call_tool("list_indexed_files", {}))
        search = _payload(
            await session.call_tool("search_code", {"query": "email validation", "limit": 5})
        )
        symbol = _payload(
            await session.call_tool("find_symbol", {"name": "validate_email", "limit": 20})
        )
        similar = _payload(
            await session.call_tool(
                "find_similar",
                {"code_snippet": "def validate_email(value): return '@' in value", "limit": 3},
            )
        )

    # Assert
    assert (summary.total_files, summary.total_symbols, summary.total_chunks) == (4, 11, 16)
    assert isinstance(status, dict)
    assert (status["total_files"], status["total_symbols"], status["total_chunks"]) == (
        4,
        11,
        16,
    )
    assert isinstance(search, list)
    assert any(
        item["file"] == "validators.py"
        and item["start_line"] == 6
        and item["end_line"] == 9
        and item["symbol"] == "validate_email"
        for item in search
    )
    assert isinstance(symbol, list)
    assert symbol[0]["name"] == "validate_email"
    assert symbol[0]["file"] == "validators.py"
    assert isinstance(similar, list)
    assert all(not Path(item["file"]).is_absolute() for item in similar)
    assert all(len(item["snippet"]) <= 8_192 for item in similar)
