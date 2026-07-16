# CodeScope Hackathon Compliance

This living checklist records evidence without treating future submission work as complete.

| Requirement | Current status | Evidence file or command | Submission-stage action | Notes |
|---|---|---|---|---|
| Developer Tools category | In progress | `CODESCOPE_CODEX_BUILD_MASTER.md` | Select Developer Tools in the final Devpost entry | Category intent is documented; final submission selection is pending. |
| Working project | In progress | `uv run codescope version`; `uv run codescope index tests/fixtures/sample_python`; `uv run codescope status`; Phase 1-5 tests | Complete the query, MCP, demonstration, and final P0 gates | End-to-end local indexing and status validation work; semantic queries and MCP behavior are not implemented. |
| Codex and GPT-5.6 usage | In progress | README collaboration section; Codex thread history; Phase 5 security ledger | Preserve the primary implementation-session evidence | Phase 1-5 implementation, validation, and security-review usage is documented; final demo usage is pending. |
| Dated Build Week commit evidence | In progress | `git log --oneline --decorate`; `BUILD_WEEK_CHANGELOG.md` | Continue phase-scoped dated commits | Phase 0-4 commits exist; Phase 5 is complete only in the working tree and awaits owner commit authorization. |
| Pre-existing planning versus Build Week implementation | Complete | `BUILD_WEEK_CHANGELOG.md`; `docs/design-history/` | Preserve history without rewriting dates | Planning and implementation are explicitly distinguished. |
| English project description | In progress | `README.md` | Refine and enter the owner-reviewed final description | The current positioning is in English; final submission copy is pending. |
| Public repository and relevant license | In progress | `LICENSE`; repository remote | Verify public access or required private sharing | MIT license exists; judge access is not yet verified. |
| README setup and testing instructions | In progress | `README.md`; Phase 5 CLI acceptance commands | Expand and clean-clone test the final quickstart | Setup, test, model-preparation policy, fixture indexing, and status commands are present; final MCP/judge instructions remain pending. |
| Codex acceleration narrative | In progress | README collaboration section; `BUILD_WEEK_CHANGELOG.md` | Add concrete later-phase examples and owner edits | Phase 1-5 research, implementation, bounded reproduction, regression, and security-review examples are recorded without final submission claims. |
| Owner-made key decisions | In progress | Build Master; `docs/.CHAT_MEMORY.md`; README | Preserve product, architecture, security, and scope decisions | Owner decisions are identified; evidence will grow with implementation. |
| Public YouTube video under three minutes | Not started | No evidence yet | Record, upload publicly, and verify while signed out | Must remain under three minutes. |
| Demo audio requirements | Not started | No evidence yet | Include clear audio explaining the project, Codex, and GPT-5.6 | Audio has not been recorded. |
| `/feedback` Session ID | Not started | Pending user action | Run `/feedback` in the primary implementation thread after most core functionality is built | No Session ID has been invented or recorded. |
| Installation instructions | In progress | `README.md` setup and current-operation sections | Clean-clone verify model preparation, indexing, and final MCP operation | Locked environment and Phase 5 acceptance commands are documented; clean-clone and final MCP setup remain pending. |
| Supported platforms | In progress | Build Master cross-platform policy | Test and document verified operating systems | Linux development baseline is observed; broader verification is pending. |
| Direct judge testing path | In progress | `README.md` current operation; `tests/fixtures/sample_python/` | Add semantic-query/MCP steps and clean-clone timing | A deterministic development indexing/status path exists, but it is explicitly not the final judge workflow. |
| Sample repository or sample data | In progress | `tests/fixtures/sample_python/`; Phase 5 integration test | Polish and license-review the final judge sample | The fixture is deterministically indexable at 4 files, 11 symbols, and 16 production-model chunks; final judge presentation is pending. |
| Final security checks | In progress | Phase security reports; 61-test security suite; `BUILD_WEEK_CHANGELOG.md` | Repeat security checks after later implementation phases and before submission | Phase 5 reviewed six changed production files, corrected one nonreportable directory-bound hardening defect, and finalized with zero reportable findings. The final MVP review remains future work. |
| Benchmark evidence | Not started | Planned benchmark script and report | Measure and document real results | No benchmark numbers are claimed. |
| Clean-clone verification | Not started | No evidence yet | Run the documented path from a clean clone | Must not depend on private local state. |
| Third-party license review | Not started | `pyproject.toml`; `uv.lock` | Record dependency licenses and incompatibilities | Dependencies are locked; license review is pending. |
| Original work requirement | In progress | Git history; Build Week changelog | Review final repository and third-party assets | No claim beyond current repository evidence. |
| Devpost submission status | Not started | Devpost entry pending | Submit rather than leave the entry as draft | No submission claim has been made. |
