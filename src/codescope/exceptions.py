"""Stable domain exceptions for CodeScope."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar


class ErrorCode(StrEnum):
    """Machine-readable error codes exposed by CodeScope."""

    INDEX_NOT_FOUND = "INDEX_NOT_FOUND"
    INVALID_PATH = "INVALID_PATH"
    INVALID_QUERY = "INVALID_QUERY"
    INVALID_LANGUAGE = "INVALID_LANGUAGE"
    INVALID_LIMIT = "INVALID_LIMIT"
    INVALID_CONFIG = "INVALID_CONFIG"
    PARSE_FAILED = "PARSE_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"
    QUERY_FAILED = "QUERY_FAILED"


class CodeScopeError(Exception):
    """Base class for safe, expected CodeScope failures."""

    code: ClassVar[ErrorCode]
    default_suggestion: ClassVar[str] = "Review the request and try again."

    def __init__(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize a safe domain error.

        Args:
            message: Public message that contains no sensitive values.
            suggestion: Optional public recovery guidance.
            metadata: Optional pre-sanitized diagnostic metadata.
        """
        self.message = message
        self.suggestion = suggestion or self.default_suggestion
        self.metadata = MappingProxyType(dict(metadata or {}))
        super().__init__(message)


class IndexNotFoundError(CodeScopeError):
    """Raised when no usable CodeScope index exists."""

    code = ErrorCode.INDEX_NOT_FOUND
    default_suggestion = "Build the index before running a query."


class InvalidPathError(CodeScopeError):
    """Raised when a filesystem path fails a security check."""

    code = ErrorCode.INVALID_PATH
    default_suggestion = "Choose an existing path within the configured repository root."


class InvalidQueryError(CodeScopeError):
    """Raised when a query does not meet the public input contract."""

    code = ErrorCode.INVALID_QUERY
    default_suggestion = "Provide a non-empty query that meets the configured limits."


class InvalidLanguageError(CodeScopeError):
    """Raised when a language or extension is not supported."""

    code = ErrorCode.INVALID_LANGUAGE
    default_suggestion = "Use Python with the .py or .pyi extension."


class InvalidLimitError(CodeScopeError):
    """Raised when a numeric request limit is outside its allowed range."""

    code = ErrorCode.INVALID_LIMIT
    default_suggestion = "Use a positive limit within the configured maximum."


class InvalidConfigError(CodeScopeError):
    """Raised when a configuration file cannot be loaded safely."""

    code = ErrorCode.INVALID_CONFIG
    default_suggestion = "Review codescope.toml and its referenced paths."


class ParseFailedError(CodeScopeError):
    """Raised when source parsing cannot complete safely."""

    code = ErrorCode.PARSE_FAILED
    default_suggestion = "Review the source file syntax and try indexing again."


class StorageFailedError(CodeScopeError):
    """Raised when local index storage cannot complete an operation."""

    code = ErrorCode.STORAGE_FAILED
    default_suggestion = "Check the configured storage directory and retry."


class QueryFailedError(CodeScopeError):
    """Raised when a repository query cannot complete safely."""

    code = ErrorCode.QUERY_FAILED
    default_suggestion = "Verify the index state and retry the query."
