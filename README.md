# CodeScope

CodeScope is a local-first MCP preflight system for developer tools. Its intended workflow helps GPT-5.6 and Codex inspect an existing Python repository before generating code, so they can make evidence-backed **REUSE**, **EXTEND**, or **CREATE** decisions and reduce duplicate logic.

## Current implementation status

OpenAI Build Week Phase 9 is complete at commit `2c358ac`. Phase 10 release hardening is complete
and owner-approved. The repository currently provides:

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
- verified Codex MCP configuration examples under `.codex/config.toml.example` and `examples/codex_mcp_config.toml`;
- a repository-scoped `$codescope-preflight` skill that inventories first, gathers semantic,
  exact-symbol, and similar-code evidence, and reports REUSE, EXTEND, or CREATE before editing;
- a fixed cache-only duplication-prevention demo that uses the real stdio MCP server, verifies the
  canonical fixture and before/after source hashes, and leaves its isolated runtime temporary.
- a bounded offline fixture benchmark with direct query, MCP, and demo timing;
- a clean-candidate verifier that applies the working-tree patch to a real no-local clone, creates
  a fresh locked environment, runs the CLI/MCP/demo judge path, proves source immutability, and
  removes temporary state;
- release security, setup, architecture, API, benchmark, coverage, and troubleshooting evidence;
- verified sdist/wheel license metadata, artifact contents, and fresh-wheel installation.

CodeScope can build, validate, query, and reset a local index for a Python repository through its
CLI, typed Python engine API, four-tool local MCP interface, and agent preflight workflow. Phase 11
submission packaging, video production, final `/feedback` capture, and Devpost work are not part of
the current implementation.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A platform supported by the locked Python dependencies

Phases 1 through 10 have been validated in the current Linux development environment. Public paths
and path guards have cross-platform tests, but broader macOS/Windows execution claims remain
unverified.

## Setup

Clone the repository, then install the locked development environment:

```bash
uv sync --locked
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
uv run python scripts/demo.py
uv run python scripts/demo.py --json
```

The isolated offline demonstration indexed 4 files into 11 symbols and 16 chunks. Inventory,
semantic, exact-symbol, and similar-code calls converged on `validate_email` at `validators.py`
lines 6–9, the report recommended REUSE, exact source hashes remained unchanged, and no
`is_valid_email` duplicate was created. The model still requires one explicit external-cache
preparation step.

For the verified clean-candidate path and its prerequisites, see
[`docs/SETUP.md`](docs/SETUP.md). The final July 18 Linux run reached the fixed demo in 45.937
seconds after setup timing began and completed in 47.731 seconds total, excluding model download. This is
an environment-specific observation, not a universal guarantee.

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
uv run pytest tests/e2e -q
uv run pytest tests/release -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/codescope
uv run mypy scripts/demo.py scripts/benchmark.py scripts/verify_clean_setup.py
uv run codescope version
```

Phase-specific commands and observed results are recorded in
[`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Hackathon submission requirements are
tracked in [`docs/HACKATHON_COMPLIANCE.md`](docs/HACKATHON_COMPLIANCE.md).

## Technical documentation

- [Setup and judge path](docs/SETUP.md)
- [Architecture and trust boundaries](docs/ARCHITECTURE.md)
- [CLI and MCP API](docs/API.md)
- [Security model and dependency/license inventory](docs/SECURITY.md)
- [Fixture benchmark methodology and measured values](docs/BENCHMARKS.md)
- [Coverage methodology and per-module evidence](docs/COVERAGE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Codex handoff](docs/CODEX_HANDOFF.md)
- [Duplication-prevention demo runbook](docs/DEMO_SCRIPT.md)

## Sample data

The license-safe fixtures under `tests/fixtures/sample_python/` cover representative Python syntax
and serve as the deterministic indexing, query, benchmark, and clean-setup sample.
`tests/fixtures/duplication_demo/task.json` defines the fixed email-validator task. Unit tests use
injected model/tokenizer/storage seams without network access; explicit integration, e2e,
benchmark, and clean-candidate checks exercise the already cached default model offline through the
real stdio server.

## Current limitations

- Python repositories only; supported source extensions are `.py` and `.pyi`.
- Only the repository-root `.gitignore` is interpreted; nested `.gitignore` semantics are deferred.
- No symbol or similar-code CLI subcommands; those evidence paths are available through MCP and the
  preflight skill.
- The real model must be prepared explicitly before cache-only use; no model assets are stored in this repository.
- Repository setup uses `uv sync --locked` for exact locked dependency reproduction. A standalone
  wheel install resolves the package's compatible dependency ranges and is not an exact substitute
  for the repository lockfile.
- The demonstration fixture is intentionally small, and a REUSE, EXTEND, or CREATE recommendation
  still requires agent judgment; similarity does not prove semantic equivalence.
- Rebuild promotion is rollback-capable across tested failures, but portable filesystem operations cannot eliminate validation-to-use races or guarantee recovery from every simultaneous filesystem failure.
- The benchmark uses an intentionally small fixture. Its numbers are environment-specific and do
  not establish large-repository performance or semantic quality.
- No dashboard, remote hosting, authentication, deployment, file watching, or incremental update.
- Broader Windows and macOS execution, automated CI, and final submission work remain pending.

## Built During OpenAI Build Week

The repository distinguishes pre-existing planning from Build Week implementation through dated Git
history and [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Work completed through Phase 10
comprises the package foundation, validated configuration/path security, Python parsing and
model-budgeted chunking, local embeddings and Chroma, secure failure-safe indexing, read-only query
and MCP surfaces, the CLI, preflight skill, fixed duplication demo, complete release-security
documentation, measured fixture benchmark, meaningful coverage evidence, real candidate-clone
verification, and package build/install auditing. Phase 11 submission work must not be inferred
from planning documents.

## How Codex and GPT-5.6 Were Used

Codex with GPT-5.6 was used in the primary implementation thread to inspect the Build Master and
repository constraints; consult version-matched Tree-sitter, Hugging Face, Chroma, pathlib,
pathspec, Typer, Rich, pytest, uv build, MCP SDK, and official Codex documentation; implement Phases
1–10; run deterministic, real-model, rollback, protocol, security, CLI, e2e, benchmark,
clean-candidate, coverage, and package validation; and review each working-tree security diff. In
Phase 10, Codex reproduced and corrected combined-suite test collection and package-license
metadata blockers, then implemented bounded release tooling and factual technical evidence. The
owner supplied and approved the product positioning, phase boundaries, architecture, ranking and
safety policies, evidence rules, model lifecycle, and implementation contract.

This section records only completed work. The final acceleration narrative, demo claims, contribution summary, and `/feedback` Session ID remain pending until most core functionality is built. The Session ID will be obtained by the user running `/feedback` in the primary implementation thread; no value is invented here.

## License

CodeScope is distributed under the repository's unchanged MIT [`LICENSE`](LICENSE). The wheel and
sdist include that license through PEP 639 metadata. Direct and notable transitive dependency/model
license evidence is recorded factually in [`docs/SECURITY.md`](docs/SECURITY.md); it is not legal
advice.
