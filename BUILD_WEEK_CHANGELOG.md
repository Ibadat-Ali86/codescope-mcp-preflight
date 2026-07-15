# CodeScope Build Week Changelog

This document records implementation completed during OpenAI Build Week 2026.

## Pre-existing work

Before implementation began, the project contained planning and technical specification documents.

## Build Week implementation

### Phase 0 — Repository foundation

- Initialized the Git repository.
- Configured Python 3.12 with uv.
- Created an isolated project environment.
- Installed and locked runtime and development dependencies.
- Created the initial package and CLI entry point.
- Added project quality configuration.
- Added the initial repository structure.

### Phase 1 — Configuration, models, and path security

Work performed on July 15, 2026:

- Added immutable validated Pydantic configuration loaded with Python 3.12 `tomllib`.
- Added immutable public data models and a deeply immutable language-count mapping.
- Added stable domain exceptions and machine-readable error codes.
- Added Python-only language and canonical extension validation.
- Added centralized repository-root, candidate-file, symlink, and reset-target guards.
- Added focused configuration, model, language, and path-security tests.
- Added the Phase 1 README foundation and living hackathon compliance checklist.

Security decisions:

- Containment is checked only after strict path resolution; string-prefix checks are not used.
- Symlink components are rejected by default, and followed targets must remain inside the root.
- Candidate reads require regular files; directories and special files are rejected.
- Reset validation requires the exact configured runtime directory and performs no deletion.
- Public expected errors do not echo raw paths, TOML contents, source code, or tracebacks.
- Configuration files are rejected when any lexical path component is a symlink or junction.
- `IndexStatus.languages` uses a `MappingProxyType` defensive copy with explicit JSON-object serialization.

Final validation:

- Focused tests: 42 configuration, 64 model, 21 language, and 24 path-security tests passed.
- Aggregate tests: 128 unit and 24 security tests passed.
- Ruff passed; Ruff formatting reported 23 files already formatted.
- Strict mypy passed for 17 source files.
- `uv run codescope version` returned `CodeScope 0.1.0`.
- Scoped Phase 1 coverage: 97% (446 statements, 15 missed; 151 tests passed).

Codex Security working-tree diff review:

- Reviewed all five Phase 1 production source files in the authorized security scope.
- Reproduced two contract defects: reassignable nested model backing state and an
  intermediate-directory symlink accepted during configuration loading.
- Attack-path analysis classified both as non-reportable security issues because the current
  Phase 1 surface is local/developer-controlled and exposes no lower-privileged or MCP path.
- Fixed both validated defects and added focused regression tests.
- No validated high- or critical-severity finding remains.

Every Phase 1 completion gate passed. Phase 1 is complete in the working tree and awaits owner
review and explicit commit authorization. No Phase 2 functionality was started.

### Phase 2 — Tree-sitter Python symbol extraction

Work performed on July 15, 2026:

- Added a cached Tree-sitter Python parser that accepts already-read bytes and performs no
  filesystem access.
- Added deterministic extraction for module-level functions, async functions, classes, and
  direct class methods.
- Added decorator-aware symbol ranges, one-based line metadata, qualified method names,
  token-aware multiline signature normalization, and structurally validated docstrings.
- Added bounded malformed-source recovery that omits unreliable definitions while preserving
  independently valid symbols.
- Added representative Python fixtures and focused parser tests.

Security and scope decisions:

- Public file names remain project-relative POSIX paths; unsafe or host-absolute paths are
  rejected with fixed messages that do not echo attacker-controlled input.
- Parser binding failures are translated to chained `PARSE_FAILED` domain exceptions without
  exposing source bytes, paths, tracebacks, or dependency details.
- Extraction is bounded to module definitions and direct class methods; nested functions and
  conditional definitions are intentionally excluded.
- String docstrings are decoded with `ast.literal_eval` only after Tree-sitter structurally
  identifies the exact string-expression node.
- Multiline token offsets use a precomputed line-offset table, avoiding repeated prefix scans on
  large declarations.
- No file I/O, chunking, embeddings, storage, indexing, search, MCP tools, or Phase 3 behavior was
  added.

Final validation:

- Focused parser tests: 37 passed.
- Aggregate tests: 165 unit and 24 security tests passed.
- Ruff passed; Ruff formatting reported 28 files already formatted.
- Strict mypy passed for 17 source files.
- `uv run codescope version` returned `CodeScope 0.1.0`.
- Scoped parser coverage: 90% (199 statements, 20 missed; 37 tests passed).
- Manual security review produced one in-scope performance-hardening observation, which was fixed
  and regression-tested. The delegated Codex Security helper was blocked by an external
  content-policy error and produced no plugin finding.
