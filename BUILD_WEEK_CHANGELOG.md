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

### Phase 3 — Symbol-aware, model-budgeted code chunking

Work performed on July 15, 2026, from starting commit `c16e5b9`:

- Added a typed, dependency-injected wordpiece tokenizer protocol; Phase 3 loads neither tokenizer
  assets nor embedding-model weights.
- Added deterministic symbol-first source chunking for top-level functions, async functions,
  classes, and direct methods.
- Added interval-based class/method ownership so class declaration, docstring, and class-level gaps
  retain class context without duplicating complete method bodies.
- Added module fallback chunks for meaningful source outside parser-owned symbol ranges.
- Added complete embedding-context budgeting, line-preferred oversized splitting, tokenizer-offset
  splitting for overlong logical lines, bounded same-owner overlap, and explicit progress guards.
- Kept `CodeChunk.text` as exact source while adding a canonical transient embedding formatter for
  language, project-relative file, qualified symbol name, and signature context.
- Added deterministic SHA-256 source hashes and canonical-JSON SHA-256 chunk IDs.
- Added focused construction, ownership, splitting, Unicode, CRLF, fallback, determinism,
  serialization, safe-failure, and operation-count tests using an offset-aware fake tokenizer.
- Updated `README.md`, this changelog, `docs/.CHAT_MEMORY.md`, and
  `docs/HACKATHON_COMPLIANCE.md` with Phase 3 facts only.

Tokenizer research and lifecycle decisions:

- Confirmed installed `sentence-transformers` 5.6.0, `transformers` 5.13.1, `tokenizers` 0.22.2,
  and `huggingface-hub` 1.23.0 behavior against installed signatures and Context7 documentation.
- Fast-tokenizer offset mappings use original-character spans, and special tokens must be disabled
  for exact chunk-budget accounting.
- Constructing `SentenceTransformer` loads model modules/weights and may download uncached assets;
  Phase 3 therefore accepts an externally managed tokenizer and performs no construction.
- An offline, cache-only default-tokenizer probe reported that the tokenizer was not locally
  available; no download was attempted. Phase 4 will supply the tokenizer from one managed cached
  model lifecycle.

Security and scope decisions:

- Fixed errors do not echo source, signatures, tokenizer output, or attacker-controlled paths.
- Token offsets are validated for type, order, bounds, and exact count agreement before slicing
  decoded Python strings; UTF-8 byte offsets are never applied to decoded text.
- Every completed split part is recounted against the complete canonical embedding text before it
  is returned.
- Split selection tokenizes each logical source region once for offsets and uses bounded search;
  the deterministic large-source test guards against repeated whole-source prefix scanning.
- A delegated Phase 3 security review found no validated high- or critical-severity issue. It
  confirmed one low-severity hardening suggestion: an unusually long, tokenizer-cheap signature can
  amplify character processing because mandatory signature context is retokenized for split
  candidates. The bounded reproduction measured 192.4x source-character processing. A character
  cap or signature rewrite would conflict with this phase's exact context contract, so the issue is
  recorded for the Phase 4 tokenizer/indexer boundary, where file-size limits and model lifecycle
  can be enforced together.
- No filesystem reads, network access, model loading, vector generation, storage, indexing, search,
  MCP behavior, or CLI expansion was added.
- Graphify was not run or regenerated, and Phase 4 was not started.

Changed files:

- `src/codescope/chunker.py`
- `tests/unit/test_chunker.py`
- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`

Final validation:

- `uv run pytest tests/unit/test_chunker.py -q` — 71 passed.
- `uv run pytest tests/unit/test_chunker.py -v` — 71 passed.
- Scoped chunker coverage — 96% (323 statements, 13 missed; 71 tests passed).
- `uv run pytest tests/unit -q` — 236 passed.
- `uv run pytest tests/security -q` — 24 passed.
- Ruff passed; Ruff formatting reported 29 files already formatted.
- Strict mypy passed for 17 source files.
- `uv run codescope version` returned `CodeScope 0.1.0`.
- The Codex Security configuration preflight returned `ready` with exit code 0; the delegated
  review completed without a content-policy blocker and produced no reportable finding.
- A bounded manual LF/CRLF/Unicode module-splitting check passed 200 deterministic cases.
- Dependency, lockfile, Phase 4 module, and Graphify diff checks were empty.

Every Phase 3 implementation and quality gate passed. Phase 3 is complete and its final clean audit
received owner commit authorization. No Phase 4 functionality was started.

### Phase 4 — Local embeddings and persistent vector storage

Work performed on July 15–16, 2026, from starting commit `3dc46f2`:

- Added a lazy `LocalEmbedder` with injected model construction, process-local lifecycle reuse,
  cache-only normal loading, explicit preparation-time download permission, configured device and
  batch handling, finite two-dimensional `float32` output validation, and normalization checks.
- Added one model-managed fast-tokenizer adapter with special tokens disabled, validated
  original-character offsets, the verified model input limit, and bounded exact prefix-count reuse.
- Integrated the prefix-count seam into Phase 3 chunk budgeting without changing source text,
  chunk ownership, hashes, IDs, or the dependency-injected tokenizer fallback.
- Added telemetry-disabled persistent local Chroma storage with explicit cosine configuration,
  caller-provided embeddings, scalar project-relative metadata, embedding-free query responses,
  deterministic validation, exact-file deletion, and collection-only reset behavior.
- Added atomic UTF-8 JSON persistence for fixed `symbols.json` and `index_meta.json` names using a
  same-directory temporary file, file and directory synchronization, and atomic replacement.
- Added central runtime-directory validation and applied it to direct `StorageConfig` construction
  after reproducing ancestor-symlink acceptance and link-evidence loss in the prior validator.
- Added focused embedder, storage, integration, configuration-regression, and Phase 4 security
  tests. No repository scanner, indexer, query engine, MCP tool, or CLI expansion was added.

Model and dependency verification:

- Inspected installed `sentence-transformers` 5.6.0, `transformers` 5.13.1, `tokenizers` 0.22.2,
  `huggingface-hub` 1.23.0, `chromadb` 1.5.9, `numpy` 2.5.1, and `torch` 2.13.0 APIs locally and
  consulted Context7 for the version-sensitive Sentence Transformers, Hugging Face tokenizer, and
  Chroma contracts.
- Ran the explicitly authorized real-model path once with download permission and a cache outside
  the repository: one integration test passed in 25.11 seconds.
- Re-ran the same integration test in a fresh process with download permission disabled plus
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`: one test passed in 6.60 seconds.
- Verified the default model produces `(2, 384)` `float32` unit-normalized vectors, reports a
  256-wordpiece input limit, supplies fast Unicode character offsets, and keeps formatted Phase 3
  chunks within the configured 220-wordpiece budget.

Changed implementation and test files:

- `src/codescope/embedder.py`
- `src/codescope/storage.py`
- `src/codescope/utils/json_io.py`
- `src/codescope/chunker.py`
- `src/codescope/utils/path_guard.py`
- `src/codescope/config.py`
- `tests/unit/test_embedder.py`
- `tests/unit/test_storage.py`
- `tests/unit/test_config.py`
- `tests/security/test_phase4_safety.py`
- `tests/integration/test_embedder_real_model.py`
- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`

Observed validation before the final evidence-only pass:

- `uv run pytest tests/unit/test_embedder.py -q` — 30 passed.
- `uv run pytest tests/unit/test_storage.py -q` — 43 passed with 36 installed-Chroma
  deprecation warnings.
- Combined focused verbose suite — 73 passed with 36 installed-Chroma deprecation warnings.
- `uv run pytest tests/unit -q` — 310 passed with 36 installed-Chroma deprecation warnings.
- Forced-offline `uv run pytest tests/integration -q` — 1 passed.
- `uv run pytest tests/security -q` — 34 passed with 5 installed-Chroma deprecation warnings.
- Ruff passed; Ruff formatting reported 34 files already formatted.
- Strict mypy passed for 18 source files.
- `uv run codescope version` returned `CodeScope 0.1.0`.
- Scoped embedder/storage coverage measured 90% (505 statements, 53 missed; 73 tests passed).

Security and scope decisions:

- Cache-only operation is the default; network/model download permission must be explicit.
- CPU operation does not inspect CUDA. Explicit CUDA configuration fails safely before model
  construction when CUDA is unavailable.
- Expected storage messages do not include source documents, vectors, JSON contents, or absolute
  runtime paths; lower-level exceptions are retained only through chaining as required by the
  Phase 4 contract.
- Runtime and metadata paths reject link components and special filesystem objects. Reset deletes
  only the configured Chroma collection and optionally the two fixed metadata files; it never
  recursively removes the runtime directory.
- The Codex Security configuration preflight returned `ready`. Six changed production files were
  reviewed in full. Discovery produced two plausible candidates; neither survived validation and
  attack-path analysis as a reportable issue.
- Chained storage causes were rejected because Phase 4 has no CLI/MCP/logger traceback sink, public
  messages remain fixed, and the contract explicitly requires original exceptions through chaining.
- Complete-file metadata parsing without a pre-parse byte limit was rejected as a current security
  issue because no Phase 4 product caller or lower-privileged runtime writer exists. Metadata sizing
  remains a Phase 5 hardening consideration when the complete indexing/read lifecycle is defined.
- The delegated metadata validation helper was blocked once by its content-policy gate. It was not
  retried; parent static validation and attack-path analysis completed the candidate ledger.
- The finalized Codex Security report contains zero reportable findings and no unresolved validated
  high- or critical-severity issue.
- Dependency and lockfile diffs, Phase 5 module diffs, and Graphify diffs were empty. Graphify was
  not run or regenerated, and Phase 5 was not started.

Final Phase 4 validation after evidence updates:

- `uv run pytest tests/unit/test_embedder.py -q` — 30 passed in 0.32 seconds.
- `uv run pytest tests/unit/test_storage.py -q` — 43 passed with 36 installed-Chroma
  deprecation warnings in 3.59 seconds.
- `uv run pytest tests/unit/test_embedder.py tests/unit/test_storage.py -v` — 73 passed with 36
  warnings in 3.69 seconds.
- Scoped embedder/storage coverage — 90% (505 statements, 53 missed; 73 tests passed in 5.15
  seconds).
- `uv run pytest tests/unit -q` — 310 passed with 36 warnings in 4.11 seconds.
- Ordinary `uv run pytest tests/integration -q` — one explicit real-model test skipped because the
  opt-in environment flag was absent.
- Fresh-process forced-offline integration — 1 passed in 6.54 seconds.
- `uv run pytest tests/security -q` — 34 passed with 5 warnings in 1.31 seconds.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed; 34 files already formatted.
- `uv run mypy src/codescope` — passed; 18 source files checked.
- `uv run codescope version` — `CodeScope 0.1.0`.
- `git diff --check` — passed with no output.
- Generated test/coverage artifacts were removed; the final artifact scan returned no repository
  model cache, `.codescope`, Chroma database, temporary JSON, coverage output, NumPy dump, or
  `__pycache__` outside the existing ignored environment.

Every Phase 4 implementation, regression, quality, security, and scope gate passed. Phase 4 owner
review and commit authorization were received; this Phase 4 commit records the validated result.


### Phase 5 — Secure repository scanner and indexing orchestration

Work performed on July 16, 2026, from Phase 4 commit `42c607c`:

- Added deterministic `RepositoryScanner` discovery for `.py` and `.pyi` files using sorted project-relative POSIX ownership paths and physical inode/device deduplication.
- Added configured exclusions plus repository-root `.gitignore` matching through installed `pathspec` 1.1.1. Nested `.gitignore` semantics are intentionally deferred.
- Added mandatory environment, secret, key/certificate, archive, image, database, model-cache, virtual-environment, dependency-tree, cache, build, distribution, and runtime exclusions that ignore negations cannot re-enable.
- Added default symlink rejection plus opt-in contained symlink following with external-target rejection, directory-cycle termination, runtime exclusion, and one deterministic physical-file owner.
- Added maximum-plus-one descriptor reads, before/after identity/size/mtime checks, regular-file enforcement, NUL rejection, and strict UTF-8 decoding.
- Added `RepositoryIndexer` orchestration across parser, chunker, complete embedding formatter, injected embedder, configured batches, temporary Chroma storage, atomic symbols/metadata, second-client verification, and live promotion.
- Added restricted sibling `.codescope.build-*` and `.codescope.backup-*` handling, explicit Chroma closure before rename, rollback-capable promotion, and exact generated-path recursive cleanup.
- Added `codescope index [PATH]`, explicit `--allow-model-download`, and `codescope status` while preserving `codescope version`.
- Added status reconciliation for configuration fingerprint, model, language/file counts, symbol count, Chroma count, metadata schema, and bounded runtime size without model loading.
- Added separate descriptor-read limits of 64 KiB for `index_meta.json` and 16 MiB for `symbols.json`; the smaller fixed-shape document and potentially larger symbol inventory do not share an arbitrary source-file limit.
- Added deterministic scanner, Git-ignore, CLI, full-pipeline integration, rollback, corruption, model-network, metadata-size, and generated-path security tests.

Phase 5 changed files:

- `src/codescope/cli.py`
- `src/codescope/indexer.py`
- `src/codescope/models.py`
- `src/codescope/storage.py`
- `src/codescope/utils/gitignore.py`
- `src/codescope/utils/json_io.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_gitignore.py`
- `tests/unit/test_indexer.py`
- `tests/unit/test_models.py`
- `tests/unit/test_storage.py`
- `tests/integration/test_indexer_pipeline.py`
- `tests/security/test_phase5_safety.py`
- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`

Starting-state evidence:

- Branch `main`, `HEAD`, and `origin/main` were all at `42c607c`; the working tree was clean.
- `uv sync --frozen` checked 139 packages without changing `uv.lock`.
- Python was 3.12.13 and CodeScope was 0.1.0.
- Baseline suites passed 310 unit and 34 security tests; the existing real-model integration remained opt-in.
- Baseline Ruff, formatting, and strict mypy passed.

Final Phase 5 validation after the security correction:

- `uv run pytest tests/unit/test_indexer.py -q` — 41 passed with 82 installed-Chroma deprecation warnings.
- `uv run pytest tests/integration/test_indexer_pipeline.py -q` — 1 passed, 1 explicit real-model test skipped, with 38 warnings.
- `uv run pytest tests/security/test_phase5_safety.py -q` — 27 passed with 111 warnings.
- `uv run pytest tests/unit/test_cli.py tests/unit/test_gitignore.py -q` — 19 passed.
- Focused verbose pipeline review — 69 passed, 1 explicit real-model test skipped, with 231 warnings.
- Scoped `codescope.indexer` coverage — 88% (572 statements, 68 missed; 69 passed and 1 skipped).
- `uv run pytest tests/unit -q` — 377 passed with 119 warnings.
- `uv run pytest tests/integration -q` — 1 passed, 2 explicit real-model tests skipped, with 38 warnings.
- Explicit fresh-process offline real-model integration — 3 passed with 58 warnings in 8.34 seconds.
- `uv run pytest tests/security -q` — 61 passed with 116 warnings.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed; 39 files already formatted.
- `uv run mypy src/codescope` — passed; 18 source files checked.
- `uv run codescope version` — `CodeScope 0.1.0`.
- CLI fixture acceptance — 4 files, 11 symbols, 16 chunks, 0 skipped in 6.920 seconds; status reported root `.`, Python count 4, and index size 457982 bytes.
- The generated `.codescope` runtime and coverage artifact were removed through exact validated cleanup; no repository-local model cache, build/backup directory, Chroma database, temporary JSON, or NumPy dump remained.

Security review:

- Codex Security capability preflight returned `ready`.
- All six changed production files received full-file completion receipts. Delegated discovery workers exhausted their external usage allowance without producing usable receipts, so the parent completed every review and candidate phase locally.
- One CWE-400 candidate was reproduced: repository and runtime directory iterators were fully materialized by `sorted()` before their entry counters ran. With a configured test limit of two, the instrumented iterator was consumed four times before the intended error could execute.
- Validation classified the control-order defect as valid. Attack-path policy suppressed it as a reportable vulnerability because exploitation is developer-initiated, resource-intensive, transient, local, and limited to one process.
- The working tree was hardened with a shared remaining-limit-plus-one iterator guard before sorting, and an operation-count regression proved exactly three consumptions for a remaining allowance of two.
- Post-correction Ruff, strict mypy, and 68 focused indexer/security tests passed. The sealed scan report has complete coverage, zero reportable findings, and no unresolved validated high- or critical-severity issue.

Scope confirmation:

- `pyproject.toml` and `uv.lock` are unchanged.
- `src/codescope/engine.py` and `src/codescope/server.py` are unchanged.
- Graphify was not run or regenerated; `graphify-out/`, `.graphifyignore`, and `.codex/skills/graphify` are unchanged.
- Phase 6 query-engine behavior was not started.

Phase 5 is complete in the working tree and awaits owner review. No commit, push, tag, pull request, or remote-state change was made.
