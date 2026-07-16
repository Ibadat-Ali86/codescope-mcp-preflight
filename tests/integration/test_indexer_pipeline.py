"""Integration tests for the real parser/chunker/Chroma indexing pipeline."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from codescope.chunker import TokenOffset
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.embedder import LocalEmbedder
from codescope.exceptions import StorageFailedError
from codescope.indexer import RepositoryIndexer
from codescope.storage import ChromaStorage

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "sample_python"
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class DeterministicTokenizer:
    def count_wordpieces(self, text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        return tuple(match.span() for match in TOKEN_PATTERN.finditer(text))


class DeterministicEmbedder:
    tokenizer = DeterministicTokenizer()

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
        if self.fail:
            raise RuntimeError("simulated safe embedding failure")
        vectors = np.zeros((len(texts), 8), dtype=np.float32)
        for row, text in enumerate(texts):
            vectors[row, sum(text.encode("utf-8")) % 8] = 1.0
        return vectors


def _config(runtime: Path) -> AppConfig:
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=FIXTURE_ROOT,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=(".git", ".codescope", ".venv", "__pycache__"),
            max_file_size_kb=500,
            max_chunk_wordpieces=80,
            chunk_overlap_wordpieces=5,
            follow_symlinks=False,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=3,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=runtime, collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def _stored_ids(storage: ChromaStorage) -> list[str]:
    result = storage._get_collection().get(include=[])
    identifiers = result.get("ids")
    assert isinstance(identifiers, list)
    return sorted(identifiers)


def test_fixture_repository_pipeline_is_persistent_deterministic_and_failure_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    config = _config(runtime)
    indexer = RepositoryIndexer(config, embedder=DeterministicEmbedder())

    # Act: first complete rebuild
    first = indexer.rebuild()
    first_status = indexer.status()
    first_storage = ChromaStorage(config.storage, create=False)
    try:
        first_symbols = first_storage.read_symbols()
        first_metadata = first_storage.read_index_metadata()
        first_ids = _stored_ids(first_storage)
        first_count = first_storage.count()
        matches = first_storage.query(
            np.array([1.0] + [0.0] * 7, dtype=np.float32),
            limit=1,
        )
    finally:
        first_storage.close()

    # Act: deterministic second rebuild and persistence through a second client
    second = indexer.rebuild()
    second_storage = ChromaStorage(config.storage, create=False)
    try:
        second_ids = _stored_ids(second_storage)
        second_count = second_storage.count()
    finally:
        second_storage.close()

    # Act: failed rebuild must preserve the second healthy index
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=DeterministicEmbedder(fail=True)).rebuild()
    after_failure = RepositoryIndexer(config).status()

    # Assert
    assert (first.total_files, first.total_symbols, first.total_chunks) == (4, 11, 17)
    assert first.skipped_files == 0
    assert any(symbol.qualified_name == "validate_email" for symbol in first_symbols)
    assert first_metadata.file_count == 4
    assert first_metadata.symbol_count == 11
    assert first_metadata.chunk_count == first_count == 17
    assert first_status.total_chunks == first_count
    assert second.total_files == first.total_files
    assert second.total_symbols == first.total_symbols
    assert second.total_chunks == first.total_chunks
    assert second_ids == first_ids
    assert second_count == first_count
    assert after_failure.total_chunks == second_count
    assert not hasattr(matches[0], "embedding")
    captured = capsys.readouterr()
    assert "validate_email(email" not in captured.out + captured.err


def test_real_cached_model_can_drive_full_fixture_index_when_explicitly_enabled(
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
    config = _config(tmp_path / ".codescope")
    embedder = LocalEmbedder(config.embeddings, allow_download=False)

    # Act
    summary = RepositoryIndexer(config, embedder=embedder).rebuild()

    # Assert
    assert summary.total_files == 4
    assert summary.total_symbols == 11
    assert summary.total_chunks > 0
    assert RepositoryIndexer(config).status().total_chunks == summary.total_chunks
