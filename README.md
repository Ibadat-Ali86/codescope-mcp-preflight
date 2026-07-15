# CodeScope

CodeScope is a local-first MCP preflight system for developer tools. Its intended workflow helps GPT-5.6 and Codex inspect an existing Python repository before generating code, so they can make evidence-backed **REUSE**, **EXTEND**, or **CREATE** decisions and reduce duplicate logic.

## Current implementation status

OpenAI Build Week Phase 3 is complete. The repository currently provides:

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
- focused unit and path-security tests, including malformed-source recovery coverage.

The functional indexing and MCP preflight workflow are not implemented yet. Parsing accepts
already-read bytes, and chunking accepts already-decoded source plus parser-produced symbols. These
phases do not scan or read repository files, load a model, generate embeddings, persist an index,
search code, expose MCP tools, or delete runtime data.

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

The default configuration is [`codescope.toml`](codescope.toml). Configuration paths are resolved relative to that file. Its indexing root must already exist; its storage directory may be absent until a later runtime phase.

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

Parser fixtures under `tests/fixtures/sample_python/` cover representative Python syntax, and the
chunker tests use a deterministic offset-aware fake tokenizer without network access. No indexed
sample repository or judge-ready sample data exists yet. A safe, documented sample path will be
added before submission and will not require judges to inspect unrelated host files.

## Current limitations

- Python repositories only; supported source extensions are `.py` and `.pyi`.
- No embedding generation, Chroma persistence, repository indexing, or search.
- No MCP tools or MCP server workflow are operational yet.
- Phase 3 does not load the Sentence Transformers model or tokenizer. Phase 4 must connect the
  chunker seam to one locally managed production tokenizer without duplicating model lifecycle.
- No dashboard, remote hosting, authentication, deployment, or file watching.
- Path validation reduces traversal and symlink risk, but filesystem state can change after validation; future read and deletion operations must validate immediately before use.
- No benchmark or performance claim has been established.

## Built During OpenAI Build Week

The repository distinguishes pre-existing planning from Build Week implementation through dated
Git history and [`BUILD_WEEK_CHANGELOG.md`](BUILD_WEEK_CHANGELOG.md). Work completed through Phase 3
comprises the package foundation, validated configuration, public models, domain exceptions,
Python language validation, path-security guards, Tree-sitter Python symbol extraction,
model-budgeted symbol-aware chunking, deterministic hashes and IDs, oversized-source splitting,
module fallback, and focused tests. Later MVP functionality remains unimplemented and must not be
inferred from planning documents.

## How Codex and GPT-5.6 Were Used

Codex with GPT-5.6 was used in the primary implementation thread to inspect the Build Master and
repository constraints, consult version-matched Tree-sitter and Hugging Face tokenizer
documentation, implement the Phase 1 foundation, Phase 2 parser, and Phase 3 chunker/tests, run
validation, and review the working-tree security diffs. The owner supplied and approved the product
positioning, phase boundaries, architecture, security policies, evidence rules, tokenizer boundary,
and implementation contract.

This section records only completed work. The final acceleration narrative, demo claims, contribution summary, and `/feedback` Session ID remain pending until most core functionality is built. The Session ID will be obtained by the user running `/feedback` in the primary implementation thread; no value is invented here.

## License

CodeScope is distributed under the repository's [`LICENSE`](LICENSE). Third-party dependency licenses must be reviewed and documented before submission.
