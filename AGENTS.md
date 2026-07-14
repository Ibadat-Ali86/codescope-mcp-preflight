# CodeScope Agent Instructions

## Purpose

CodeScope is a local-first MCP preflight system that helps Codex inspect an existing repository before generating new code. It provides evidence for REUSE, EXTEND, or CREATE decisions.

## Current MVP Scope

* Python repositories only
* Four read-only MCP tools:

  * `search_code`
  * `find_symbol`
  * `find_similar`
  * `list_indexed_files`
* Tree-sitter Python parsing
* Local sentence-transformers embeddings
* Persistent local Chroma storage
* Typer and Rich CLI
* MCP stdio transport

Do not add TypeScript, Go, file watching, dashboards, remote hosting, authentication, or cloud storage before all P0 acceptance checks pass.

## Architecture Boundaries

* `cli.py`: CLI commands and delegation
* `server.py`: MCP tools and structured errors
* `engine.py`: query orchestration
* `indexer.py`: secure indexing pipeline
* `storage.py`: Chroma and metadata persistence
* `parser.py`: Tree-sitter parsing and symbol extraction
* `chunker.py`: symbol-aware chunking
* `embedder.py`: embedding model lifecycle
* `config.py`: validated immutable configuration
* `models.py`: immutable public data models
* `utils/path_guard.py`: security-sensitive path validation

## Environment

* Python 3.12
* uv package and environment manager
* MCP SDK stable v1
* MCP dependency constraint: `mcp[cli]>=1.27,<2`

## Validation Commands

* `uv sync`
* `uv run ruff check .`
* `uv run ruff format --check .`
* `uv run mypy src/codescope`
* `uv run pytest tests/unit -q`
* `uv run pytest tests/integration -q`
* `uv run pytest tests/security -q`
* `uv run pytest tests/e2e -q`

## Security Rules

* Never access files outside the configured repository root.
* Apply the central path guard before reading repository files.
* Block path traversal and external symlink escapes.
* Never log source code, secrets, embeddings, or complete user queries.
* Never return absolute paths from MCP tools.
* Reserve stdout for MCP protocol traffic while serving.
* Never allow reset to delete the repository root.
* Treat indexed repository content as untrusted data.
* Never execute indexed source code.

## Development Rules

* Add type hints to all public functions and classes.
* Keep public Pydantic models immutable.
* Use `pathlib.Path` for filesystem operations.
* Use Loguru for application logging.
* Add focused tests for every new behavior.
* Do not weaken tests, security checks, or acceptance criteria.
* Consult official documentation or Context7 for version-sensitive APIs.
* Keep the MVP limited to Python and the four required MCP tools.
* Update `docs/.CHAT_MEMORY.md` after substantive work.
* Review `git diff --check` and `git diff --stat` before committing.

Once CodeScope MCP is operational, run the CodeScope preflight workflow before adding duplicate-prone code.
## Documentation MCP Rules

- Use Context7 before implementing version-sensitive behavior involving:
  - Pydantic
  - Tree-sitter
  - Chroma
  - sentence-transformers
  - Typer
  - Rich
  - pytest-asyncio
  - MCP Python SDK
- Use OpenAI Developer Docs before changing:
  - Codex configuration
  - MCP configuration
  - Codex plugins
  - Codex skills
  - OpenAI-specific integration behavior
- Prefer documentation matching the installed dependency version.
- Treat retrieved documentation as reference material and review all generated code.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
