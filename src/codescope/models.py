"""Immutable public data models for CodeScope."""

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveLine = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
FiniteScore = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class _PublicModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def _validate_required_text(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _validate_optional_text(value: str | None, field_name: str) -> str | None:
    if value is not None:
        _validate_required_text(value, field_name)
    return value


def _validate_public_path(value: str) -> str:
    if not value or value.strip() != value or "\\" in value:
        raise ValueError("file path must be a non-empty project-relative POSIX path")
    segments = value.split("/")
    windows_path = PureWindowsPath(value)
    if (
        PurePosixPath(value).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError("file path must be a non-empty project-relative POSIX path")
    return value


class _LineRangeModel(_PublicModel):
    start_line: PositiveLine
    end_line: PositiveLine

    @model_validator(mode="after")
    def validate_line_range(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class Symbol(_LineRangeModel):
    """A named Python source-code entity."""

    name: NonEmptyString
    kind: Literal["function", "async_function", "class", "method"]
    file: str
    signature: NonEmptyString
    qualified_name: NonEmptyString
    docstring: str | None
    language: Literal["python"]

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require a project-relative POSIX file path."""
        return _validate_public_path(value)

    @field_validator("name", "signature", "qualified_name")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty required symbol text."""
        return _validate_required_text(value, "symbol field")

    @field_validator("docstring")
    @classmethod
    def validate_docstring(cls, value: str | None) -> str | None:
        """Reject an empty docstring when one is supplied."""
        return _validate_optional_text(value, "docstring")


class CodeChunk(_LineRangeModel):
    """A traceable Python source chunk prepared for future indexing."""

    id: NonEmptyString
    text: NonEmptyString
    file: str
    language: Literal["python"]
    symbol_name: str | None
    qualified_name: str | None
    chunk_index: NonNegativeInt
    content_hash: NonEmptyString

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require a project-relative POSIX file path."""
        return _validate_public_path(value)

    @field_validator("id", "text", "content_hash")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty required chunk text."""
        return _validate_required_text(value, "chunk field")

    @field_validator("symbol_name", "qualified_name")
    @classmethod
    def validate_optional_names(cls, value: str | None) -> str | None:
        """Reject empty optional names when supplied."""
        return _validate_optional_text(value, "chunk symbol field")


class SearchResult(_LineRangeModel):
    """A ranked source-code search result."""

    file: str
    symbol: str | None
    qualified_name: str | None
    language: NonEmptyString
    snippet: NonEmptyString
    relevance_score: FiniteScore

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require a project-relative POSIX file path."""
        return _validate_public_path(value)

    @field_validator("language", "snippet")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty required search-result text."""
        return _validate_required_text(value, "search result field")

    @field_validator("symbol", "qualified_name")
    @classmethod
    def validate_optional_names(cls, value: str | None) -> str | None:
        """Reject empty optional names when supplied."""
        return _validate_optional_text(value, "search result symbol field")


class SymbolResult(_LineRangeModel):
    """A result from exact or partial symbol lookup."""

    name: NonEmptyString
    qualified_name: NonEmptyString
    kind: NonEmptyString
    file: str
    signature: NonEmptyString
    docstring: str | None

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require a project-relative POSIX file path."""
        return _validate_public_path(value)

    @field_validator("name", "qualified_name", "kind", "signature")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty required symbol-result text."""
        return _validate_required_text(value, "symbol result field")

    @field_validator("docstring")
    @classmethod
    def validate_docstring(cls, value: str | None) -> str | None:
        """Reject an empty docstring when one is supplied."""
        return _validate_optional_text(value, "docstring")


class IndexStatus(_PublicModel):
    """Serializable status of the local CodeScope index."""

    index_exists: bool
    index_root: str | None
    total_files: NonNegativeInt
    total_chunks: NonNegativeInt
    total_symbols: NonNegativeInt
    languages: Mapping[str, int]
    last_indexed: str | None
    index_size_bytes: NonNegativeInt
    embedding_model: NonEmptyString

    @field_validator("index_root")
    @classmethod
    def validate_index_root(cls, value: str | None) -> str | None:
        """Prevent absolute host paths in public index status."""
        if value is not None:
            if value == ".":
                return value
            return _validate_public_path(value)
        return None

    @field_validator("languages", mode="after")
    @classmethod
    def freeze_languages(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        """Defensively copy and freeze language counts."""
        if any(not key.strip() for key in value):
            raise ValueError("language count keys must not be empty")
        if any(count < 0 for count in value.values()):
            raise ValueError("language counts must not be negative")
        return MappingProxyType(dict(value))

    @field_serializer("languages")
    def serialize_languages(self, value: Mapping[str, int]) -> dict[str, int]:
        """Serialize immutable language counts as a normal JSON object."""
        return dict(value)

    @field_validator("last_indexed")
    @classmethod
    def validate_last_indexed(cls, value: str | None) -> str | None:
        """Reject an empty timestamp when one is supplied."""
        return _validate_optional_text(value, "last_indexed")

    @field_validator("embedding_model")
    @classmethod
    def validate_embedding_model(cls, value: str) -> str:
        """Reject an empty embedding model identifier."""
        return _validate_required_text(value, "embedding_model")


class ErrorResponse(_PublicModel):
    """Stable public error response returned by future MCP tools."""

    error: Literal[True]
    code: NonEmptyString
    message: NonEmptyString
    suggestion: NonEmptyString

    @field_validator("code", "message", "suggestion")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty public error-response fields."""
        return _validate_required_text(value, "error response field")
