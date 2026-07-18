# CodeScope Duplication-Prevention Evidence

This record separates the fixed scenario from evidence actually observed during Phase 9.

## Before CodeScope preflight

- Task: add email validation before creating a user account.
- Likely naive plan: create a new helper named `is_valid_email`.
- Duplication risk: the repository may already own equivalent validation behavior under another
  name or module.
- Minimal non-executable pseudocode: `def is_valid_email(email: str) -> bool: ...`.
- This is a demonstration scenario only. No duplicate implementation is committed or executed.

## After CodeScope preflight

### Automated deterministic evidence

- The fixed Phase 9 manifest targets `validate_email` in `validators.py` at lines 6–9, matching the
  reviewed fixture directly.
- The injected workflow called, in order: `list_indexed_files`, `search_code`, `find_symbol`, and
  `find_similar`.
- Inventory, behavioral search, exact-symbol metadata, and similar-code evidence converged on the
  expected implementation in the deterministic success case.
- The decision was `REUSE`; it was based on evidence convergence rather than a universal score
  threshold.
- Exact SHA-256 maps before and after the deterministic workflow were equal.
- The source-tree digest matched the reviewed canonical fixture trust anchor; an unchanged but
  noncanonical source tree produces `REVIEW_REQUIRED`.
- No `is_valid_email` implementation was created.
- Failure tests prevented false REUSE for missing index, tool failure, missing symbol, conflicting
  evidence, incorrect line metadata, malformed manifest, unexpected response, child-session
  failure, changed source hashes, and a duplicate-present state.
- Observed focused result: 27 tests passed and the one explicit real-model test skipped because its
  opt-in environment flag was absent.

### Opt-in real-model evidence

- The established `CODESCOPE_RUN_REAL_MODEL=1` e2e path ran with Hugging Face and Transformers
  forced offline: 28 tests passed with 5 installed-Chroma deprecation warnings.
- The isolated real stdio workflow indexed 4 files, 11 symbols, and 16 chunks, then called all four
  tools.
- Semantic evidence found `validate_email` at `validators.py:6-9` with an observed relevance score
  of `0.7134328484535217`.
- Similar-code evidence found the same implementation and location with an observed relevance
  score of `0.7630198001861572`.
- Exact-symbol evidence confirmed the top-level `validate_email` function at the same location.
- The fixed convergence rule recommended `REUSE`; neither score was used as a universal threshold
  or proof of equivalence.
- The human demo completed in an observed 14.72 seconds in this development environment. This is a
  one-run observation, not a benchmark or performance claim.
- The JSON-only output parsed successfully. It contained no source snippet, embedding, protocol
  frame, model-cache path, temporary path, or timestamp.
- Exact source-hash maps were equal before and after, and no `is_valid_email` implementation was
  present. The stdio process closed and the isolated runtime and workspace were removed.

### Manual Codex skill evidence

- Explicit invocation recognized `$codescope-preflight` and completed the sequence
  `list_indexed_files` → `search_code` → `find_symbol` → `find_similar`.
- It emitted the required `CodeScope Preflight` structure, compared behavior, ownership,
  differences, confidence, and uncertainty, recommended `REUSE`, planned to call the existing
  function, required post-change testing and another duplication search, and edited no file.
- After the description was refined using the natural prompt's trigger wording, a fresh natural
  invocation completed `list_indexed_files` first, then `search_code`, `find_similar`, and
  `find_symbol`. It emitted the structured preflight, recommended `REUSE`, recorded uncertainty,
  and edited no file.
- The accepted natural session ran in an isolated temporary Git workspace. Exact fixture hashes
  before and after were equal. Only sanitized tool order and conclusions are recorded here; raw
  transcripts, session identifiers, account data, and local links were deleted with the workspace.
- One earlier natural-session attempt was not counted: its read-only bubblewrap environment failed
  before any tool call or decision. It made no edit. The accepted rerun used the same isolated
  workspace with explicit no-edit instructions and independent source-hash verification.

### Security-review evidence

- Two defects were reproduced in the initial demo boundary: resolving a fixture-root symlink before
  inspection could copy external Python files, and unchanged but noncanonical fixture content could
  still receive `REUSE`. Both required developer control of the protected checkout and were
  nonreportable under attack-path policy, but both were corrected and regression-tested.
- The final path boundary rejects symlink and junction components for the task manifest, fixture
  copying, source hashing, and duplicate checks. A later bypass review also reproduced and closed a
  symlinked-ancestor path in the standalone hash helper.
- Fixed manifest literals defeated the prompt-reflection candidate. A symlinked manifest ancestor
  could not influence the supported scenario, but it was hardened to fail closed for consistent
  path semantics.
- Post-fix full-file review found no surviving plausible security candidate. No source, query,
  planned signature, embedding, protocol frame, secret, or machine-specific path is present in the
  demo output.

Similarity remains evidence, not proof. A coding agent must still compare behavior, ownership,
signature, architectural fit, important differences, confidence, and uncertainty before editing.
