Not submitted yet — nothing has been sent to Devpost.

# CodeScope — Owner-Review Submission Draft

This is the owner-reviewed technical and editorial draft prepared from verified repository evidence.
It is not a Devpost submission payload; release, video, `/feedback`, project creation, and final
submission remain separately authorized actions.

## Project fields

- **Name:** CodeScope
- **Tagline:** A local-first MCP preflight that helps coding agents understand existing Python code
  before deciding whether to REUSE, EXTEND, or CREATE.
- **Tagline status:** Owner-provided and approved for this draft.
- **Submitter type:** Individual — owner confirmed.
- **Country of residence:** Pakistan — owner confirmed.
- **Team:** Solo submission; no teammate invitations required — owner confirmed.
- **Category:** Developer Tools.
- **Repository:** https://github.com/Ibadat-Ali86/codescope-mcp-preflight
- **Release:** Pending owner-authorized final GitHub Release.
- **Video:** A supplied public YouTube recording was verified reachable on July 22, 2026, but it is
  5:47 and therefore not an eligible final submission video. Do not enter it in Devpost; a compliant
  public or Unlisted replacement under three minutes remains required.
- **Devpost project:** Not created; a separate explicit owner authorization is required.

## Description — owner-reviewed draft

I built CodeScope because I kept seeing coding agents generate new code before properly checking
what a repository already contained. The requested behavior might already exist under another name,
in a different file, or as a method inside an existing service, but the agent would still create
another helper or validator because generating code was easier than understanding the codebase.

That creates a real maintenance problem. Two functions may solve almost the same problem but handle
edge cases differently. Later, a bug gets fixed in one copy and remains in the other. The repository
becomes larger, ownership becomes less clear, and review becomes harder.

CodeScope adds a preflight step before generation. It inventories the repository, extracts Python
symbols, searches for behavior and similar implementations, and shows where the evidence came from.
The agent must then make an explicit REUSE, EXTEND, or CREATE decision instead of assuming that every
request requires a new file or function.

In my fixed demo, the task is to validate an email before creating a user account. CodeScope finds
the existing `validate_email` function in `validators.py` and recommends REUSE. The important result
is not just that search worked. It is that the repository stayed unchanged and a second validator
was not created.

As a solo builder, I feel the cost of unnecessary code very quickly. If an AI tool creates a
duplicate abstraction, there is no separate maintenance team that will clean it up later. I am the
person who has to understand both versions, decide which one is authoritative, update the tests, and
repair the architecture.

I like using coding agents because they can move quickly, but speed becomes a problem when generation
happens without enough repository context. I did not want to solve that by telling the agent to
“search more carefully” in a prompt. I wanted the repository-understanding step to become an actual
tool with a repeatable workflow.

The local-first part also matters to me. CodeScope indexes source locally, uses local embeddings,
stores its index locally, and exposes read-only MCP tools. Repository code is evidence for the agent,
not something that should automatically be uploaded, executed, or treated as instructions. That
reflects the way I personally want AI development tools to work: useful, inspectable, and limited by
clear boundaries.

CodeScope is a local-first Developer Tools project for Python repositories that gives Codex and other
MCP clients implementation evidence for a deliberate **REUSE**, **EXTEND**, or **CREATE** decision.
It does not write repository files, execute indexed source, or send source code to a cloud embedding
service.

### What the experience looks like

A developer creates a local index, checks its authoritative status, and searches from the CLI. A
coding agent connects to the local stdio MCP server, inventories indexed files, searches by
behavior, looks up likely symbols, and compares similar code. The repository-scoped
`$codescope-preflight` skill combines those results into a structured recommendation with behavior,
ownership, important differences, confidence, and uncertainty.

The final decision stays with the developer or coding agent. Similarity is treated as evidence,
not proof of equivalence, and retrieved repository text is treated as untrusted content rather
than instructions.

### Demonstrated result

The deterministic Build Week demonstration asks for email validation before creating a user
account. CodeScope indexes the committed sample repository into 4 files, 11 symbols, and 16 chunks.
Inventory, semantic search, exact-symbol lookup, and similar-code search converge on the existing
`validate_email` function at `validators.py:6-9`. The workflow recommends **REUSE**, exact source
hashes remain unchanged, and no duplicate `is_valid_email` helper is created.

### Technical implementation

The pipeline begins with centralized path guards, mandatory secret/cache/archive/build exclusions,
bounded reads, root-level `.gitignore` handling, contained-symlink checks, and physical-file
deduplication. Tree-sitter extracts Python symbols without filesystem access. The chunker assigns
nonduplicative class/method ownership and uses exact tokenizer wordpieces—including transient
embedding context—to stay within the model budget. SHA-256 content hashes and canonical chunk IDs
are deterministic.

The default Sentence Transformers model is prepared explicitly in an external cache and used
cache-only for normal operation. Embeddings and Chroma storage remain local with telemetry
disabled. Rebuilds are created in validated sibling directories and verified before rollback-capable
promotion. Fixed, bounded, atomic JSON metadata supports authoritative status checks.

`QueryEngine` provides semantic code search, exact/partial symbol lookup, similar-code evidence,
and status with deterministic ordering and typed failures. A Typer/Rich CLI exposes six commands.
The lazy FastMCP server exposes exactly four read-only tools—`search_code`, `find_symbol`,
`find_similar`, and `list_indexed_files`—over local stdio with protocol-only stdout and structured,
nonreflective error responses.

### Why the idea is different

CodeScope is not a hosted code search interface and not an embedding proof of concept. Its product
idea is repository understanding as a required agent preflight: combine secure local discovery,
semantic evidence, exact symbols, similar-code evidence, architectural ownership, and explicit
uncertainty before deciding to generate. The local-first boundary also supports repositories whose
source should not be uploaded to an external embedding API.

### Target audience and potential impact

The audience is developers and teams using AI coding agents on existing Python repositories. The
potential value is avoiding unnecessary duplicate validators, services, and helpers; preserving
clear ownership; reducing inconsistent implementations; and giving reviewers traceable evidence
for why an agent reused, extended, or created code. The small fixture demonstrates the workflow,
but no organization-wide cost savings or large-repository performance claim is made.

### Codex and GPT-5.6 collaboration

Codex with GPT-5.6 helped inspect the evolving repository, consult installed-version documentation,
implement Phases 1–10, construct focused and adversarial tests, reproduce failures, review security
boundaries, validate the CLI and MCP protocol, build the deterministic demo, measure the fixture
benchmark, verify a clean candidate clone, audit package artifacts, and structure the release and
submission evidence.

Codex helped me move through the project in structured phases. I used it for repository inspection,
architecture exploration, implementation, test generation, failure reproduction, MCP integration,
security review, packaging checks, documentation, and the deterministic demo. GPT-5.6 was most
useful when the problem required reasoning across several constraints at once, such as balancing
retrieval quality, source ownership, tokenizer limits, local-only operation, and safe filesystem
behavior.

I did not treat its output as automatically correct. One Codex-assisted implementation I corrected
involved chunking classes and methods. An early direction could cause a method body to appear twice:
once as its own method chunk and again inside a larger class chunk. That would make retrieval results
look more confident than the underlying evidence justified because the same implementation could be
counted twice.

I changed the chunking design to preserve ownership and avoid duplicating class and method content.
That correction was important because CodeScope is supposed to reduce false confidence, not create it.
The same principle shaped the final product: semantic similarity is evidence, but it is not
permission to silently make the coding decision.

The product boundaries were also my responsibility. I chose the Python-only MVP, the local embedding
policy, the four read-only MCP tools, the REUSE/EXTEND/CREATE contract, and the rule that CodeScope
must not modify indexed source.

### Built during OpenAI Build Week

Planning and design-history documents existed before implementation. Dated repository history
records the Build Week implementation from the Python/uv foundation through immutable config and
path safety, Tree-sitter parsing, model-budgeted chunking, local embeddings and Chroma, secure
indexing, query orchestration, CLI, MCP, the preflight skill, deterministic demo, security
hardening, benchmark, coverage evidence, clean-candidate verification, and release documentation.
The detailed phase ledger is in `BUILD_WEEK_CHANGELOG.md`; published history was not rewritten.

### Evidence

- 91% production coverage: 2,838 statements, 245 missed; 653 passed and 8 explicit/platform skips
  in the measured final-candidate combined coverage run.
- 492 unit tests and 102 security tests in the parser-fixed final-candidate gates.
- 37 tests passed in the explicit offline real-model integration/e2e matrix.
- Clean-candidate verification reached the fixed demo 60.855 seconds after setup timing began and
  completed cleanup in 63.586 seconds on the observed Linux environment.
- Fixture medians of approximately 55 ms for semantic search and 66.6 ms for pooled MCP round trips.
- Zero reportable findings in the recorded Phase 10 repository/diff security review and no
  unresolved validated high- or critical-severity issue.

These are environment- and fixture-specific observations, not universal performance, quality, or
scale guarantees. Complete methodology and limitations are in `docs/COVERAGE.md`,
`docs/BENCHMARKS.md`, and `docs/SECURITY.md`.

### Challenges and accomplishments

The difficult parts were not the happy-path calls. They included proving resolved path
containment, stopping external symlink and descriptor-race escapes, preventing class/method source
duplication while staying inside the real tokenizer budget, promoting new local indexes without
destroying a valid prior index, keeping MCP stdout protocol-only, translating errors without
reflecting attacker-controlled content, and proving the demo did not modify its source fixture.

The resulting project is a cohesive local workflow rather than a disconnected set of components:
index → inspect → search → MCP → preflight → REUSE/EXTEND/CREATE.

I am most proud that CodeScope became a complete preflight workflow rather than remaining a
semantic-search demo.

It securely discovers repository files, extracts Python symbols with Tree-sitter, creates
deterministic ownership-aware chunks, generates embeddings locally, stores the index in Chroma, and
exposes the evidence through both a CLI and four read-only MCP tools. The preflight skill then guides
the coding agent through repository inventory, behavior search, symbol lookup, similar-code
inspection, confidence, uncertainty, and the final REUSE, EXTEND, or CREATE decision.

The part that matters most to me is that CodeScope can reach a useful conclusion without changing the
repository. In the email-validation demo, it identifies `validate_email`, points to its exact source
location, recommends REUSE, and verifies that no duplicate helper was added.

Building that safely was harder than making search return a plausible result. I had to handle path
containment, symlink escapes, bounded reads, secret and cache exclusions, tokenizer budgets,
deterministic identities, safe index promotion, protocol-only MCP output, structured errors, and
source-change verification. I am proud that the safety boundaries are part of the working product
rather than promises added to the README afterward.

### Lessons learned

The clearest lesson I learned is that similarity must remain evidence, not become the decision itself.

At first, it is tempting to think that the highest embedding score should produce a simple answer:
if the score is high, reuse the code. Real repositories are not that clean. Two functions can look
similar while belonging to different layers, handling different edge cases, or having different
ownership. A lower-ranked exact symbol can sometimes be more relevant than the highest semantic
match.

That changed how I designed CodeScope. It combines repository inventory, semantic behavior search,
exact and partial symbol lookup, similar-code retrieval, source locations, ownership, important
differences, confidence, and uncertainty. The final recommendation must be explainable from those
pieces of evidence.

I also learned that directing an AI coding agent requires explicit boundaries. “Build a repository
search tool” was not enough. I had to specify what it must never do: never execute indexed code,
never escape the repository boundary, never write source through MCP, never treat retrieved text as
instructions, and never turn one score into an unsupported conclusion.

### Limitations and future work

CodeScope currently supports only Python `.py` and `.pyi` files, interprets only the repository-root
`.gitignore`, requires separate model-cache preparation, and has been fully validated only on Linux.
The benchmark and demo fixtures are intentionally small. Similarity does not establish semantic
equivalence. There is no dashboard, remote hosting, authentication, deployment, file watcher, or
incremental index update.

Potential future work includes additional language adapters, broader macOS/Windows validation,
nested ignore semantics, larger representative performance/quality evaluation, and incremental
index updates. These are future directions, not current features.

### Closing

CodeScope is a local-first MCP preflight that helps coding agents understand existing Python code
before deciding whether to REUSE, EXTEND, or CREATE.

I built it around a simple belief: an agent should understand the repository before it generates more
code. CodeScope does not replace developer judgment, and it does not claim that similarity proves
equivalence. It gathers local, traceable evidence so that the next coding decision is deliberate
rather than automatic.

I reviewed the project description and it reflects my own words and experience.

## Built with

Python, Codex, GPT-5.6, MCP, FastMCP, Typer, Rich, Tree-sitter, sentence-transformers, ChromaDB,
Pydantic, uv, and pytest.

## Submission assets

- `assets/submission/cover.png`
- `assets/submission/architecture.png` and `architecture.svg`
- `assets/submission/screenshot-cli.png`
- `assets/submission/screenshot-mcp.png`
- `assets/submission/screenshot-preflight.png`
- `assets/submission/screenshot-demo-result.png`

## Judge instructions

The complete no-source-build, locked-source, and evidence-only routes are in
`docs/JUDGE_TESTING.md`. The release-wheel route is not yet available because the release action is
separately owner-gated. The default model requires one explicit external-cache preparation step;
normal operation is cache-only. The expected result is REUSE for `validate_email` at
`validators.py:6-9`, with unchanged source and no duplicate created.

## Exact Devpost form answers

### `27945` — Submitter Type

`Individual`

### `27946` — Country of Residence

`["Pakistan"]`

### `27947` — Category

`Developer Tools`

### `27948` — Repository URL

`https://github.com/Ibadat-Ali86/codescope-mcp-preflight`

### `27949` — Judge testing link or instructions

Use the public repository and `docs/JUDGE_TESTING.md`. After the separately authorized final
release, use the attached `codescope-0.1.0-py3-none-any.whl` and `SHA256SUMS.txt` from tag
`v1.0.0-build-week` for the no-source-build route. CodeScope requires Python 3.12 and one explicit
external preparation of `sentence-transformers/all-MiniLM-L6-v2`; normal use is offline/cache-only.
The full locked route is `git clone`, `uv sync --locked`, sample index, status, search, and
`scripts/demo.py`. Expected result: REUSE `validate_email` at `validators.py:6-9`, source unchanged,
duplicate avoided. The submitted video must demonstrate a reproducible documented route; the
currently supplied 5:47 routing recording is not that evidence. Judges unable to prepare the model can review the video, screenshots,
architecture, demo evidence, coverage, benchmark, security record, source, and tests; that route
does not run live semantic search. The public video and release links will be added only after they
exist and are verified.

### `27950` — `/feedback` Session ID

Pending owner action: run `/feedback` in the primary CodeScope implementation thread after the
final technical/repository review, then verify that the captured Session ID belongs to this project.
No value is invented.

### `27951` — Developer Tool Instructions

Prerequisites: Python 3.12, Git, and uv for the locked source route. Validated on Linux; public path
and security logic have cross-platform tests; full macOS/Windows runtime validation is pending.

Install with the final GitHub Release wheel for the no-source-build route or clone the repository
and run `uv sync --locked` for exact dependency reproduction. The wheel route verifies the exact
wheel checksum before installation and runs the installed CLI; it does not execute a downloaded
source script. Set `CODESCOPE_MODEL_CACHE_DIR` to an external directory and run one explicitly
authorized index with `--allow-model-download`; then set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`. Run the sample index, `codescope status`, and
`codescope search "email validation"`; use `python scripts/demo.py` only on the locked-source
route. Expect REUSE for `validate_email` at `validators.py:6-9`, unchanged source, and duplicate avoided. Configure the
local stdio MCP server from `examples/codex_mcp_config.toml`; it exposes exactly four read-only
tools. Use `codescope reset --yes` for runtime cleanup. Limitations and troubleshooting are in
`docs/JUDGE_TESTING.md` and `docs/TROUBLESHOOTING.md`.

## Readiness gaps

- Final owner review of the populated narrative and owner-review report.
- Explicit authorization to create a new CodeScope Devpost project draft.
- Final test/security/clean-candidate gates for the Phase 11 candidate.
- Owner-authorized release commit, tag, GitHub Release, wheel, checksum, and verified public links.
- A replacement public-viewable YouTube video under three minutes with required audio and signed-out
  verification; the supplied 5:47 routing recording is not eligible.
- `/feedback` Session ID from the primary CodeScope implementation thread.
- Final live Devpost requirement refresh, payload review, exact submission authorization, and
  submitted-status readback.
