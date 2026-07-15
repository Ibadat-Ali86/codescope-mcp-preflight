# Graph Report - codescope-mcp-preflight  (2026-07-15)

## Corpus Check
- 46 files · ~41,219 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 749 nodes · 1054 edges · 83 communities (79 shown, 4 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 104 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7e283cd5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]

## God Nodes (most connected - your core abstractions)
1. `load_config()` - 27 edges
2. `CodeParser` - 27 edges
3. `CodeScopeError` - 20 edges
4. `_write_config()` - 20 edges
5. `safe_resolve()` - 19 edges
6. `CodeScope — Complete Technical Specification v2.0` - 19 edges
7. `IndexStatus` - 16 edges
8. `validate_reset_target()` - 15 edges
9. `20. Implementation Phases and Gates` - 13 edges
10. `Symbol` - 12 edges

## Surprising Connections (you probably didn't know these)
- `test_code_chunk_negative_index_is_rejected()` --calls--> `CodeChunk`  [INFERRED]
  tests/unit/test_models.py → src/codescope/models.py
- `test_search_result_invalid_relevance_score_is_rejected()` --calls--> `SearchResult`  [INFERRED]
  tests/unit/test_models.py → src/codescope/models.py
- `test_error_response_false_error_flag_is_rejected()` --calls--> `ErrorResponse`  [INFERRED]
  tests/unit/test_models.py → src/codescope/models.py
- `test_parser_binding_failure_does_not_leak_source_or_path()` --calls--> `CodeParser`  [INFERRED]
  tests/unit/test_parser.py → src/codescope/parser.py
- `test_parser_decorated_ranges_include_decorators_without_duplicate_symbols()` --calls--> `CodeParser`  [INFERRED]
  tests/unit/test_parser.py → src/codescope/parser.py

## Import Cycles
- None detected.

## Communities (83 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.15
Nodes (8): Require a project-relative POSIX file path., A result from exact or partial symbol lookup., Require a project-relative POSIX file path., Reject empty required symbol-result text., Prevent absolute host paths in public index status., Require a project-relative POSIX file path., SymbolResult, _validate_public_path()

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (49): 20. Implementation Phases and Gates, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance (+41 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (46): NoReturn, OSError, RuntimeError, _candidate_beneath_root(), _is_relative_to(), Path, _raise_invalid_path(), Central security-sensitive filesystem path validation. (+38 more)

### Community 3 - "Community 3"
Cohesion: 0.23
Nodes (15): _chunk_data(), Any, Tests for immutable public CodeScope models., _search_data(), _symbol_data(), _symbol_result_data(), test_code_chunk_negative_index_is_rejected(), test_public_model_assignment_is_frozen() (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.24
Nodes (27): load_config(), Load and validate a CodeScope TOML configuration file.      Args:         config, MonkeyPatch, Path, Tests for immutable validated application configuration., _replace(), test_app_config_is_frozen_and_collections_are_tuples(), test_load_config_absent_storage_path_is_accepted() (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (17): Exception, CodeScopeError, IndexNotFoundError, InvalidLimitError, InvalidPathError, InvalidQueryError, QueryFailedError, Stable domain exceptions for CodeScope. (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (18): Build Week implementation, CodeScope Build Week Changelog, Phase 0 — Repository foundation, Phase 1 — Configuration, models, and path security, Phase 2 — Tree-sitter Python symbol extraction, Pre-existing work, CodeScope Hackathon Compliance, Built During OpenAI Build Week (+10 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (16): 5.1 High-level architecture, 5.2 Main data flow, 5.3 Architectural boundaries, 5. Architecture, `chunker.py`, `config.py`, `embedder.py`, `engine.py` (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.23
Nodes (14): AppConfig, EmbeddingsConfig, _FrozenConfigModel, Immutable validated application configuration., Syntactic embedding-model configuration for a future phase., Local runtime storage location and collection name., Default and maximum public query limits., Complete immutable CodeScope application configuration. (+6 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (13): InvalidLanguageError, Raised when a language or extension is not supported., language_from_extension(), normalize_language(), SupportedLanguage, Python-only language and extension validation., Normalize a supported language name.      Args:         language: User-provided, Map a canonical supported extension to Python.      Args:         extension: A c (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.14
Nodes (14): 18.1 General rules, 18.2 Unit tests, 18.3 Integration tests, 18.4 Security tests, 18.5 End-to-end test, 18.6 Standard validation commands, 18. Testing Strategy, Chunker (+6 more)

### Community 12 - "Community 12"
Cohesion: 0.14
Nodes (14): 9.1 Architecture — Three Layers of Extension, 9.2 Tier 1 — Install Before Writing Any Code, 9.3 Tier 2 — Install Before Starting Implementation, 9.4 What NOT to Install, 9.5 Complete `~/.codex/config.toml` — Global Developer Config, 9.6 Priority Install Order (Timeline), 9. Codex Plugin & Skill Stack, Codex Security Plugin (Official OpenAI) (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (12): 14. Codex MCP Configuration, 15. Repository Skill: `$codescope-preflight`, 21. `AGENTS.md` Requirements, 22. Session Memory Protocol, 24.1 Required Codex/GPT-5.6 section, 24. README Contract, 26. Devpost Submission Checklist, 29. First Prompt to Run After Supplying This File to Codex (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (13): 27.1 Recommended schedule, 27.2 Pivot rules, 27.3 Stop conditions, 27. Time Management and Pivot Rules, July 13, July 14, July 15, July 16 (+5 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (10): Architecture Boundaries, CodeScope Agent Instructions, Current MVP Scope, Development Rules, Documentation MCP Rules, Environment, graphify, Purpose (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (11): 0:00–0:20 — Problem, 0:20–0:40 — Solution, 0:40–1:05 — Without CodeScope, 1:05–2:05 — With CodeScope, 25.1 Wow moment, 25.2 Three-minute video storyboard, 25.3 Screenshot list, 25. Demo Package (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.18
Nodes (11): 3.1 Priority definitions, 3.2 P0 deliverables, 3.3 P1 deliverables, 3.4 P2 deliverables, 3. Scope and Priorities, Agent workflow, CLI, Core indexing (+3 more)

### Community 18 - "Community 18"
Cohesion: 0.18
Nodes (11): 6. Implementation Roadmap, Phase 0.5: Codex Environment Setup (Day 1 — ~30 minutes), Phase 0: Project Initialization (Day 1 — ~1.5 hours), Phase 1: AST Parser (Day 1–2 — ~4 hours), Phase 2: Embedder + Storage (Day 2 — ~3 hours), Phase 3: Indexer Pipeline (Day 2–3 — ~4 hours), Phase 4: Query Engine (Day 3 — ~3 hours), Phase 5: MCP Server (Day 3–4 — ~4 hours) (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.27
Nodes (8): _immutable_string_tuple(), IndexConfig, Any, SupportedLanguage, Repository indexing boundaries and chunking limits., Normalize the immutable Python-only language allowlist., Validate canonical immutable source extensions., Validate and freeze exclusion entries.

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (12): Blockers, Changed files, CodeScope Session Memory, Exact final validation, Important decisions, Next atomic phase, Phase 1 completed work, Phase 2 changed files (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.20
Nodes (9): 13. Token Efficiency Notes for AI Agents, 15. Agent Chat Storage Protocol — `docs/.CHAT_MEMORY.md`, 2. Technology Stack, 4. Directory Structure, 5. System Instructions — `docs/.SYSTEM_INSTRUCTIONS.md`, 7. `AGENTS.md` — Root-Level Agent Context File, 8. `docs/codex.md` — Codex Integration Reference, CodeScope — Complete Technical Specification v2.0 (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 23 - "Community 23"
Cohesion: 0.25
Nodes (8): 10. Comprehensive Testing Strategy, Phase T1: Unit Tests, Phase T2: Integration Tests, Phase T3: Performance Tests, Phase T4: Security Tests, Phase T5: E2E Demo Test, Test Design Methodology — AAA Pattern (Mandatory), Test Suite Overview

### Community 24 - "Community 24"
Cohesion: 0.25
Nodes (5): Path, Resolve a storage path and reject existing non-directories., Return a newly validated configuration with a different index root.          Rel, Require an existing repository directory., _resolve_config_paths()

### Community 25 - "Community 25"
Cohesion: 0.29
Nodes (7): 10.1 File scanner, 10.2 Path security, 10.3 Python parser, 10.4 Chunking, 10.5 Stable identifiers, 10.6 Full rebuild behavior, 10. Indexing Design

### Community 26 - "Community 26"
Cohesion: 0.29
Nodes (7): 8.1 `Symbol`, 8.2 `CodeChunk`, 8.3 `SearchResult`, 8.4 `SymbolResult`, 8.5 `IndexStatus`, 8.6 `ErrorResponse`, 8. Data Models

### Community 27 - "Community 27"
Cohesion: 0.29
Nodes (4): _non_empty(), Trim and validate the model identifier without loading it., Trim and validate the storage collection name., Trim and validate the server name.

### Community 28 - "Community 28"
Cohesion: 0.33
Nodes (6): 12.1 Engine initialization, 12.2 Semantic search, 12.3 Symbol search, 12.4 Snippet safety, 12.5 Errors, 12. Query Engine Design

### Community 29 - "Community 29"
Cohesion: 0.33
Nodes (6): 13.1 `codescope index [PATH]`, 13.2 `codescope status`, 13.3 `codescope search QUERY`, 13.4 `codescope serve`, 13.5 `codescope reset`, 13. CLI Design

### Community 30 - "Community 30"
Cohesion: 0.33
Nodes (6): 16.1 Python style, 16.2 Function and file size, 16.3 Logging, 16.4 Async policy, 16.5 Dependency policy, 16. Coding Standards

### Community 31 - "Community 31"
Cohesion: 0.33
Nodes (6): 2.1 Problem, 2.2 Target users, 2.3 MVP user story, 2.4 MVP success scenario, 2.5 Non-goals for Build Week, 2. Product Definition

### Community 32 - "Community 32"
Cohesion: 0.33
Nodes (6): 4.1 Required baseline, 4.2 Version rules, 4.3 Initial dependency commands, 4.4 Embedding model constraints, 4.5 Cross-platform policy, 4. Technology Policy

### Community 33 - "Community 33"
Cohesion: 0.33
Nodes (6): 9.1 `search_code`, 9.2 `find_symbol`, 9.3 `find_similar`, 9.4 `list_indexed_files`, 9.5 MCP server instructions, 9. MCP Tool Contracts

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 35 - "Community 35"
Cohesion: 0.33
Nodes (5): main(), CodeScope command-line interface., Run the CodeScope command-line interface., Show the installed CodeScope version., version()

### Community 36 - "Community 36"
Cohesion: 0.40
Nodes (5): 0. Instruction to Codex, CodeScope — Codex Build Master Instructions, Mandatory startup behavior, Never do these things, Required working style

### Community 37 - "Community 37"
Cohesion: 0.40
Nodes (5): 11.1 Embedder, 11.2 Chroma storage, 11.3 Relevance score, 11.4 Metadata files, 11. Embedding and Storage Design

### Community 38 - "Community 38"
Cohesion: 0.40
Nodes (5): 17.1 Critical protections, 17.2 Input bounds, 17.3 Threat model, 17.4 Agent trust boundary, 17. Security Requirements

### Community 39 - "Community 39"
Cohesion: 0.40
Nodes (5): 1.1 Official event facts, 1.2 Build Week evidence, 1.3 Judge-facing product statement, 1.4 Judge-facing differentiation, 1. Hackathon Compliance Contract

### Community 40 - "Community 40"
Cohesion: 0.40
Nodes (5): 28. Final MVP Acceptance Gate, Functionality, Product and judging, Quality, Security

### Community 41 - "Community 41"
Cohesion: 0.40
Nodes (5): 12. Code Optimization Guidelines, Caching Strategy, ChromaDB Query Optimization, Embedding Optimization, Performance Targets

### Community 42 - "Community 42"
Cohesion: 0.40
Nodes (5): 14. Custom Skill Definitions, Skill 1: `$new-mcp-tool`, Skill 2: `$add-language`, Skill 3: `$cs-test`, Skill 4: `$benchmark`

### Community 43 - "Community 43"
Cohesion: 0.40
Nodes (5): 1.1 Problem Statement, 1.2 Goals (Specific & Measurable), 1.3 Scope, 1.4 Success Metrics, 1. Project Overview

### Community 44 - "Community 44"
Cohesion: 0.40
Nodes (5): 3.1 High-Level Architecture, 3.2 MCP Tool Contracts (Full API Reference), 3.3 Data Flow: File → Index → Search Result, 3.4 Project Configuration (`codescope.toml`), 3. Architecture & System Design

### Community 45 - "Community 45"
Cohesion: 0.40
Nodes (5): DevOps & Deployment, Disaster Recovery, Monitoring & Observability, Scalability, Strategic Gaps & Recommendations

### Community 46 - "Community 46"
Cohesion: 0.40
Nodes (3): Self, Require overlap to remain below the chunk budget., Require the default result limit to fit within the maximum.

### Community 47 - "Community 47"
Cohesion: 0.50
Nodes (4): 19.1 Targets, 19.2 Benchmark methodology, 19.3 Claims policy, 19. Performance and Benchmark Policy

### Community 48 - "Community 48"
Cohesion: 0.50
Nodes (4): 23.1 Commit rules, 23.2 Branching, 23.3 Review checklist, 23. Git and Review Protocol

### Community 49 - "Community 49"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 50 - "Community 50"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 51 - "Community 51"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 52 - "Community 52"
Cohesion: 0.50
Nodes (4): Appendix, Change Log, Glossary, References

### Community 53 - "Community 53"
Cohesion: 0.50
Nodes (4): Before You Start — Confirm All 7 Items, Core Identity of This Project, ⚡ Quick Reference for AI Agents, Your First Four Tasks (In Order)

### Community 54 - "Community 54"
Cohesion: 0.50
Nodes (3): Tests for the CodeScope package foundation., The package should expose its initial semantic version., test_package_exposes_expected_version()

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): 11. Security Requirements, Context7 Security Note, Path Traversal Prevention — Concrete Implementation

### Community 65 - "Community 65"
Cohesion: 0.07
Nodes (53): Node, Parser, ParseFailedError, Raised when source parsing cannot complete safely., A named Python source-code entity., Reject an empty docstring when one is supplied., Symbol, _build_python_parser() (+45 more)

### Community 72 - "Community 72"
Cohesion: 0.20
Nodes (13): IndexStatus, Serializable status of the local CodeScope index., Defensively copy and freeze language counts., Serialize immutable language counts as a normal JSON object., _status_data(), test_index_status_languages_blocks_backing_attribute_reassignment(), test_index_status_languages_blocks_item_assignment(), test_index_status_languages_defensively_copies_input() (+5 more)

### Community 73 - "Community 73"
Cohesion: 0.18
Nodes (8): BaseService, outer(), Service parser fixture., Return the display label., Load one service instance., Return a value without exposing the nested helper as a symbol., Coordinate user operations., UserService

### Community 74 - "Community 74"
Cohesion: 0.24
Nodes (8): BaseModel, ErrorResponse, _LineRangeModel, _PublicModel, Self, Immutable public data models for CodeScope., Stable public error response returned by future MCP tools., test_error_response_false_error_flag_is_rejected()

### Community 75 - "Community 75"
Cohesion: 0.20
Nodes (7): authenticate(), AuthService, Authentication parser fixture., Provide authentication operations., Store the expected issuer., Validate a token against the configured issuer., Validate an authentication token asynchronously.

### Community 76 - "Community 76"
Cohesion: 0.29
Nodes (4): Reject empty optional names when supplied., Reject an empty docstring when one is supplied., Reject an empty timestamp when one is supplied., _validate_optional_text()

### Community 77 - "Community 77"
Cohesion: 0.29
Nodes (4): Reject an empty embedding model identifier., Reject empty public error-response fields., Reject empty required symbol text., _validate_required_text()

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (4): CodeChunk, Require a project-relative POSIX file path., Reject empty required chunk text., A traceable Python source chunk prepared for future indexing.

### Community 79 - "Community 79"
Cohesion: 0.33
Nodes (4): A ranked source-code search result., Reject empty required search-result text., Reject empty optional names when supplied., SearchResult

### Community 80 - "Community 80"
Cohesion: 0.33
Nodes (5): Validation parser fixture., Validate a username length., Return whether an email has a simple local and domain shape., validate_email(), validate_username()

### Community 81 - "Community 81"
Cohesion: 0.40
Nodes (5): ErrorCode, Machine-readable error codes exposed by CodeScope., StrEnum, Exception, test_domain_exception_type_has_stable_error_code()

### Community 82 - "Community 82"
Cohesion: 0.50
Nodes (3): Malformed-source parser fixture stored as inert sample data., Remain extractable as a normal control symbol., recovered()

## Knowledge Gaps
- **308 isolated node(s):** `codescope`, `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)`, `Step 1 - Ensure graphify is installed` (+303 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `20. Implementation Phases and Gates` connect `Community 1` to `Community 13`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `CodeScopeError` connect `Community 6` to `Community 65`, `Community 9`, `Community 10`, `Community 19`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Why does `IndexStatus` connect `Community 72` to `Community 0`, `Community 74`, `Community 76`, `Community 77`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `load_config()` (e.g. with `InvalidConfigError` and `validate_config_file()`) actually correct?**
  _`load_config()` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `CodeParser` (e.g. with `ParseFailedError` and `Symbol`) actually correct?**
  _`CodeParser` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `CodeScopeError` (e.g. with `AppConfig` and `EmbeddingsConfig`) actually correct?**
  _`CodeScopeError` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `codescope`, `CodeScope command-line interface.`, `Run the CodeScope command-line interface.` to the rest of the system?**
  _403 weakly-connected nodes found - possible documentation gaps or missing edges._