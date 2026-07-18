# CodeScope

CodeScope is a local-first MCP preflight system for developer tools. Its intended workflow helps GPT-5.6 and Codex inspect an existing Python repository before generating code, so they can make evidence-backed **REUSE**, **EXTEND**, or **CREATE** decisions and reduce duplicate logic.

## Current implementation status

OpenAI Build Week Phase 8 is implemented on `main` in owner-created checkpoint commit `5afc064`. A final clean audit was completed on July 18, 2026; the resulting factual evidence corrections are in the working tree awaiting owner review. The repository currently provides:

- a Python 3.12 package with `version`, `index`, `status`, `search`, `serve`, and `reset` commands;
- immutable validated configuration, public models, stable domain errors, and centralized path guards;
- Tree-sitter Python symbol extraction and model-budgeted, symbol-aware source chunking;
- lazy cache-only Sentence Transformers embeddings and telemetry-disabled persistent Chroma storage;
- secure deterministic `.py` and `.pyi` discovery with configured and root `.gitignore` exclusions;
- mandatory secret, environment, cache, model, archive, image, database, build, and dependency-tree exclusions that repository negation rules cannot re-enable;
- bounded descriptor reads with size-race, regular-file, binary, and strict UTF-8 checks;
- contained symlink handling with physical-file deduplication and cycle prevention;
- bounded embedding batches, deterministic source metadata, SHA-256 hashes, and stable chunk IDs;
- failure-safe full-index rebuilds in restricted sibling directories, verified before promotion;
- rollback-capable live-index replacement with exact generated-path cleanup;
- atomic `symbols.json` and `index_meta.json` persistence plus bounded metadata reads;
- status validation that reconciles metadata, symbol, language, model, fingerprint, Chroma count, and runtime size.
- a read-only query engine for semantic search, exact and partial symbol lookup, similar-code evidence, and authoritative index status;
- bounded source-only snippets, deterministic ranking and tie-breaking, finite relevance scores, and stable typed query failures.
- a production Typer/Rich CLI for safe indexing, authoritative status, semantic search, deterministic JSON, and exact-runtime reset;
- a lazy local stdio MCP server exposing exactly four read-only tools: `search_code`, `find_symbol`, `find_similar`, and `list_indexed_files`;
- structured safe tool errors, strict nonreflective protocol validation, read-only annotations, protocol-only stdout, and explicit untrusted-source instructions;
- verified Codex MCP configuration examples under `.codex/config.toml.example` and `examples/codex_mcp_config.toml`.

CodeScope can now build, validate, query, and reset a local index for a Python repository through its CLI, typed Python engine API, and four-tool local MCP interface. It does not yet provide the Phase 9 repository preflight skill, the final duplication-prevention demonstration, benchmarks, or submission packaging.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A platform supported by the locked Python dependencies

Phases 1 through 8 have been validated in the current Linux development environment. Broader supported-platform claims and clean-clone verification remain deferred.

## Setup

Clone the repository, then install the locked development environment:

```bash
uv sync
```

The default configuration is [`codescope.toml`](codescope.toml). Configuration paths are resolved relative to that file. The indexing root must already exist; `codescope index` creates the configured runtime only for a validated rebuild.

The first preparation of the default embedding model requires explicit network permission and a local cache outside the repository. Normal indexing is cache-only and fails safely with an actionable message when the model is unavailable. Use `--allow-model-download` only for an explicitly authorized one-time preparation run.

## Current operation

Run the current acceptance path from the repository root after the default model has been prepared locally:

```bash
uv run codescope version
uv run codescope index tests/fixtures/sample_python
uv run codescope status
uv run codescope search "email validation"
uv run codescope search "email validation" --json
uv run codescope reset --yes
```

The Phase 8 isolated offline acceptance path indexed 4 files into 11 symbols and 16 chunks, reported authoritative status, returned `validate_email` at `validators.py` lines 6–9 through MCP semantic and symbol calls, exercised similar-code evidence, and preserved project-relative source metadata. This remains a development acceptance path rather than the final judge workflow: clean-clone model preparation, the Phase 9 preflight skill, and the duplication-prevention demonstration remain pending.

## Local MCP operation

From the repository root, prepare the configured model and build an index before semantic calls, then start the protocol server with:

```bash
uv run codescope serve
```

The server writes MCP JSON-RPC traffic only to stdout and performs no repository scan, model load, Chroma open, or index creation at startup. Missing indexes become structured `INDEX_NOT_FOUND` tool results rather than startup failures.

For Codex, copy the `mcp_servers.codescope` table from [`.codex/config.toml.example`](.codex/config.toml.example) or [`examples/codex_mcp_config.toml`](examples/codex_mcp_config.toml) into a trusted Codex configuration. Launch Codex from the CodeScope repository root, verify registration with `codex mcp list`, and inspect the tools with `/mcp`. The examples use only configuration keys verified against the installed Codex CLI and current official Codex MCP documentation; they do not modify the active project configuration.

## Testing

Run the current checks with:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest tests/security -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/codescope
uv run codescope version
```

Phase-specific commands and observed results are recorded in [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Hackathon submission requirements are tracked in [`docs/HACKATHON_COMPLIANCE.md`](docs/HACKATHON_COMPLIANCE.md).

## Sample data

The license-safe fixtures under `tests/fixtures/sample_python/` cover representative Python syntax and serve as the deterministic indexing and query sample. Unit tests use injected model/tokenizer/storage seams without network access; explicit integration tests exercise the already cached default model in offline mode from indexing through semantic, symbol, similar-code, and status queries. A polished judge path and clean-clone model-preparation flow remain submission-stage work.

## Current limitations

- Python repositories only; supported source extensions are `.py` and `.pyi`.
- Only the repository-root `.gitignore` is interpreted; nested `.gitignore` semantics are deferred.
- No symbol/similar-code CLI commands, Phase 9 agent preflight skill, or final duplication-prevention demonstration.
- The real model must be prepared explicitly before cache-only use; no model assets are stored in this repository.
- Rebuild promotion is rollback-capable across tested failures, but portable filesystem operations cannot eliminate validation-to-use races or guarantee recovery from every simultaneous filesystem failure.
- No dashboard, remote hosting, authentication, deployment, file watching, benchmark, or performance claim.

## Built During OpenAI Build Week

The repository distinguishes pre-existing planning from Build Week implementation through dated Git history and [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Work completed through Phase 8 comprises the package foundation, validated configuration and path security, Tree-sitter Python extraction, model-aware chunking, local embeddings, persistent Chroma, atomic metadata, deterministic secure discovery, bounded reads and batching, failure-safe full rebuilds, status verification, read-only semantic and symbol querying, similar-code evidence, the six-command CLI, safe terminal/JSON output, exact-runtime reset, and the four-tool local stdio MCP server with protocol and security tests. The Phase 9 skill, demonstration, benchmark, and submission work remains incomplete and must not be inferred from planning documents.

## How Codex and GPT-5.6 Were Used

Codex with GPT-5.6 was used in the primary implementation thread to inspect the Build Master and repository constraints; consult version-matched Tree-sitter, Hugging Face, Chroma, pathlib, pathspec, Typer, Rich, MCP SDK, and official Codex MCP documentation; implement Phases 1–8; run deterministic, real-model, rollback, protocol, security, and CLI validation; and review each working-tree security diff. In Phase 5, Codex traced scanner and promotion boundaries and corrected a bounded-directory materialization defect. In Phase 6, Codex implemented dependency-injected query orchestration and deterministic ranking. In Phase 7, Codex implemented the CLI boundary, exact-runtime reset, offline command integration, and terminal/JSON injection hardening. In Phase 8, Codex verified installed MCP structured-output behavior, implemented lazy read-only stdio tools, added nonreflective malformed-call handling, exercised the committed CLI through an SDK stdio client, and ran an offline real-model MCP fixture path. The owner supplied and approved the product positioning, phase boundaries, architecture, ranking and safety policies, evidence rules, model lifecycle, and implementation contract.

This section records only completed work. The final acceleration narrative, demo claims, contribution summary, and `/feedback` Session ID remain pending until most core functionality is built. The Session ID will be obtained by the user running `/feedback` in the primary implementation thread; no value is invented here.

## License

CodeScope is distributed under the repository's [`LICENSE`](LICENSE). Third-party dependency licenses must be reviewed and documented before submission.
