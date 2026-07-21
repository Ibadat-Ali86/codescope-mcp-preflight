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


### Phase 6 — Read-only semantic and symbol query engine

Work performed on July 16, 2026, from committed Phase 5 SHA `9865e0c2c94bd62507a679be555e661cde22d4b5` on `main`:

- Added a typed `QueryEngine` with `search_code`, `find_symbol`, `find_similar`, and `get_index_status` methods.
- Reused the authoritative Phase 5 status path before every operation; missing or corrupt indexes fail without creating a runtime, collection, build directory, or backup directory.
- Added lazy cache-only query embeddings with exactly one validated finite vector and no automatic model download.
- Reused `ChromaStorage.query()` with `create=False`, optional normalized Python filtering, caller-bounded result counts, source-only stored snippets, and no returned embeddings.
- Added bounded query, symbol-name, and snippet materialization; strict integer limits reject booleans and values outside `1..20`.
- Added deterministic semantic ordering by score, path, lines, ownership, and stored identifier, with cosine relevance clamped to `[0.0, 1.0]`.
- Added the required five-group symbol ranking, deterministic tie-breaking, kind filtering before limits, duplicate suppression, and no symbol cache that could hide index replacement.
- Preserved known domain exceptions and safely chained only unexpected query-orchestration failures without source, query, vector, Chroma, or absolute-path content.
- Added a deterministic fake-backed unit suite and an explicit cache-only/offline real-model integration that rebuilds the fixture, opens it through a new engine, finds `validate_email`, confirms `validators.py` lines 6–9, exercises similar-code search, and reconciles status counts.
- No new version-sensitive direct Chroma or sentence-transformers API was introduced; Phase 6 uses the already documented and committed Phase 4/5 wrappers, so no additional Context7 lookup was required.

Phase 6 changed files:

- `src/codescope/engine.py`
- `tests/unit/test_engine.py`
- `tests/integration/test_query_engine.py`
- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`

Observed Phase 6 validation before the final evidence-only pass:

- `uv run pytest tests/unit/test_engine.py -q` — 63 passed.
- `uv run pytest tests/integration/test_query_engine.py -q` — 1 explicit real-model test skipped because the opt-in environment flag was absent.
- Scoped `codescope.engine` coverage — 91% (207 statements, 19 missed; uncovered lines 82, 194–195, 203–204, 209, 227–228, 236–239, 249–250, 266, 316, 358–359, and 375).
- `uv run pytest tests/unit -q` — 440 passed with 119 installed-Chroma deprecation warnings.
- `uv run pytest tests/integration -q` — 1 passed, 3 explicit real-model tests skipped, with 38 warnings.
- Explicit cache-only/offline real-model matrix — 4 passed with 71 installed-Chroma deprecation warnings in 9.48 seconds.
- `uv run pytest tests/security -q` — 61 passed with 116 warnings.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed; 41 files already formatted.
- `uv run mypy src/codescope` — passed; 18 source files checked.
- `uv run codescope version` — `CodeScope 0.1.0`.
- `git diff --check` — passed.

Phase 6 security and scope review:

- Codex Security capability preflight returned `ready`.
- The repository-wide threat model was generated independently of the Phase 6 diff and copied unchanged into the scan context.
- The single production worklist row, `src/codescope/engine.py`, received a complete full-file receipt with the Phase 6 tests and committed status/storage/model contracts used only as supporting evidence.
- Discovery found no technically plausible candidate across query/snippet leakage, absolute paths, arbitrary source reads, query-side creation or mutation, unbounded materialization, malformed stored results, stale state, model egress, vector exposure, denial of service, and nondeterministic output.
- With no candidate, validation and attack-path phases were correctly skipped. The finalized canonical scan bundle reports complete coverage, zero reportable findings, and no deferred work.
- Independent manual review reached the same result.
- `pyproject.toml`, `uv.lock`, `src/codescope/cli.py`, `src/codescope/server.py`, Graphify output/configuration/skill files, and all Phase 7+ files are unchanged.
- Graphify was not run or regenerated. `/feedback` was not run. Phase 7 was not started.

Phase 6 is complete in the working tree and awaits owner review. No Phase 6 file was staged, committed, pushed, tagged, or used to change remote state.


### Phase 7 — Command-line interface and validated runtime reset

Work performed on July 16, 2026, from committed Phase 6 SHA `f68f1e90c276e486be09825e4cbb435421889465` on `main`:

- Replaced the Phase 5 acceptance shell with the six-command Typer interface: `version`, `index`, `status`, `search`, `serve`, and `reset`.
- Kept `version` and every help path independent of configuration, storage, model loading, runtime creation, and network access.
- Delegated index, authoritative status, and semantic search to the existing Phase 5/6 boundaries, preserving cache-only default model behavior and the explicit indexing download flag.
- Added bounded deterministic progress output, complete index/status summaries, source-only human results, and stable sorted JSON output.
- Disabled Rich markup/highlighting for repository-controlled values and neutralized terminal controls in human output. JSON uses ASCII escapes so line separators, bidi controls, and surrogate values cannot reach stdout literally while parsed values round-trip exactly.
- Added a lazy, fail-closed `serve` shell. Phase 8 remains responsible for the MCP stdio implementation; the current failure writes a safe error to stderr and no protocol data to stdout.
- Added confirmation-gated reset and `RepositoryIndexer.reset()`. Only the exact configured runtime strictly below the validated repository root can reach deletion, after a second immediate validation.
- Added focused CLI unit, reset security, malicious-filename, and explicit offline real-model CLI integration tests.
- Consulted installed-version Context7 references for Typer annotated options, confirmations, `CliRunner`, Rich stderr consoles, terminal detection, tables, and non-animated output.

Phase 7 changed files:

- Production: `src/codescope/cli.py` and `src/codescope/indexer.py`.
- Tests: `tests/unit/test_cli.py`, `tests/integration/test_cli.py`, and `tests/security/test_cli_safety.py`.
- Evidence: `README.md`, `BUILD_WEEK_CHANGELOG.md`, `docs/.CHAT_MEMORY.md`, and `docs/HACKATHON_COMPLIANCE.md`.

Observed Phase 7 validation after the final terminal-output correction:

- `uv run pytest tests/unit/test_cli.py -q` — 31 passed.
- `uv run pytest tests/security -q -k 'cli or reset'` — 24 passed, 1 platform-specific junction test skipped, and 51 deselected, with 2 installed-Chroma deprecation warnings.
- `uv run pytest tests/integration/test_cli.py -q` — 1 explicit real-model test skipped because the opt-in flag was absent.
- All seven help/version checks passed; the root help lists exactly the six authorized commands and `CodeScope 0.1.0` remains unchanged.
- `uv run pytest tests/unit -q` — 465 passed with 119 installed-Chroma deprecation warnings.
- `uv run pytest tests/integration -q` — 1 passed, 4 explicit real-model tests skipped, with 38 warnings.
- `uv run pytest tests/security -q` — 75 passed, 1 platform-specific junction test skipped, with 116 warnings.
- Scoped CLI/indexer coverage — 90% total (799 statements, 82 missed). `codescope.cli` measured 95% (209 statements, 11 missed; uncovered lines 90, 111–120, 130, 159–168, 235–236, 250, and 360). `codescope.indexer` measured 88% (590 statements, 71 missed); reset-specific uncovered lines are the `OSError` translation and post-delete failure branches at 1021–1022 and 1024.
- Explicit cache-only/offline real-model matrix, including the CLI workflow — 5 passed with 81 installed-Chroma deprecation warnings in 8.89 seconds.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed; 43 files already formatted.
- `uv run mypy src/codescope` — passed; 18 source files checked.
- `git diff --check` — passed.

Phase 7 manual acceptance in an isolated temporary workspace:

- Help exposed the six authorized commands and version returned `CodeScope 0.1.0`.
- Indexing accepted 4 files, extracted 11 symbols, stored 16 chunks, skipped 0 files, and completed in 5.717 seconds.
- Status reported root `.`, Python count 4, and 457982 bytes.
- Human and JSON semantic search both returned `validate_email` at `validators.py:6-9`; the JSON array parsed successfully.
- Fixture source hashes were unchanged and reset removed only the temporary `.codescope` runtime.

Phase 7 security and scope review:

- Codex Security capability preflight was ready and the two changed production files received complete full-file discovery receipts.
- Two terminal-integrity defects were reproduced and corrected: human metadata allowed newline/bidi visual forgery, and JSON stdout emitted literal Unicode separators/bidi controls. Regression tests now cover both human neutralization and exact JSON round-tripping with escaped controls.
- Post-fix review found no remaining plausible candidate. Reset validation, path containment, symlink/junction behavior, confirmation, stdout/stderr separation, query/source privacy, bounded output, cache-only search, and generated-state behavior were reviewed explicitly.
- The remaining reset validation-to-use race requires same-user or privileged filesystem mutation, is documented, and remains an accepted local-filesystem limitation rather than an unresolved high- or critical-severity issue.
- `pyproject.toml`, `uv.lock`, `src/codescope/server.py`, `src/codescope/engine.py`, Graphify output/configuration/skill files, and every Phase 8+ production file are unchanged.
- Graphify was not run or regenerated. `/feedback` was not run. Phase 8 was not started.

Phase 7 is complete in the working tree and awaits owner review. No Phase 7 file is staged, committed, pushed, tagged, or used to change remote state.

### Phase 8 — Local stdio MCP server and four read-only tools

Work performed on July 16, 2026.

Phase boundary:

- Phase 7 implementation commit: `a874df89c19519c44c1eba342d47f6c1b9534552`.
- Phase 7 corrective review commit: `c107abcbdb47c256cff21418384479eb8daf6323`.
- Phase 8 starting SHA: `c107abcbdb47c256cff21418384479eb8daf6323`.
- The two published Phase 7 commits were preserved without squash, amend, rebase, reset, or force-push.

Implemented work:

- Added a testable lazy FastMCP v1 server factory and stdio runner without import-time configuration, repository scanning, index validation, model loading, Chroma access, runtime creation, or network permission.
- Exposed exactly `search_code`, `find_symbol`, `find_similar`, and `list_indexed_files` as read-only, non-destructive, idempotent, local/closed-world tools.
- Delegated searches and status to the committed Phase 6 engine while preserving exact parameters, deterministic ordering, configured bounds, cache-only model behavior, source-only snippets, and authoritative per-call index revalidation.
- Added deterministic server instructions whose first 512 characters contain the complete preflight policy, followed by explicit untrusted-source and REUSE/EXTEND/CREATE guidance.
- Preserved existing immutable Pydantic success models and stable domain errors. Installed MCP 1.28.1 represents list/status success and error unions as schema-valid structured content under one `result` field.
- Added strict protocol argument validation before FastMCP's compatibility conversion so malformed values and undocumented parameters return fixed structured errors without reflecting attacker-controlled content.
- Added fixed-message expected and unexpected error translation, safe Loguru stderr metadata, protocol-only stdout, and cancellation/process-exit preservation.
- Connected `codescope serve` to the real lazy stdio runner while keeping all unrelated CLI commands free from FastMCP initialization.
- Added verified Codex configuration examples without modifying the active `.codex/config.toml`.

Installed-version research:

- Confirmed locked and installed `mcp` 1.28.1 with the stable project constraint `mcp[cli]>=1.27,<2`.
- Used Context7 and installed package signatures/source to verify FastMCP construction, tool registration, structured output, `ToolAnnotations`, stdio client lifecycle, and SDK list/union schema wrapping.
- Used current official Codex MCP documentation to verify stdio `command`, `args`, `startup_timeout_sec`, `tool_timeout_sec`, `enabled`, `required`, `enabled_tools`, and `default_tools_approval_mode`, plus the first-512-character instruction guidance.
- Parsed `.codex/config.toml.example` with installed Codex CLI 0.144.5; `codex mcp list` registered `codescope` as enabled.

Changed files:

- Production: `src/codescope/server.py` and `src/codescope/cli.py`.
- Tests: `tests/conftest.py`, `tests/unit/test_server.py`, `tests/unit/test_cli.py`, `tests/integration/test_mcp_tools.py`, and `tests/security/test_mcp_safety.py`.
- Configuration examples: `.codex/config.toml.example` and `examples/codex_mcp_config.toml`.
- Evidence: `README.md`, `BUILD_WEEK_CHANGELOG.md`, `docs/.CHAT_MEMORY.md`, and `docs/HACKATHON_COMPLIANCE.md`.

Observed Phase 8 validation:

- `uv run pytest tests/unit/test_server.py -q` — 18 passed in 2.64 seconds.
- `uv run pytest tests/integration/test_mcp_tools.py -q` — 3 passed and 1 explicit real-model test skipped in 2.62 seconds.
- `uv run pytest tests/security/test_mcp_safety.py -q` — 21 passed in 1.46 seconds.
- `uv run pytest tests/unit/test_cli.py -q` — 33 passed in 0.98 seconds.
- `uv run pytest tests/integration/test_cli.py -q` — 1 explicit real-model test skipped in 0.76 seconds.
- `uv run pytest tests/security/test_cli_safety.py -q` — 14 passed and 1 platform-specific junction test skipped in 0.79 seconds.
- Aggregate unit suite — 485 passed with 119 installed-Chroma deprecation warnings in 10.08 seconds.
- Aggregate ordinary integration suite — 4 passed, 5 explicit real-model tests skipped, and 38 installed-Chroma deprecation warnings in 4.10 seconds.
- Aggregate security suite — 96 passed, 1 platform-specific junction test skipped, and 116 installed-Chroma deprecation warnings in 6.53 seconds.
- Explicit cache-only/offline real-model integration matrix — 9 passed with 86 installed-Chroma deprecation warnings in 18.14 seconds, including the MCP fixture index and all four tool calls.
- Scoped coverage — `server.py` 100%, affected `cli.py` 92%, and 95% combined (332 statements, 18 missed); no server line remained uncovered.
- CLI help, `serve --help`, and version passed; version remained `CodeScope 0.1.0`.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed; 46 files already formatted.
- `uv run mypy src/codescope` — passed; 18 source files checked.
- `git diff --check` — passed.

Security and scope review:

- The final Codex Security capability preflight returned `ready` for the immutable Phase 8 revision diff from `c107abcb` through `5afc064`.
- Independent full-file discovery reviewed all 355 lines of `server.py` and all 371 lines of `cli.py`; no technically plausible security candidate survived, so candidate validation and attack-path analysis were not applicable.
- The canonical scan bundle was validated and sealed with complete diff coverage, zero reportable findings, and no unresolved validated high- or critical-severity issue. The report was produced outside the repository; no machine-specific report path is recorded here.
- Manual review confirmed no raw-input reflection, source/query/snippet/path leakage, stdout contamination, destructive or write tool, model download authorization, index mutation, filesystem read, schema-invalid response, cancellation swallowing, or Phase 9 behavior.
- One non-reportable defense-in-depth observation remains: installed FastMCP executes synchronous tool bodies serially within the caller's local stdio process. Existing bounds and the absence of a remote or cross-user service keep this a local performance limitation rather than a reportable finding.
- The expected local stdio request-allocation limitation remains bounded only after SDK JSON parsing; no remote listener or cross-user service is present in this phase.
- `pyproject.toml`, `uv.lock`, indexer/storage, Graphify output/configuration/skill files, and every Phase 9+ production file are unchanged.
- `/feedback` was not run.

On July 18, 2026, the final audit found that the owner had preserved the complete Phase 8 patch in checkpoint commit `5afc0648fb743c943f1fa2e592d8882967708b7c`, followed only by documentation handoff commits. Published history was not rewritten. The final evidence corrections were committed separately as `cd6f062bdad2ef25b28948ad79bdd62c49f97746` before Phase 9 began.

### Phase 9 — Codex preflight skill and duplication-prevention demonstration

Work performed on July 18, 2026, from clean synchronized `main` commit
`cd6f062bdad2ef25b28948ad79bdd62c49f97746`:

- Added the repository-scoped `codescope-preflight` Codex skill with valid minimal frontmatter,
  inventory-first tool order, semantic, symbol, and similar-code evidence, an exact structured
  REUSE/EXTEND/CREATE report, explicit untrusted-snippet handling, and fail-closed tool behavior.
- Added a fixed bounded email-validator task manifest targeting `validate_email` in
  `validators.py` at lines 6–9.
- Added an import-safe judge demo that copies the reviewed fixture into a temporary workspace,
  builds a separate cache-only index, starts the real committed stdio server, calls all four MCP
  tools, and removes its Chroma/runtime state on success or failure.
- Kept source snippets out of the report, produced deterministic source-free human and JSON output,
  and required inventory, location, exact-symbol, similar-code, canonical-source, unchanged-hash,
  and duplicate-absence evidence before recommending REUSE.
- Added focused deterministic and opt-in real-model e2e coverage for skill contracts, task parsing,
  tool ordering, safe output, fail-closed responses, path handling, canonical fixture integrity,
  evidence conflicts, source changes, duplicate detection, and the real stdio workflow.
- Added a reproducible demo runbook and factual before/after evidence without raw Codex
  transcripts, session identifiers, account data, model-cache paths, or machine-specific links.

Official Codex skill research and manual acceptance:

- Current official Codex documentation confirmed repository skill discovery at
  `.agents/skills/<name>/SKILL.md`, required `name` and `description` frontmatter, explicit
  `$skill-name` invocation, and natural triggering from the description.
- A controlled explicit invocation called `list_indexed_files`, `search_code`, `find_symbol`, and
  `find_similar`, emitted the required report, recommended REUSE, and edited no file.
- After refining only the description trigger wording, a fresh natural invocation called inventory
  first, used all three search modes, emitted the structured report with uncertainty, recommended
  REUSE, and edited no file. Exact fixture hashes before and after were equal.

Phase 9 changed files:

- Skill: `.agents/skills/codescope-preflight/SKILL.md`.
- Demo: `scripts/demo.py` and `tests/fixtures/duplication_demo/task.json`.
- Tests: `tests/e2e/test_duplication_prevention.py`.
- Demo evidence: `docs/DEMO_SCRIPT.md` and `docs/DEMO_EVIDENCE.md`.
- Living evidence: `README.md`, `BUILD_WEEK_CHANGELOG.md`, `docs/.CHAT_MEMORY.md`, and
  `docs/HACKATHON_COMPLIANCE.md`.
- No file under `src/codescope`, dependency or lockfile, MCP configuration example, Graphify path,
  or Phase 10 file changed.

Observed final validation after security corrections:

- `uv run pytest tests/e2e/test_duplication_prevention.py -q` — 27 passed and 1 explicit real-model
  test skipped in 2.97 seconds; `uv run python scripts/demo.py --help` passed.
- `uv run pytest tests/unit/test_server.py -q` — 18 passed in 3.24 seconds.
- `uv run pytest tests/integration/test_mcp_tools.py -q` — 3 passed and 1 explicit real-model test
  skipped in 3.57 seconds.
- `uv run pytest tests/security/test_mcp_safety.py -q` — 21 passed in 1.91 seconds.
- `uv run pytest tests/unit/test_cli.py -q` — 33 passed in 1.67 seconds.
- Aggregate unit — 485 passed with 119 installed-Chroma deprecation warnings in 10.11 seconds.
- Aggregate ordinary integration — 4 passed, 5 explicit real-model tests skipped, and 38
  installed-Chroma deprecation warnings in 4.03 seconds.
- Aggregate security — 96 passed, 1 operating-system junction test skipped, and 116
  installed-Chroma deprecation warnings in 6.95 seconds.
- Aggregate e2e — 27 passed and 1 explicit real-model test skipped in 2.87 seconds.
- Explicit offline/cache-only Phase 9 e2e — 28 passed with 5 installed-Chroma deprecation warnings
  in 15.11 seconds.
- Explicit offline/cache-only integration plus e2e matrix — 37 passed with 91 installed-Chroma
  deprecation warnings in 20.14 seconds.
- Ruff passed; formatting reported 48 files already formatted; strict mypy passed for 18 source
  files, and the additional typed demo check passed for 1 file.
- `uv lock --check` resolved the unchanged 142-package lock; `CodeScope 0.1.0` remained functional;
  `git diff --check` passed.
- The final human demo indexed 4 files, 11 symbols, and 16 chunks; all three evidence calls pointed
  to `validate_email` at `validators.py:6-9`; the recommendation was REUSE; exact source hashes were
  unchanged; no duplicate was present; observed duration was 14.72 seconds. This is an observation,
  not a benchmark.
- JSON-only output parsed successfully and contained no source snippet, embedding, protocol frame,
  cache path, temporary path, or timestamp.

Security and scope review:

- Codex Security capability preflight returned `ready`, and complete-file review receipts covered
  the skill, demo, manifest, tests, and demo documentation.
- A fixture-root symlink escape and an unchanged-but-noncanonical false-REUSE path were reproduced
  through the real cache-only demo. Attack-path policy classified both as nonreportable because
  they require developer control of protected checkout state and have no remote surface or
  privilege delta; both were corrected and regression-tested anyway.
- A manifest-ancestor candidate could not influence the fixed scenario, and instruction-like task
  values were rejected by exact literal validation. Manifest ancestry was hardened consistently.
- A post-fix bypass review reproduced and closed a symlinked-ancestor path in the standalone source
  hash helper. Final discovery found no surviving plausible candidate and no unresolved validated
  high- or critical-severity issue.
- The remaining validation-to-use race requires same-user filesystem mutation after validation and
  is an accepted portable local-filesystem limitation.
- One repository-required read-only `graphify query` was attempted during reconnaissance; its
  stale result was not used in place of direct source inspection. Graphify output was not
  regenerated or modified. Phase 10 was not started and `/feedback` was not run.

Phase 9 is complete in the working tree and awaits owner review. Every Phase 9 file remains
unstaged and uncommitted; no remote state was changed.

### Phase 10 — Security, performance, documentation, and release readiness

Work performed on July 18, 2026, from clean synchronized `main` commit
`2c358ac3d1b3ab46e5c36b8302529fe4414276c9`:

- Added an import-safe, bounded, cache-only fixture benchmark covering one index rebuild,
  authoritative status, semantic search, exact symbol lookup, similar-code lookup, real MCP stdio
  startup and calls, and the fixed duplication-prevention demo. Reports contain timing and
  aggregate fixture metadata only; no source, embedding, hostname, user, cache, repository, or
  temporary path is emitted.
- Added an opt-in candidate-clone verifier. It clones `HEAD` with `--no-local`, applies the tracked
  patch, copies only a fixed bounded allowlist of regular untracked Phase 10 files, synchronizes a
  fresh clone-local environment, runs the CLI/MCP/demo/reset judge path offline, checks source and
  source-repository integrity, and removes the clone/runtime on success or failure.
- Added deterministic release/security tests for benchmark limits and privacy, candidate-patch
  containment, untracked-file rejection, environment minimization, subprocess output/time bounds,
  POSIX descendant termination, source immutability, cleanup, and complete real verification.
- Added setup, architecture, API, security/threat, benchmark, coverage, troubleshooting, and Codex
  handoff documentation. Updated the README and living submission checklist without marking video,
  audio, Devpost, `/feedback`, tag, or repository-visibility work complete.
- Corrected a real combined-suite collection blocker by selecting pytest's documented `importlib`
  import mode for same-named test modules and added `mypy_path = "src"` so the exact typed-script
  release command works.
- Corrected a real package-compliance blocker by declaring the existing MIT license through PEP 639
  metadata and including `LICENSE` in both sdist and wheel. No dependency or locked version changed.
- Kept CI deferred: local ordinary suites are deterministic, but adding a workflow was optional and
  would broaden this phase while the real model and clone paths intentionally require an external
  prepared cache. The final owner may make a separate Phase 11 CI decision.

Phase 10 files added:

- `scripts/benchmark.py`
- `scripts/verify_clean_setup.py`
- `tests/release/test_benchmark.py`
- `tests/release/test_clean_setup.py`
- `tests/security/test_phase10_safety.py`
- `docs/SECURITY.md`
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/SETUP.md`
- `docs/BENCHMARKS.md`
- `docs/COVERAGE.md`
- `docs/TROUBLESHOOTING.md`

Phase 10 files modified:

- `pyproject.toml`
- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`
- `docs/CODEX_HANDOFF.md`

Observed final Phase 10 validation:

- `uv run pytest tests/release -q` — 24 passed and 1 explicit clean-setup test skipped in 6.86
  seconds.
- `CODESCOPE_RUN_CLEAN_SETUP=1 uv run pytest tests/release/test_clean_setup.py -q` — 10 passed in
  52.15 seconds.
- Aggregate unit — 485 passed with 119 installed-Chroma deprecation warnings in 10.57 seconds.
- Aggregate ordinary integration — 4 passed, 5 explicit real-model tests skipped, and 38 warnings
  in 4.20 seconds.
- Aggregate security after Phase 10 tests — 101 passed, 1 operating-system junction test skipped,
  and 116 warnings in 7.29 seconds.
- Aggregate ordinary e2e — 27 passed and 1 explicit real-model test skipped in 3.03 seconds.
- Explicit cache-only/offline integration plus e2e — 37 passed with 91 warnings in 20.53 seconds.
- Combined production coverage — 641 passed, 8 explicit/platform skips, and 273 warnings; 91%
  across 2,833 statements with 245 missed in 28.27 seconds.
- Ordinary deterministic script coverage — 56 passed and 2 opt-in skips; 57% combined (demo 71%,
  benchmark 46%, clean verifier 50%). Separate real-process runs measured benchmark 76%, invoked
  demo 74%, and clean verifier 55%; subprocess coverage was not combined into an inflated result.
- Ruff passed; formatting reported 53 files already formatted; strict mypy passed for 18 source
  files and the three typed scripts; `uv lock --check` resolved the unchanged 142-package lock;
  `CodeScope 0.1.0` remained functional; `git diff --check` passed.

Measured fixture benchmark on Linux, Python 3.12.13, 8 logical CPUs, CodeScope 0.1.0, and MCP
1.28.1, with the already prepared default model cache and network disabled:

- Fixture: 4 files, 11 symbols, 16 chunks.
- Indexing: 5,638.879 ms.
- Authoritative status: 23.999 ms median over 5 measured samples.
- Semantic search: 54.975 ms median over 5 samples.
- Exact symbol lookup: 37.858 ms median over 5 samples.
- Similar-code lookup: 56.795 ms median over 5 samples.
- MCP transport startup: 4.666 ms; initialization: 1,035.417 ms.
- MCP tool round trip: 66.611 ms median over 20 calls.
- Fixed demo: 7,717.399 ms; complete benchmark: 23,068.540 ms.
- The demo recommended REUSE, source hashes remained unchanged, the duplicate was avoided, and all
  benchmark runtime/workspace cleanup checks passed. These values are small-fixture,
  environment-specific observations, not scale, quality, percentile, or service-level claims.

Clean candidate and package evidence:

- The final successful Linux candidate-clone verifier reached the demo in 45,937.116 ms and
  completed in 47,731.470 ms, excluding model download. It applied all 12 authorized untracked
  Phase 10 files, used a fresh clone-local `.venv`, a validated
  external uv package cache, a separately prepared external model cache, temporary user state,
  offline model flags, all four MCP tools, REUSE, exact source hashes, and complete clone/runtime
  cleanup. A deliberately empty uv-cache run first reached the fixed 300-second timeout and cleaned
  safely; the documented verifier now reuses the validated package cache rather than private
  environment state.
- `uv build` produced `codescope-0.1.0.tar.gz` and `codescope-0.1.0-py3-none-any.whl`. The wheel and
  sdist include the unchanged MIT `LICENSE`, expose `License-Expression: MIT`, exclude tests,
  runtime/model/Chroma/security/coverage/temp artifacts, and installed successfully in a fresh
  temporary Python 3.12 environment. Version, root help, serve help, import, and safe missing-config
  failure passed without creating runtime state. The standalone wheel resolves compatible declared
  dependency ranges; `uv sync --locked` remains the exact repository-reproduction path.
- Installed direct dependency and default-model license metadata was inventoried factually in
  `docs/SECURITY.md`; no legal conclusion is claimed.

Phase 10 security review:

- Codex Security capability preflights returned `ready` for both the repository and working-tree
  diff profiles. The repository scan ranked 82 source-like rows, selected 25 active runtime/config
  files, manually added the preflight skill and two MCP examples, and closed all 28 full-file
  receipts plus 12 high-impact boundary rows. No candidate or reportable finding survived.
- One delegated MCP/storage review was blocked by the external content-policy classifier before it
  produced a finding or receipt. Two longer repository workers and the diff worker were stopped at
  the bounded review window. They were not retried or described as successful plugin reviews; the
  parent completed every exact worklist row and the sealed reports record these limitations.
- The Phase 10 working-tree diff scan reviewed `pyproject.toml`, both new release scripts, and the
  three direct release/security test files. All six receipts and all three changed security
  surfaces closed with no candidate or reportable finding.
- Both canonical scan bundles finalized successfully outside the repository with complete
  coverage and zero findings. Manual source-to-control review agreed: no shell execution,
  attacker-controlled command, candidate path escape, inherited secret/process-injection state,
  network/model download permission, source/path leak, unbounded loop, orphan child process,
  repository-local cache/runtime, dependency drift, or Phase 11 behavior survived review.
- No validated critical, high, medium, or low reportable issue remains. Documented residual risks
  are the same-user filesystem validation-to-use race, explicit initial dependency/model
  acquisition, local stdio allocation/performance limits, and environment-specific timing.

Phase 10 passed its owner review and final clean audit. Phase 11 was not started, Graphify was not
regenerated, `/feedback` was not run, and no release tag was created.

### Phase 11 — Final submission packaging and evidence closure

Work in progress on July 19, 2026, from synchronized `main` commit
`39f85be6f5e876a82d52f487505952b0a9f4ff3b`:

- Re-verified the live OpenAI Build Week Devpost overview, rules, announcements, dates, form
  fields, judging criteria, prizes, authenticated registration, and existing-project inventory.
  Pakistan is present in the reviewed official eligible-country list; the corrected deadline is
  Tuesday, July 21, 2026 at 5:00 PM Pacific Time, equivalent to July 22 at 5:00 AM Pakistan time.
- Recorded the owner's July 19 confirmation of Pakistan residence, age-of-majority eligibility,
  no exclusion or conflict, original work and compliant third-party use, rules/terms agreement,
  Individual submitter type, and solo-team status. No legal conclusion is inferred.
- Added an original CodeScope cover and architecture diagram plus four privacy-safe screenshots
  based on observed CLI, real MCP stdio discovery, and deterministic demo output. The temporary
  fixture, runtime, browser page, browser metadata, and capture server were removed.
- Added the owner-review submission draft, three judge-testing routes, video script, screenshot
  provenance/privacy record, and final release/submission checklist. The draft is explicitly not
  submitted and records the remaining external-write gates; its narrative-personalization markers
  were subsequently replaced with the owner's supplied wording.
- Refined the README into a judge landing page with the verified small-fixture result, problem,
  solution, differentiators, architecture, workflow, measured evidence, and direct judge path.
- Updated the living compliance and Codex handoff records without marking the release, video,
  `/feedback`, Devpost project, or submission complete.
- Received the owner's first-person submission narrative and exact owner-voice confirmation. Applied
  the supplied motivation, personal relevance, Codex/GPT-5.6 account, accomplishment, lesson,
  closing, and tagline to `devpost-submission.md`; no wording was invented or attributed to the
  owner without confirmation.

Phase 11 files currently added:

- `assets/submission/architecture.svg`
- `assets/submission/architecture.png`
- `assets/submission/cover.png`
- `assets/submission/screenshot-cli.png`
- `assets/submission/screenshot-mcp.png`
- `assets/submission/screenshot-preflight.png`
- `assets/submission/screenshot-demo-result.png`
- `devpost-submission.md`
- `docs/JUDGE_TESTING.md`
- `docs/VIDEO_SCRIPT.md`
- `docs/SCREENSHOT_PLAN.md`
- `docs/FINAL_RELEASE_CHECKLIST.md`

Phase 11 files currently modified:

- `README.md`
- `BUILD_WEEK_CHANGELOG.md`
- `docs/.CHAT_MEMORY.md`
- `docs/HACKATHON_COMPLIANCE.md`
- `docs/CODEX_HANDOFF.md`

Observed Phase 11 candidate validation so far:

- Unit suite — 485 passed with 119 installed-Chroma deprecation warnings in 10.93 seconds.
- Ordinary integration suite — 4 passed, 5 explicit real-model tests skipped, and 38 warnings in
  4.76 seconds.
- Security suite — 101 passed, 1 operating-system junction test skipped, and 116 warnings in 7.28
  seconds.
- Ordinary e2e suite — 27 passed and 1 explicit real-model test skipped in 3.17 seconds.
- Release suite — 24 passed and 1 explicit clean-candidate test skipped in 6.67 seconds.
- Explicit offline/cache-only integration plus e2e matrix — 37 passed with 91 warnings in 20.66
  seconds.
- Combined production coverage — 641 passed, 8 explicit/platform skips, and 273 warnings; 91%
  across 2,833 statements with 245 missed in 27.71 seconds.
- Ruff passed; formatting reported 53 files already formatted; strict mypy passed for 18 source
  files and 3 release scripts; `uv lock --check` resolved the unchanged 142-package lock; CLI
  version remained `CodeScope 0.1.0`.
- Both human and JSON real cache-only demos passed. Each reported 4 files, 11 symbols, 16 chunks,
  `validate_email` at `validators.py:6-9`, REUSE, unchanged source, and duplicate avoided.
- All six PNGs are 1600×900, contain no text/EXIF metadata or trailing data, and the architecture
  SVG is well-formed. Local Markdown target validation checked 40 links with no missing target.
- Placeholder, private-path, secret-pattern, prohibited-file, and dependency/production-code diff
  checks found no new Phase 11 leak or executable scope change. One private-path grep match remains
  in the unchanged historical v2 design document and is not part of the Phase 11 patch.

Current Phase 11 gates and blockers:

- The Codex Security capability preflight returned `ready`. Delegated full-file review covered the
  submission docs and architecture assets; direct review covered all raster assets plus the two
  subsequently changed evidence ledgers. One judge-route checksum/control candidate was reproduced
  and fixed in the working tree. The plugin's canonical finalization was unavailable after an
  account-handoff environment removed its cache, so no completed plugin report is claimed.
- Manual post-fix review found no unresolved validated high- or critical-severity issue. The
  remaining model/dependency acquisition trust boundary is an explicitly authorized external
  prerequisite already documented in the Phase 10 threat model.
- The owner has supplied the marked narrative sections, approved the draft tagline, and confirmed
  that the description reflects their own words and experience. Final owner review and staging
  authorization remain separate gates.
- Creating or updating a Devpost project, committing, tagging, pushing, publishing a GitHub
  Release, uploading/finalizing media, and submitting remain separate explicit owner gates.
- The public YouTube URL, `/feedback` Session ID, final release URL/checksums, signed-out public
  repository verification, and live Submitted readback do not exist yet and are not invented.
- The clean-candidate verifier will run after owner review and staging because its exact Phase 10
  untracked-file allowlist intentionally rejects new Phase 11 assets before they enter the staged
  candidate patch. The verifier itself and its security boundary remain unchanged.

Post-fix rerun after hardening the judge checksum/source-execution instructions:

- Unit — 485 passed with 119 warnings in 11.56 seconds.
- Ordinary integration — 4 passed, 5 explicit model skips, 38 warnings in 5.31 seconds.
- Security — 101 passed, 1 operating-system junction skip, 116 warnings in 7.86 seconds.
- Ordinary e2e — 27 passed, 1 explicit model skip in 4.42 seconds.
- Release — 24 passed, 1 explicit clean-candidate skip in 7.28 seconds.
- Offline/cache-only integration plus e2e — 37 passed, 91 warnings in 25.59 seconds.
- Combined production coverage — 641 passed, 8 explicit/platform skips, 273 warnings; 91%
  (2,833 statements, 245 missed) in 30.38 seconds.
- Ruff, formatting, strict source/script mypy, lock check, CLI version, link checks, XML validation,
  diff checks, privacy scans, and prohibited-artifact scans passed again.

Staged-candidate audit on July 19, 2026:

- Staged exactly 18 Phase 11 evidence files: five modified evidence documents, six new submission
  documents, and seven original submission assets. No dependency, production-code, Graphify,
  runtime, model cache, Chroma, coverage, temporary, or build file was staged.
- Aggregate ordinary unit, integration, security, e2e, and release tests passed: 641 passed, 8
  explicit/platform skips, 273 warnings, 23.30 seconds. The explicit offline cache-only
  integration/e2e matrix passed 37 tests with 91 warnings in 23.49 seconds. The dedicated security
  suite passed 101 tests with one operating-system junction skip and 116 warnings in 6.05 seconds.
- Ruff, formatting, strict source and release-script mypy, `uv lock --check`, CLI version, staged
  whitespace/scope/privacy checks, SVG validation, PNG structural-chunk audit, and a temporary
  wheel/sdist build plus MIT-license audit passed.
- The initial real clean-candidate verifier attempt stopped before candidate-patch application. At
  that attempted run, the binary-inclusive patch was 2,839,881 bytes: below the verifier's 16 MiB
  candidate-patch ceiling but above its generic 2 MiB subprocess-output cap.
- The owner authorized a narrow release-tool correction. `SubprocessRunner.run()` retains the generic
  2 MiB cap; only the hard-coded `git diff --binary --no-ext-diff HEAD --` candidate-patch capture
  now uses the existing 16 MiB patch cap and rejects every other command. Focused regression coverage
  passed 13 tests with one explicit opt-in skip in 5.95 seconds, including real Git binary patches
  above 2 MiB/below 16 MiB, above 16 MiB, ordinary output above 2 MiB, non-candidate commands, and
  existing small-candidate materialization.
- The real clean-candidate verifier then passed. It applied the staged patch to an isolated clone,
  passed locked sync, CLI, fixture index/status/search, MCP tool listing, the REUSE demo, reset, and
  source-immutability checks; clone/runtime cleanup completed. Observed timings were 510.832 ms clone,
  415.021 ms dependency sync, 54,459.702 ms setup-to-demo, and 57,177.122 ms total.

## July 22, 2026 — Parser native-stability remediation (uncommitted)

A final-release parser defect was reproduced while parsing `src/codescope/chunker.py` with the
previous resolved `tree-sitter` 0.26.0 together with `tree-sitter-python` 0.25.0. The native
binding produced corrupted node line metadata and then terminated the interpreter.

- Pinned `tree-sitter` to `0.25.2`, matching the installed `tree-sitter-python` 0.25.0 grammar
  release, and regenerated only the corresponding lockfile entries.
- Retained the parsed Tree through symbol traversal and added defensive identifier byte-range
  validation without changing extracted symbol semantics.
- Added parser coverage for direct, decorated, class, static, and async methods; repeated parser
  reuse; every `src/codescope` Python module; existing fixture files; invalid identifier ranges; and
  candidate-index preservation after an injected parser-boundary failure.
- `uv sync --locked` installed `tree-sitter` 0.25.2 and `tree-sitter-python` 0.25.0.
- Focused parser tests passed: 44 passed.
- Candidate-index rollback regression passed: 1 passed, 27 deselected (seven installed-Chroma
  deprecation warnings).
- Aggregate unit, integration, security, e2e, and release suites passed: 492 passed; 4 passed and
  5 explicit model skips; 102 passed and one operating-system junction skip; 27 passed and one
  explicit model skip; and 28 passed with one explicit clean-candidate skip.
- Explicit cache-only offline integration and e2e validation passed: 37 passed with 91
  installed-Chroma deprecation warnings.
- Ruff, formatting, strict source/script mypy, lock validation, CLI version, and `git diff --check`
  passed.
- The clean-candidate verifier passed with tracked-patch application, all four MCP tools, REUSE,
  unchanged source, and clone/runtime cleanup. Timings: 491.227 ms clone, 314.736 ms dependency
  sync, 47,584.966 ms setup-to-demo, and 49,774.695 ms total.
- No commit, push, tag, release, Devpost change, video upload, or `/feedback` action occurred.
- The attempted local `codex review --uncommitted` did not produce findings and was stopped with
  only its spawned read-only stdio children after it remained stuck; it is not recorded as a
  completed review.

## July 22, 2026 — supplied-video and demo-alignment audit (uncommitted)

- Verified the owner-supplied public YouTube link in a real signed-out browser. The page loaded
  without sign-in and displayed the title `CODEX HACKATHON CODESCOPE PLUGIN short interview` and a
  duration of 5:47.
- The duration exceeds the required sub-three-minute limit. The recording is not a final submission
  asset and must not be added to Devpost. Closed captions were unavailable, so required narration
  coverage was not verified.
- The recording references a routing-ownership comparison, but searches found no committed
  `RoutingPolicy`, `ResponseSla`, multi-route broadcaster, keyword router, or eight-test fixture.
  The reproducible repository and judge route remain the email-validation REUSE demo.
- Updated release and submission evidence to distinguish the two demos and record the replacement
  requirement. No commit, push, video upload, Devpost update, `/feedback`, or release action
  occurred.
- A full-patch clean-candidate verifier applied the tracked patch and passed locked setup,
  CLI, fixture index/status/search, four MCP tools, REUSE demo, reset, source equality, and cleanup.
  Observed timings: 516.993 ms clone, 415.546 ms dependency sync, 60,855.219 ms setup to demo, and
  63,586.124 ms total.

Final local rerun before owner-controlled release actions:

- At `2026-07-22T01:01:40+05:00`, live Devpost data still reported OpenAI Build Week as
  `submissions_open`, with the official deadline unchanged at `2026-07-22T00:00:00Z` (05:00 PKT).
  The account remained registered, no CodeScope project existed, and the form fields, Developer
  Tools category, four judging criteria, and Pakistan eligibility still matched the draft.
- Combined ordinary production coverage passed 653 tests with 8 documented explicit/platform
  skips and 280 installed-dependency warnings; coverage remained 91% (2,838 statements, 245
  missed) in 32.53 seconds.
- Human and JSON offline demos again reported 4 files, 11 symbols, 16 chunks,
  `validators.py:6-9`, `validate_email`, REUSE, unchanged source, and duplicate avoided.
- A temporary wheel/sdist audit passed: the wheel contained the project MIT license and
  `License-Expression: MIT`; the sdist contained the license; and wheel metadata preserved the
  exact Tree-sitter compatibility pins. No package artifact was written inside the repository.
- The final staged-scope/privacy/artifact audit still found 20 staged Phase 11/release-verifier
  files, zero prohibited staged artifacts, zero private-path or secret-pattern matches, 37 valid
  local Markdown links, a safe well-formed architecture SVG, and six metadata-free 1600x900 PNGs
  with no trailing data.
