# CodeScope Codex Handoff

## Project goal

CodeScope is a local-first MCP preflight system for Python repositories. It helps Codex inspect
existing implementation evidence before generating code and supports a reasoned REUSE, EXTEND, or
CREATE decision without executing indexed source.

## Current working state

- Branch: `main`.
- Phase 10 commit and Phase 11 starting SHA:
  `39f85be6f5e876a82d52f487505952b0a9f4ff3b`.
- Current phase: Phase 11 — final submission packaging, release, and Devpost verification.
- Status: the staged Phase 11 candidate passed the real clean-candidate verifier and remains
  uncommitted; final owner review and all external-write gates remain open. The supplied public
  routing-ownership recording is 5:47 and is not an eligible final video; its fixture is not in
  this repository.
- Version: `0.1.0`.
- The Phase 10 boundary is the commit containing this handoff update. No Phase 10 release tag was
  created.

## Completed phases

| Phase | Outcome | Commit boundary |
|---|---|---|
| 0 | Python 3.12 uv package foundation | `6b32222` baseline |
| 1 | Immutable config/models/errors and path security | `1459a27` |
| 2 | Tree-sitter Python symbol extraction | `c16e5b9` |
| 3 | Symbol-aware model-budgeted chunking | `3dc46f2` |
| 4 | Local embeddings and persistent Chroma storage | `42c607c` |
| 5 | Secure scanner and failure-safe indexing | `9865e0c` |
| 6 | Read-only semantic/symbol/similar query engine | `f68f1e9` |
| 7 | Six-command CLI and validated reset | `a874df8` plus `c107abc` correction |
| 8 | Four-tool local stdio MCP server | `5afc064` plus `cd6f062` evidence closure |
| 9 | Repository preflight skill and fixed duplication demo | `2c358ac` |
| 10 | Release security/docs, benchmark, coverage, clean clone, package audit | `39f85be` |
| 11 | Final submission assets, owner-reviewed narrative, release, video, and Devpost | In progress; uncommitted |

Detailed implementation and observed results are in `BUILD_WEEK_CHANGELOG.md` and
`docs/.CHAT_MEMORY.md`.

## Architecture decisions

- Python 3.12 only; `.py` and `.pyi` only.
- Stable MCP v1 dependency constrained to `mcp[cli]>=1.27,<2`.
- Frozen Pydantic public/config models and stable machine-readable domain errors.
- Resolved-path containment, centralized path guards, and exact runtime reset validation.
- Root `.gitignore` plus mandatory exclusions that cannot be negated.
- Parser is filesystem-free; chunker receives decoded source and exact tokenizer accounting.
- Stored chunk text is exact source; embedding metadata is transient.
- Model lifecycle is lazy, process-reused, external-cache, and cache-only by default.
- Chroma is local and telemetry-disabled; metadata JSON is fixed-name, bounded, and atomic.
- Rebuilds use verified sibling state and rollback-capable promotion.
- Query status is authoritative and revalidated; symbol/status paths avoid model load.
- MCP exposes exactly four read-only tools and reserves stdout for protocol traffic.
- Similarity is evidence, never proof; the agent owns the final decision.
- Phase 10 release tools use bounded input/output/time, isolated temporary state, minimized child
  environments, and source-free/path-free reports.

See `docs/ARCHITECTURE.md`, `docs/API.md`, and `docs/SECURITY.md`.

## Main commands

### Install and prepare

```bash
uv sync --locked
uv run codescope version
uv run codescope --help
```

Model preparation requires one explicit owner-authorized `codescope index ...
--allow-model-download` run with `CODESCOPE_MODEL_CACHE_DIR` outside the repository. Normal use is
offline/cache-only.

### Operate

```bash
uv run codescope index tests/fixtures/sample_python
uv run codescope status
uv run codescope search "email validation" --json
uv run codescope serve
uv run python scripts/demo.py --json
uv run codescope reset --yes
```

### Release evidence

```bash
uv run python scripts/benchmark.py --json
CODESCOPE_RUN_CLEAN_SETUP=1 uv run python scripts/verify_clean_setup.py --json
uv build
```

The benchmark and clean verifier also require the external prepared model-cache variable and
offline flags described in `docs/SETUP.md`.

### Exact tests and quality gates

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
uv lock --check
git diff --check
```

Explicit offline real-model validation:

```bash
CODESCOPE_RUN_REAL_MODEL=1 \
CODESCOPE_MODEL_CACHE_DIR="<prepared-external-cache>" \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
uv run pytest tests/integration tests/e2e -q
```

Full production coverage:

```bash
uv run pytest tests/unit tests/integration tests/security tests/e2e tests/release \
  --cov=codescope --cov-report=term-missing
```

## Required environment variables

- `CODESCOPE_MODEL_CACHE_DIR`: prepared cache outside the repository for real model use.
- `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`: required for explicit offline evidence.
- `CODESCOPE_RUN_REAL_MODEL=1`: opts into cached real-model integration/e2e tests.
- `CODESCOPE_RUN_CLEAN_SETUP=1`: separately opts into the real candidate-clone verifier/test.
- `CODESCOPE_ALLOW_MODEL_DOWNLOAD=1`: used only by the explicit model smoke test when the owner has
  authorized initial preparation; never normal query/demo/benchmark operation.

Do not record cache paths or secret environment values in repository evidence.

## Known limitations

- Only Python and root-level `.gitignore` semantics are supported.
- Model assets are not bundled; one explicit external-cache preparation is required.
- Fixture benchmark and clean-setup timing are environment-specific and intentionally small-scale.
- Similarity does not prove behavior or equivalence.
- Portable same-user filesystem validation-to-use races remain documented residual risk.
- The Linux Build Week environment is fully observed; broad Windows/macOS operation is not.
- No CI was added in Phase 10 because the real model/clean path needs an external prepared cache;
  ordinary CI remains a Phase 11 owner decision.
- Repository installation uses `uv sync --locked` for exact locked dependency reproduction. A
  standalone wheel install resolves compatible declared ranges and is not lockfile-exact.
- No dashboard, remote service, authentication, deployment, file watcher, or incremental index.
- Devpost entry, public video/audio, `/feedback` Session ID, release tag, and final submission
  packaging remain incomplete.

## Current Phase 11 task

Complete the owner-reviewed submission narrative, final candidate validation, public release,
sub-three-minute YouTube demo with required audio, `/feedback` Session ID capture from the primary
implementation thread, and live Devpost submission verification. Do not change product behavior
unless a reproduced release blocker receives separate owner approval. Creating or updating a
Devpost project, committing, tagging, publishing a release, uploading media, and submitting are
separate owner-gated external writes.

## Final completion criteria

- Phase 10 is owner-reviewed, committed, and synchronized without rewriting published history.
- Phase 11 evidence is factual, English, judge-accessible, and matches current code.
- Public repository or correctly shared private repository and MIT license are verified.
- Installation, supported platforms, sample data, and direct judge path are explicit.
- Video is public, under three minutes, and audibly explains CodeScope plus Codex/GPT-5.6 use.
- `/feedback` Session ID is captured by the user; no value is invented.
- Clean-clone, package, coverage, security, full tests, and artifact/privacy gates pass.
- No critical/high validated security finding remains, no secret/private artifact is committed, and
  the final Devpost entry is submitted rather than left as a draft.
