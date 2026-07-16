"""Explicit real-model integration test for the persisted Phase 6 query pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.embedder import LocalEmbedder
from codescope.engine import QueryEngine
from codescope.indexer import RepositoryIndexer

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "sample_python"


def _config(runtime: Path) -> AppConfig:
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=FIXTURE_ROOT,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=(".git", ".codescope", ".venv", "__pycache__"),
            max_file_size_kb=500,
            max_chunk_wordpieces=220,
            chunk_overlap_wordpieces=30,
            follow_symlinks=False,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=8,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=runtime, collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def test_cached_real_model_index_to_query_pipeline_is_persistent_and_traceable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    if os.environ.get("CODESCOPE_RUN_REAL_MODEL") != "1":
        pytest.skip("explicit real-model validation is not enabled")
    cache_value = os.environ.get("CODESCOPE_MODEL_CACHE_DIR")
    if not cache_value:
        pytest.fail("CODESCOPE_MODEL_CACHE_DIR must identify the external validation cache")
    cache = Path(cache_value).resolve()
    repository = Path(__file__).parents[2].resolve()
    if cache == repository or cache.is_relative_to(repository):
        pytest.fail("the real-model cache must remain outside the repository")
    monkeypatch.setenv("HF_HOME", str(cache))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    config = _config(tmp_path / ".codescope")
    index_embedder = LocalEmbedder(config.embeddings, allow_download=False)
    summary = RepositoryIndexer(config, embedder=index_embedder).rebuild()

    # Act: a new engine opens the persisted index through new storage clients.
    engine = QueryEngine(config)
    semantic = engine.search_code("email validation", language="python", limit=5)
    exact = engine.find_symbol("validate_email")
    similar = engine.find_similar(
        "def validate_address(value: str) -> bool:\n    return '@' in value",
        language="python",
        limit=3,
    )
    status = engine.get_index_status()

    # Assert
    email_results = [result for result in semantic if result.symbol == "validate_email"]
    assert email_results
    assert email_results[0].file == "validators.py"
    assert (email_results[0].start_line, email_results[0].end_line) == (6, 9)
    assert len(exact) == 1
    assert exact[0].file == "validators.py"
    assert (exact[0].start_line, exact[0].end_line) == (6, 9)
    assert similar
    assert all(result.snippet for result in similar)
    assert status.total_files == summary.total_files == 4
    assert status.total_symbols == summary.total_symbols == 11
    assert status.total_chunks == summary.total_chunks
    assert status.index_root == "."
