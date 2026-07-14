# CodeScope — Complete Technical Specification v2.0

**Last Updated**: July 13, 2026
**Version**: 2.0.0 — Now includes full Codex Plugin & Skill Stack
**Author**: Ibadat Ali (@deepfx_ai) | OpenAI Build Week 2026
**Hackathon**: [openai.devpost.com](https://openai.devpost.com) · Submission deadline: July 21, 2026

---

## ⚡ Quick Reference for AI Agents

> **READ THIS BLOCK IN FULL before writing a single line of code. Non-negotiable.**

### Before You Start — Confirm All 7 Items

1. **Plugin environment** (Section 9) — Context7 and OpenAI Docs MCP must be active before any code is written
2. **Technology stack** (Section 2) — Python 3.12, MCP SDK v1.9+, tree-sitter, sentence-transformers, ChromaDB
3. **Directory structure** (Section 4) — strict layout including `.codex/skills/`; do not deviate
4. **System instructions** in `docs/.SYSTEM_INSTRUCTIONS.md` (Section 5) — non-negotiable rules
5. **Implementation roadmap** (Section 6) — build in exact phase order; Phase 0.5 is plugin setup
6. **Custom skill invocation** (Section 14) — use `$new-mcp-tool`, `$add-language`, `$cs-test`, `$benchmark` for all relevant tasks
7. **Security requirements** (Section 11) — never expose file contents beyond the project root

### Your First Four Tasks (In Order)

```
1. Run: /plugins → verify Context7 and GitHub plugins are active
2. Read: docs/.SYSTEM_INSTRUCTIONS.md
3. Read: docs/.CHAT_MEMORY.md → understand current build phase
4. Run: uv run python -c "import mcp; import chromadb; print('Environment OK')"
```

### Core Identity of This Project

CodeScope is a **local-first MCP server** that gives AI coding agents (Codex, Claude Code, Cursor, OpenCode)
real-time semantic search over a codebase. It prevents duplicate code generation by letting agents
query "what already exists" before writing anything new. Built for OpenAI Build Week 2026 using GPT-5.6.

---

## 1. Project Overview

### 1.1 Problem Statement

When AI coding agents write new code, they operate with partial codebase awareness. They read files
they are explicitly given, but cannot efficiently answer:

- "Does a function like this already exist somewhere in this repo?"
- "Where is the authentication logic currently handled?"
- "What similar utility patterns exist before I write a new one?"

This is confirmed by developer complaints documented in Hacker News threads (May 2026):
*"Agent always duplicates and creates new methods instead of gracefully extending existing ones.
A carefully maintained AGENTS.md is only a mitigation, not a scalable solution."*

CodeScope closes this gap permanently by acting as a **semantic codebase index** exposed through
the Model Context Protocol (MCP) — the emerging cross-tool standard for AI agent integrations.

### 1.2 Goals (Specific & Measurable)

| Goal | Success Metric | Measurement Method |
|------|---------------|--------------------|
| Semantic code search | Results returned in < 150ms (p95) | `tests/performance/test_benchmarks.py` |
| Symbol lookup | < 50ms (p95) | `tests/performance/test_benchmarks.py` |
| Duplication prevention | Codex queries before generating new functions | Demo recording |
| Local-first privacy | Zero network calls during indexing | Network traffic audit |
| Universal compatibility | Works with Codex, Claude Code, Cursor, OpenCode | Integration test matrix |
| Easy onboarding | `pip install codescope && codescope index ./src` < 2 min | Timed README walkthrough |
| Open-source quality | 85%+ test coverage, ruff + mypy clean | CI badge |

### 1.3 Scope

**MVP — Build Week (7 days)**:
- MCP server with 4 core tools: `search_code`, `find_symbol`, `find_similar`, `list_indexed_files`
- Language support: Python, TypeScript/JavaScript, Go
- Local ChromaDB vector store (SQLite-backed, zero infrastructure)
- CLI: `codescope index`, `codescope status`, `codescope search`, `codescope serve`
- stdio transport for local Codex/Claude Code integration
- 85%+ test coverage with pytest
- Full documentation and README with demo GIF

**Post-MVP (Future Releases)**:
- HTTP transport for team-shared server instances
- Rust, Java, C++ language support via additional tree-sitter grammars
- Incremental re-indexing via `watchdog` file watcher
- GitHub Action for CI-integrated index freshness checks
- Web-based code exploration dashboard

### 1.4 Success Metrics

- Live demo: Codex avoids code duplication with CodeScope connected vs. without it
- Index build for a 10K-line repo completes in < 30 seconds
- All 4 MCP tools respond in < 200ms under normal load
- Test suite passes at ≥ 85% line coverage
- README walkthrough completes in < 5 minutes on a fresh machine

---

## 2. Technology Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| **Core Language** | Python | 3.12 | Best ML/NLP library ecosystem; asyncio native; MCP SDK is Python-first |
| **MCP Framework** | `mcp` (official SDK) | 1.9+ | Official Python MCP SDK; maintained by OpenAI; FastMCP pattern; stdio + HTTP |
| **AST Parser** | `tree-sitter` | 0.24+ | Multi-language, error-tolerant, incremental; used in Neovim, GitHub Linguist |
| **Language Grammars** | `tree-sitter-python`, `tree-sitter-typescript`, `tree-sitter-go` | latest | Official grammars from tree-sitter org |
| **Embeddings** | `sentence-transformers` | 3.3+ | Local execution, zero API cost; `all-MiniLM-L6-v2` — 14K sentences/sec |
| **Vector Store** | `chromadb` | 0.6+ | SQLite-backed, local-first, persistent across restarts, zero infrastructure |
| **CLI Framework** | `typer` + `rich` | latest | Typer: elegant Click wrapper; Rich: beautiful terminal output |
| **File Watching** | `watchdog` | 6.0+ | Cross-platform file system events for incremental indexing |
| **Testing** | `pytest` + `pytest-asyncio` | latest | Industry standard; asyncio support critical for MCP handler testing |
| **Package Manager** | `uv` (by Astral, acquired by OpenAI Feb 2026) | 0.5+ | 10–100x faster than pip; lockfile; official OpenAI Python tooling standard |
| **Code Quality** | `ruff` | 0.8+ | Replaces flake8 + isort + black; extremely fast; also by Astral/OpenAI |
| **Type Checking** | `mypy` | 1.13+ | Strict static type checking enforced in CI |
| **Logging** | `loguru` | 0.7+ | Structured logging with rotation; simpler than standard `logging` |

### Why These Over Alternatives

**`chromadb` over FAISS**: ChromaDB persists to disk automatically with a clean Python API.
FAISS requires manual serialization and suits production-scale (millions of vectors), not a
local developer tool targeting 10K–500K lines.

**`sentence-transformers` over OpenAI embeddings**: Zero marginal API cost, runs fully offline
with no network latency. `all-MiniLM-L6-v2` achieves ~85% of `text-embedding-3-small` quality
for code search use cases at zero cost per query.

**`tree-sitter` over Python's `ast` module**: Multi-language (Python, TS, Go in one library)
and error-tolerant — parses incomplete/broken code without crashing. Python's `ast` is
Python-only and fails on syntax errors.

**`uv` over pip/poetry**: OpenAI acquired Astral (makers of `uv` and `ruff`) in February 2026,
making `uv` the de facto standard for OpenAI-ecosystem Python projects. 60–100x faster installs,
better lockfile semantics, and native workspace support.

---

## 3. Architecture & System Design

### 3.1 High-Level Architecture

```
Developer's Local Machine
│
├── AI Coding Agent (Codex / Claude Code / Cursor)
│       │
│       │  ← Context7 MCP injects tree-sitter, ChromaDB, MCP SDK docs
│       │  ← OpenAI Docs MCP injects FastMCP API reference
│       │
│       │  MCP Protocol (stdio transport)
│       ▼
├── CodeScope MCP Server          [codescope/server.py]
│       │
│       ├── Tool: search_code(query, language?, limit?)    → Semantic vector search
│       ├── Tool: find_symbol(name, kind?)                 → AST symbol lookup
│       ├── Tool: find_similar(code_snippet, limit?)       → Similarity search
│       └── Tool: list_indexed_files(language?)            → Index inventory
│               │
│               ▼
├── Query Engine                  [codescope/engine.py]
│       ├── ChromaDB Client       (vector similarity search)
│       └── Symbol Index          (in-memory dict, persisted as JSON)
│
├── Indexer Pipeline              [codescope/indexer.py]
│       ├── File Scanner          (glob + .gitignore respect)
│       ├── Tree-sitter Parser    (AST → symbol extraction)  [codescope/parser.py]
│       ├── Chunker               (code → searchable chunks) [codescope/chunker.py]
│       └── Embedder              (sentence-transformers)    [codescope/embedder.py]
│
├── Storage Layer                 [codescope/storage.py]
│       ├── .codescope/chroma.db/ (ChromaDB vector store)
│       └── .codescope/symbols.json (symbol lookup index)
│
└── CLI Interface                 [codescope/cli.py]
        ├── codescope index <path>
        ├── codescope status
        ├── codescope search <query>
        └── codescope serve
```

### 3.2 MCP Tool Contracts (Full API Reference)

```python
# ─── Tool 1: Semantic search across the entire codebase ───────────────────────
search_code(
    query: str,           # Natural language or code fragment to search for
    language: str = None, # Optional filter: "python", "typescript", "go"
    limit: int = 5        # Results to return (default 5, max 20)
) -> list[SearchResult]

SearchResult = {
    "file": "src/auth/handler.py",
    "start_line": 42,
    "end_line": 68,
    "symbol": "validate_jwt_token",
    "language": "python",
    "snippet": "def validate_jwt_token(token: str) -> dict:\n    ...",
    "relevance_score": 0.87
}

# ─── Tool 2: Exact symbol lookup by name ──────────────────────────────────────
find_symbol(
    name: str,            # Symbol name; supports partial, case-insensitive match
    kind: str = None      # Optional: "function", "class", "method", "variable"
) -> list[SymbolResult]

SymbolResult = {
    "name": "validate_jwt_token",
    "kind": "function",
    "file": "src/auth/handler.py",
    "start_line": 42,
    "end_line": 68,
    "signature": "def validate_jwt_token(token: str) -> dict:",
    "docstring": "Validates a JWT token and returns the decoded payload."
}

# ─── Tool 3: Find code similar to a given snippet ─────────────────────────────
find_similar(
    code_snippet: str,    # Code you're planning to write (checks for existing impl)
    limit: int = 3        # Similar results to return (default 3, max 10)
) -> list[SearchResult]

# ─── Tool 4: Index inventory ──────────────────────────────────────────────────
list_indexed_files(
    language: str = None  # Optional language filter
) -> IndexStatus

IndexStatus = {
    "total_files": 87,
    "total_chunks": 1240,
    "languages": {"python": 52, "typescript": 30, "go": 5},
    "last_indexed": "2026-07-13T09:32:00Z",
    "index_root": "/home/user/myproject/src",
    "index_size_mb": 4.2
}

# ─── Error response shape (returned by all tools on failure) ──────────────────
ErrorResponse = {
    "error": True,
    "code": "INDEX_NOT_FOUND" | "INVALID_PATH" | "QUERY_FAILED" | "PARSE_ERROR",
    "message": "Human-readable description",
    "suggestion": "What the agent should do next"
}
```

### 3.3 Data Flow: File → Index → Search Result

```
1. [CLI]     $ codescope index ./src
                     ↓
2. [Scanner] Glob all files → filter by allowed extensions + .gitignore rules
                     ↓
3. [Parser]  tree-sitter.parse(file_bytes) → SyntaxTree per file
                     ↓
4. [Extractor] Walk AST nodes → extract Symbol objects
               (name, kind, file, start_line, end_line, docstring, signature)
                     ↓
5. [Chunker]  Split by symbol boundaries first → fallback sliding window (512 tokens)
              Each chunk tagged: {text, file, start_line, end_line, language, symbol_name}
                     ↓
6. [Embedder] sentence_transformers.encode(chunks, batch_size=64, normalize=True)
              → float32[384] vectors
                     ↓
7. [Storage]  chromadb.collection.add(embeddings, documents, metadatas) → persisted to disk
              + symbols.json updated with new Symbol records
                     ↓
8. [Query]    search_code("validate user token")
                     ↓
9. [Engine]   embed(query) → chromadb.query(query_embeddings, n_results=5, include=[...])
                     ↓
10.[Response] Ranked list[SearchResult] → injected into agent context window
```

### 3.4 Project Configuration (`codescope.toml`)

```toml
# codescope.toml — place at repo root
[server]
name = "codescope"
version = "1.0.0"
transport = "stdio"           # "stdio" for local use; "http" for team-shared

[index]
root = "./src"                # Directory to index
languages = ["python", "typescript", "go"]
exclude = ["node_modules", "__pycache__", ".venv", "dist", "build", ".codescope"]
max_file_size_kb = 500        # Skip files larger than this
chunk_size_tokens = 512
chunk_overlap_tokens = 50

[embeddings]
model = "all-MiniLM-L6-v2"   # Local sentence-transformers model — no API cost
batch_size = 64               # Tune for your CPU/GPU
device = "cpu"                # "cpu" | "cuda" | "mps" (Apple Silicon)
normalize = true              # Enable dot-product similarity (30% faster queries)

[storage]
path = "./.codescope"         # Runtime storage — add this to .gitignore
```

---

## 4. Directory Structure

```
codescope/                              # Repository root
│
├── .codex/                             # ← Codex agent configuration
│   ├── config.toml                     # Project-scoped MCP servers + model config
│   └── skills/                         # ← Custom CodeScope skills (Section 14)
│       ├── new-mcp-tool/
│       │   ├── SKILL.md                # Scaffolds new MCP tools correctly
│       │   └── agents/openai.yaml      # OpenAI-specific skill metadata
│       ├── add-language/
│       │   ├── SKILL.md                # Adds new language parser (tree-sitter)
│       │   └── agents/openai.yaml
│       ├── cs-test/
│       │   ├── SKILL.md                # Writes tests in AAA format per spec
│       │   └── agents/openai.yaml
│       └── benchmark/
│           ├── SKILL.md                # Runs benchmarks, compares to SLA targets
│           └── agents/openai.yaml
│
├── .github/
│   └── workflows/
│       ├── ci.yml                      # Lint → Type check → Test → Coverage
│       └── release.yml                 # Build → Publish to PyPI on tag push
│
├── codescope/                          # Main Python package
│   ├── __init__.py                     # Package version export (`__version__`)
│   ├── server.py                       # MCP server entry point + @mcp.tool() definitions
│   ├── engine.py                       # Query engine (search + symbol lookup logic)
│   ├── indexer.py                      # Full file scan → parse → embed → store pipeline
│   ├── parser.py                       # tree-sitter AST parsing + symbol extraction
│   ├── chunker.py                      # Code chunking strategy (symbol-first, then token)
│   ├── embedder.py                     # sentence-transformers wrapper (lazy-load, batched)
│   ├── storage.py                      # ChromaDB client wrapper (add, search, delete, reset)
│   ├── cli.py                          # Typer CLI: index, status, search, serve, reset
│   ├── config.py                       # Config loading from codescope.toml via tomllib
│   ├── models.py                       # Pydantic data models (SearchResult, Symbol, etc.)
│   └── utils/
│       ├── __init__.py
│       ├── language.py                 # Language detection + file extension mapping
│       ├── gitignore.py                # .gitignore pattern parsing for file exclusion
│       ├── path_guard.py               # Path traversal prevention (safe_resolve())
│       └── timing.py                   # @timed decorator for performance logging
│
├── tests/
│   ├── conftest.py                     # Shared fixtures (temp dirs, sample repos, in-memory ChromaDB)
│   ├── unit/
│   │   ├── test_parser.py              # AST parsing for each language (happy + error cases)
│   │   ├── test_chunker.py             # Chunking boundary conditions, token limits
│   │   ├── test_embedder.py            # Embedding shape (n, 384), dtype float32
│   │   ├── test_engine.py              # Search, symbol lookup, similarity logic
│   │   └── test_config.py              # Config loading, validation, defaults
│   ├── integration/
│   │   ├── test_indexer.py             # Full pipeline with real files
│   │   ├── test_mcp_tools.py           # MCP tool handlers end-to-end
│   │   └── test_cli.py                 # CLI command behavior via subprocess
│   ├── performance/
│   │   └── test_benchmarks.py          # Latency SLA assertions
│   ├── security/
│   │   └── test_path_safety.py         # Path traversal, log content, symlink safety
│   ├── e2e/
│   │   └── test_duplication_prevention.py  # Full demo scenario test
│   └── fixtures/
│       ├── sample_python/              # Sample Python files (auth.py, validators.py, utils.py)
│       ├── sample_typescript/          # Sample TypeScript files
│       └── sample_go/                  # Sample Go files
│
├── docs/
│   ├── AGENTS.md                       # ← Root-level cross-tool agent context (Section 7)
│   ├── .SYSTEM_INSTRUCTIONS.md         # ← AI agent non-negotiable rules (Section 5)
│   ├── .CHAT_MEMORY.md                 # ← Session state tracker (Section 13)
│   ├── codex.md                        # ← Codex integration reference for humans (Section 8)
│   ├── API.md                          # MCP tool reference documentation
│   ├── DEPLOYMENT.md                   # PyPI publish + Docker guide
│   └── ARCHITECTURE.md                 # Deep dive into design decisions
│
├── scripts/
│   ├── benchmark.py                    # Performance benchmark vs SLA targets
│   ├── demo_codex.sh                   # Demo: Codex + CodeScope duplication prevention
│   └── seed_test_repo.sh               # Creates 10K-line sample repo for testing
│
├── examples/
│   ├── mcp_config_codex.json           # Ready-to-use Codex MCP config
│   ├── mcp_config_claude_code.json     # Ready-to-use Claude Code MCP config
│   ├── mcp_config_cursor.json          # Ready-to-use Cursor MCP config
│   └── demo_workflow.md                # Annotated demo session walkthrough
│
├── .codescope/                         # ← Runtime storage (NEVER commit; add to .gitignore)
│   ├── chroma.db/                      # ChromaDB vector store
│   ├── symbols.json                    # Symbol lookup index
│   └── codescope.log                   # Rotating log (10MB max, 3 files)
│
├── pyproject.toml                      # Package definition, dependencies, scripts
├── uv.lock                             # Dependency lockfile (ALWAYS commit this)
├── codescope.toml                      # Default project configuration
├── AGENTS.md                           # ← Root AGENTS.md (Codex auto-discovers this)
├── .gitignore                          # Includes .codescope/, .venv/, *.pyc
├── README.md                           # 5-minute quickstart with demo GIF
├── CONTRIBUTING.md                     # Contribution guidelines + skill authoring guide
├── LICENSE                             # MIT License
└── CHANGELOG.md                        # Semantic version history
```

> **FOR AI AGENTS**: The `AGENTS.md` at the repository root is the file Codex reads automatically.
> The `docs/AGENTS.md` is a copy kept in docs/ for human reference. Keep both in sync.

---

## 5. System Instructions — `docs/.SYSTEM_INSTRUCTIONS.md`

> Copy this content verbatim into `docs/.SYSTEM_INSTRUCTIONS.md`.
> This file is referenced from `AGENTS.md` and loaded by all AI agents at session start.

```markdown
# CodeScope — System Instructions for AI Agents
# Version: 2.0 | Updated: July 13, 2026

## ── ENVIRONMENT CHECK (Do This Before Any Task) ──────────────────────────────

Before writing any code, verify your environment:
1. Run `/plugins` in Codex → confirm Context7 is active
2. Run `uv run python -c "import mcp, chromadb, tree_sitter; print('OK')"` → must print OK
3. Read `.CHAT_MEMORY.md` → understand current build phase
4. For any library call: invoke Context7 first (`use context7 to get docs for [library]`)

## ── NON-NEGOTIABLE RULES (Violation = Restart the Task) ─────────────────────

1.  NEVER hardcode file paths — use `pathlib.Path` everywhere
2.  NEVER write synchronous blocking I/O inside async functions — use `asyncio.to_thread()`
3.  NEVER access files outside the configured `index.root` — use `safe_resolve()` from `utils/path_guard.py`
4.  NEVER store file content in logs — log metadata only (path, line numbers, scores, timing)
5.  NEVER use `subprocess` or `os.system()` without a comment explaining why
6.  ALL public functions and classes MUST have type hints (mypy strict mode is enforced in CI)
7.  ALL new MCP tools MUST follow the exact docstring format used in `server.py`
8.  ALL Pydantic models MUST use `model_config = ConfigDict(frozen=True)`
9.  NEVER import from `codescope.server` into other modules — server is entry point only
10. ALWAYS use `loguru` for logging — never use `print()` in production code
11. BEFORE implementing any function that uses a library — invoke Context7 for that library's docs
12. AFTER completing any task — run `uv run ruff check . && uv run mypy codescope/` before marking done

## ── CODE CONVENTIONS ─────────────────────────────────────────────────────────

- File naming:      snake_case.py for all Python files
- Class naming:     PascalCase
- Function naming:  snake_case, verb-first (parse_file, build_index, search_code)
- Variable naming:  snake_case, descriptive (chunk_vectors, not cv)
- Constants:        UPPER_SNAKE_CASE in config.py
- Max function:     40 lines — refactor if longer
- Max file:         300 lines — split into modules if longer
- Docstrings:       Google style — every public function requires one
- Comments:         Explain WHY, not WHAT

## ── PROHIBITED PATTERNS ──────────────────────────────────────────────────────

❌ `from module import *`              — always use explicit named imports
❌ `except Exception: pass`            — always log or re-raise with context
❌ `time.sleep()` in async code        — use `asyncio.sleep()`
❌ Mutable default arguments           — use None + guard pattern
❌ Global state mutation outside storage.py
❌ `assert` in production code         — use `if not x: raise ValueError(...)`
❌ `SELECT *` or `collection.get()` without `include=` — always specify fields

## ── REQUIRED PATTERNS ────────────────────────────────────────────────────────

✅ All async MCP handlers:     wrap in try/except, return ErrorResponse on failure
✅ All file reads:             call safe_resolve() from utils/path_guard.py first
✅ All ChromaDB queries:       use include=["documents","metadatas","distances"] — never "embeddings"
✅ All embedding calls:        use embedder.encode(batch), never one-by-one
✅ All CLI commands:           show Rich progress bar for any operation > 1 second
✅ All new MCP tools:          add integration test in tests/integration/test_mcp_tools.py
✅ All language parsers:       handle empty file, malformed syntax, and file > 500KB gracefully

## ── CONTEXT7 USAGE RULES ────────────────────────────────────────────────────

ALWAYS invoke Context7 when working with:
- `mcp` SDK (FastMCP, tool decorators, transport config)
- `tree_sitter` (parser init, node traversal, grammar loading)
- `chromadb` (collection API, query params, metadata filters)
- `sentence_transformers` (encode params, model loading, normalization)
- `typer` + `rich` (CLI patterns, progress bars, output formatting)
- `watchdog` (Observer, FileSystemEventHandler)
- `pytest-asyncio` (async fixture patterns)

Command: `use context7 to get docs for [library_name]`

## ── CUSTOM SKILLS (USE THESE FOR RECURRING TASKS) ───────────────────────────

$new-mcp-tool   → Adding any new tool to server.py
$add-language   → Adding tree-sitter support for a new programming language
$cs-test        → Writing any test in the CodeScope test suite
$benchmark      → Running and interpreting performance benchmarks

## ── GIT COMMIT FORMAT ───────────────────────────────────────────────────────

Use Conventional Commits only:
  feat:     add find_similar MCP tool
  fix:      handle empty files in tree-sitter parser
  docs:     update AGENTS.md with new tool examples
  test:     add integration tests for TypeScript parser
  refactor: extract chunking logic to chunker.py
  perf:     batch embedding calls for 3x speedup
  chore:    update uv.lock dependencies

## ── TEST NAMING CONVENTION ─────────────────────────────────────────────────

Format: test_[unit]_[scenario]_[expected_outcome]
Examples:
  test_parser_empty_file_returns_empty_symbols
  test_engine_search_returns_results_ranked_by_score
  test_mcp_find_symbol_partial_name_matches_correctly
  test_path_guard_traversal_attempt_raises_value_error

## ── VALIDATION CHECKLIST (Run Before Marking Any Task Complete) ──────────────

☐ uv run ruff check codescope/       — zero linting errors
☐ uv run mypy codescope/             — zero type errors
☐ uv run pytest tests/unit/ -v       — all unit tests pass
☐ uv run pytest tests/integration/   — all integration tests pass
☐ git diff --stat                    — review what changed before committing
```

---

## 6. Implementation Roadmap

> Build in exact phase order. Each phase has a validation checkpoint.
> Do not proceed to the next phase until the current validation passes.

---

### Phase 0: Project Initialization (Day 1 — ~1.5 hours)

**0.1 — Bootstrap the repository**

```bash
uv init codescope
cd codescope
uv add mcp tree-sitter tree-sitter-python tree-sitter-typescript tree-sitter-go \
       sentence-transformers chromadb typer rich watchdog loguru pydantic tomllib
uv add --dev pytest pytest-asyncio mypy ruff coverage
```

- Files to create: `pyproject.toml`, `.gitignore`, `README.md`, `codescope.toml`
- Add to `pyproject.toml`:
```toml
[project.scripts]
codescope = "codescope.cli:app"

[tool.mypy]
strict = true
python_version = "3.12"

[tool.ruff]
line-length = 100
target-version = "py312"
```
- Validation: `uv run python -c "import mcp; import chromadb; print('OK')"` prints OK

**0.2 — Create complete directory skeleton**

- Create all directories and `__init__.py` files per Section 4 layout
- Validation: `find codescope/ -name "*.py" | wc -l` returns ≥ 10

**0.3 — Create `config.py` and `models.py`**

- Implement `AppConfig` dataclass loading from `codescope.toml` via `tomllib`
- Implement all Pydantic models: `SearchResult`, `SymbolResult`, `IndexStatus`, `CodeChunk`, `Symbol`
- All models must use `model_config = ConfigDict(frozen=True)`
- Validation: `uv run python -c "from codescope.config import load_config; print(load_config())"` works

---

### Phase 0.5: Codex Environment Setup (Day 1 — ~30 minutes)

> This phase configures your Codex agent environment so it can build CodeScope professionally.
> Complete this before writing any implementation code.

**0.5.1 — Install project-scoped MCP servers**

Create `.codex/config.toml` in the repo root:

```toml
# .codex/config.toml — project-scoped Codex configuration for CodeScope
# This file is read by Codex when run from the codescope/ directory.

[model]
default = "gpt-5.6-terra"   # Everyday implementation tasks

[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
startup_timeout_ms = 20000

[mcp_servers.openai-docs]
url = "https://developers.openai.com/mcp"

[project]
project_doc_max_bytes = 65536   # 64 KiB — raise from default 32 KiB
```

**0.5.2 — Install plugins via Codex CLI**

```bash
# Open Codex and run:
/plugins

# Install in this order:
# 1. Context7         (from Upstash marketplace)
# 2. GitHub           (from OpenAI Curated)
# 3. Codex Security   (from OpenAI Curated)
# 4. Sentry           (from OpenAI Curated)
```

Or via command line:
```bash
codex plugin marketplace add upstash/context7
codex plugin add context7@context7-marketplace

codex mcp add openai-docs -- npx -y @openai/openai-docs-mcp
```

**0.5.3 — Create custom skills directory**

```bash
mkdir -p .codex/skills/new-mcp-tool
mkdir -p .codex/skills/add-language
mkdir -p .codex/skills/cs-test
mkdir -p .codex/skills/benchmark
```

Then copy all 4 SKILL.md files from Section 14 of this document.

**0.5.4 — Verify environment**

```bash
# Restart Codex, then run:
codex --ask-for-approval never "List all active MCP servers and loaded skills."
```

Expected output: Context7, OpenAI Docs, and all 4 custom skills listed.

**Validation**: Codex can answer "What does the FastMCP @mcp.tool() decorator do?" using Context7 docs.

---

### Phase 1: AST Parser (Day 1–2 — ~4 hours)

> **Before starting**: `use context7 to get docs for tree-sitter python bindings`

**1.1 — Implement `codescope/parser.py`**

```python
class CodeParser:
    def parse_file(self, path: Path, source: bytes, language: str) -> list[Symbol]:
        """Parse a source file and return all top-level symbols."""

    def _extract_python_symbols(self, tree: Tree, source: bytes, file: Path) -> list[Symbol]:
        """Walk Python AST: extract function_definition, class_definition nodes."""

    def _extract_typescript_symbols(self, tree: Tree, source: bytes, file: Path) -> list[Symbol]:
        """Walk TypeScript AST: extract function_declaration, class_declaration nodes."""

    def _extract_go_symbols(self, tree: Tree, source: bytes, file: Path) -> list[Symbol]:
        """Walk Go AST: extract function_declaration, type_declaration nodes."""
```

Symbol model: `{name, kind, file, start_line, end_line, docstring, signature}`
Validation: All tests in `tests/unit/test_parser.py` pass for all 3 languages

**1.2 — Implement `codescope/chunker.py`**

Strategy: symbol-first (one function = one chunk), fall back to 512-token sliding window
Each `CodeChunk` must contain: `text`, `file`, `start_line`, `end_line`, `language`, `symbol_name`
Validation: No chunk exceeds 600 tokens; `test_chunker.py` passes

---

### Phase 2: Embedder + Storage (Day 2 — ~3 hours)

> **Before starting**: `use context7 to get docs for sentence-transformers encode method`
> `use context7 to get docs for chromadb python client collection API`

**2.1 — Implement `codescope/embedder.py`**

- Lazy-load `SentenceTransformer("all-MiniLM-L6-v2")` on first call; cache at class level
- Always use: `model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)`
- Return: `np.ndarray` shape `(n, 384)`, dtype `float32`
- Validation: `test_embedder.py` confirms shape `(n, 384)` and normalized vectors

**2.2 — Implement `codescope/storage.py`**

> **Before starting**: `use context7 to get docs for chromadb 0.6 collection query`

- ChromaDB collection name: `"codescope_chunks"`
- Implement: `add_chunks()`, `search()`, `delete_by_file()`, `count()`, `reset()`
- Always use `include=["documents", "metadatas", "distances"]` — never `"embeddings"`
- Handle `chromadb.errors.NotFoundError` explicitly in all query methods
- Validation: `test_storage.py` — add 10 chunks, search returns correct top-3

---

### Phase 3: Indexer Pipeline (Day 2–3 — ~4 hours)

**3.1 — Implement `codescope/utils/gitignore.py`**

Parse `.gitignore` patterns; return `is_ignored(path: Path) -> bool`
Validation: Files matching `.gitignore` patterns are excluded from index scan

**3.2 — Implement `codescope/indexer.py`**

Full pipeline function: `index(root: Path, config: AppConfig) -> IndexStatus`
```
scan_directory → filter_by_language + gitignore → parse → chunk → embed → store
```
Show `rich.progress.Progress` during indexing
Log: files scanned, files skipped, chunks created, time elapsed
Validation: `test_indexer.py` — index `tests/fixtures/sample_python/` in < 5 seconds

---

### Phase 4: Query Engine (Day 3 — ~3 hours)

**4.1 — Implement `codescope/engine.py`**

```python
class QueryEngine:
    def search_code(self, query: str, language: str | None, limit: int) -> list[SearchResult]: ...
    def find_symbol(self, name: str, kind: str | None) -> list[SymbolResult]: ...
    def find_similar(self, snippet: str, limit: int) -> list[SearchResult]: ...
    def get_index_status(self) -> IndexStatus: ...
```

Symbol index: load `symbols.json` at startup → keep in-memory dict for O(1) lookup
Validation: `test_engine.py` — all 3 search methods return correct results for test fixtures

---

### Phase 5: MCP Server (Day 3–4 — ~4 hours)

> This is the core deliverable for the hackathon. Use `$new-mcp-tool` skill for each tool.
> **Before starting**: `use context7 to get docs for FastMCP mcp python sdk tool decorator`

**5.1 — Implement `codescope/server.py`**

```python
from mcp.server.fastmcp import FastMCP
from codescope.engine import QueryEngine
from codescope.config import load_config
from codescope.models import SearchResult, SymbolResult, IndexStatus
from loguru import logger

config = load_config()
engine = QueryEngine(config)
mcp = FastMCP("codescope")

@mcp.tool()
def search_code(query: str, language: str | None = None, limit: int = 5) -> list[dict]:
    """
    Search the codebase semantically. ALWAYS call this before writing any new function
    to verify similar code does not already exist.

    Args:
        query: Natural language description or code fragment to search for
        language: Optional language filter ('python', 'typescript', 'go')
        limit: Number of results (default 5, max 20)

    Returns:
        List of matching code chunks with file path, line numbers, and relevance score.
        If relevance_score > 0.80, extend existing code rather than writing new code.
    """
    try:
        results = engine.search_code(query, language, min(limit, 20))
        return [r.model_dump() for r in results]
    except Exception as e:
        logger.error(f"search_code failed: {e}")
        return [{"error": True, "code": "QUERY_FAILED", "message": str(e),
                 "suggestion": "Verify the index exists by calling list_indexed_files()"}]

@mcp.tool()
def find_symbol(name: str, kind: str | None = None) -> list[dict]:
    """
    Find a specific function, class, method, or variable by name.
    Use this BEFORE modifying any existing code to locate its exact position.

    Args:
        name: Symbol name — supports partial match, case-insensitive
        kind: Optional filter: 'function', 'class', 'method', 'variable'

    Returns:
        List of matching symbols with exact file path and line number.
    """
    try:
        results = engine.find_symbol(name, kind)
        return [r.model_dump() for r in results]
    except Exception as e:
        logger.error(f"find_symbol failed: {e}")
        return [{"error": True, "code": "QUERY_FAILED", "message": str(e),
                 "suggestion": "Check that the index is built with codescope index ./src"}]

@mcp.tool()
def find_similar(code_snippet: str, limit: int = 3) -> list[dict]:
    """
    Find code semantically similar to the provided snippet.
    Use this BEFORE writing any new implementation to discover existing patterns.

    Args:
        code_snippet: The code you plan to write, or a fragment of it
        limit: Number of similar results (default 3, max 10)

    Returns:
        List of similar code chunks ranked by similarity. Score > 0.75 = likely duplicate.
    """
    try:
        results = engine.find_similar(code_snippet, min(limit, 10))
        return [r.model_dump() for r in results]
    except Exception as e:
        logger.error(f"find_similar failed: {e}")
        return [{"error": True, "code": "QUERY_FAILED", "message": str(e),
                 "suggestion": "Ensure the index is built and not empty"}]

@mcp.tool()
def list_indexed_files(language: str | None = None) -> dict:
    """
    Get a summary of what is currently in the CodeScope index.
    Call this FIRST at the start of any session to confirm the index is loaded.

    Args:
        language: Optional filter to count only files of a specific language

    Returns:
        Index status: file count, chunk count, language breakdown, last-indexed timestamp.
    """
    try:
        status = engine.get_index_status()
        return status.model_dump()
    except Exception as e:
        logger.error(f"list_indexed_files failed: {e}")
        return {"error": True, "code": "INDEX_NOT_FOUND", "message": str(e),
                "suggestion": "Run: codescope index ./src to build the index first"}

if __name__ == "__main__":
    mcp.run()
```

Validation: `test_mcp_tools.py` passes; live demo shows tools responding correctly in Codex

---

### Phase 6: CLI Interface (Day 4–5 — ~3 hours)

> **Before starting**: `use context7 to get docs for typer CLI python` and `rich progress`

**6.1 — Implement `codescope/cli.py`** with these commands:

```bash
codescope index [PATH]    # Index directory; show Rich progress bar
codescope status          # Show index statistics in Rich table
codescope search [QUERY]  # CLI search for testing without an AI agent
codescope serve           # Start MCP server in foreground
codescope reset           # Clear the entire index with confirmation prompt
```

Validation: `uv run codescope --help` shows all commands with descriptions

---

### Phase 7: Demo + Documentation (Day 5–6)

**7.1 — Create MCP configuration examples**

`examples/mcp_config_codex.json`:
```json
{
  "mcpServers": {
    "codescope": {
      "command": "uv",
      "args": ["run", "codescope", "serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

**7.2 — Record the demo** (`scripts/demo_codex.sh`)

Scenario: "User asks Codex to add email validation. Without CodeScope: Codex generates a new
validator function. With CodeScope: Codex calls `find_similar('email validation regex')`,
finds the existing `validate_email()` in validators.py, and extends it instead."

**7.3 — Finalize README.md** — include demo GIF, 5-minute quickstart, MCP config for
Codex + Claude Code + Cursor, tool reference table, install badge, test coverage badge

---

### Phase 8: Testing & Polish (Day 6–7)

Run `$cs-test` skill for each module, then `$benchmark` skill to verify all SLAs.
See Section 10 for complete test specifications.

---

## 7. `AGENTS.md` — Root-Level Agent Context File

> Place this at the repository root (`codescope/AGENTS.md`).
> Codex auto-discovers and reads this file at the start of every session.
> Keep under 200 lines — Codex performs better with concise, specific files.

```markdown
# CodeScope — AGENTS.md
# Auto-read by: Codex, Claude Code, Cursor, OpenCode, Gemini CLI

## What Is This Project?

CodeScope is a local MCP server that indexes a codebase and exposes semantic search tools.
Built with Python 3.12, the MCP SDK (FastMCP), tree-sitter, sentence-transformers, and ChromaDB.
Target: OpenAI Build Week 2026 hackathon. Open-source, MIT license.

## Core Modules (Read These Before Touching Anything)

- `codescope/server.py`   — MCP tool definitions (project entry point)
- `codescope/engine.py`   — Search and query logic
- `codescope/indexer.py`  — Full indexing pipeline
- `codescope/models.py`   — All data models (Pydantic, frozen)
- `codescope/config.py`   — Configuration loading from codescope.toml

## Build & Test Commands

```bash
uv sync                                         # Install all dependencies
uv run codescope index ./tests/fixtures/sample_python  # Test index build
uv run codescope status                         # Check index stats
uv run codescope search "validate user input"   # Test search
uv run codescope serve                          # Start MCP server
uv run pytest tests/unit/ -v                    # Fast unit tests
uv run pytest tests/ --cov=codescope --cov-report=term-missing  # Full suite
uv run ruff check codescope/                    # Linting
uv run mypy codescope/                          # Type checking
```

## Context7 Auto-Invoke Rule

Always use Context7 MCP when generating any code that uses these libraries:
mcp SDK, tree_sitter, chromadb, sentence_transformers, typer, rich, watchdog, pytest-asyncio.
Invoke: `use context7 to get [library] docs for [specific topic]`

## Custom Skills Available

Use these for recurring CodeScope tasks:
- `$new-mcp-tool`  — Scaffold a new MCP tool in server.py + engine.py + test
- `$add-language`  — Add tree-sitter language support with parser + tests
- `$cs-test`       — Write tests in AAA format matching the naming convention
- `$benchmark`     — Run benchmarks and compare results against SLA targets

## Architecture Summary

```
CLI (typer+rich) → MCP Server (FastMCP) → Query Engine → ChromaDB + SymbolIndex
                                           ↑
                               Indexer Pipeline:
                               Scanner → tree-sitter Parser → Chunker → Embedder
```

## Non-Negotiable Rules

1. Type hints on all public functions — mypy strict mode enforced in CI
2. Use safe_resolve() from utils/path_guard.py before reading any file
3. Use loguru for logging — no print() statements
4. Invoke Context7 before any library-specific implementation
5. Run ruff + mypy + pytest before marking any task complete
6. All new MCP tools need a test in tests/integration/test_mcp_tools.py

## DO NOT

- Modify `.codescope/` directory (runtime storage; excluded from git)
- Change MCP tool parameter names (breaks existing client configs)
- Import from `server.py` into other modules
- Add any function without a Google-style docstring
- Use `except Exception: pass` — always log or re-raise
```

---

## 8. `docs/codex.md` — Codex Integration Reference

> This is a **human-readable** documentation file.
> It is NOT auto-discovered by Codex. Keep it as a reference for the developer.

```markdown
# CodeScope — Codex Professional Usage Guide
# For: Ibadat Ali | @deepfx_ai | OpenAI Build Week 2026

## Model Selection Strategy

| Task Type | Model | Reasoning |
|-----------|-------|-----------|
| Implementing a new module | GPT-5.6 Terra | Balanced speed + quality for standard code |
| Architecture decisions | GPT-5.6 Sol | Complex reasoning; high-stakes choices |
| Adding docstrings | GPT-5.6 Luna | Fast, cheap; mechanical task |
| Refactoring existing code | GPT-5.6 Terra | Context-aware; moderate complexity |
| Debugging a failing test | GPT-5.6 Sol | Needs full diagnostic reasoning chain |
| Writing SKILL.md content | GPT-5.6 Terra | Moderate complexity prose |
| Security review | GPT-5.6 Sol | Highest stakes; no cost cutting |
| Benchmarks + performance | GPT-5.6 Sol | Needs deep analysis of results |

Switch model mid-session: `/model` in Codex TUI

## Active MCP Servers (Project-Scoped)

### Context7 — Library Documentation (HIGHEST PRIORITY)

Purpose: Injects version-specific, accurate library docs into Codex context.
Prevents hallucinated APIs that don't exist in the actual installed version.

Usage triggers (automatic via AGENTS.md rule):
- Any code using `mcp` SDK → Context7 fetches FastMCP docs
- Any `tree_sitter` code → Context7 fetches tree-sitter Python binding docs
- Any `chromadb` code → Context7 fetches v0.6 collection API docs
- Any `sentence_transformers` code → Context7 fetches encode() method docs

Manual invocation example:
```
use context7 to get chromadb 0.6 collection.query() docs with examples
```

### OpenAI Docs MCP — Official API Reference

Purpose: Live access to developers.openai.com documentation.
Use when: Looking up FastMCP patterns, MCP tool schemas, Codex config syntax.

Manual invocation example:
```
use openai-docs to find FastMCP @mcp.tool() decorator parameter schema
```

## Active Plugins

### GitHub Plugin (Official OpenAI)
Tasks enabled: Create PRs, read CI logs, manage issues, trigger Actions
Use for: Publishing releases, reading failed CI output, opening hackathon submission PR

### Codex Security Plugin (Official OpenAI)
Use before every PR: `/review` in Codex TUI
Focus areas for CodeScope: path traversal, log content leakage, input validation

### Sentry Plugin (Official OpenAI)
Use after any live demo deployment: "Codex, show me errors from Sentry for codescope"

### Matt Pocock Skills
$grill-me  → Run at the START of any Phase; forces clarifying questions before coding
$tdd       → Run when starting a new module; writes test first, then implementation
$diagnose  → Run when a test fails and the root cause is unclear
$zoom-out  → Run AFTER completing a Phase; checks for architecture drift

### Superpowers Plugin
Automatically enforces plan → execute → verify → review loop.
Best used for: Phase 3 (Indexer) and Phase 5 (MCP Server) — most complex phases.

## Codex Task Template (Copy This for Every Phase)

```
Goal:
  [One sentence: what should exist after this task that doesn't exist now]

Context:
  @codescope/[relevant_file].py
  @tests/[relevant_test_file].py

Constraints:
  - Follow rules in docs/.SYSTEM_INSTRUCTIONS.md
  - Use Context7 for any library calls
  - Use $new-mcp-tool / $cs-test skill as appropriate
  - Type hints on all public functions (mypy strict)
  - loguru for all logging — no print()

Done when:
  - uv run ruff check codescope/ → zero errors
  - uv run mypy codescope/ → zero errors
  - uv run pytest tests/[relevant_test].py -v → all pass
```

## API Key Management

- OpenAI API key: `OPENAI_API_KEY` environment variable — never hardcoded
- Context7 API key: `CONTEXT7_API_KEY` (optional; free tier works without it)
- All secrets: in `.env.local` (in `.gitignore`) — never in `.env` committed to git
- Production: use OS keychain or environment secrets management

## Prompt Engineering Best Practices for CodeScope

### Specificity Examples

GOOD: "Add a `_extract_rust_symbols()` method to `codescope/parser.py` that extracts
function_item and impl_item nodes from a tree-sitter Rust syntax tree.
Follow the exact same pattern as `_extract_python_symbols()`.
Use Context7 to get the tree-sitter-rust node type names.
Validation: uv run pytest tests/unit/test_parser.py::test_parser_rust -v passes."

BAD: "Add Rust support."

### Context Provision Pattern

Always use `@filename` to attach relevant files instead of describing them.
Example: `@codescope/parser.py @tests/unit/test_parser.py — add Rust parser method`

### Few-Shot Pattern

"Implement find_similar() in engine.py.
It should:
1. Accept code_snippet: str and limit: int = 3
2. Call self.embedder.encode([code_snippet]) to embed the snippet
3. Call self.storage.search(query_vector, n_results=limit)
4. Return list[SearchResult] converted from ChromaDB results
Validation: uv run pytest tests/unit/test_engine.py::test_find_similar -v passes"

## Cost Management

- Use GPT-5.6 Luna for: docstrings, formatting, type stubs — saves ~60% per task
- Use GPT-5.6 Terra for: all implementation tasks — baseline for CodeScope
- Reserve GPT-5.6 Sol for: architecture reviews, security analysis, complex debugging
- Context7 is free tier (1,000 requests/month) — sufficient for Build Week development
```

---

## 9. Codex Plugin & Skill Stack

> This section is the definitive reference for the CodeScope development environment.
> Every item here was verified against official documentation as of July 13, 2026.

### 9.1 Architecture — Three Layers of Extension

Understanding what type each extension is prevents configuration errors:

| Layer | What It Does | How Installed | When Active |
|-------|-------------|---------------|-------------|
| **MCP Server** | Provides live tools (search, fetch, query) | `config.toml` | Every session |
| **Plugin** | Bundles skills + app connections + MCP servers | `/plugins` UI | After install + restart |
| **Skill** | Reusable workflow instructions Codex follows | `SKILL.md` file | Implicit or `$skill-name` |

### 9.2 Tier 1 — Install Before Writing Any Code

#### Context7 MCP Server (MANDATORY)

**What it does**: Context7 is the #1 MCP server of 2026. It injects version-specific,
accurate library documentation directly into Codex's context. It has 54,100+ GitHub stars
and is placed in ThoughtWorks Technology Radar.

**Why it is mandatory for CodeScope**: Every core library you're using — the `mcp` Python SDK,
`tree-sitter` Python bindings (0.24+), `chromadb` (0.6 — API changed significantly from 0.4),
`sentence-transformers` (3.3+), and `FastMCP` — has changed in the last 12 months. Without
Context7, Codex writes code against APIs that no longer exist. This is not optional.

**Install (two methods — pick one)**:

Method A — Plugin (recommended, persistent):
```bash
codex plugin marketplace add upstash/context7
codex plugin add context7@context7-marketplace
# Restart Codex thread after installation
```

Method B — MCP config (add to `.codex/config.toml`):
```toml
[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
startup_timeout_ms = 20000
# Optional for higher rate limits:
# args = ["-y", "@upstash/context7-mcp", "--api-key", "YOUR_KEY"]
```

Method C — Remote HTTP (no local install required):
```toml
[mcp_servers.context7]
url = "https://mcp.context7.com/mcp"
```

**Auto-invoke rule** (add to `AGENTS.md`):
```markdown
Always use context7 when writing code that uses mcp, tree-sitter, chromadb,
sentence-transformers, typer, rich, or watchdog.
```

**Cost**: Free tier — 1,000 requests/month. Sufficient for Build Week.

---

#### OpenAI Docs MCP (MANDATORY)

**What it does**: Gives Codex live access to `developers.openai.com` documentation,
including the MCP SDK reference, FastMCP patterns, and Codex CLI configuration syntax.

**Why it is mandatory for CodeScope**: CodeScope IS an MCP server. Codex needs accurate
documentation on the FastMCP API, `@mcp.tool()` decorator schema, and transport configuration
to build it correctly without hallucinating parameters.

**Install**:
```toml
# Add to .codex/config.toml
[mcp_servers.openai-docs]
url = "https://developers.openai.com/mcp"
```

Or via CLI:
```bash
codex mcp add openai-docs -- npx -y @openai/openai-docs-mcp
```

**Cost**: Free.

---

#### GitHub Plugin (Official OpenAI — MANDATORY)

**What it does**: Enables Codex to triage PRs, read CI logs, manage issues, trigger Actions,
and publish releases — all from within the Codex session.

**Why it is mandatory for CodeScope**: You're building an open-source library with GitHub
Actions CI. Codex needs to: create the release PR, read failing CI output, manage the
hackathon submission workflow, and publish to PyPI via tagged releases.

**Install**:
```bash
# In Codex TUI:
/plugins → search "GitHub" → Install (OpenAI Curated)
# Or:
codex plugin install github --source openai
```

**Cost**: Free.

---

### 9.3 Tier 2 — Install Before Starting Implementation

#### Codex Security Plugin (Official OpenAI)

**What it does**: Runs a dedicated security review against uncommitted changes or a base
branch. Reports prioritized findings without modifying your working tree.

**Why critical for CodeScope**: CodeScope reads files from the developer's machine via an
MCP server. Path traversal vulnerabilities, unsafe file reads, and insufficient input
validation are existential security risks for this project. Run `/review` before every PR.

**Install**:
```bash
/plugins → search "Codex Security" → Install (OpenAI Curated)
```

**Usage**:
```
/review                           # Review uncommitted changes
/review --base main               # Review diff from main branch
```

---

#### Matt Pocock Community Skills Pack

**What it does**: Practical engineering skills that improve Codex's workflow behavior.

**Install**:
```bash
codex plugin install matt-pocock-skills --source awesome-codex-plugins
# Or manually: copy SKILL.md files from github.com/mattpocock/codex-skills
```

**Skills relevant to CodeScope and when to use them**:

| Skill | CodeScope Use Case | Command |
|-------|-------------------|---------|
| `grill-me` | Run at the start of every Phase — Codex asks clarifying questions before writing code | `$grill-me` |
| `tdd` | Run when starting each new module — writes test first, then implementation | `$tdd` |
| `diagnose` | Run when a pytest fails and root cause is unclear | `$diagnose` |
| `zoom-out` | Run after each Phase completes — checks for architecture drift | `$zoom-out` |
| `to-prd` | Run if scope expands — converts idea to structured spec update | `$to-prd` |

---

#### Superpowers Plugin

**What it does**: Adds a structured agent workflow layer: plan → execute → verify → review.
Prevents Codex from making random mid-task decisions (editing 6 unrelated files, generating
tests for untested behavior, scope creep during complex phases).

**Why valuable for CodeScope**: Phase 3 (Indexer Pipeline) and Phase 5 (MCP Server) are
the most complex phases. Without a structured workflow, Codex may partially implement a
function then jump to writing tests before the implementation is stable.

**Install**:
```bash
codex plugin install superpowers --source awesome-codex-plugins
```

**Usage**: Activate automatically for complex phases:
```
Superpowers: implement Phase 3 of the CodeScope indexer pipeline per CODESCOPE_SPEC_v2.md
```

---

#### Sentry Plugin (Official OpenAI)

**What it does**: Connects Codex to your Sentry error monitoring workspace — read error
traces, filter by environment, and ask Codex to fix specific production errors by Sentry ID.

**Why valuable**: Once CodeScope is in hackathon evaluators' hands, errors will occur in
environments you cannot reproduce. Sentry integration closes that loop.

**Install**:
```bash
/plugins → search "Sentry" → Install (OpenAI Curated) → authenticate
```

**Usage**:
```
"Codex, fix the error in Sentry issue CS-142 — show me the stack trace first"
```

---

### 9.4 What NOT to Install

| Plugin | Why to Skip |
|--------|-------------|
| Vercel / Build Web Apps | CodeScope is a CLI tool + Python package, not a web app. Adds irrelevant tools to context. |
| Notion / Linear | Unnecessary for a solo hackathon build. Wastes context tokens every session. |
| 10+ plugins at once | More plugins = more context overhead = worse Codex performance. Start small. |
| Hugging Face plugin | CodeScope uses sentence-transformers locally; no HF inference API needed. |
| Google Drive / Gmail | No relevance to Python MCP server development. |

**Rule**: Only install a plugin if you can name the specific task in CodeScope development
that it enables. If you cannot, skip it.

---

### 9.5 Complete `~/.codex/config.toml` — Global Developer Config

```toml
# ~/.codex/config.toml
# Global Codex configuration — applies to ALL repositories on this machine.
# Project-specific overrides live in .codex/config.toml at the repo root.

[model]
default = "gpt-5.6-terra"    # Default for everyday implementation tasks

[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
startup_timeout_ms = 20000
# Optional: add your API key for higher rate limits
# args = ["-y", "@upstash/context7-mcp", "--api-key", "YOUR_CONTEXT7_KEY"]

[mcp_servers.openai-docs]
url = "https://developers.openai.com/mcp"

[project]
# Raise the AGENTS.md size cap from 32 KiB (default) to 64 KiB
project_doc_max_bytes = 65536
# Fallback instruction file names (checked after AGENTS.md)
project_doc_fallback_filenames = [".SYSTEM_INSTRUCTIONS.md"]

[approval]
# Always require approval before Codex runs shell commands
shell_commands = "approve"
# Suggest file changes without auto-applying (safer for production code)
default_mode = "suggest"

[shell]
# Allowed commands for CodeScope development — block everything else
allowed_commands = [
    "uv", "python", "pytest", "ruff", "mypy",
    "git", "codescope", "npx", "cat", "ls", "find", "grep"
]
```

### 9.6 Priority Install Order (Timeline)

```
╔══════════════════════════════════════════════════════════════╗
║  Day 1 — Before Writing Any Code (Phase 0.5)                ║
╠══════════════════════════════════════════════════════════════╣
║  1. Context7 MCP          ← Prevents library API hallucinations
║  2. OpenAI Docs MCP       ← Live FastMCP + MCP SDK reference
║  3. Superpowers Plugin    ← Enforces plan→code→verify loop
╠══════════════════════════════════════════════════════════════╣
║  Day 2 — After First Module Is Built                        ║
╠══════════════════════════════════════════════════════════════╣
║  4. GitHub Plugin         ← CI integration + PR management
║  5. Matt Pocock Skills    ← $tdd and $diagnose active
╠══════════════════════════════════════════════════════════════╣
║  Day 6 — Before Hackathon Submission                        ║
╠══════════════════════════════════════════════════════════════╣
║  6. Codex Security scan   ← /review all changes before submit
║  7. Sentry Plugin         ← If hosting a live demo endpoint
╚══════════════════════════════════════════════════════════════╝

Custom Skills ($new-mcp-tool, $add-language, $cs-test, $benchmark)
— build at start of Phase 0.5; use throughout all phases
```

---

## 10. Comprehensive Testing Strategy

### Test Suite Overview

| Type | Framework | Location | Max Run Time | Coverage Target |
|------|-----------|----------|-------------|----------------|
| Unit | pytest | `tests/unit/` | 10 seconds | 90%+ |
| Integration | pytest | `tests/integration/` | 60 seconds | 85%+ |
| Performance | pytest | `tests/performance/` | 5 minutes | N/A (SLA checks) |
| Security | pytest | `tests/security/` | 30 seconds | 100% of security module |
| E2E Demo | pytest + bash | `tests/e2e/` | 2 minutes | N/A (scenario-based) |

### Phase T1: Unit Tests

Use `$cs-test` skill to generate all unit tests. Tests follow AAA (Arrange-Act-Assert) pattern.

**Critical test cases for each module:**

```python
# tests/unit/test_parser.py
def test_parser_python_function_extracts_name_and_lines(): ...
def test_parser_empty_file_returns_empty_list(): ...
def test_parser_malformed_syntax_returns_partial_results(): ...
def test_parser_typescript_class_extracts_all_methods(): ...
def test_parser_go_function_with_multiple_returns(): ...
def test_parser_file_over_size_limit_is_handled_gracefully(): ...

# tests/unit/test_chunker.py
def test_chunker_function_over_512_tokens_splits_at_boundary(): ...
def test_chunker_small_file_produces_single_chunk(): ...
def test_chunker_every_chunk_has_required_metadata_fields(): ...
def test_chunker_no_chunk_exceeds_600_tokens(): ...

# tests/unit/test_embedder.py
def test_embedder_returns_correct_shape_n_by_384(): ...
def test_embedder_returns_float32_dtype(): ...
def test_embedder_batch_mode_faster_than_sequential(): ...
def test_embedder_model_lazy_loaded_only_once(): ...

# tests/unit/test_engine.py
def test_engine_search_returns_results_ranked_by_score(): ...
def test_engine_find_symbol_case_insensitive_partial_match(): ...
def test_engine_find_similar_returns_fewer_when_index_small(): ...
def test_engine_search_with_language_filter_excludes_others(): ...

# tests/unit/test_path_guard.py
def test_path_guard_traversal_attempt_raises_value_error(): ...
def test_path_guard_valid_path_within_root_returns_resolved(): ...
def test_path_guard_symlink_outside_root_raises_value_error(): ...
```

### Phase T2: Integration Tests

```python
# tests/integration/test_indexer.py
def test_indexer_full_pipeline_indexes_python_fixtures(): ...
def test_indexer_respects_gitignore_patterns(): ...
def test_indexer_skips_files_over_size_limit(): ...
def test_indexer_completes_10k_lines_under_30_seconds(): ...

# tests/integration/test_mcp_tools.py
async def test_search_code_returns_relevant_result_for_fixture(): ...
async def test_find_symbol_locates_exact_function_and_line(): ...
async def test_find_similar_detects_near_duplicate(): ...
async def test_list_indexed_files_reflects_actual_state(): ...
async def test_all_tools_return_error_response_when_index_missing(): ...
```

### Phase T3: Performance Tests

```python
# tests/performance/test_benchmarks.py
def test_index_10k_line_repo_under_30_seconds(): ...       # SLA: < 30s
def test_search_latency_p95_under_150ms(): ...             # SLA: < 150ms
def test_symbol_lookup_p95_under_50ms(): ...               # SLA: < 50ms
def test_batch_embedding_3x_faster_than_sequential(): ...  # SLA: ≥ 3x speedup
def test_memory_footprint_idle_under_200mb(): ...          # SLA: < 200MB
```

Run after every significant change: `$benchmark` skill automates this.

### Phase T4: Security Tests

```python
# tests/security/test_path_safety.py
def test_search_query_cannot_read_files_outside_index_root(): ...
def test_index_rejects_symlinks_pointing_outside_root(): ...
def test_log_output_does_not_contain_file_content(): ...
def test_input_validation_rejects_limit_over_20(): ...
def test_input_validation_rejects_invalid_language_string(): ...
```

### Phase T5: E2E Demo Test

```python
# tests/e2e/test_duplication_prevention.py
def test_codescope_prevents_email_validator_duplication():
    # Arrange: index sample_python/ which contains validate_email() in validators.py
    # Act: call find_similar("def validate_email(email: str) -> bool:")
    # Assert: top result points to validators.py with score > 0.75
    ...
```

### Test Design Methodology — AAA Pattern (Mandatory)

```python
def test_engine_search_returns_results_ranked_by_score():
    # ── Arrange ──────────────────────────────────────────────
    engine = QueryEngine(test_config)
    # (fixtures pre-index sample_python/ via conftest.py)

    # ── Act ──────────────────────────────────────────────────
    results = engine.search_code("validate user credentials", language=None, limit=5)

    # ── Assert ────────────────────────────────────────────────
    assert len(results) > 0
    assert results[0].relevance_score >= results[1].relevance_score  # Ranked
    assert all(isinstance(r, SearchResult) for r in results)
    assert all(0.0 <= r.relevance_score <= 1.0 for r in results)
```

---

## 11. Security Requirements

| Requirement | Implementation | Severity |
|-------------|---------------|----------|
| Path traversal prevention | `safe_resolve()` validates all paths before file reads | Critical |
| No code content in logs | loguru format excludes file content; only metadata | High |
| Config injection prevention | `tomllib` only (stdlib) — no `eval()` in config loading | High |
| Dependency pinning | `uv.lock` committed; `uv sync --frozen` in CI | Medium |
| MCP server isolation | stdio transport only in default config | Medium |
| `.codescope/` gitignore | Auto-add on first `codescope index` run | Medium |
| Input validation | `limit` clamped to [1, 20]; `language` validated against allowlist | Medium |
| Context7 trust | Treat Context7 output as documentation reference, not executable code | Medium |

### Path Traversal Prevention — Concrete Implementation

```python
# codescope/utils/path_guard.py
from pathlib import Path

def safe_resolve(path: Path, root: Path) -> Path:
    """
    Resolve path and verify it stays within the allowed root directory.
    Call this BEFORE any file read operation in the indexer or server.

    Raises:
        ValueError: If the resolved path is outside the allowed root.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()

    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"Security: path traversal blocked. "
            f"{resolved} is outside allowed root {root_resolved}"
        )
    return resolved
```

### Context7 Security Note

Context7 delivers community-contributed documentation into Codex's context. A context
poisoning vulnerability (ContextCrush) was discovered and patched in February 2026.
Mitigation: treat Context7 output as documentation reference only — never execute it
directly. Review all generated code before running, as you would with any AI output.

---

## 12. Code Optimization Guidelines

### Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Index time (10K lines) | < 30 seconds | `test_benchmarks.py` |
| Search latency (p95) | < 150ms | `test_benchmarks.py` |
| Symbol lookup (p95) | < 50ms | `test_benchmarks.py` |
| Memory footprint (idle) | < 200MB | `psutil` in benchmark |
| Embedding batch (64 chunks) | < 2 seconds | `test_benchmarks.py` |
| CLI startup time | < 1 second | Manual timing |

### Caching Strategy

```python
# Embedder: cache the model at class level — load once per process
class Embedder:
    _model: SentenceTransformer | None = None

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        if cls._model is None:
            cls._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._model

# Engine: cache symbol index in memory after first load
class QueryEngine:
    def __init__(self, config: AppConfig) -> None:
        self._symbol_index: dict[str, list[SymbolResult]] | None = None

    @property
    def symbol_index(self) -> dict[str, list[SymbolResult]]:
        if self._symbol_index is None:
            self._symbol_index = self._load_symbol_index()
        return self._symbol_index
```

### Embedding Optimization

```python
# Always batch, always normalize — in embedder.py
vectors = model.encode(
    texts,
    batch_size=64,
    normalize_embeddings=True,    # Enables dot-product (30% faster at query time)
    show_progress_bar=False,
    convert_to_numpy=True,
)
```

### ChromaDB Query Optimization

```python
# Never include "embeddings" in query results — wastes memory and bandwidth
results = collection.query(
    query_embeddings=[query_vector.tolist()],
    n_results=limit,
    include=["documents", "metadatas", "distances"],  # Only what you need
    where={"language": language} if language else None,
)
```

---

## 13. Token Efficiency Notes for AI Agents

These guidelines minimize token waste across all Codex sessions on CodeScope.

1. **Start each session** by reading `.CHAT_MEMORY.md` — know where the build is before exploring anything else
2. **Before asking "what does X do?"** — call `find_symbol("X")` (if index is built) or read only that module's file
3. **Before writing any new function** — call `search_code("[description]")` and `find_similar("[planned code]")`
4. **When debugging a failing test** — read only the failing test file + the module it imports. Don't load the whole codebase
5. **When implementing a new MCP tool** — invoke `$new-mcp-tool` skill; it loads only the files that are needed
6. **Context7 is token-efficient** — a focused Context7 call (`get docs for chromadb collection.query`) is cheaper than having Codex infer from stale training data and then correcting mistakes
7. **Module read order for new sessions** (minimum viable context):
   - `models.py` → understand data structures
   - `config.py` → understand configuration
   - `server.py` → understand the public interface
   - Then ONLY the module you're modifying

---

## 14. Custom Skill Definitions

> Copy each SKILL.md into `.codex/skills/[skill-name]/SKILL.md`.
> After adding skills, restart Codex for them to be discovered.

### Skill 1: `$new-mcp-tool`

**File**: `.codex/skills/new-mcp-tool/SKILL.md`

```markdown
---
name: new-mcp-tool
description: Add a new MCP tool to CodeScope server.py following the project pattern.
  Trigger on: "add a new tool", "implement a new MCP tool", "add search capability",
  "expose a new query as a tool". Handles engine method + server tool + integration test.
---

# Add New MCP Tool to CodeScope

## Step 1: Confirm Requirements
Ask the user:
- What is the tool name? (snake_case verb)
- What does it accept as parameters?
- What does it return?
- Is there already an engine method for this, or do we need to add one?

## Step 2: Check Existing Patterns
Read `codescope/server.py` — study the existing @mcp.tool() decorator pattern.
Read `codescope/engine.py` — find the most similar existing query method.
Invoke Context7: `use context7 to get FastMCP @mcp.tool() docstring format`

## Step 3: Implement Engine Method (if needed)
In `codescope/engine.py`, add the query method following the existing pattern.
All engine methods return typed Pydantic models, not raw dicts.

## Step 4: Implement MCP Tool in server.py
Follow the EXACT docstring format of existing tools:
- Args section with all parameters
- Returns section explaining shape and interpretation
- Error handling via try/except returning ErrorResponse dict
- Log errors with loguru: logger.error(f"tool_name failed: {e}")

## Step 5: Write Integration Test
In `tests/integration/test_mcp_tools.py`, add:
  async def test_[tool_name]_[happy_path_scenario](): ...
  async def test_[tool_name]_error_when_index_missing(): ...

## Step 6: Validate
Run: uv run pytest tests/integration/test_mcp_tools.py -v
Run: uv run ruff check codescope/ && uv run mypy codescope/
```

---

### Skill 2: `$add-language`

**File**: `.codex/skills/add-language/SKILL.md`

```markdown
---
name: add-language
description: Add tree-sitter language support to CodeScope's parser.py.
  Trigger on: "add Rust support", "support Java", "add [language] parsing",
  "extend language support", "add new programming language". Full pipeline:
  dependency install + parser method + language mapping + unit tests.
---

# Add New Language to CodeScope

## Step 1: Get Context7 Docs
`use context7 to get tree-sitter [language_name] python bindings node types`

## Step 2: Install Grammar
```bash
uv add tree-sitter-[language]
```
Verify the grammar package name on PyPI first.

## Step 3: Update Language Mapping
In `codescope/utils/language.py`, add the file extension(s) to the language map.

## Step 4: Add Parser Method
In `codescope/parser.py`, add:
```python
def _extract_[language]_symbols(
    self, tree: Tree, source: bytes, file: Path
) -> list[Symbol]:
    """Extract functions, classes, and methods from [Language] source.

    Relevant node types (from tree-sitter-[language]):
    - [list node type names from Context7 docs]
    """
```
Follow the EXACT same structure as `_extract_python_symbols()`.
Handle at minimum: function declarations, class/struct declarations.

## Step 5: Wire into parse_file()
Add an `elif language == "[language]"` branch in `parse_file()`.

## Step 6: Add Test Fixtures
Create: `tests/fixtures/sample_[language]/` with 2–3 realistic source files.
Include at minimum: a file with functions, a file with classes, an empty file.

## Step 7: Write Unit Tests
In `tests/unit/test_parser.py`, add:
  def test_parser_[language]_function_extracts_name_and_lines(): ...
  def test_parser_[language]_class_extracts_correctly(): ...
  def test_parser_[language]_empty_file_returns_empty_list(): ...

## Step 8: Validate
uv run pytest tests/unit/test_parser.py -v -k "[language]"
uv run ruff check codescope/ && uv run mypy codescope/
```

---

### Skill 3: `$cs-test`

**File**: `.codex/skills/cs-test/SKILL.md`

```markdown
---
name: cs-test
description: Write tests for the CodeScope project following the AAA pattern and
  naming convention. Trigger on: "write a test for", "add test coverage", "test this
  function", "add unit tests", "write integration tests for", or when implementing
  any new function (use alongside $new-mcp-tool and $add-language).
---

# Write Tests for CodeScope

## Naming Convention (Mandatory)
Format: test_[unit]_[scenario]_[expected_outcome]
Examples:
  test_parser_empty_file_returns_empty_symbols
  test_engine_search_returns_results_ranked_by_score
  test_mcp_find_symbol_partial_name_matches_correctly
  test_path_guard_traversal_attempt_raises_value_error

## Test Structure (AAA — Mandatory)
```python
def test_[unit]_[scenario]_[expected_outcome]():
    # ── Arrange ──────────────────────────────────
    [Set up all inputs, mocks, and expected values]

    # ── Act ──────────────────────────────────────
    result = [call the single function under test]

    # ── Assert ───────────────────────────────────
    assert [specific condition about result]
    assert [second condition if needed]
    # Max 3 assertions per test — split into multiple tests if more needed
```

## Coverage Requirements
- Every new function needs: 1 happy path test + at least 2 error/edge case tests
- Error cases to always cover: empty input, None input, oversized input, invalid type
- Integration tests: use real files from tests/fixtures/, never mocks for ChromaDB

## Async Tests (for MCP tools)
```python
import pytest

@pytest.mark.asyncio
async def test_mcp_[tool_name]_[scenario]():
    # Use the shared engine fixture from conftest.py
    ...
```

## Fixtures (use from conftest.py, don't recreate)
- `test_config` — AppConfig with test paths
- `indexed_engine` — pre-indexed QueryEngine using sample_python fixtures
- `temp_index_dir` — temporary .codescope/ directory, cleaned after test

## Validation
uv run pytest tests/[target_test_file].py -v
uv run pytest tests/ --cov=codescope --cov-report=term-missing
```

---

### Skill 4: `$benchmark`

**File**: `.codex/skills/benchmark/SKILL.md`

```markdown
---
name: benchmark
description: Run CodeScope performance benchmarks and compare results against SLA targets.
  Trigger on: "run benchmarks", "check performance", "test speed", "is this fast enough",
  "benchmark the indexer", "check if we meet the SLA", or after completing any Phase
  in the implementation roadmap.
---

# Run and Interpret CodeScope Benchmarks

## Step 1: Run the Benchmark Suite
```bash
uv run python scripts/benchmark.py
uv run pytest tests/performance/test_benchmarks.py -v --tb=short
```

## Step 2: Compare Against SLA Targets
Check each result against these targets:

| Metric | SLA Target | PASS/FAIL |
|--------|-----------|-----------|
| Index 10K lines | < 30 seconds | ? |
| Search latency p95 | < 150ms | ? |
| Symbol lookup p95 | < 50ms | ? |
| Batch embedding (64) | < 2 seconds | ? |
| Memory idle | < 200MB | ? |
| CLI startup | < 1 second | ? |

## Step 3: If Any SLA Fails — Diagnose

For slow indexing:
- Check batch_size in embedder (should be 64, not 1)
- Verify tree-sitter grammar is pre-compiled (not re-parsing on each call)
- Profile with: uv run python -m cProfile -s cumulative scripts/benchmark.py

For slow search:
- Verify normalize_embeddings=True in encode() (enables dot-product)
- Check ChromaDB include list (never include "embeddings")
- Check index size (too many chunks from small files?)

For high memory:
- Confirm sentence-transformers model is lazily loaded (class-level cache)
- Check if ChromaDB is loading full collection on startup

## Step 4: Report Format
After running benchmarks, report:
```
BENCHMARK RESULTS — [DATE]
══════════════════════════════════════
Index 10K lines:  [X.X]s    [PASS/FAIL — target <30s]
Search p95:       [X]ms     [PASS/FAIL — target <150ms]
Symbol lookup p95:[X]ms     [PASS/FAIL — target <50ms]
Batch embed (64): [X.X]s    [PASS/FAIL — target <2s]
Memory idle:      [X]MB     [PASS/FAIL — target <200MB]
══════════════════════════════════════
Overall: [X/6] SLAs passing
```
```

---

## 15. Agent Chat Storage Protocol — `docs/.CHAT_MEMORY.md`

> AI agents MUST update this file at the end of every work session.
> Prevents re-analyzing the full codebase at the start of each new session.
> Template — fill in as the build progresses.

```markdown
# CodeScope — Session Memory (.CHAT_MEMORY.md)
# Update this file at the END of every Codex session, before closing.

**Last Updated**: [DATE TIME]
**Updated By**: [Codex / Claude Code / Manual]
**Spec Version**: CODESCOPE_SPEC_v2.md

## ── BUILD STATUS ────────────────────────────────────────────────────

| Phase | Status | Completed | Notes |
|-------|--------|-----------|-------|
| Phase 0: Project Init | ⏳ | — | — |
| Phase 0.5: Codex Env Setup | ⏳ | — | — |
| Phase 1: AST Parser | ⏳ | — | — |
| Phase 2: Embedder + Storage | ⏳ | — | — |
| Phase 3: Indexer Pipeline | ⏳ | — | — |
| Phase 4: Query Engine | ⏳ | — | — |
| Phase 5: MCP Server | ⏳ | — | — |
| Phase 6: CLI Interface | ⏳ | — | — |
| Phase 7: Demo + Docs | ⏳ | — | — |
| Phase 8: Testing + Polish | ⏳ | — | — |

Status: ✅ Complete | 🔄 In Progress | ⏳ Not Started | ❌ Blocked

## ── PLUGIN ENVIRONMENT STATUS ────────────────────────────────────────

| Plugin/MCP | Status | Notes |
|-----------|--------|-------|
| Context7 MCP | ⏳ | — |
| OpenAI Docs MCP | ⏳ | — |
| GitHub Plugin | ⏳ | — |
| Codex Security Plugin | ⏳ | — |
| Matt Pocock Skills | ⏳ | — |
| Superpowers Plugin | ⏳ | — |
| $new-mcp-tool skill | ⏳ | — |
| $add-language skill | ⏳ | — |
| $cs-test skill | ⏳ | — |
| $benchmark skill | ⏳ | — |

## ── LAST SESSION ─────────────────────────────────────────────────────

**What was completed**: [Describe]
**Files modified**: [List file paths]
**Tests status**: [X/Y unit passing | X/Y integration passing]
**Coverage**: [X]%
**SLAs passing**: [X/6]

## ── CURRENT BLOCKERS ────────────────────────────────────────────────

[Any issues that blocked progress or need resolution next session]

## ── NEXT SESSION TASK ───────────────────────────────────────────────

Phase: [Phase X.Y]
Task: [Exact task from the roadmap]
Skill to invoke: [$skill-name if applicable]
Start command: [exact command to run first]

## ── KEY DECISIONS LOG ───────────────────────────────────────────────

| Date | Decision | Rationale |
|------|---------|-----------|
| [DATE] | Chose ChromaDB over FAISS | Local dev tool; persistence matters more than throughput |
| [DATE] | all-MiniLM-L6-v2 model | Zero API cost; 85% quality of text-embedding-3-small for code |
```

---

## Strategic Gaps & Recommendations

### Scalability

Current design is local-first, single-developer. For team-shared mode:
- Change `transport = "stdio"` to `"streamable-http"` in `codescope.toml`
- Replace ChromaDB with PostgreSQL + `pgvector` for concurrent access
- Add API key authentication middleware to the HTTP endpoint
- A single server instance per team handles up to ~20 concurrent developers

### DevOps & Deployment

**CI/CD — `.github/workflows/ci.yml`**:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { version: "0.5" }
      - run: uv sync --frozen
      - run: uv run ruff check codescope/
      - run: uv run mypy codescope/
      - run: uv run pytest tests/ --cov=codescope --cov-fail-under=85
      - uses: codecov/codecov-action@v4
```

**PyPI Release — `.github/workflows/release.yml`**:
```yaml
on:
  push:
    tags: ['v*']
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv build
      - run: uv publish --token ${{ secrets.PYPI_TOKEN }}
```

### Monitoring & Observability

```python
# codescope/utils/timing.py — apply @timed to all MCP tool handlers
import functools, time
from loguru import logger

def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"{func.__name__} | {elapsed_ms:.1f}ms")
        if elapsed_ms > 500:
            logger.warning(f"SLA BREACH: {func.__name__} took {elapsed_ms:.1f}ms (target <150ms)")
        return result
    return wrapper
```

Log configuration: `.codescope/codescope.log`, rotation at 10MB, retention of 3 files.

### Disaster Recovery

CodeScope's index is always rebuildable from source files:
- **Corruption**: `codescope reset && codescope index ./src`
- **Version upgrade**: always reset + rebuild (schema may change between versions)
- **No user data risk**: the index only contains code that already exists in the repo

---

## Appendix

### Glossary

| Term | Definition |
|------|-----------|
| **MCP** | Model Context Protocol — open standard for AI tools to connect to external data sources |
| **FastMCP** | High-level decorator API in the official MCP Python SDK for defining tools |
| **tree-sitter** | Incremental, error-tolerant parser generator; builds concrete syntax trees |
| **AST** | Abstract Syntax Tree — tree representation of a source file's grammatical structure |
| **Symbol** | Named code entity: function, class, method, variable, or type declaration |
| **Chunk** | A segment of code (typically one function or ≤512 tokens) used as the unit of indexing |
| **Embedding** | Fixed-length float32 vector representing the semantic meaning of text or code |
| **ChromaDB** | Open-source, local-first vector database backed by SQLite; zero infrastructure |
| **sentence-transformers** | Python library for generating text embeddings locally using transformer models |
| **stdio transport** | MCP communication via standard input/output; used for local process communication |
| **Context7** | MCP server (#1 in 2026) that injects version-specific library docs into agent context |
| **uv** | Modern Python package manager by Astral (acquired by OpenAI Feb 2026); 100x faster than pip |
| **ruff** | Fast Python linter and formatter by Astral; replaces flake8, isort, and black |
| **Skill** | A `SKILL.md` file containing reusable workflow instructions for Codex |
| **Plugin** | A versioned bundle of skills + app connections + MCP servers, installable via `/plugins` |
| **AGENTS.md** | Cross-tool agent instruction file; auto-read by Codex, Claude Code, Cursor, and 30+ tools |

### References

| Resource | URL |
|---------|-----|
| MCP Python SDK | github.com/modelcontextprotocol/python-sdk |
| FastMCP Documentation | developers.openai.com/codex/mcp |
| tree-sitter Documentation | tree-sitter.github.io/tree-sitter |
| sentence-transformers: all-MiniLM-L6-v2 | huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |
| ChromaDB Python Client | docs.trychroma.com |
| uv Package Manager | docs.astral.sh/uv |
| Codex Plugin Marketplace | developers.openai.com/codex/plugins |
| Codex Skills Documentation | developers.openai.com/codex/skills |
| Context7 Setup | context7.com/docs/resources/all-clients |
| AGENTS.md Specification | agents.md |
| OpenAI Build Week | openai.devpost.com |

### Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-07-12 | Initial specification |
| 2.0.0 | 2026-07-13 | Added Section 9 (Plugin & Skill Stack), Phase 0.5, updated all AGENTS.md/codex.md with plugin integration, 4 custom SKILL.md definitions, updated ~/.codex/config.toml, Context7 security note, priority install timeline |

---

*This specification is agent-executable. An AI agent reading this can start at Phase 0,
set up the plugin environment in Phase 0.5, and build all 8 phases without clarification.
Update `.CHAT_MEMORY.md` at the end of every session.*
