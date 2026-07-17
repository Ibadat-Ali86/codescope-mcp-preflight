"""Shared isolated test configuration."""

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


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    """Return a complete configuration whose runtime does not yet exist."""
    repository = tmp_path / "repository"
    repository.mkdir()
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=repository,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=(".git", ".codescope"),
            max_file_size_kb=500,
            max_chunk_wordpieces=220,
            chunk_overlap_wordpieces=30,
            follow_symlinks=False,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=32,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=repository / ".codescope", collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )
