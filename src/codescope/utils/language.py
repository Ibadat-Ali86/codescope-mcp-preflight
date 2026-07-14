"""Python-only language and extension validation."""

from typing import Final, Literal

from codescope.exceptions import InvalidLanguageError

type SupportedLanguage = Literal["python"]

SUPPORTED_LANGUAGES: Final[tuple[SupportedLanguage, ...]] = ("python",)
SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (".py", ".pyi")


def normalize_language(language: str) -> SupportedLanguage:
    """Normalize a supported language name.

    Args:
        language: User-provided language name.

    Returns:
        The canonical Python language name.

    Raises:
        InvalidLanguageError: If the value is empty or unsupported.
    """
    if not isinstance(language, str) or language.strip().casefold() != "python":
        raise InvalidLanguageError("Only the Python language is supported.")
    return "python"


def language_from_extension(extension: str) -> SupportedLanguage:
    """Map a canonical supported extension to Python.

    Args:
        extension: A complete file extension including its leading dot.

    Returns:
        The canonical Python language name.

    Raises:
        InvalidLanguageError: If the extension is not exactly supported.
    """
    if not isinstance(extension, str) or extension not in SUPPORTED_EXTENSIONS:
        raise InvalidLanguageError("Only the .py and .pyi extensions are supported.")
    return "python"
