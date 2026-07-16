"""Tests for root-level Git-ignore and configured exclusion matching."""

from pathlib import Path

import pytest

from codescope.exceptions import InvalidPathError
from codescope.utils.gitignore import GitIgnoreMatcher


def _matcher(
    tmp_path: Path,
    patterns: str,
    *,
    configured: tuple[str, ...] = (),
) -> GitIgnoreMatcher:
    (tmp_path / ".gitignore").write_text(patterns, encoding="utf-8")
    return GitIgnoreMatcher.from_root(tmp_path, configured_exclusions=configured)


@pytest.mark.parametrize(
    ("patterns", "path", "is_directory", "expected"),
    [
        ("ignored.py\n", "ignored.py", False, True),
        ("generated/\n", "generated", True, True),
        ("*.generated.py\n", "src/item.generated.py", False, True),
        ("/root_only.py\n", "root_only.py", False, True),
        ("/root_only.py\n", "nested/root_only.py", False, False),
        ("nested/*.py\n", "nested/item.py", False, True),
        ("*.py\n!keep.py\n", "keep.py", False, False),
        ("*.py\n!keep.py\n", "drop.py", False, True),
    ],
)
def test_root_gitignore_patterns_match_posix_paths(
    tmp_path: Path,
    patterns: str,
    path: str,
    is_directory: bool,
    expected: bool,
) -> None:
    # Arrange
    matcher = _matcher(tmp_path, patterns)

    # Act and Assert
    assert matcher.repository_match(path, is_directory=is_directory) is expected


def test_windows_separator_input_is_normalized_for_matching(tmp_path: Path) -> None:
    # Arrange
    matcher = _matcher(tmp_path, "src/generated.py\n")

    # Act and Assert
    assert matcher.repository_match(r"src\generated.py", is_directory=False) is True


def test_configured_exclusion_remains_separate_from_gitignore_negation(tmp_path: Path) -> None:
    # Arrange
    matcher = _matcher(tmp_path, "!private.py\n", configured=("private.py",))

    # Act and Assert
    assert matcher.repository_match("private.py", is_directory=False) is False
    assert matcher.configured_match("private.py", is_directory=False) is True


def test_missing_root_gitignore_creates_empty_repository_spec(tmp_path: Path) -> None:
    # Arrange and Act
    matcher = GitIgnoreMatcher.from_root(tmp_path, configured_exclusions=())

    # Assert
    assert matcher.repository_match("src/example.py", is_directory=False) is False


def test_symlinked_root_gitignore_is_rejected_safely(tmp_path: Path) -> None:
    # Arrange
    external = tmp_path / "external-ignore"
    external.write_text("*.py\n", encoding="utf-8")
    link = tmp_path / ".gitignore"
    try:
        link.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(InvalidPathError) as error_info:
        GitIgnoreMatcher.from_root(tmp_path, configured_exclusions=())
    assert str(tmp_path) not in str(error_info.value)


def test_nested_gitignore_is_not_automatically_loaded(tmp_path: Path) -> None:
    # Arrange
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".gitignore").write_text("ignored.py\n", encoding="utf-8")

    # Act
    matcher = GitIgnoreMatcher.from_root(tmp_path, configured_exclusions=())

    # Assert
    assert matcher.repository_match("nested/ignored.py", is_directory=False) is False
