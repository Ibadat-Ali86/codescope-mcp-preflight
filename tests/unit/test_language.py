"""Tests for Python-only language validation."""

import pytest

from codescope.exceptions import ErrorCode, InvalidLanguageError
from codescope.utils.language import language_from_extension, normalize_language


@pytest.mark.parametrize("language", ["python", " Python ", "PYTHON", "pYtHoN"])
def test_normalize_language_supported_spellings_return_python(language: str) -> None:
    # Arrange and Act
    result = normalize_language(language)

    # Assert
    assert result == "python"


@pytest.mark.parametrize("language", ["", "   ", "typescript", "python3", ".py"])
def test_normalize_language_invalid_values_raise_stable_error(language: str) -> None:
    # Arrange and Act
    with pytest.raises(InvalidLanguageError) as error_info:
        normalize_language(language)

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_LANGUAGE
    assert str(error_info.value) == "Only the Python language is supported."


@pytest.mark.parametrize("extension", [".py", ".pyi"])
def test_language_from_extension_supported_values_return_python(extension: str) -> None:
    # Arrange and Act
    result = language_from_extension(extension)

    # Assert
    assert result == "python"


@pytest.mark.parametrize(
    "extension",
    ["", "py", "pyi", "*.py", ".PY", ".PyI", ".py ", "file.py", "src/file.py", ".js"],
)
def test_language_from_extension_unsupported_values_raise_stable_error(extension: str) -> None:
    # Arrange and Act
    with pytest.raises(InvalidLanguageError) as error_info:
        language_from_extension(extension)

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_LANGUAGE
    assert str(error_info.value) == "Only the .py and .pyi extensions are supported."
