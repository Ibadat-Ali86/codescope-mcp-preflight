"""Immutable validated application configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from codescope.exceptions import CodeScopeError, InvalidConfigError
from codescope.utils.language import SupportedLanguage, language_from_extension, normalize_language
from codescope.utils.path_guard import validate_config_file, validate_repository_root

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class _FrozenConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def _non_empty(value: str, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field_name} must not be empty")
    return trimmed


def _immutable_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} entries must be strings")
    return tuple(value)


class ServerConfig(_FrozenConfigModel):
    """MCP server identity and transport configuration."""

    name: NonEmptyString
    transport: Literal["stdio"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim and validate the server name."""
        return _non_empty(value, "server.name")


class IndexConfig(_FrozenConfigModel):
    """Repository indexing boundaries and chunking limits."""

    root: Path
    languages: tuple[SupportedLanguage, ...]
    include_extensions: tuple[str, ...]
    exclude: tuple[str, ...]
    max_file_size_kb: PositiveInt
    max_chunk_wordpieces: PositiveInt
    chunk_overlap_wordpieces: NonNegativeInt
    follow_symlinks: bool

    @field_validator("root")
    @classmethod
    def validate_root(cls, value: Path) -> Path:
        """Require an existing repository directory."""
        return validate_repository_root(value)

    @field_validator("languages", mode="before")
    @classmethod
    def validate_languages(cls, value: Any) -> tuple[SupportedLanguage, ...]:
        """Normalize the immutable Python-only language allowlist."""
        entries = _immutable_string_tuple(value, "index.languages")
        normalized = tuple(normalize_language(entry) for entry in entries)
        if len(normalized) != len(set(normalized)):
            raise ValueError("index.languages must not contain duplicates")
        return normalized

    @field_validator("include_extensions", mode="before")
    @classmethod
    def validate_extensions(cls, value: Any) -> tuple[str, ...]:
        """Validate canonical immutable source extensions."""
        entries = _immutable_string_tuple(value, "index.include_extensions")
        for extension in entries:
            language_from_extension(extension)
        if len(entries) != len(set(entries)):
            raise ValueError("index.include_extensions must not contain duplicates")
        return entries

    @field_validator("exclude", mode="before")
    @classmethod
    def validate_exclusions(cls, value: Any) -> tuple[str, ...]:
        """Validate and freeze exclusion entries."""
        entries = _immutable_string_tuple(value, "index.exclude")
        trimmed = tuple(_non_empty(entry, "index.exclude entry") for entry in entries)
        return trimmed

    @model_validator(mode="after")
    def validate_chunk_limits(self) -> Self:
        """Require overlap to remain below the chunk budget."""
        if self.chunk_overlap_wordpieces >= self.max_chunk_wordpieces:
            raise ValueError("chunk overlap must be smaller than the chunk limit")
        return self


class EmbeddingsConfig(_FrozenConfigModel):
    """Syntactic embedding-model configuration for a future phase."""

    model: NonEmptyString
    batch_size: PositiveInt
    device: Literal["cpu", "cuda"]
    normalize: bool

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        """Trim and validate the model identifier without loading it."""
        return _non_empty(value, "embeddings.model")


class StorageConfig(_FrozenConfigModel):
    """Local runtime storage location and collection name."""

    path: Path
    collection: NonEmptyString

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: Path) -> Path:
        """Resolve a storage path and reject existing non-directories."""
        try:
            resolved = value.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise ValueError("storage.path could not be resolved") from error
        if resolved.exists() and not resolved.is_dir():
            raise ValueError("storage.path must be a directory when it exists")
        return resolved

    @field_validator("collection")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        """Trim and validate the storage collection name."""
        return _non_empty(value, "storage.collection")


class SearchConfig(_FrozenConfigModel):
    """Default and maximum public query limits."""

    default_limit: PositiveInt
    maximum_limit: PositiveInt
    minimum_query_characters: PositiveInt

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        """Require the default result limit to fit within the maximum."""
        if self.default_limit > self.maximum_limit:
            raise ValueError("default search limit must not exceed maximum search limit")
        return self


class AppConfig(_FrozenConfigModel):
    """Complete immutable CodeScope application configuration."""

    server: ServerConfig
    index: IndexConfig
    embeddings: EmbeddingsConfig
    storage: StorageConfig
    search: SearchConfig

    def with_index_root(self, root: Path) -> AppConfig:
        """Return a newly validated configuration with a different index root.

        Relative overrides are resolved against the invocation working directory by
        ``Path.resolve`` inside repository-root validation.

        Args:
            root: Existing directory to use for one future indexing run.

        Returns:
            A new immutable application configuration.
        """
        index_data = self.index.model_dump()
        index_data["root"] = root
        new_index = IndexConfig.model_validate(index_data)
        return AppConfig(
            server=self.server,
            index=new_index,
            embeddings=self.embeddings,
            storage=self.storage,
            search=self.search,
        )


def _resolve_config_paths(data: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    index = data.get("index")
    storage = data.get("storage")
    if not isinstance(index, dict) or not isinstance(storage, dict):
        return data
    root = index.get("root")
    storage_path = storage.get("path")
    if isinstance(root, str):
        index["root"] = config_dir / root
    if isinstance(storage_path, str):
        storage["path"] = config_dir / storage_path
    return data


def load_config(config_path: Path) -> AppConfig:
    """Load and validate a CodeScope TOML configuration file.

    Args:
        config_path: Path to the configuration file.

    Returns:
        A complete immutable application configuration.

    Raises:
        InvalidConfigError: If the file or any configuration value is unsafe or invalid.
    """
    try:
        resolved_config = validate_config_file(config_path)
        with resolved_config.open("rb") as config_file:
            raw_data = tomllib.load(config_file)
        data = _resolve_config_paths(raw_data, resolved_config.parent)
        return AppConfig.model_validate(data)
    except InvalidConfigError:
        raise
    except (
        CodeScopeError,
        OSError,
        RuntimeError,
        tomllib.TOMLDecodeError,
        ValidationError,
    ) as error:
        raise InvalidConfigError(
            "The configuration file is missing, unreadable, malformed, or invalid."
        ) from error
