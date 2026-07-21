# CodeScope Judge Testing

CodeScope is a Python 3.12 developer tool. The complete semantic workflow uses the local
`sentence-transformers/all-MiniLM-L6-v2` model, which must be prepared explicitly in an external
cache before cache-only operation. No model files are stored in this repository or its release
artifacts.

## Supported platform statement

Validated on Linux with Python 3.12. Public path and security logic include cross-platform tests.
Full macOS and Windows runtime validation remains pending.

## Expected result

The deterministic small-fixture path indexes 4 files into 11 symbols and 16 chunks. The requested
task is email validation before account creation. Inventory, semantic search, exact symbol lookup,
and similar-code evidence converge on `validate_email` at `validators.py:6-9`; the demo recommends
`REUSE`, confirms that source hashes are unchanged, and confirms that no duplicate implementation
was created.

## Video alignment

The committed judge route is the email-validation case above. The owner supplied a separate public
routing-ownership recording, but the repository does not contain its `RoutingPolicy` / `ResponseSla`
comparison fixture or its claimed eight-test route. The recording is 5:47, exceeding the Build Week
under-three-minute requirement. It is not a substitute for this reproducible judge path and must not
be entered as the final submission video. A compliant replacement must either demonstrate this
documented email-validation route or accompany a newly committed, reproducible routing fixture.

## Route A — Prebuilt release wheel

Status: this route becomes available only after the owner authorizes the final release commit,
`v1.0.0-build-week` tag, GitHub Release, wheel, and checksum publication. The package version
remains `0.1.0`; the Build Week tag does not change it.

This route installs CodeScope without building the package from source. The release source archive
is used only for the committed sample fixture; the wheel route does not execute downloaded source.

```bash
set -euo pipefail
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  -o codescope-0.1.0-py3-none-any.whl \
  https://github.com/Ibadat-Ali86/codescope-mcp-preflight/releases/download/v1.0.0-build-week/codescope-0.1.0-py3-none-any.whl
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  -o SHA256SUMS.txt \
  https://github.com/Ibadat-Ali86/codescope-mcp-preflight/releases/download/v1.0.0-build-week/SHA256SUMS.txt
grep -E '^[[:xdigit:]]{64}  codescope-0\.1\.0-py3-none-any\.whl$' SHA256SUMS.txt \
  | sha256sum --check -

git clone --branch v1.0.0-build-week --depth 1 \
  https://github.com/Ibadat-Ali86/codescope-mcp-preflight.git
cd codescope-mcp-preflight
python3.12 -m venv .judge-venv
. .judge-venv/bin/activate
python -m pip install ../codescope-0.1.0-py3-none-any.whl
codescope version
```

Prepare the model once in a cache outside the repository. This is the only step that authorizes a
model download:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
codescope index tests/fixtures/sample_python --allow-model-download
codescope reset --yes
```

Then force offline/cache-only behavior and run the judge path:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
codescope index tests/fixtures/sample_python
codescope status
codescope search "email validation"
codescope reset --yes
```

The release-wheel route deliberately runs only the installed CLI; it does not execute a script
from the downloaded source archive. `set -euo pipefail` and the exact wheel checksum pipeline make
the verification a hard gate: a missing, malformed, or mismatched wheel entry stops before
installation. The full `scripts/demo.py` workflow is available through the locked-source route and
the evidence-only route below.

## Route B — Locked source path

This is the fully reproducible repository path:

```bash
git clone https://github.com/Ibadat-Ali86/codescope-mcp-preflight.git
cd codescope-mcp-preflight
uv sync --locked
uv run codescope version
```

Prepare the external model cache once:

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
uv run codescope index tests/fixtures/sample_python --allow-model-download
uv run codescope reset --yes
```

Run offline after preparation:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
uv run codescope index tests/fixtures/sample_python
uv run codescope status
uv run codescope search "email validation"
uv run python scripts/demo.py
uv run python scripts/demo.py --json
uv run codescope reset --yes
```

To inspect the real local MCP surface, configure the example in
[`examples/codex_mcp_config.toml`](../examples/codex_mcp_config.toml), run `codex mcp list`, and
confirm exactly four tools: `search_code`, `find_symbol`, `find_similar`, and
`list_indexed_files`.

## Route C — Fast evidence review without model preparation

This route reviews evidence and does not execute live semantic search:

- the public demonstration video, once the owner supplies and verifies its YouTube URL;
- the [CLI screenshot](../assets/submission/screenshot-cli.png),
  [MCP screenshot](../assets/submission/screenshot-mcp.png),
  [preflight screenshot](../assets/submission/screenshot-preflight.png), and
  [demo-result screenshot](../assets/submission/screenshot-demo-result.png);
- the [architecture](../assets/submission/architecture.svg);
- the deterministic [demo evidence](DEMO_EVIDENCE.md);
- the [coverage record](COVERAGE.md), [benchmark record](BENCHMARKS.md), and
  [security record](SECURITY.md);
- the source and complete unit, integration, security, e2e, and release tests.

## Known limitations

- Python `.py` and `.pyi` repositories only.
- Only root-level `.gitignore` semantics are implemented.
- The default embedding model must be prepared separately; it is not bundled.
- The benchmark and demonstration use a small committed fixture.
- Similarity is evidence, not proof of behavioral equivalence.
- Linux is the fully validated runtime platform; complete macOS and Windows runs remain pending.

## Cleanup

Use the validated command rather than recursive shell deletion:

```bash
codescope reset --yes
deactivate  # only for Route A
```

The external model cache is a reusable prerequisite, not CodeScope runtime data. The demo creates
and removes its own isolated temporary workspace.
