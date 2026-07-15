"""Lazy local sentence-transformer embeddings and exact tokenizer accounting."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import ClassVar, Final, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from codescope.chunker import TokenOffset, WordpieceTokenizer
from codescope.config import EmbeddingsConfig

DEFAULT_EMBEDDING_MODEL: Final = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSION: Final = 384
DEFAULT_MAX_INPUT_WORDPIECES: Final = 256

_MODEL_SPECS: Final[dict[str, tuple[int, int]]] = {
    DEFAULT_EMBEDDING_MODEL: (
        DEFAULT_EMBEDDING_DIMENSION,
        DEFAULT_MAX_INPUT_WORDPIECES,
    )
}
_INPUT_ERROR: Final = "Embedding input is invalid."
_MODEL_LOAD_ERROR: Final = (
    "The embedding model is unavailable locally. Prepare it with explicit download "
    "permission and retry."
)
_CUDA_ERROR: Final = "CUDA was requested but is unavailable."
_MODEL_OUTPUT_ERROR: Final = "Embedding model output is invalid."
_MODEL_SPEC_ERROR: Final = "Embedding model dimensions are unknown until the model is prepared."
_TOKENIZER_ERROR: Final = "Embedding tokenizer output is invalid."
_PREFIX_CACHE_SIZE: Final = 128

type Float32Array = NDArray[np.float32]


class _FastTokenizerBackend(Protocol):
    """Structural subset of a managed Hugging Face fast tokenizer."""

    is_fast: bool
    model_max_length: int

    def __call__(self, text: str, **kwargs: object) -> Mapping[str, object]: ...


class _SentenceModel(Protocol):
    """Structural subset of ``SentenceTransformer`` used by CodeScope."""

    tokenizer: _FastTokenizerBackend
    max_seq_length: int

    def get_embedding_dimension(self) -> int | None: ...

    def encode(
        self,
        inputs: list[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> object: ...


class ModelFactory(Protocol):
    """Injectable sentence-transformer construction boundary."""

    def __call__(
        self,
        model_name: str,
        *,
        device: str,
        local_files_only: bool,
    ) -> _SentenceModel: ...


def _default_model_factory(
    model_name: str,
    *,
    device: str,
    local_files_only: bool,
) -> _SentenceModel:
    from sentence_transformers import SentenceTransformer

    return cast(
        _SentenceModel,
        SentenceTransformer(
            model_name,
            device=device,
            local_files_only=local_files_only,
        ),
    )


def _default_cuda_available() -> bool:
    import torch

    return bool(torch.cuda.is_available())


class ManagedWordpieceTokenizer(WordpieceTokenizer):
    """Exact no-special-token adapter over the model-managed fast tokenizer.

    The default MiniLM tokenizer has a whitespace-delimited metadata boundary.
    After verifying that boundary once per immutable prefix, the bounded cache
    reuses its exact token count instead of reprocessing long signatures for
    every split candidate.
    """

    def __init__(
        self,
        backend: _FastTokenizerBackend,
        *,
        maximum_input_wordpieces: int,
        enable_prefix_cache: bool,
    ) -> None:
        if backend.is_fast is not True or maximum_input_wordpieces <= 0:
            raise ValueError(_TOKENIZER_ERROR)
        self._backend = backend
        self._maximum_input_wordpieces = maximum_input_wordpieces
        self._enable_prefix_cache = enable_prefix_cache
        self._prefix_counts: OrderedDict[str, int | None] = OrderedDict()
        self._cache_lock = Lock()

    @property
    def maximum_input_wordpieces(self) -> int:
        """Return the model lifecycle's effective input limit."""
        return self._maximum_input_wordpieces

    def count_wordpieces(self, text: str) -> int:
        """Return the exact wordpiece count with special tokens disabled."""
        input_ids, _ = self._encode(text, return_offsets=False)
        return len(input_ids)

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        """Return validated Python-character offsets for every wordpiece."""
        input_ids, offsets = self._encode(text, return_offsets=True)
        if offsets is None or len(offsets) != len(input_ids):
            raise ValueError(_TOKENIZER_ERROR)
        return offsets

    def count_prefixed_wordpieces(self, prefix: str, text: str) -> int:
        """Count canonical ``prefix + text`` with bounded exact prefix reuse."""
        if not self._enable_prefix_cache or not prefix.endswith("\n\n"):
            return self.count_wordpieces(prefix + text)

        with self._cache_lock:
            found = prefix in self._prefix_counts
            cached = self._prefix_counts.get(prefix)
            if found:
                self._prefix_counts.move_to_end(prefix)
        text_count = self.count_wordpieces(text)
        if cached is not None:
            return cached + text_count
        if found:
            return self.count_wordpieces(prefix + text)

        prefix_count = self.count_wordpieces(prefix)
        combined_count = self.count_wordpieces(prefix + text)
        reusable_count = prefix_count if combined_count == prefix_count + text_count else None
        with self._cache_lock:
            self._prefix_counts[prefix] = reusable_count
            self._prefix_counts.move_to_end(prefix)
            while len(self._prefix_counts) > _PREFIX_CACHE_SIZE:
                self._prefix_counts.popitem(last=False)
        return combined_count

    def _encode(
        self,
        text: str,
        *,
        return_offsets: bool,
    ) -> tuple[tuple[int, ...], tuple[TokenOffset, ...] | None]:
        if not isinstance(text, str):
            raise ValueError(_TOKENIZER_ERROR)
        try:
            encoded = self._backend(
                text,
                add_special_tokens=False,
                truncation=False,
                padding=False,
                return_attention_mask=False,
                return_token_type_ids=False,
                return_offsets_mapping=return_offsets,
            )
        except (LookupError, RuntimeError, TypeError, ValueError) as error:
            raise ValueError(_TOKENIZER_ERROR) from error
        if not isinstance(encoded, Mapping):
            raise ValueError(_TOKENIZER_ERROR)
        input_ids = self._validate_input_ids(encoded.get("input_ids"))
        if not return_offsets:
            return input_ids, None
        offsets = self._validate_offsets(encoded.get("offset_mapping"), text)
        return input_ids, offsets

    @staticmethod
    def _validate_input_ids(value: object) -> tuple[int, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(_TOKENIZER_ERROR)
        result: list[int] = []
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                raise ValueError(_TOKENIZER_ERROR)
            result.append(item)
        return tuple(result)

    @staticmethod
    def _validate_offsets(value: object, text: str) -> tuple[TokenOffset, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(_TOKENIZER_ERROR)
        result: list[TokenOffset] = []
        previous_end = 0
        for item in value:
            if isinstance(item, (str, bytes)) or not isinstance(item, Sequence) or len(item) != 2:
                raise ValueError(_TOKENIZER_ERROR)
            start, end = item
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < previous_end
                or start < 0
                or end <= start
                or end > len(text)
            ):
                raise ValueError(_TOKENIZER_ERROR)
            result.append((start, end))
            previous_end = end
        return tuple(result)


@dataclass(frozen=True, slots=True)
class _ModelBundle:
    model: _SentenceModel
    tokenizer: ManagedWordpieceTokenizer
    dimension: int
    maximum_input_wordpieces: int
    factory: object


class LocalEmbedder:
    """Lazy local sentence-transformer lifecycle for indexing and querying."""

    _model_cache: ClassVar[dict[tuple[str, str, int], _ModelBundle]] = {}
    _model_cache_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        config: EmbeddingsConfig,
        *,
        allow_download: bool = False,
        model_factory: ModelFactory | None = None,
        cuda_available: Callable[[], bool] | None = None,
    ) -> None:
        """Configure a lazy model lifecycle without loading model weights.

        Args:
            config: Immutable embedding settings.
            allow_download: Whether an explicit preparation path may use the network.
            model_factory: Injectable model construction boundary.
            cuda_available: Injectable CUDA capability check.
        """
        self._config = config
        self._allow_download = allow_download
        self._model_factory = model_factory or _default_model_factory
        self._cuda_available = cuda_available or _default_cuda_available

    @property
    def tokenizer(self) -> WordpieceTokenizer:
        """Return the exact tokenizer managed by the loaded model lifecycle."""
        return self._load_bundle().tokenizer

    @property
    def embedding_dimension(self) -> int:
        """Return the verified embedding width without loading the default model."""
        bundle = self._cached_bundle()
        if bundle is not None:
            return bundle.dimension
        spec = _MODEL_SPECS.get(self._config.model)
        if spec is None:
            raise RuntimeError(_MODEL_SPEC_ERROR)
        return spec[0]

    @property
    def maximum_input_wordpieces(self) -> int:
        """Return the verified effective tokenizer/model input limit."""
        bundle = self._cached_bundle()
        if bundle is not None:
            return bundle.maximum_input_wordpieces
        spec = _MODEL_SPECS.get(self._config.model)
        if spec is None:
            raise RuntimeError(_MODEL_SPEC_ERROR)
        return spec[1]

    def encode(self, texts: Sequence[str]) -> Float32Array:
        """Encode validated text in order as finite two-dimensional float32 vectors.

        Args:
            texts: Nonblank embedding inputs. A bare string is not a valid batch.

        Returns:
            One normalized or unnormalized embedding row per input.

        Raises:
            ValueError: If inputs or model output violate the embedding contract.
            RuntimeError: If the configured model or device cannot be prepared safely.
        """
        validated = self._validate_texts(texts)
        if not validated:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)

        bundle = self._load_bundle()
        try:
            output = bundle.model.encode(
                validated,
                batch_size=self._config.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=self._config.normalize,
            )
            array = np.asarray(output)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise ValueError(_MODEL_OUTPUT_ERROR) from error
        if array.ndim != 2 or array.shape != (len(validated), bundle.dimension):
            raise ValueError(_MODEL_OUTPUT_ERROR)
        try:
            result = array.astype(np.float32, copy=False)
        except (TypeError, ValueError) as error:
            raise ValueError(_MODEL_OUTPUT_ERROR) from error
        if not np.isfinite(result).all():
            raise ValueError(_MODEL_OUTPUT_ERROR)
        if self._config.normalize:
            norms = np.linalg.norm(result, axis=1)
            if not np.allclose(norms, 1.0, rtol=1e-3, atol=1e-4):
                raise ValueError(_MODEL_OUTPUT_ERROR)
        return result

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> list[str]:
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise ValueError(_INPUT_ERROR)
        result: list[str] = []
        for item in texts:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(_INPUT_ERROR)
            result.append(item)
        return result

    def _cache_key(self) -> tuple[str, str, int]:
        return self._config.model, self._config.device, id(self._model_factory)

    def _cached_bundle(self) -> _ModelBundle | None:
        with self._model_cache_lock:
            return self._model_cache.get(self._cache_key())

    def _load_bundle(self) -> _ModelBundle:
        key = self._cache_key()
        with self._model_cache_lock:
            cached = self._model_cache.get(key)
            if cached is not None:
                return cached
            if self._config.device == "cuda" and not self._cuda_available():
                raise RuntimeError(_CUDA_ERROR)
            try:
                model = self._model_factory(
                    self._config.model,
                    device=self._config.device,
                    local_files_only=not self._allow_download,
                )
            except (OSError, RuntimeError, ValueError) as error:
                raise RuntimeError(_MODEL_LOAD_ERROR) from error
            bundle = self._build_bundle(model)
            self._model_cache[key] = bundle
            return bundle

    def _build_bundle(self, model: _SentenceModel) -> _ModelBundle:
        try:
            dimension = model.get_embedding_dimension()
            maximum = model.max_seq_length
            backend = model.tokenizer
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimeError(_MODEL_LOAD_ERROR) from error
        if (
            not isinstance(dimension, int)
            or isinstance(dimension, bool)
            or dimension <= 0
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum <= 0
        ):
            raise RuntimeError(_MODEL_LOAD_ERROR)
        known_spec = _MODEL_SPECS.get(self._config.model)
        if known_spec is not None and (dimension, maximum) != known_spec:
            raise RuntimeError(_MODEL_LOAD_ERROR)
        try:
            tokenizer = ManagedWordpieceTokenizer(
                backend,
                maximum_input_wordpieces=maximum,
                enable_prefix_cache=self._config.model == DEFAULT_EMBEDDING_MODEL,
            )
        except ValueError as error:
            raise RuntimeError(_MODEL_LOAD_ERROR) from error
        return _ModelBundle(
            model=model,
            tokenizer=tokenizer,
            dimension=dimension,
            maximum_input_wordpieces=maximum,
            factory=self._model_factory,
        )
