# CodeScope Hackathon Compliance

This living checklist records evidence without treating future submission work as complete.

| Requirement | Current status | Evidence file or command | Submission-stage action | Notes |
|---|---|---|---|---|
| Developer Tools category | In progress | `CODESCOPE_CODEX_BUILD_MASTER.md` | Select Developer Tools in the final Devpost entry | Category intent is documented; final submission selection is pending. |
| Working project | In progress | `uv run codescope version`; Phase 1-3 tests | Complete all P0 implementation gates | Package, isolated parsing, and source chunking work; indexing and MCP behavior are not implemented. |
| Codex and GPT-5.6 usage | In progress | README collaboration section; Codex thread history | Preserve the primary implementation-session evidence | Phase 1-3 usage is documented; final demo usage is pending. |
| Dated Build Week commit evidence | In progress | `git log --oneline --decorate` | Continue phase-scoped dated commits | Phase 0-2 commits exist; Phase 3 received owner approval after its final clean audit. |
| Pre-existing planning versus Build Week implementation | Complete | `BUILD_WEEK_CHANGELOG.md`; `docs/design-history/` | Preserve history without rewriting dates | Planning and implementation are explicitly distinguished. |
| English project description | In progress | `README.md` | Refine and enter the owner-reviewed final description | The current positioning is in English; final submission copy is pending. |
| Public repository and relevant license | In progress | `LICENSE`; repository remote | Verify public access or required private sharing | MIT license exists; judge access is not yet verified. |
| README setup and testing instructions | In progress | `README.md` | Expand and clean-clone test the final quickstart | Current development, parser, chunker, and test status is present; functional operation instructions are pending. |
| Codex acceleration narrative | In progress | README collaboration section; `BUILD_WEEK_CHANGELOG.md` | Add concrete later-phase examples and owner edits | Phase 1-3 implementation and documentation research are recorded without final submission claims. |
| Owner-made key decisions | In progress | Build Master; `docs/.CHAT_MEMORY.md`; README | Preserve product, architecture, security, and scope decisions | Owner decisions are identified; evidence will grow with implementation. |
| Public YouTube video under three minutes | Not started | No evidence yet | Record, upload publicly, and verify while signed out | Must remain under three minutes. |
| Demo audio requirements | Not started | No evidence yet | Include clear audio explaining the project, Codex, and GPT-5.6 | Audio has not been recorded. |
| `/feedback` Session ID | Not started | Pending user action | Run `/feedback` in the primary implementation thread after most core functionality is built | No Session ID has been invented or recorded. |
| Installation instructions | Not started | Final README pending | Document and clean-clone verify installation | Current commands cover only the development foundation. |
| Supported platforms | In progress | Build Master cross-platform policy | Test and document verified operating systems | Linux development baseline is observed; broader verification is pending. |
| Direct judge testing path | Not started | Final README and demo pending | Provide a short deterministic judge workflow | Functional indexing and MCP tools do not exist yet. |
| Sample repository or sample data | In progress | `tests/fixtures/sample_python/` | Add and verify a judge-ready, license-safe sample | Parser fixtures exist, but no indexed sample or judge path is implemented. |
| Final security checks | In progress | Phase 1 security report; Phase 2-3 changelog entries and tests | Repeat security checks after later implementation phases and before submission | Phase 3 preflight was ready and its delegated review found no reportable issue; one low-severity signature-processing hardening suggestion is deferred to the tokenizer/indexer boundary. Final MVP review remains future work. |
| Benchmark evidence | Not started | Planned benchmark script and report | Measure and document real results | No benchmark numbers are claimed. |
| Clean-clone verification | Not started | No evidence yet | Run the documented path from a clean clone | Must not depend on private local state. |
| Third-party license review | Not started | `pyproject.toml`; `uv.lock` | Record dependency licenses and incompatibilities | Dependencies are locked; license review is pending. |
| Original work requirement | In progress | Git history; Build Week changelog | Review final repository and third-party assets | No claim beyond current repository evidence. |
| Devpost submission status | Not started | Devpost entry pending | Submit rather than leave the entry as draft | No submission claim has been made. |
