# CodeScope Coverage Evidence

## Production coverage

The Phase 10 pre-change ordinary-suite baseline used pytest's documented `importlib` import mode to
avoid collisions between `tests/unit/test_cli.py` and `tests/integration/test_cli.py`. The project
now configures that mode so the contract command runs unchanged:

```bash
uv run pytest \
  tests/unit \
  tests/integration \
  tests/security \
  tests/e2e \
  tests/release \
  --cov=codescope \
  --cov-report=term-missing
```

Before Phase 10 release tests were added, the combined suite passed 612 tests, skipped 7 explicit
or platform-specific cases, and measured 91% production line coverage (2,833 statements, 245
missed). After the Phase 10 release and security tests were added, the same production modules
measured 91% coverage (2,833 statements, 245 missed); 641 tests passed, 8 explicit or
platform-specific cases skipped, and pytest reported 273 installed-dependency warnings. The new
tests therefore increased release-path evidence without manufacturing a production coverage gain.

| Production module | Baseline coverage | Accepted gap classification |
|---|---:|---|
| `codescope.__init__` | 100% | None |
| `chunker` | 96% | Defensive tokenizer/segmentation contract failures |
| `cli` | 92% | Unexpected console/runtime failure translations and interactive-only edges |
| `config` | 98% | Defensive helper/type boundary |
| `embedder` | 90% | Backend/model failure shapes and platform CUDA edges |
| `engine` | 91% | Defensive malformed storage/embedder branches |
| `exceptions` | 100% | None |
| `indexer` | 88% | Filesystem race/error branches, rollback failures, platform-only objects |
| `models` | 99% | Defensive validators |
| `parser` | 90% | Malformed binding/tree edge branches |
| `server` | 100% | None |
| `storage` | 89% | Installed-backend failure translations and defensive response shapes |
| `utils.gitignore` | 82% | Bounded-read failures and invalid third-party pattern branches |
| `utils.json_io` | 87% | fsync/cleanup/read-race defensive branches |
| `utils.language` | 100% | None |
| `utils.path_guard` | 87% | OS/runtime failure and inaccessible-path branches |

The 91% baseline exceeds the 85% meaningful production target. Tests are not added merely to
exercise exception lines that require unsafe global monkeypatching or impossible supported-state
combinations.

## Script coverage

Import-safe deterministic tests cover the demo, benchmark, and clean verifier without network or a
cached model:

```bash
uv run pytest \
  tests/e2e/test_duplication_prevention.py \
  tests/release \
  tests/security/test_phase10_safety.py \
  --cov=scripts \
  --cov-report=term-missing
```

The first measured run passed 56 tests, skipped the two explicit real-model/clean-clone cases, and
reported 57% across all three scripts: demo 71%, benchmark 46%, verifier 50%. Those percentages
exclude the core real model, MCP subprocess, clone, sync, and command-sequence paths because the
ordinary suite deliberately does not require external cache/network/process state. The same paths
are separately executed by:

- the explicit offline real-model e2e test;
- the real measured benchmark;
- the opt-in real candidate-clone verifier;
- direct JSON parsing and cleanup assertions.

Separate `coverage run --source=scripts` measurements exercised the real paths without combining
subprocess children into an inflated parent number. The real benchmark process measured 76% for
`scripts/benchmark.py` and 74% for the demo it invokes. The real clean-clone process measured 55%
for `scripts/verify_clean_setup.py`. These script percentages are supplementary release evidence;
they are not mixed into the 91% production-module figure.

## Real-model and platform treatment

Ordinary suites skip five model-backed integration tests and one model-backed e2e test unless
`CODESCOPE_RUN_REAL_MODEL=1`; they are rerun explicitly with Hugging Face and Transformers offline.
The full clean-clone test has its own `CODESCOPE_RUN_CLEAN_SETUP=1` opt-in. The Windows junction
test skips only when the current operating system cannot create a junction and records the reason.

`.coverage`, `coverage.xml`, and `htmlcov/` are temporary evidence artifacts. They are removed
before the final working-tree audit and are never committed.
