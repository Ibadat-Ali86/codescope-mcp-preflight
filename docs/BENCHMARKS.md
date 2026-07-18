# CodeScope Fixture Benchmark

## Measurement record

- Date: July 18, 2026.
- Command: `uv run python scripts/benchmark.py --json` with the documented external model-cache
  variable and Hugging Face/Transformers offline flags.
- Environment: Linux, Python 3.12.13, 8 logical CPUs, CodeScope 0.1.0, MCP 1.28.1.
- Fixture: committed `tests/fixtures/sample_python`, copied into an isolated temporary repository.
- Fixture result: 4 accepted Python files, 11 symbols, 16 chunks.
- Model: `sentence-transformers/all-MiniLM-L6-v2`, already prepared in an external cache.
- Model-download time: excluded; network during model use: disabled.
- Query methodology: 1 unmeasured warm-up followed by 5 measured iterations.
- MCP methodology: 1 warm-up of all four tools, then 5 iterations of all four tools (20 measured
  round trips).
- Indexing and fixed demo: one measured run each because both are materially heavier than queries.
- Timer: `time.perf_counter_ns()`; reported milliseconds are rounded to three decimals.

## Observed values

| Operation | Samples | Median ms | Minimum ms | Maximum ms |
|---|---:|---:|---:|---:|
| Authoritative status | 5 | 23.999 | 21.686 | 27.131 |
| Semantic search | 5 | 54.975 | 54.062 | 60.422 |
| Exact symbol lookup | 5 | 37.858 | 36.965 | 38.575 |
| Similar-code lookup | 5 | 56.795 | 54.032 | 58.659 |
| MCP tool round trip (all four tools pooled) | 20 | 66.611 | 40.880 | 80.613 |

Single-run observations:

| Operation | Duration ms |
|---|---:|
| Fixture indexing | 5,638.879 |
| MCP transport startup | 4.666 |
| MCP initialization | 1,035.417 |
| Fixed real-stdio demo | 7,717.399 |
| Complete benchmark | 23,068.540 |

The demo recommended REUSE, source hashes remained unchanged, the duplicate was avoided, and the
benchmark reported successful fixture/runtime/workspace cleanup.

## Interpretation

These are fixture-specific observations, not service-level objectives or universal performance
claims. The fixture is intentionally small. Results depend on CPU, filesystem, dependency cache,
model cache, process startup, and whether the model is already resident in the Python process.
Indexing includes cache-only model construction in this run; model download is excluded. Query
latency does not measure semantic quality, and similarity scores do not establish correctness or
equivalence. Five samples support a median/minimum/maximum summary but not statistical
significance; no percentile is reported.

The benchmark never indexes the developer repository, writes no raw report by default, includes no
hostname/user/cache/temp/repository path, emits no source snippet or embedding, and removes its
temporary state on success or failure.

## Reproduction

```bash
export CODESCOPE_MODEL_CACHE_DIR="$HOME/.cache/codescope-build-week-models"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
uv run python scripts/benchmark.py
uv run python scripts/benchmark.py --json
```

Optional `--iterations` is bounded from 1 through 50; `--warmup` is bounded from 1 through 10.
Importing the module performs no benchmark, model load, filesystem write, or network operation.
