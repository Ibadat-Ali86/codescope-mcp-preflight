# CodeScope Final Release and Submission Checklist

This checklist is a gate record. Items remain open until the stated action is actually completed.

## Owner and official-rules gates

- [x] Country of residence confirmed as Pakistan.
- [x] Owner confirmed age-of-majority eligibility and no exclusion/conflict condition.
- [x] Owner confirmed original work and compliant use of third-party software and materials.
- [x] Owner confirmed agreement with the OpenAI Build Week Official Rules and Devpost terms.
- [x] Submitter type confirmed as Individual; solo submission; no teammate invitation required.
- [x] Owner personalized the required description sections on July 19, 2026.
- [x] Owner confirmed: “I reviewed the project description and it reflects my own words and experience.”
- [x] Owner supplied the final draft tagline on July 19, 2026.

## Repository candidate

- [x] Final ordinary unit, integration, security, e2e, and release suites passed on July 19, 2026.
- [x] Offline real-model matrix passed with the prepared external cache on July 19, 2026.
- [x] Ruff, formatting, mypy, lock, package/license, secret, privacy, placeholder, and link gates
  passed on July 19, 2026.
- [x] Final clean-candidate verifier passed on July 19, 2026.
- [ ] Final `/review`, repository security review, and Phase 11 diff review are complete.
- [ ] No high or critical validated security finding remains.
- [ ] No runtime, model, cache, coverage, build, recording, or temporary artifact is committed.
- [ ] Public repository, README, MIT license, default branch, assets, final commit, and clone are
  verified signed out.

## Release

- [ ] Owner approves the exact Phase 11 staged patch and release action.
- [ ] Final release commit is created and pushed without rewriting history.
- [ ] `v1.0.0-build-week` annotated tag is created and pushed.
- [ ] `uv build` succeeds from the final commit.
- [ ] Wheel and sdist contents and PEP 639 license metadata are verified.
- [ ] SHA-256 checksum file is created.
- [ ] GitHub Release is created with wheel, optional sdist, and checksum attached.
- [ ] Release wheel installs in a fresh Python 3.12 environment.
- [ ] Release URLs and checksums are recorded in judge and submission documents.

## Video and Codex evidence

- [ ] Public or Unlisted YouTube video is under 2:59 and contains audible narration.
- [ ] Video explains CodeScope, Codex use, and GPT-5.6 use.
- [ ] Video is readable, contains no private data, and uses no unauthorized copyrighted material.
- [ ] Video URL opens without sign-in in an incognito/private browser.
- [ ] Owner runs `/feedback` in the primary CodeScope implementation thread.
- [ ] Owner verifies the captured Session ID belongs to that thread.

### July 22 supplied-video audit

- The owner supplied a public YouTube link. A real signed-out browser reached the video titled
  `CODEX HACKATHON CODESCOPE PLUGIN short interview` without a sign-in prompt.
- The displayed duration was 5:47, exceeding the mandatory under-three-minute limit. It is not a
  final submission asset and must not be entered in Devpost.
- Closed captions were unavailable. Audio coverage, private-data review, and rights review were not
  verified from the link.
- The video describes a routing-ownership comparison, but the `RoutingPolicy` / `ResponseSla`
  fixture and claimed eight-test route are absent from the public repository. The reproducible
  repository route remains the email-validation demo.

## Devpost

- [ ] Owner explicitly authorizes creation of the new CodeScope Devpost project draft.
- [ ] New CodeScope project—not the unrelated Gemini draft—is created and read back.
- [ ] Final live rules, announcements, dates, form fields, judging criteria, and Pakistan eligibility
  are refreshed before submission.
- [ ] Developer Tools category, Individual submitter type, Pakistan residence, repository, video,
  testing instructions, release, and `/feedback` Session ID are present.
- [ ] Cover thumbnail upload is prepared and finalized only after owner authorization.
- [ ] Owner reviews the complete pre-submit payload and authorizes the exact submission action.
- [ ] Devpost submission succeeds and live readback confirms Submitted.
- [ ] Public Devpost URL works signed out and final evidence is archived factually.

## Required stop points

Creating a Devpost draft, updating it, uploading/finalizing media, committing, tagging, publishing a
GitHub Release, and submitting to judging are separate external writes. Each requires the explicit
owner authorization specified by the Phase 11 contract. No unchecked item may be represented as
complete.

## Current staged-candidate audit

On July 19, 2026, the 18-file Phase 11 evidence candidate was staged without any dependency,
production-code, Graphify, runtime, cache, build, or temporary artifact. The aggregate ordinary
suite passed 641 tests with 8 explicit/platform skips and 273 warnings in 23.30 seconds. The
explicit offline cache-only integration/e2e matrix passed 37 tests with 91 warnings in 23.49 seconds.
The dedicated security suite passed 101 tests with one operating-system junction skip and 116
warnings in 6.05 seconds. Ruff, formatting, strict source/script mypy, `uv lock --check`, CLI
version, and the temporary package build/license audit passed.

The initial verifier attempt reproduced a bounded-output conflict: its 2 MiB generic child-output
cap rejected an otherwise permitted 2,839,881-byte binary-inclusive candidate patch before patch
application. The owner authorized a narrow correction that keeps the generic cap unchanged while
allowing only the hard-coded candidate `git diff --binary` capture to use the existing 16 MiB patch
limit. Focused release tests passed 13 tests with one explicit opt-in skip in 5.95 seconds, including
real-Git binary-patch cases above 2 MiB/below 16 MiB and above 16 MiB, an ordinary-output cap case,
and rejection of any non-candidate command from the special capture path. The final clean-candidate
rerun passed: the candidate patch applied, all required CLI/MCP/demo checks passed, the fixture
source stayed unchanged, and clone/runtime cleanup completed. Observed timings were 510.832 ms clone,
415.021 ms dependency sync, 54,459.702 ms setup to demo, and 57,177.122 ms total.

## July 22 parser-compatibility candidate

A real parser-native stability defect is included in the current unstaged candidate: `tree-sitter`
0.26.0 with the installed Python grammar 0.25.0 corrupted node metadata while parsing CodeScope
source. The candidate pins `tree-sitter` 0.25.2, retains the parsed Tree during traversal, validates
identifier byte ranges, and adds focused parser and candidate-index rollback coverage.

On the locked candidate, parser tests passed 44; ordinary unit/integration/security/e2e/release
suites passed 492/4/102/27/28 respectively with only their documented explicit or platform skips;
the cache-only real-model integration/e2e matrix passed 37; quality and lock gates passed; and the
clean-candidate verifier passed in 49,774.695 ms. This material remains subject to final owner
review and staging. A local `codex review --uncommitted` attempt did not return findings and was
stopped; do not treat that attempt as a completed review.

At 01:01 PKT on July 22, live Devpost still reported submissions open until 05:00 PKT. The refreshed
rules, requirements, fields, judging criteria, eligibility, registration, and project list matched
the draft, but no CodeScope project exists. The final combined ordinary coverage rerun passed 653
tests with 8 documented skips and measured 91% across 2,838 production statements. Human/JSON
demos, temporary package/license inspection, staged scope/privacy/secret/link/SVG/PNG checks, and
the clean-candidate verifier passed. These checks do not replace the remaining owner gates.
