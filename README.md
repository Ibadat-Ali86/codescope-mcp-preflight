# CodeScope

CodeScope is a local-first MCP preflight system for developer tools. Its intended workflow helps GPT-5.6 and Codex inspect an existing Python repository before generating code, so they can make evidence-backed **REUSE**, **EXTEND**, or **CREATE** decisions and reduce duplicate logic.

## Current implementation status

OpenAI Build Week Phase 4 is complete and owner-reviewed. The repository currently provides:

- a Python 3.12 package and version command;
- immutable, validated TOML configuration;
- immutable public data models and stable domain error codes;
- Python-only language and extension validation;
- centralized repository-file and future reset-target path guards;
- Tree-sitter Python symbol extraction for module functions, async functions, classes, and
  direct methods;
- model-budgeted, symbol-aware source chunking with nonduplicative class/method ownership;
- deterministic source metadata, SHA-256 content hashes, and stable chunk IDs;
- oversized-symbol and module-fallback splitting through a dependency-injected tokenizer seam;
- lazy local Sentence Transformers embeddings with cache-only normal operation;
- one model-managed fast tokenizer for exact wordpiece counts and original-character offsets;
- finite two-dimensional `float32` vector validation with configurable batching and normalization;
- telemetry-disabled persistent local Chroma storage with explicit cosine configuration;
- source-only chunk documents, scalar project-relative metadata, and embedding-free query results;
- atomic `symbols.json` and `index_meta.json` persistence restricted to fixed metadata names;
- focused unit and path-security tests, including malformed-source recovery coverage.

The complete indexing and MCP preflight workflow is not implemented yet. Parsing accepts
already-read bytes, chunking accepts already-decoded source plus parser-produced symbols, and the
Phase 4 embedder/storage components have no repository scanner or query orchestrator. CodeScope
does not yet index a repository end to end, search code, expose MCP tools, or delete runtime
directories.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A platform supported by the locked Python dependencies

Phases 1 and 2 have been validated in the current Linux development environment. Broader supported-platform claims and clean-clone verification are deferred until the functional MVP exists.

## Setup

Clone the repository, then install the locked development environment:

```bash
uv sync
```

The default configuration is [`codescope.toml`](codescope.toml). Configuration paths are resolved
relative to that file. Its indexing root must already exist; its storage directory is created only
when the storage component is explicitly initialized.

The first preparation of the default embedding model requires explicit network permission and a
local cache outside the repository. Normal embedding and tokenizer construction is cache-only and
fails safely when the model is unavailable locally.

## Current operation

The only functional CLI behavior implemented so far is package version reporting:

```bash
uv run codescope version
```

This is not yet the final judge testing path. Installation, indexing, MCP configuration, sample-data, and end-to-end judge instructions will be added only after those workflows are implemented and verified.

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

Parser fixtures under `tests/fixtures/sample_python/` cover representative Python syntax. Unit
tests use deterministic injected model and tokenizer doubles without network access, while one
explicit integration test exercises the real cached default model. No indexed sample repository or
judge-ready sample data exists yet. A safe, documented sample path will be added before submission
and will not require judges to inspect unrelated host files.

## Current limitations

- Python repositories only; supported source extensions are `.py` and `.pyi`.
- No complete repository indexing or semantic search orchestration.
- No MCP tools or MCP server workflow are operational yet.
- The real model must be prepared explicitly before cache-only use; no model assets are stored in
  this repository.
- Persistent storage is a lower-level Phase 4 component, not yet a healthy-index lifecycle or
  public CLI workflow.
- No dashboard, remote hosting, authentication, deployment, or file watching.
- Path validation reduces traversal and symlink risk, but filesystem state can change after validation; future read and deletion operations must validate immediately before use.
- No benchmark or performance claim has been established.

## Built During OpenAI Build Week

The repository distinguishes pre-existing planning from Build Week implementation through dated
Git history and [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Work completed through Phase 4
comprises the package foundation, validated configuration, public models, domain exceptions,
Python language validation, path-security guards, Tree-sitter Python symbol extraction,
model-budgeted symbol-aware chunking, deterministic hashes and IDs, oversized-source splitting,
module fallback, lazy local embeddings, managed tokenizer accounting, persistent local Chroma,
atomic metadata persistence, and focused tests. Later MVP functionality remains unimplemented and
must not be inferred from planning documents.

## How Codex and GPT-5.6 Were Used

Codex with GPT-5.6 was used in the primary implementation thread to inspect the Build Master and
repository constraints, consult version-matched Tree-sitter and Hugging Face tokenizer
documentation, implement the Phase 1 foundation, Phase 2 parser, Phase 3 chunker, and Phase 4
embedding/storage foundation, run local and real-model validation, and review working-tree security
diffs. The owner supplied and approved the product positioning, phase boundaries, architecture,
security policies, evidence rules, tokenizer/model lifecycle, and implementation contract.

This section records only completed work. The final acceleration narrative, demo claims, contribution summary, and `/feedback` Session ID remain pending until most core functionality is built. The Session ID will be obtained by the user running `/feedback` in the primary implementation thread; no value is invented here.

## License

CodeScope is distributed under the repository's [`LICENSE`](LICENSE). Third-party dependency licenses must be reviewed and documented before submission.
