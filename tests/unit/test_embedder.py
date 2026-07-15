"""Fast model-independent tests for the local embedding lifecycle."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import numpy as np
import pytest

from codescope.chunker import CodeChunker
from codescope.config import EmbeddingsConfig
from codescope.embedder import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_INPUT_WORDPIECES,
    LocalEmbedder,
    ManagedWordpieceTokenizer,
)
from codescope.models import Symbol


class FakeTokenizerBackend:
    is_fast = True
    model_max_length = 256

    def __init__(self, *, offsets: object | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._offsets = offsets

    def __call__(self, text: str, **kwargs: object) -> Mapping[str, object]:
        self.calls.append((text, kwargs))
        offsets = list(re.finditer(r"\S+", text))
        mapping: object = (
            self._offsets
            if self._offsets is not None
            else [(match.start(), match.end()) for match in offsets]
        )
        return {
            "input_ids": list(range(len(offsets))),
            "offset_mapping": mapping,
        }


class FakeModel:
    def __init__(
        self,
        *,
        output: object | None = None,
        dimension: int = 3,
        maximum: int = 64,
        tokenizer: FakeTokenizerBackend | None = None,
    ) -> None:
        self.output = output
        self.dimension = dimension
        self.max_seq_length = maximum
        self.tokenizer = tokenizer or FakeTokenizerBackend()
        self.encode_calls: list[dict[str, object]] = []

    def get_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, inputs: list[str], **kwargs: object) -> object:
        self.encode_calls.append({"inputs": list(inputs), **kwargs})
        if self.output is not None:
            return self.output
        rows = []
        for index, _text in enumerate(inputs):
            row = np.zeros(self.dimension, dtype=np.float64)
            row[index % self.dimension] = 1.0
            rows.append(row)
        return np.stack(rows)


class FakeFactory:
    def __init__(self, model: FakeModel | None = None, *, error: Exception | None = None) -> None:
        self.model = model or FakeModel()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        model_name: str,
        *,
        device: str,
        local_files_only: bool,
    ) -> FakeModel:
        self.calls.append(
            {
                "model_name": model_name,
                "device": device,
                "local_files_only": local_files_only,
            }
        )
        if self.error is not None:
            raise self.error
        return self.model


def _config(
    *,
    model: str = "test/model",
    batch_size: int = 7,
    device: str = "cpu",
    normalize: bool = True,
) -> EmbeddingsConfig:
    return EmbeddingsConfig(
        model=model,
        batch_size=batch_size,
        device=device,
        normalize=normalize,
    )


def test_constructor_is_lazy_and_does_not_inspect_cuda() -> None:
    # Arrange
    factory = FakeFactory()
    cuda_calls = 0

    def cuda_available() -> bool:
        nonlocal cuda_calls
        cuda_calls += 1
        return True

    # Act
    LocalEmbedder(_config(), model_factory=factory, cuda_available=cuda_available)

    # Assert
    assert factory.calls == []
    assert cuda_calls == 0


def test_empty_default_input_returns_known_shape_without_loading() -> None:
    # Arrange
    factory = FakeFactory(FakeModel(dimension=DEFAULT_EMBEDDING_DIMENSION, maximum=256))
    embedder = LocalEmbedder(
        _config(model=DEFAULT_EMBEDDING_MODEL),
        model_factory=factory,
        cuda_available=lambda: (_ for _ in ()).throw(AssertionError("CUDA inspected")),
    )

    # Act
    result = embedder.encode([])

    # Assert
    assert result.shape == (0, DEFAULT_EMBEDDING_DIMENSION)
    assert result.dtype == np.float32
    assert factory.calls == []
    assert embedder.maximum_input_wordpieces == DEFAULT_MAX_INPUT_WORDPIECES


def test_empty_custom_model_requires_preparation_without_guessing_dimension() -> None:
    # Arrange
    embedder = LocalEmbedder(_config(), model_factory=FakeFactory())

    # Act and Assert
    with pytest.raises(RuntimeError, match="dimensions are unknown"):
        embedder.encode([])


@pytest.mark.parametrize("texts", ["source text", b"source bytes", ["valid", "   "]])
def test_invalid_embedding_inputs_fail_with_fixed_safe_message(texts: Any) -> None:
    # Arrange
    factory = FakeFactory()
    embedder = LocalEmbedder(_config(), model_factory=factory)

    # Act
    with pytest.raises(ValueError) as error_info:
        embedder.encode(texts)

    # Assert
    assert str(error_info.value) == "Embedding input is invalid."
    assert "source" not in str(error_info.value)
    assert factory.calls == []


def test_repeated_encode_reuses_model_and_forwards_configuration() -> None:
    # Arrange
    model = FakeModel()
    factory = FakeFactory(model)
    embedder = LocalEmbedder(_config(batch_size=7, normalize=True), model_factory=factory)

    # Act
    first = embedder.encode(["first", "second"])
    second = embedder.encode(["third"])

    # Assert
    assert len(factory.calls) == 1
    assert factory.calls[0] == {
        "model_name": "test/model",
        "device": "cpu",
        "local_files_only": True,
    }
    assert [call["batch_size"] for call in model.encode_calls] == [7, 7]
    assert all(call["normalize_embeddings"] is True for call in model.encode_calls)
    assert all(call["convert_to_numpy"] is True for call in model.encode_calls)
    assert first.dtype == second.dtype == np.float32
    assert first.tolist() == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def test_explicit_download_permission_disables_cache_only_factory_mode() -> None:
    # Arrange
    factory = FakeFactory()
    embedder = LocalEmbedder(_config(), allow_download=True, model_factory=factory)

    # Act
    embedder.encode(["ready"])

    # Assert
    assert factory.calls[0]["local_files_only"] is False


def test_cpu_encode_never_inspects_cuda() -> None:
    # Arrange
    factory = FakeFactory()

    def unexpected_cuda_check() -> bool:
        raise AssertionError("CPU path inspected CUDA")

    embedder = LocalEmbedder(
        _config(device="cpu"),
        model_factory=factory,
        cuda_available=unexpected_cuda_check,
    )

    # Act and Assert
    assert embedder.encode(["ready"]).shape == (1, 3)


def test_unavailable_explicit_cuda_fails_before_model_loading() -> None:
    # Arrange
    factory = FakeFactory()
    embedder = LocalEmbedder(
        _config(device="cuda"),
        model_factory=factory,
        cuda_available=lambda: False,
    )

    # Act
    with pytest.raises(RuntimeError) as error_info:
        embedder.encode(["ready"])

    # Assert
    assert str(error_info.value) == "CUDA was requested but is unavailable."
    assert factory.calls == []


def test_cache_miss_error_is_actionable_and_does_not_leak_source_or_logs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    secret = "TOP_SECRET_SOURCE"
    factory = FakeFactory(error=OSError(f"cache miss for {secret}"))
    embedder = LocalEmbedder(_config(), model_factory=factory)

    # Act
    with pytest.raises(RuntimeError) as error_info:
        embedder.encode([secret])

    # Assert
    assert "unavailable locally" in str(error_info.value)
    assert secret not in str(error_info.value)
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


@pytest.mark.parametrize(
    "output",
    [
        np.array([1.0, 0.0, 0.0]),
        np.ones((2, 3)),
        np.ones((1, 4)),
        np.array([[np.nan, 0.0, 0.0]]),
        np.array([[np.inf, 0.0, 0.0]]),
        np.array([[2.0, 0.0, 0.0]]),
    ],
)
def test_invalid_model_outputs_are_rejected(output: np.ndarray[Any, Any]) -> None:
    # Arrange
    embedder = LocalEmbedder(_config(), model_factory=FakeFactory(FakeModel(output=output)))

    # Act and Assert
    with pytest.raises(ValueError, match="Embedding model output is invalid"):
        embedder.encode(["ready"])


def test_unnormalized_finite_float64_output_is_converted_once_to_float32() -> None:
    # Arrange
    output = np.array([[2.0, 0.0, 0.0]], dtype=np.float64)
    embedder = LocalEmbedder(
        _config(normalize=False),
        model_factory=FakeFactory(FakeModel(output=output)),
    )

    # Act
    result = embedder.encode(["ready"])

    # Assert
    assert result.dtype == np.float32
    assert result.tolist() == [[2.0, 0.0, 0.0]]


def test_tokenizer_adapter_disables_special_tokens_and_preserves_unicode_offsets() -> None:
    # Arrange
    backend = FakeTokenizerBackend()
    tokenizer = ManagedWordpieceTokenizer(
        backend,
        maximum_input_wordpieces=256,
        enable_prefix_cache=True,
    )
    text = "café βeta"

    # Act
    count = tokenizer.count_wordpieces(text)
    offsets = tokenizer.wordpiece_offsets(text)

    # Assert
    assert count == 2
    assert offsets == ((0, 4), (5, 9))
    assert [text[start:end] for start, end in offsets] == ["café", "βeta"]
    assert all(call[1]["add_special_tokens"] is False for call in backend.calls)
    assert all(call[1]["truncation"] is False for call in backend.calls)


@pytest.mark.parametrize(
    "offsets",
    [[(0, 2), (1, 3)], [(0, 0)], [(0, 99)], "unsafe"],
)
def test_tokenizer_adapter_rejects_invalid_offsets(offsets: object) -> None:
    # Arrange
    backend = FakeTokenizerBackend(offsets=offsets)
    tokenizer = ManagedWordpieceTokenizer(
        backend,
        maximum_input_wordpieces=256,
        enable_prefix_cache=False,
    )

    # Act and Assert
    with pytest.raises(ValueError, match="Embedding tokenizer output is invalid"):
        tokenizer.wordpiece_offsets("one two")


def test_tokenizer_adapter_rejects_offset_count_mismatch() -> None:
    # Arrange
    tokenizer = ManagedWordpieceTokenizer(
        FakeTokenizerBackend(offsets=[(0, 3)]),
        maximum_input_wordpieces=256,
        enable_prefix_cache=False,
    )

    # Act and Assert
    with pytest.raises(ValueError, match="Embedding tokenizer output is invalid"):
        tokenizer.wordpiece_offsets("one two")


def test_tokenizer_adapter_rejects_slow_backend() -> None:
    # Arrange
    backend = FakeTokenizerBackend()
    backend.is_fast = False

    # Act and Assert
    with pytest.raises(ValueError, match="Embedding tokenizer output is invalid"):
        ManagedWordpieceTokenizer(
            backend,
            maximum_input_wordpieces=256,
            enable_prefix_cache=False,
        )


def test_embedder_and_tokenizer_share_one_model_lifecycle() -> None:
    # Arrange
    factory = FakeFactory()
    embedder = LocalEmbedder(_config(), model_factory=factory)

    # Act
    first = embedder.tokenizer
    second = embedder.tokenizer
    dimension = embedder.embedding_dimension

    # Assert
    assert first is second
    assert dimension == 3
    assert embedder.maximum_input_wordpieces == 64
    assert len(factory.calls) == 1


def test_invalid_model_specification_fails_safely() -> None:
    # Arrange
    factory = FakeFactory(FakeModel(dimension=0))
    embedder = LocalEmbedder(_config(), model_factory=factory)

    # Act and Assert
    with pytest.raises(RuntimeError, match="unavailable locally"):
        _ = embedder.tokenizer


def test_model_encode_failure_does_not_echo_input() -> None:
    # Arrange
    secret = "TOP_SECRET_MODEL_INPUT"

    class FailingModel(FakeModel):
        def encode(self, inputs: list[str], **kwargs: object) -> object:
            raise RuntimeError(inputs[0])

    embedder = LocalEmbedder(_config(), model_factory=FakeFactory(FailingModel()))

    # Act
    with pytest.raises(ValueError) as error_info:
        embedder.encode([secret])

    # Assert
    assert str(error_info.value) == "Embedding model output is invalid."
    assert secret not in str(error_info.value)


def test_repeated_long_prefix_is_not_fully_reprocessed_for_every_count() -> None:
    # Arrange
    backend = FakeTokenizerBackend()
    tokenizer = ManagedWordpieceTokenizer(
        backend,
        maximum_input_wordpieces=256,
        enable_prefix_cache=True,
    )
    prefix = "signature: " + "value " * 2_000 + "\n\n"

    # Act
    counts = [tokenizer.count_prefixed_wordpieces(prefix, f"part {index}") for index in range(8)]

    # Assert
    prefixed_calls = [text for text, _kwargs in backend.calls if text.startswith(prefix)]
    exact_prefix_calls = [text for text, _kwargs in backend.calls if text == prefix]
    assert counts == [2_003] * 8
    assert len(prefixed_calls) == 2
    assert len(exact_prefix_calls) == 1


def test_chunker_reuses_long_signature_prefix_across_split_budget_counts() -> None:
    # Arrange
    backend = FakeTokenizerBackend()
    tokenizer = ManagedWordpieceTokenizer(
        backend,
        maximum_input_wordpieces=2_000,
        enable_prefix_cache=True,
    )
    source = "def oversized():\n" + "".join(
        f"    value_{index} = {index}\n" for index in range(180)
    )
    signature = "def oversized(" + "value " * 1_000 + "):"
    symbol = Symbol(
        name="oversized",
        kind="function",
        file="src/large.py",
        start_line=1,
        end_line=181,
        signature=signature,
        qualified_name="oversized",
        docstring=None,
        language="python",
    )
    chunker = CodeChunker(
        tokenizer=tokenizer,
        max_wordpieces=1_050,
        overlap_wordpieces=10,
    )

    # Act
    chunks = chunker.chunk(source, file="src/large.py", symbols=[symbol])

    # Assert
    prefix_marker = "signature: " + signature + "\n\n"
    prefixed_calls = [text for text, _kwargs in backend.calls if prefix_marker in text]
    assert len(chunks) > 1
    assert len(prefixed_calls) == 2
    assert all(chunk.qualified_name == "oversized" for chunk in chunks)
