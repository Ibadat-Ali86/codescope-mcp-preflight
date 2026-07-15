"""Explicit real-model and production-tokenizer Phase 4 smoke validation."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from codescope.chunker import CodeChunker, format_embedding_text
from codescope.config import EmbeddingsConfig
from codescope.embedder import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_INPUT_WORDPIECES,
    LocalEmbedder,
)
from codescope.parser import CodeParser


def test_default_model_and_managed_tokenizer_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
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
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HF_HOME", str(cache))
    allow_download = os.environ.get("CODESCOPE_ALLOW_MODEL_DOWNLOAD") == "1"
    config = EmbeddingsConfig(
        model=DEFAULT_EMBEDDING_MODEL,
        batch_size=2,
        device="cpu",
        normalize=True,
    )
    embedder = LocalEmbedder(config, allow_download=allow_download)

    # Act
    vectors = embedder.encode(["validate an email address", "load a user service"])
    tokenizer = embedder.tokenizer
    unicode_text = "def café(value: str) -> βeta:"
    offsets = tokenizer.wordpiece_offsets(unicode_text)
    source = "def validate(value: str) -> bool:\n    return bool(value)\n"
    symbols = CodeParser().parse(source.encode("utf-8"), file="src/validators.py")
    chunks = CodeChunker(
        tokenizer=tokenizer,
        max_wordpieces=220,
        overlap_wordpieces=30,
    ).chunk(source, file="src/validators.py", symbols=symbols)
    wide_source = (
        "def wide():\n    values = ["
        + ", ".join(f'"βeta_{index}"' for index in range(400))
        + "]\n    return values\n"
    )
    wide_symbols = CodeParser().parse(wide_source.encode("utf-8"), file="src/wide.py")
    wide_chunks = CodeChunker(
        tokenizer=tokenizer,
        max_wordpieces=220,
        overlap_wordpieces=30,
    ).chunk(wide_source, file="src/wide.py", symbols=wide_symbols)

    # Assert
    assert vectors.shape == (2, DEFAULT_EMBEDDING_DIMENSION)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-3, atol=1e-4)
    assert embedder.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION
    assert embedder.maximum_input_wordpieces == DEFAULT_MAX_INPUT_WORDPIECES
    assert len(offsets) == tokenizer.count_wordpieces(unicode_text)
    assert offsets
    assert all(unicode_text[start:end] for start, end in offsets)
    assert chunks[0].text == source
    assert (
        tokenizer.count_wordpieces(format_embedding_text(chunks[0], signature=symbols[0].signature))
        <= 220
    )
    assert len(wide_chunks) > 1
    assert any(chunk.start_line == chunk.end_line == 2 for chunk in wide_chunks)
    assert all(chunk.text for chunk in wide_chunks)
    assert all(
        tokenizer.count_wordpieces(
            format_embedding_text(chunk, signature=wide_symbols[0].signature)
        )
        <= 220
        for chunk in wide_chunks
    )
