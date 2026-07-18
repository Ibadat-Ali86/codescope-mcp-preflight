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

On July 18, 2026, the final audit found that the owner had preserved the complete Phase 8 patch in checkpoint commit `5afc0648fb743c943f1fa2e592d8882967708b7c`, followed only by documentation handoff commits. Published history was not rewritten. Phase 8 is complete; these final evidence corrections remain unstaged and uncommitted for owner review. Phase 9 was not started.
