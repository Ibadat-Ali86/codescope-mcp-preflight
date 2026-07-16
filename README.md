# CodeScope

CodeScope is a local-first MCP preflight system for developer tools. Its intended workflow helps GPT-5.6 and Codex inspect an existing Python repository before generating code, so they can make evidence-backed **REUSE**, **EXTEND**, or **CREATE** decisions and reduce duplicate logic.

## Current implementation status

OpenAI Build Week Phase 6 is complete in the working tree and awaiting owner review. The repository currently provides:

- a Python 3.12 package with `version`, `index`, and `status` acceptance commands;
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

CodeScope can now build, validate, and query a local index for a Python repository through its typed Python engine API. It does not yet provide MCP tools, the complete Phase 7 CLI, or the final duplication-prevention demonstration.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A platform supported by the locked Python dependencies

Phases 1 through 6 have been validated in the current Linux development environment. Broader supported-platform claims and clean-clone verification are deferred until the functional MVP exists.

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
```

The observed Phase 5 fixture result is 4 accepted files, 11 symbols, and 16 chunks. The Phase 6 offline integration builds that fixture, finds `validate_email` for an email-validation search, returns `validators.py` lines 6–9 for exact symbol lookup, exercises similar-code search, and validates persisted status through a new engine instance. This remains a development acceptance path rather than the final judge workflow: CLI search, MCP configuration, clean-clone model preparation, and the duplication-prevention demonstration remain pending.

## Testing

Run the current checks with:

```bash
uv run pytest tests/unit -q
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
- No MCP tools, CLI search command, complete Phase 7 CLI, or agent preflight skill.
- The real model must be prepared explicitly before cache-only use; no model assets are stored in this repository.
- Rebuild promotion is rollback-capable across tested failures, but portable filesystem operations cannot eliminate validation-to-use races or guarantee recovery from every simultaneous filesystem failure.
- No dashboard, remote hosting, authentication, deployment, file watching, benchmark, or performance claim.

## Built During OpenAI Build Week

The repository distinguishes pre-existing planning from Build Week implementation through dated Git history and [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Work completed through Phase 6 comprises the package foundation, validated configuration and path security, Tree-sitter Python extraction, model-aware chunking, local embeddings, persistent Chroma, atomic metadata, deterministic secure discovery, bounded reads and batching, failure-safe full rebuilds, status verification, basic index/status CLI acceptance, read-only semantic and symbol querying, similar-code evidence, and focused regression/security tests. Later CLI, MCP, demonstration, and submission functionality remains unimplemented and must not be inferred from planning documents.

## How Codex and GPT-5.6 Were Used

Codex with GPT-5.6 was used in the primary implementation thread to inspect the Build Master and repository constraints; consult version-matched Tree-sitter, Hugging Face, Chroma, pathlib, and pathspec documentation; implement Phases 1–6; run deterministic, real-model, rollback, security, and CLI validation; and review each working-tree security diff. In Phase 5, Codex traced scanner and promotion boundaries, reproduced and corrected a bounded-directory materialization defect, and finalized the security ledger. In Phase 6, Codex implemented dependency-injected read-only query orchestration, deterministic semantic and symbol ranking, typed failure conversion, offline persisted-query integration, and a complete diff-focused security review. The owner supplied and approved the product positioning, phase boundaries, architecture, ranking and safety policies, evidence rules, model lifecycle, and implementation contract.

This section records only completed work. The final acceleration narrative, demo claims, contribution summary, and `/feedback` Session ID remain pending until most core functionality is built. The Session ID will be obtained by the user running `/feedback` in the primary implementation thread; no value is invented here.

## License

CodeScope is distributed under the repository's [`LICENSE`](LICENSE). Third-party dependency licenses must be reviewed and documented before submission.
