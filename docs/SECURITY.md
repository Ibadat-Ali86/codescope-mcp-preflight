# CodeScope Security Model

CodeScope is a local-first developer tool. It indexes source code chosen by the developer, stores
embeddings and metadata locally, and exposes read-only repository evidence over MCP stdio. This
document describes implemented safeguards and residual limits; it is not a formal compliance or
penetration-test certification.

## Assets and trust boundaries

- **Developer source code:** sensitive, untrusted input. CodeScope reads it but never executes it.
- **Configured repository root:** the filesystem boundary for discovery and file reads.
- **External model cache:** prepared separately from the repository. Normal model use is offline and
  cache-only.
- **Local Chroma runtime:** generated `.codescope` state containing source chunks, vectors, and
  metadata. It is local sensitive data and is excluded from Git and package artifacts.
- **MCP stdio boundary:** protocol frames use stdout; diagnostics use stderr. The local MCP client and
  server run with the invoking user's privileges.
- **Coding-agent boundary:** indexed comments, strings, docstrings, and snippets are untrusted
  evidence, never instructions.
- **Reset/delete boundary:** only the exact configured runtime strictly below the validated
  repository root may be removed.
- **Supply-chain boundary:** Python wheels and the embedding model are external artifacts. Their
  provenance and licenses must be reviewed before preparation or upgrade.

There is no remote listener, authentication layer, multi-user isolation, or cloud storage in the
MVP. The stdio server is intended for a trusted local developer session.

## Threat analysis

Severity is contextual to this local, single-user MVP. A local denial of service or disclosure can
still be important because repositories may contain proprietary code and secrets.

| Threat | Asset and attack surface | Implemented mitigation | Tests/evidence | Residual limitation | Severity rationale |
|---|---|---|---|---|---|
| Repository-root traversal | Source confidentiality; configured roots and candidate file names | Resolve the trusted root and candidate, require resolved containment with `Path.is_relative_to`, reject lexical traversal, and require regular files | `tests/security/test_path_safety.py`; `test_safe_resolve_traversal_spelling_is_rejected` | Portable validation cannot stop the same user changing the filesystem after validation | High if reachable because it could disclose arbitrary local files; current boundary rejects tested traversal forms |
| Symlink or junction escape | Source confidentiality and reset integrity | Default scanning rejects links; explicitly followed links must resolve inside the root; config/runtime components reject links and junctions | `tests/security/test_path_safety.py`; `test_safe_resolve_external_symlink_is_rejected_even_when_enabled`; `tests/security/test_phase5_safety.py`; Phase 10 candidate-link tests | Link state can change after validation; junction creation is platform-dependent | High potential impact, reduced by resolved containment and operation-specific policies |
| Oversized files or repositories | Local availability and memory | Positive file-size config, bounded directory entries, descriptor reads capped at configured size plus one detection byte, bounded embedding batches, bounded metadata and public results | `tests/security/test_phase5_safety.py`; `test_directory_entry_bound_precedes_full_iterator_materialization`; `test_read_race_is_bounded_to_maximum_plus_detection_byte` | A repository within all configured bounds can still consume substantial CPU and disk | Medium local availability risk; no remote unauthenticated surface |
| Malformed syntax trees | Index correctness and availability | Tree-sitter extraction accepts only structurally reliable symbols, returns bounded partial recovery, and safely translates binding failures | `tests/unit/test_parser.py`; malformed fixture tests | Tree-sitter recovery may omit unreliable symbols rather than infer intent | Medium because incorrect evidence can affect reuse decisions; fail-closed extraction limits false structure |
| Source or secret leakage into logs | Source confidentiality | Production logs use fixed messages and safe metadata only; no source, vectors, full queries, absolute paths, or traceback details are logged publicly | `tests/security/test_phase4_safety.py`; `test_storage_errors_and_logs_exclude_source_vector_and_absolute_path`; MCP/CLI leakage tests | A debugger or same-user process can inspect local memory and files | High for proprietary repositories; application-controlled output is tested nonreflective |
| Unsafe reset configuration | Repository and local-file integrity | Exact configured target equality, strict-below-root containment, link rejection, confirmation unless `--yes`, and immediate revalidation before deletion | `tests/security/test_cli_safety.py`; `test_reset_deletes_only_exact_runtime_and_preserves_repository_siblings`; reset-target path tests | The same user can race filesystem state between validation and use | Critical potential impact, but destructive scope is narrow and tested; no arbitrary target parameter is exposed through MCP |
| MCP stdout corruption | Protocol integrity and confidentiality | Serving reserves stdout for JSON-RPC; logs/errors go to stderr; malformed calls return structured errors; terminal controls remain JSON-escaped | `tests/security/test_mcp_safety.py`; `test_newlines_and_bidi_controls_cannot_break_json_rpc_framing`; `test_direct_tool_calls_never_write_to_stdout` | Third-party SDK behavior remains part of the trusted dependency boundary | High because framing corruption can break or confuse the agent session |
| Prompt injection in repository text | Agent decision integrity | Server and skill instructions label snippets as untrusted data; CodeScope never executes indexed source; preflight requires behavior/ownership comparison | `test_malicious_comments_and_strings_remain_unexecuted_data`; `test_skill_frontmatter_and_fail_closed_workflow_contract` | A coding agent can still make a poor judgment if it ignores instructions | High decision-quality risk; technical execution is prevented, but human/agent judgment remains necessary |
| Similarity treated as equivalence | Correctness and duplication-prevention decision | Similarity is one evidence channel; no universal threshold; fixed demo requires inventory, semantic, exact-symbol, similar-code, canonical-fixture, unchanged-source, and duplicate-absence convergence | `tests/e2e/test_duplication_prevention.py`; nonconverging and noncanonical tests | Semantic similarity cannot prove behavior, policy, or ownership | High product-integrity risk; final REUSE/EXTEND/CREATE decision remains an agent responsibility |
| Dependency/model supply chain | Source confidentiality, code execution, and reproducibility | Locked Python dependencies, MCP `<2` bound, explicit one-time model download permission, cache-only normal use, offline validation, external cache, and license inventory | `uv lock --check`; offline real-model matrix; package audit | Initial wheel/model acquisition trusts configured package/model hosts and local cache integrity | High because imported wheels and model loaders execute code; review and explicit preparation are required |
| Absolute-path leakage | Developer privacy | Public Pydantic paths are project-relative POSIX values; error text is fixed; benchmark/clean-setup output excludes repository, cache, home, and temp paths | model path tests; CLI/MCP safety suites; `test_report_json_is_parseable_source_free_and_path_private`; Phase 10 privacy audit | Local debug tooling can observe process paths | Medium privacy risk; public application output is constrained |
| Terminal-control or bidi manipulation | Operator decision integrity | Human CLI/demo/release output neutralizes control and bidi characters; JSON uses ASCII escapes and remains parseable | `test_repository_filename_cannot_forge_human_terminal_metadata_but_json_roundtrips`; `test_terminal_controls_are_neutralized_in_human_release_output` | Consumers that render raw source snippets must still treat them as untrusted | Medium because output forgery can mislead a developer even without code execution |
| Malformed persisted metadata | Index integrity and availability | Fixed metadata names, bounded descriptor reads, regular-file/no-follow checks, JSON/model validation, count/fingerprint reconciliation, and atomic replacement | storage metadata tests; `test_oversized_metadata_and_metadata_read_race_are_rejected_safely`; index status mismatch tests | A same-user process can corrupt local runtime state; CodeScope then fails safely and requires rebuild/reset | Medium; corruption blocks queries rather than silently trusting malformed state |
| Stale or partial index replacement | Query correctness and availability | Build into restricted sibling state, verify before promotion, rollback prior live state across tested rename/cleanup failures, and revalidate status per query | rollback matrix in `tests/security/test_phase5_safety.py`; `test_symbol_lookup_detects_index_replacement_count_mismatch` | Simultaneous catastrophic filesystem failures cannot be made transactional portably | High product-integrity risk; replacement/rollback paths are extensively tested |
| Demo/MCP subprocess leakage | Local availability, model cache, and temp data | Async context managers, explicit timeouts, temporary directories, stdio process closure, and Phase 10 process-group termination for clean-setup commands | Phase 9 real e2e cleanup; `test_subprocess_timeout_terminates_descendant_before_it_can_write`; real clean-clone report | Windows process-tree termination is less comprehensive than POSIX session-group termination | Medium local availability/privacy risk; all observed Linux child processes exited and temporary state was removed |
| False REUSE recommendation | Source correctness and product trust | Fixed scenario literals, canonical source-tree trust anchor, before/after hashes, four evidence channels, duplicate scan, and fail-closed `REVIEW_REQUIRED` | all Phase 9 convergence/failure tests | The fixed demo proves one scenario only; real repositories require independent review | High because an incorrect decision can preserve or introduce defects; evidence is intentionally conservative |
| Same-user validation-to-use race | Source confidentiality and destructive integrity | Resolve immediately before read/delete, descriptor before/after checks where practical, no long-lived validated file cache, and documented race boundaries | read-race and reset-revalidation security tests | Portable path APIs cannot eliminate a malicious same-user or privileged process changing state after validation | Accepted limitation: meaningful only when another process already has comparable local authority |

## Phase 10 release-tool security

The benchmark and clean-setup verifier are import-safe and do not run on import. They accept only
bounded numeric options, use fixed fixture/query inputs, emit source-free JSON, and never print
absolute paths. The clean verifier:

1. requires `CODESCOPE_RUN_CLEAN_SETUP=1`;
2. clones the current `main` `HEAD` using `git clone --no-local`;
3. applies the tracked `HEAD` diff and copies only an exact untracked-file allowlist;
4. rejects unsafe, link-backed, oversized, or unexpected untracked files;
5. creates a fresh clone-local virtual environment with `uv sync --locked`;
6. passes a minimized child environment with offline model flags and without inherited secrets,
   Python injection variables, or the source virtual environment;
7. bounds subprocess time and output, terminates POSIX process groups on timeout, and uses no shell;
8. verifies source hashes and source-repository Git state before and after;
9. resets only the candidate runtime and removes the temporary clone.

The benchmark similarly uses an isolated temporary fixture/runtime, cache-only model access,
bounded iterations, monotonic timing, real MCP stdio calls, and the fixed demo. Neither tool writes
raw benchmark output to the repository.

## Security test matrix

| Area | Representative automated coverage |
|---|---|
| Paths, traversal, files, links, reset targets | `tests/security/test_path_safety.py`, `tests/security/test_cli_safety.py` |
| Storage, telemetry, metadata, vectors | `tests/security/test_phase4_safety.py` |
| Discovery, read bounds, replacement, rollback | `tests/security/test_phase5_safety.py` |
| MCP protocol, input bounds, untrusted source | `tests/security/test_mcp_safety.py` |
| Phase 9 decision convergence and fixture containment | `tests/e2e/test_duplication_prevention.py` |
| Benchmark bounds, privacy, import safety | `tests/release/test_benchmark.py`, `tests/security/test_phase10_safety.py` |
| Candidate patch, allowlist, environment, timeout cleanup | `tests/release/test_clean_setup.py`, `tests/security/test_phase10_safety.py` |
| Package/runtime artifact leakage | Phase 10 sdist/wheel member audit and final filesystem/privacy audit |

## Dependency and license inventory

The repository itself remains MIT licensed. Installed direct versions are locked in `uv.lock`.
License identifiers below are factual metadata, not legal advice.

| Component | Purpose | Installed license evidence |
|---|---|---|
| Chroma 1.5.9 | Local vector persistence | Apache-2.0 in the installed wheel and [upstream repository](https://github.com/chroma-core/chroma) |
| Loguru 0.7.3 | Application diagnostics to stderr | MIT classifier in installed distribution metadata and [upstream project](https://github.com/Delgan/loguru) |
| MCP Python SDK 1.28.1 | Stable-v1 stdio server/client | MIT in installed metadata and [official SDK](https://github.com/modelcontextprotocol/python-sdk) |
| pathspec 1.1.1 | Root `.gitignore` matching | MPL-2.0 license file in the installed wheel |
| Pydantic 2.13.4 | Immutable validation models | MIT license expression in installed metadata |
| Rich 15.0.0 | Safe human CLI rendering | MIT license expression in installed metadata |
| Sentence Transformers 5.6.0 | Local embedding lifecycle | Apache-2.0 license expression in installed metadata |
| Tree-sitter 0.25.2 | Parser runtime | License file in the installed distribution; no license field is declared in its installed metadata; see [upstream](https://github.com/tree-sitter/tree-sitter) |
| Tree-sitter Python 0.25.0 | Python grammar | MIT license file in installed wheel and [grammar repository](https://github.com/tree-sitter/tree-sitter-python) |
| Typer 0.26.8 | CLI command surface | MIT license expression in installed metadata |
| all-MiniLM-L6-v2 | Default embedding model | Apache-2.0 on the [official model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |

Notable transitive runtime components include PyTorch (compound SPDX expression recorded in the
installed metadata), Transformers (Apache 2.0 metadata), Tokenizers (Apache classifier), and
Hugging Face Hub (Apache-2.0 metadata). `uv tree` is the authoritative installed dependency-tree
evidence for this candidate. No dependency or locked version changed in Phase 10; the current
uncommitted parser remediation pins Tree-sitter 0.25.2 for grammar compatibility.

## Reporting and operational guidance

- Do not commit `.codescope`, model files, Chroma data, raw security reports, coverage data, or
  benchmark output.
- Use `codescope reset --yes` only after reviewing `codescope.toml`; never replace it with a broad
  shell deletion example.
- Treat any unexpected absolute path, source snippet, embedding, secret, or traceback in public
  output as a security defect.
- Rebuild an invalid index rather than attempting to hand-edit Chroma or metadata files.
- Future remote or multi-user operation would require a new threat model, authentication,
  authorization, tenant isolation, transport security, rate limits, and request-size controls.
