# CodeScope Submission Screenshot Record

## Capture method

The four product screenshots use output observed from the final local CodeScope implementation on
July 18, 2026. Commands ran against an isolated copy of the committed sample fixture with the
prepared embedding model forced offline. The MCP inventory came from a real Python SDK stdio
handshake with the running `codescope serve` process. The preflight and demo-result values came
from the real `scripts/demo.py --json` and human-output paths.

Because the Linux Wayland session denied application-window screenshot access, the captured output
was rendered in privacy-safe 1600×900 terminal/evidence frames and screenshotted locally in a
browser. The values were not invented or replaced with mock results. Transient model-loading
progress, window chrome, unrelated desktop content, and machine-specific paths were deliberately
excluded. The rendering page and temporary fixture/runtime stayed outside the repository and were
removed after review.

## Reviewed assets

| Asset | Real evidence shown | Privacy and accuracy review |
|---|---|---|
| `assets/submission/cover.png` | CodeScope product identity and local-first MCP positioning | Original project graphic; no third-party asset or private data. |
| `assets/submission/screenshot-cli.png` | Actual `status` inventory and first `search "email validation"` result | Verified 4 files, 11 symbols, 16 chunks, score 0.6579, and `validators.py:6-9`; no host path or identity. |
| `assets/submission/screenshot-mcp.png` | Real server name, protocol, stdio transport, schemas, read-only annotations, and four tools | Exactly `search_code`, `find_symbol`, `find_similar`, and `list_indexed_files`; unrelated MCP servers hidden. |
| `assets/submission/screenshot-preflight.png` | Actual requested behavior, inventory, semantic/symbol/similar evidence, comparison, uncertainty, and decision | Scores and paths match the JSON demo output; similarity is explicitly qualified as evidence rather than proof. |
| `assets/submission/screenshot-demo-result.png` | Actual deterministic result | Shows `validate_email`, `validators.py:6–9`, REUSE, unchanged source, and duplicate avoided. |

## Full-resolution inspection

Each PNG and the architecture/cover sources were inspected at 1600×900. Every visible line was
reviewed. No screenshot contains a username, home directory, account identity, token, secret,
private configuration, cache path, temporary path, unrelated desktop content, cloud credential, or
source outside the committed sample fixture. Text remains readable at normal README display size.

## Reproduction boundary

The screenshots are release evidence, not a claim that the small fixture represents large-project
performance or that similarity proves equivalence. The underlying commands and exact evidence are
documented in `docs/DEMO_EVIDENCE.md`, `docs/BENCHMARKS.md`, and `docs/JUDGE_TESTING.md`.
