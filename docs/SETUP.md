# CodeScope Setup and Judge Path

## Prerequisites

- Python 3.12 (the project requires `>=3.12,<3.13`).
- [uv](https://docs.astral.sh/uv/) for locked environments and builds.
- Git for the clean-candidate verifier.
- A platform supported by the locked dependencies. Linux is the fully observed Build Week
  environment; broader platform testing is limited.

From a clone, create the locked project environment:

```bash
uv sync --locked
uv run codescope version
uv run codescope --help
```

Package installation, model preparation, index creation, and MCP startup are distinct steps. A
successful package install does not prepare the model or create an index.

## Model preparation

The default model is `sentence-transformers/all-MiniLM-L6-v2`. Keep its cache outside the
repository. The first acquisition is a supply-chain/network operation and requires explicit owner
permission:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
uv run codescope index tests/fixtures/sample_python --allow-model-download
uv run codescope reset --yes
```

After preparation, force cache-only operation:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

Normal indexing, querying, MCP, benchmark, demo, and clean verification do not authorize model
downloads. A cache miss fails with an actionable error. Do not place a cache or model file under
the repository.

## Repository configuration

`codescope.toml` is loaded from the invocation directory by the CLI/server. Relative
`index.root` and `storage.path` values resolve relative to that file. The default root is `.`, the
runtime is `.codescope`, and only `.py`/`.pyi` are supported.

Review the root, mandatory exclusions, file/chunk limits, model, and runtime before indexing.
Configuration roots must already exist. CodeScope creates only the validated runtime during a
rebuild.

## Fast verified operation path

With the model prepared externally and offline flags set:

```bash
uv sync --locked
uv run codescope index tests/fixtures/sample_python
uv run codescope status
uv run codescope search "email validation"
uv run codescope search "email validation" --json
uv run python scripts/demo.py
uv run codescope reset --yes
```

The committed fixture contains four Python files, 11 symbols, and 16 production-tokenizer chunks
in the observed default-model run. The fixed demo should recommend REUSE for `validate_email` at
`validators.py:6-9`, report unchanged source, and report that the duplicate was avoided.

## Local MCP configuration

Copy and review the `mcp_servers.codescope` table from `.codex/config.toml.example` or
`examples/codex_mcp_config.toml` into a trusted Codex configuration. The examples launch:

```bash
uv run codescope serve
```

Then:

```bash
codex mcp list
```

Within Codex, inspect `/mcp` and confirm exactly `search_code`, `find_symbol`, `find_similar`, and
`list_indexed_files`. The server uses local stdio and protocol-only stdout. Build a valid index
before semantic calls.

## Agent preflight skill

The repository skill is `.agents/skills/codescope-preflight/SKILL.md`. Invoke it explicitly:

```text
$codescope-preflight Before adding email validation, inspect the repository and recommend REUSE, EXTEND, or CREATE. Do not edit files.
```

The skill must inventory first, use behavioral and similar-code search, use symbol lookup when a
likely name exists, compare ownership/differences, and report one decision before editing. A
missing index or model is a blocker, not evidence for CREATE.

## Fixed demo

```bash
uv run python scripts/demo.py
uv run python scripts/demo.py --json
```

The demo creates its own temporary repository and runtime, calls the real stdio server, validates
the reviewed fixture trust anchor, and removes temporary state. See `docs/DEMO_SCRIPT.md` and
`docs/DEMO_EVIDENCE.md`.

## Benchmark

```bash
uv run python scripts/benchmark.py --help
uv run python scripts/benchmark.py
uv run python scripts/benchmark.py --json
```

This is a small-fixture benchmark, not a production-scale claim. It requires the external prepared
model cache and forces cache-only use. See `docs/BENCHMARKS.md`.

## Clean candidate verification

The verifier operates on the current candidate working tree without committing it. It creates a
real no-local clone of `main` `HEAD`, applies the tracked diff, copies only the authorized Phase 10
untracked files, creates a fresh clone-local `.venv`, and removes the clone afterward.

```bash
export CODESCOPE_RUN_CLEAN_SETUP=1
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
uv run python scripts/verify_clean_setup.py --json
```

The verifier uses uv's validated external package cache but does not reuse the source repository's
virtual environment. It uses a temporary home and no private user configuration, passes only a
minimal environment, and keeps the model offline. The final measured July 18 Linux run reached the
fixed demo in 45.937 seconds and completed cleanup in 47.731 seconds; this is environment-specific
and not a guarantee.

## Cleanup

Use the validated application command:

```bash
uv run codescope reset --yes
```

Do not replace it with recursive shell deletion. The benchmark, demo, and clean verifier remove
their own temporary workspaces. Model and uv caches remain external reusable prerequisites and are
not application runtime.

## Package installation

Phase 10 verifies the built wheel in a fresh temporary virtual environment. For a local wheel:

```bash
uv build
uv venv /path/to/fresh-environment --python 3.12
uv pip install --python /path/to/fresh-environment/bin/python dist/codescope-0.1.0-py3-none-any.whl
```

This installs the CLI and dependencies only. It does not download the embedding model, create
`.codescope`, configure MCP, or index a repository. A standalone wheel resolves compatible declared
dependency ranges; use the repository's `uv sync --locked` path when exact lockfile reproduction is
required. Phase 10 does not publish the package.
