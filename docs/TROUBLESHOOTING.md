# CodeScope Troubleshooting

## `INDEX_NOT_FOUND`

No complete usable index exists, or status validation rejected stale/partial state. Prepare the
model if necessary, then run:

```bash
uv run codescope index /path/to/repository
uv run codescope status
```

A missing index is not evidence for CREATE. Do not hand-edit Chroma or metadata files.

## Model cache unavailable or offline model failure

Normal indexing and every query are cache-only. Set the external cache consistently:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

If the model was never prepared, explicitly authorize one indexing preparation run with
`--allow-model-download`, then reset its temporary index. Review the model source/license first.
Never put the model cache inside the repository. Search, status, MCP, demo, and benchmark do not
provide an automatic-download fallback.

## `INVALID_CONFIG`

Review `codescope.toml` syntax, required sections, positive numeric limits, overlap smaller than
chunk size, default search limit no larger than maximum, existing directory root, and safe runtime
path. Paths are relative to the TOML file. Config files, ancestors, roots, and existing runtime
directories must obey the documented link policy. Error messages intentionally do not echo a
private path or TOML content.

## `INVALID_LANGUAGE`

The MVP accepts Python only. Language spelling is normalized for `python`; extensions must be
exactly lowercase `.py` or `.pyi`. JavaScript, TypeScript, notebooks, wildcards, and uppercase
extensions are unsupported.

## Corrupt or inconsistent runtime

Status/query failures can indicate malformed metadata, missing collection state, count mismatch,
or a configuration fingerprint mismatch. Use the validated command:

```bash
uv run codescope reset --yes
uv run codescope index /path/to/repository
```

Do not use a recursive shell deletion example and do not point reset at an arbitrary directory.
Reset removes only the exact configured runtime.

## MCP server is not listed by Codex

1. Review `.codex/config.toml.example` or `examples/codex_mcp_config.toml`.
2. Merge only the `mcp_servers.codescope` table into a trusted Codex configuration.
3. Launch Codex from the repository root expected by the example.
4. Run `codex mcp list`, then inspect `/mcp`.

The active project configuration is not modified automatically.

## MCP startup timeout

Run `uv run codescope version` and `uv run codescope serve --help` first. Confirm Python 3.12, the
locked environment, and a valid `codescope.toml`. Server construction is lazy; a missing index
should not block initialization. Increase a client startup timeout only after confirming the local
command and working directory are correct. Do not enable model download for MCP startup.

## Stdout protocol concerns

While serving, stdout is exclusively MCP JSON-RPC. Application logs and safe diagnostics use
stderr. Do not add prints, progress bars, shell wrappers, or startup banners around `codescope
serve`. Validate with the MCP integration/security tests if a client reports malformed frames.

## Reset confirmation or failure

Without `--yes`, declining confirmation makes no change and returns nonzero. With `--yes`, reset
still validates the repository and exact configured runtime. A missing runtime returns an
actionable error. Path, link, mismatch, and revalidation failures deliberately delete nothing.

## Linux, macOS, and Windows paths

Public paths always use project-relative POSIX `/` separators, including on Windows. Configuration
and internal filesystem operations use `pathlib.Path`. Drive-letter, UNC, backslash, absolute, and
traversal public paths are rejected. Symlink and junction creation/permissions differ by platform;
the security suite skips only the affected junction test when the OS reports that it is genuinely
unavailable. The complete Build Week validation was observed on Linux; do not infer broader tested
support.

## Real-model tests are skipped

This is expected in ordinary tests. To run the established offline matrix:

```bash
export CODESCOPE_RUN_REAL_MODEL=1
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
uv run pytest tests/integration tests/e2e -q
```

The full clean-candidate test uses the separate `CODESCOPE_RUN_CLEAN_SETUP=1` opt-in. Do not reuse
one flag to silently enable the other workflow.

## Benchmark or clean verification fails

- Verify the external prepared model cache without printing its path.
- Check `uv lock --check`, `git status --short`, and available disk space.
- Remove or review unexpected untracked files; the candidate verifier fails closed on anything
  outside its exact Phase 10 allowlist.
- The verifier uses a fresh clone-local `.venv` and uv's external package cache. It does not reuse
  the source `.venv` or user configuration.
- Timeouts terminate the command/process group where supported and remove the temporary clone.
- Do not solve a timeout by removing bounds or passing inherited secrets/proxy credentials into
  child processes.
