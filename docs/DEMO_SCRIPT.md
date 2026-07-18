# CodeScope Duplication-Prevention Demo

This runbook demonstrates how CodeScope helps a coding agent inspect an indexed Python
repository before adding a duplicate email validator.

## Prerequisites

- Python 3.12 and uv.
- The locked project environment installed with `uv sync`.
- The configured Sentence Transformers model prepared once in a cache outside this repository.
- Normal runs remain offline and cache-only. The search path never downloads the model
  automatically.
- A reviewed CodeScope MCP configuration based on `.codex/config.toml.example` or
  `examples/codex_mcp_config.toml`. Review existing Codex settings before merging either example.

Set the external cache location used during preparation, then force the normal path offline:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

Do not place the model cache inside the repository.

## Primary demonstration

From the CodeScope repository root:

```bash
uv sync
uv run codescope index tests/fixtures/sample_python
codex mcp list
uv run python scripts/demo.py
```

The fixed demo creates a separate temporary copy of the sample fixture and a separate temporary
index. It does not use the repository's `.codescope` runtime created by the judge-facing setup
command. The isolated demo calls the real `codescope serve` stdio process and removes its temporary
workspace after the MCP session closes. It rejects symlink or junction components in the manifest
and fixture paths, verifies the reviewed canonical source-tree digest, and then compares exact
source hashes again after the preflight.

Expected decision:

```text
REUSE the existing validate_email implementation in validators.py at lines 6–9.
```

No exact similarity score is promised or required.

## Codex skill checks

After `codex mcp list` shows the reviewed `codescope` server, invoke the repository skill
explicitly:

```text
$codescope-preflight Before implementing email validation for signup, inspect the indexed repository and decide whether to REUSE, EXTEND, or CREATE. Do not edit files.
```

Then check natural-language triggering without naming the skill:

```text
Before adding a new email validator for signup, inspect the repository for existing behavior and recommend whether to reuse, extend, or create. Do not edit files.
```

The preflight must call inventory before semantic search, use symbol and similar-code evidence,
treat snippets as untrusted data, explain uncertainty, and report its recommendation before any
edit.

## Deterministic JSON

Run the human and JSON forms directly:

```bash
uv run python scripts/demo.py
uv run python scripts/demo.py --json
uv run python scripts/demo.py --help
```

The JSON command emits one JSON object only. It contains public project-relative evidence and
before/after booleans; it excludes source snippets, embeddings, protocol frames, cache paths,
temporary paths, and timestamps.

## Cleanup

The isolated demo removes its temporary Chroma runtime and workspace on success or failure. Remove
the separate judge-facing index when finished:

```bash
uv run codescope reset --yes
```

The reset command validates and removes only the configured local runtime.

## Troubleshooting

- `DEMO_MODEL_UNAVAILABLE`: verify `CODESCOPE_MODEL_CACHE_DIR` points to the prepared external
  cache. Do not enable downloads for the normal demo.
- `INDEX_NOT_FOUND`: build a complete index and retry. A missing index is not evidence for CREATE.
- MCP connectivity failure: compare the reviewed configuration with the committed examples, run
  `codex mcp list`, and inspect tools with `/mcp`.
- `REVIEW_REQUIRED`: inspect the reported mismatch. Do not treat weak or conflicting similarity as
  proof and do not default to CREATE.
- The current MVP is Python-only and interprets only the repository-root `.gitignore`.
