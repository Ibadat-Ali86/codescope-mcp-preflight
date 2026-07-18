# CodeScope Architecture

CodeScope is a local-first Python developer tool that turns an explicitly selected repository into
read-only evidence for REUSE, EXTEND, or CREATE decisions. The MVP has no remote service or code
execution path.

## Data flow

```text
Repository
  -> secure discovery
  -> Tree-sitter parser and immutable symbols
  -> symbol-aware, model-budgeted chunker
  -> local cache-only embeddings
  -> local Chroma collection + atomic JSON metadata
  -> QueryEngine
  -> CLI / MCP stdio
  -> CodeScope preflight skill
  -> REUSE / EXTEND / CREATE decision
```

Indexing and querying are separate lifecycles. Indexing is the only normal workflow that reads
repository source. Queries use persisted source-only chunks and metadata; symbol lookup and status
do not load the embedding model.

## Components

### Configuration — `config.py`

`load_config()` reads binary TOML with Python 3.12 `tomllib`, resolves configuration paths relative
to the TOML file, and returns frozen Pydantic models. `AppConfig.with_index_root()` creates a new
validated configuration for a CLI override without mutating nested state.

### Path guard — `utils/path_guard.py`

Central path functions validate repository roots, config files, runtime directories, source files,
and reset targets. Containment is checked after resolution, never by string prefix. Link policy is
operation-specific. Validation-to-use races are reduced but cannot be eliminated portably.

### Indexer — `indexer.py`

`RepositoryScanner` performs deterministic `.py`/`.pyi` discovery under the configured root. It
combines immutable hard exclusions, configured exclusions, and the root `.gitignore`; root ignore
negation cannot re-enable mandatory exclusions. Files are read through bounded descriptors with
regular-file, binary, UTF-8, size, and change checks.

`RepositoryIndexer` orchestrates parse, chunk, embed, and storage batches. A rebuild is created in a
restricted sibling directory, verified, then promoted. Tested failure paths preserve or restore the
previous live index. Status reconciles Chroma and metadata rather than trusting file existence.

### Parser — `parser.py`

`CodeParser.parse()` is a filesystem-free bytes-in/symbols-out boundary. One Tree-sitter Python
parser is reused. It extracts top-level functions, async functions, classes, and direct methods,
including decorator-aware ranges, normalized signatures, docstrings, qualified names, and
one-based inclusive line metadata.

### Chunker — `chunker.py`

`CodeChunker` receives decoded source, parser symbols, and an injected exact wordpiece tokenizer.
Top-level symbols and methods own their bodies; a class owns only gaps not owned by direct methods;
module fallback owns meaningful remaining lines. Oversized logical regions split on source lines or
tokenizer character offsets with same-owner overlap. Stored text remains exact source. The complete
transient embedding context, including file/symbol/signature metadata, must fit the configured
model budget. SHA-256 content hashes and canonical-payload IDs are deterministic.

### Embedder — `embedder.py`

`LocalEmbedder` lazily owns one Sentence Transformer and its fast tokenizer adapter. Normal use is
cache-only and offline; model download requires an explicit indexing permission. It validates
configured CPU/CUDA policy and finite normalized `float32` output. No vector is logged.

### Storage — `storage.py` and `utils/json_io.py`

`ChromaStorage` uses a local telemetry-disabled persistent client and a cosine collection with
caller-provided embeddings. Documents contain source chunks; scalar metadata preserves public
traceability. Queries never return stored embeddings. `symbols.json` and `index_meta.json` use
fixed names, bounded reads, deterministic JSON, same-directory temporary files, fsync, and atomic
replacement.

### Query engine — `engine.py`

`QueryEngine` validates public queries and limits, revalidates index status, embeds semantic or
similar-code input cache-only, queries Chroma, and returns frozen public models. Relevance is
clamped `1 - cosine_distance`. Tie-breaking and symbol ranking are deterministic. Snippets are
bounded source-only evidence. Similarity never proves semantic equivalence.

### CLI — `cli.py`

The Typer/Rich CLI exposes exactly `version`, `index`, `status`, `search`, `serve`, and `reset`.
Help and version are lazy. Human output neutralizes terminal controls; JSON is deterministic and
ASCII-escaped. Reset validates and deletes only the exact configured runtime. Search does not
authorize model download.

### MCP server — `server.py`

FastMCP exposes exactly four read-only tools over local stdio. Import and server construction do
not load config, scan source, open Chroma, or load a model. One query engine is created lazily on
the first tool call. Protocol arguments are validated without reflecting attacker values. Success
and expected failure objects are structured under `result`; unexpected failures receive a fixed
`QUERY_FAILED` response. Stdout is protocol-only.

### Preflight skill

`.agents/skills/codescope-preflight/SKILL.md` instructs Codex to inventory first, gather behavioral,
exact-symbol, and similar-code evidence, compare ownership and differences, then choose exactly one
of REUSE, EXTEND, or CREATE before editing. Returned source is explicitly untrusted data.

### Fixed demo — `scripts/demo.py`

The demo copies the committed sample into a temporary workspace, builds an offline cache-only
index, starts the real stdio server, calls all four tools, validates the canonical task and source
hashes, and emits source-free human or JSON evidence. REUSE requires evidence convergence; any
missing/conflicting evidence becomes `REVIEW_REQUIRED`.

### Phase 10 release tooling

`scripts/benchmark.py` measures the existing fixture workflow without changing product behavior.
`scripts/verify_clean_setup.py` clones the current candidate, applies only its tracked patch and
authorized untracked files, creates a fresh virtual environment, runs the CLI/MCP/demo acceptance
path, proves the source repository unchanged, and removes temporary state.

## Data and trust boundaries

```text
Untrusted repository bytes
        |
        v  [resolved path + bounded descriptor]
Parser -> Symbol/Chunk models -> local embedding model -> local Chroma/JSON
                                                       |
                                                       v
Agent query -> validated QueryEngine -> bounded public evidence -> coding agent
                                                       ^
                                                       |
                                      local stdio MCP trust boundary
```

- Repository contents can influence source evidence, never executable control flow.
- Absolute filesystem paths remain internal; public file fields are project-relative POSIX paths.
- Model and dependency preparation cross a supply-chain/network boundary; normal use does not.
- `.codescope` contains sensitive derived repository data and must remain local and ignored.
- The agent is responsible for inspecting evidence; CodeScope does not make an authoritative
  equivalence proof.

## Deliberate MVP limits

Python is the only language. Only the root `.gitignore` is interpreted. There is no file watcher,
dashboard, remote API, authentication, cloud storage, incremental index update, or deployment.
Those are product changes, not Phase 10 release hardening.
