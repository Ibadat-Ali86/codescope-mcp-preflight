"""Tests for immutable public CodeScope models."""

import json
from math import inf, nan
from typing import Any

import pytest
from pydantic import ValidationError

from codescope.exceptions import (
    ErrorCode,
    IndexNotFoundError,
    InvalidConfigError,
    InvalidLanguageError,
    InvalidLimitError,
    InvalidPathError,
    InvalidQueryError,
    ParseFailedError,
    QueryFailedError,
    StorageFailedError,
)
from codescope.models import (
    CodeChunk,
    ErrorResponse,
    IndexStatus,
    SearchResult,
    Symbol,
    SymbolResult,
)


def _symbol_data() -> dict[str, Any]:
    return {
        "name": "validate_email",
        "kind": "function",
        "file": "src/validators.py",
        "start_line": 2,
        "end_line": 5,
        "signature": "def validate_email(value: str) -> bool:",
        "qualified_name": "validate_email",
        "docstring": "Validate an email address.",
        "language": "python",
    }


def _chunk_data() -> dict[str, Any]:
    return {
        "id": "chunk-1",
        "text": "def validate_email(value: str) -> bool:\n    return '@' in value",
        "file": "src/validators.py",
        "start_line": 2,
        "end_line": 3,
        "language": "python",
        "symbol_name": "validate_email",
        "qualified_name": "validate_email",
        "chunk_index": 0,
        "content_hash": "abc123",
    }


def _search_data() -> dict[str, Any]:
    return {
        "file": "src/validators.py",
        "start_line": 2,
        "end_line": 3,
        "symbol": "validate_email",
        "qualified_name": "validate_email",
        "language": "python",
        "snippet": "def validate_email(value: str) -> bool: ...",
        "relevance_score": 0.9,
    }


def _symbol_result_data() -> dict[str, Any]:
    data = _symbol_data()
    data.pop("language")
    return data


def _status_data(languages: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "index_exists": True,
        "index_root": "sample_repo",
        "total_files": 2,
        "total_chunks": 3,
        "total_symbols": 2,
        "languages": languages if languages is not None else {"python": 2},
        "last_indexed": "2026-07-15T00:00:00Z",
        "index_size_bytes": 1024,
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    }


@pytest.mark.parametrize(
    "model",
    [
        Symbol(**_symbol_data()),
        CodeChunk(**_chunk_data()),
        SearchResult(**_search_data()),
        SymbolResult(**_symbol_result_data()),
        IndexStatus(**_status_data()),
        ErrorResponse(
            error=True, code="INVALID_PATH", message="Invalid path.", suggestion="Retry."
        ),
    ],
)
def test_public_model_valid_value_serializes_to_json(model: Any) -> None:
    # Arrange and Act
    serialized = model.model_dump_json()

    # Assert
    assert isinstance(json.loads(serialized), dict)
    assert serialized == model.model_dump_json()


@pytest.mark.parametrize(
    ("model_type", "data"),
    [
        (Symbol, _symbol_data()),
        (CodeChunk, _chunk_data()),
        (SearchResult, _search_data()),
        (SymbolResult, _symbol_result_data()),
        (IndexStatus, _status_data()),
    ],
)
def test_public_models_forbid_extra_fields(model_type: type[Any], data: dict[str, Any]) -> None:
    # Arrange
    data["unexpected"] = "value"

    # Act and Assert
    with pytest.raises(ValidationError):
        model_type(**data)


def test_public_model_assignment_is_frozen() -> None:
    # Arrange
    model = Symbol(**_symbol_data())

    # Act and Assert
    with pytest.raises(ValidationError):
        model.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("field", ["name", "signature", "qualified_name"])
def test_symbol_empty_required_text_is_rejected(field: str) -> None:
    # Arrange
    data = _symbol_data()
    data[field] = "   "

    # Act and Assert
    with pytest.raises(ValidationError):
        Symbol(**data)


@pytest.mark.parametrize(("start_line", "end_line"), [(0, 1), (-1, 1), (2, 0), (5, 4)])
def test_symbol_invalid_line_range_is_rejected(start_line: int, end_line: int) -> None:
    # Arrange
    data = _symbol_data()
    data.update(start_line=start_line, end_line=end_line)

    # Act and Assert
    with pytest.raises(ValidationError):
        Symbol(**data)


@pytest.mark.parametrize("score", [-0.1, 1.1, nan, inf, -inf])
def test_search_result_invalid_relevance_score_is_rejected(score: float) -> None:
    # Arrange
    data = _search_data()
    data["relevance_score"] = score

    # Act and Assert
    with pytest.raises(ValidationError):
        SearchResult(**data)


def test_symbol_unsupported_language_is_rejected() -> None:
    # Arrange
    data = _symbol_data()
    data["language"] = "typescript"

    # Act and Assert
    with pytest.raises(ValidationError):
        Symbol(**data)


def test_code_chunk_negative_index_is_rejected() -> None:
    # Arrange
    data = _chunk_data()
    data["chunk_index"] = -1

    # Act and Assert
    with pytest.raises(ValidationError):
        CodeChunk(**data)


@pytest.mark.parametrize(
    "field",
    ["total_files", "total_chunks", "total_symbols", "index_size_bytes"],
)
def test_index_status_negative_counter_is_rejected(field: str) -> None:
    # Arrange
    data = _status_data()
    data[field] = -1

    # Act and Assert
    with pytest.raises(ValidationError):
        IndexStatus(**data)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../secret.py",
        "src/../secret.py",
        "src/./file.py",
        "src\\file.py",
        "C:\\secret.py",
        "C:/secret.py",
        "//server/share/file.py",
        "\\\\server\\share\\file.py",
        "src//file.py",
    ],
)
def test_symbol_unsafe_public_file_path_is_rejected(path: str) -> None:
    # Arrange
    data = _symbol_data()
    data["file"] = path

    # Act and Assert
    with pytest.raises(ValidationError):
        Symbol(**data)


@pytest.mark.parametrize("index_root", ["/home/user/repo", "C:\\repo", "../repo"])
def test_index_status_unsafe_public_root_is_rejected(index_root: str) -> None:
    # Arrange
    data = _status_data()
    data["index_root"] = index_root

    # Act and Assert
    with pytest.raises(ValidationError):
        IndexStatus(**data)


def test_index_status_languages_defensively_copies_input() -> None:
    # Arrange
    source = {"python": 2}
    status = IndexStatus(**_status_data(source))

    # Act
    source["python"] = 99

    # Assert
    assert status.languages["python"] == 2


def test_index_status_languages_blocks_item_assignment() -> None:
    # Arrange
    status = IndexStatus(**_status_data())

    # Act and Assert
    with pytest.raises(TypeError):
        status.languages["python"] = 4  # type: ignore[index]


def test_index_status_languages_blocks_backing_attribute_reassignment() -> None:
    # Arrange
    status = IndexStatus(**_status_data())

    # Act and Assert
    with pytest.raises(AttributeError):
        status.languages._values = {"python": -1}  # type: ignore[attr-defined]


@pytest.mark.parametrize("method", ["update", "clear", "pop", "popitem", "setdefault"])
def test_index_status_languages_exposes_no_mutation_methods(method: str) -> None:
    # Arrange
    status = IndexStatus(**_status_data())

    # Act and Assert
    with pytest.raises(AttributeError):
        getattr(status.languages, method)


def test_index_status_languages_serializes_as_json_object() -> None:
    # Arrange
    status = IndexStatus(**_status_data())

    # Act
    payload = json.loads(status.model_dump_json())

    # Assert
    assert payload["languages"] == {"python": 2}
    assert status.model_dump()["languages"] == {"python": 2}


def test_index_status_negative_language_count_is_rejected() -> None:
    # Arrange and Act and Assert
    with pytest.raises(ValidationError):
        IndexStatus(**_status_data({"python": -1}))


def test_error_response_false_error_flag_is_rejected() -> None:
    # Arrange and Act and Assert
    with pytest.raises(ValidationError):
        ErrorResponse(error=False, code="INVALID_PATH", message="Invalid.", suggestion="Retry.")


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (IndexNotFoundError, ErrorCode.INDEX_NOT_FOUND),
        (InvalidPathError, ErrorCode.INVALID_PATH),
        (InvalidQueryError, ErrorCode.INVALID_QUERY),
        (InvalidLanguageError, ErrorCode.INVALID_LANGUAGE),
        (InvalidLimitError, ErrorCode.INVALID_LIMIT),
        (InvalidConfigError, ErrorCode.INVALID_CONFIG),
        (ParseFailedError, ErrorCode.PARSE_FAILED),
        (StorageFailedError, ErrorCode.STORAGE_FAILED),
        (QueryFailedError, ErrorCode.QUERY_FAILED),
    ],
)
def test_domain_exception_type_has_stable_error_code(
    error_type: type[Exception], code: ErrorCode
) -> None:
    # Arrange and Act
    error = error_type("Safe message.")

    # Assert
    assert error.code is code
    assert str(error) == "Safe message."
