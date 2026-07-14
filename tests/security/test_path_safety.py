"""Security tests for centralized filesystem path validation."""

import os
from pathlib import Path

import pytest

from codescope.exceptions import ErrorCode, InvalidPathError
from codescope.utils.path_guard import (
    safe_resolve,
    validate_repository_root,
    validate_reset_target,
)


def _create_symlink(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")


def test_safe_resolve_valid_relative_child_file_returns_resolved(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    candidate = root / "module.py"
    candidate.write_text("value = 1\n", encoding="utf-8")

    # Act
    result = safe_resolve(Path("module.py"), root)

    # Assert
    assert result == candidate.resolve()


def test_safe_resolve_valid_nested_file_returns_resolved(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    nested = root / "src"
    nested.mkdir(parents=True)
    candidate = nested / "module.pyi"
    candidate.write_text("value: int\n", encoding="utf-8")

    # Act
    result = safe_resolve(Path("src/module.pyi"), root)

    # Assert
    assert result == candidate.resolve()


def test_safe_resolve_contained_absolute_file_returns_resolved(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    candidate = root / "module.py"
    candidate.write_text("", encoding="utf-8")

    # Act and Assert
    assert safe_resolve(candidate, root) == candidate.resolve()


@pytest.mark.parametrize("candidate", [Path("../outside.py"), Path("src/../module.py")])
def test_safe_resolve_traversal_spelling_is_rejected(tmp_path: Path, candidate: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "module.py").write_text("", encoding="utf-8")
    (tmp_path / "outside.py").write_text("", encoding="utf-8")

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(candidate, root)


def test_safe_resolve_external_absolute_path_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "outside.py"
    external.write_text("", encoding="utf-8")

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(external, root)


def test_validate_repository_root_missing_path_is_rejected(tmp_path: Path) -> None:
    # Arrange and Act and Assert
    with pytest.raises(InvalidPathError):
        validate_repository_root(tmp_path / "missing")


def test_validate_repository_root_regular_file_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root_file = tmp_path / "file.py"
    root_file.write_text("", encoding="utf-8")

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_repository_root(root_file)


def test_safe_resolve_missing_candidate_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(Path("missing.py"), root)


def test_safe_resolve_directory_candidate_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    candidate = root / "directory"
    candidate.mkdir(parents=True)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(candidate, root)


def test_safe_resolve_fifo_candidate_is_rejected(tmp_path: Path) -> None:
    # Arrange
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this operating system")
    root = tmp_path / "repo"
    root.mkdir()
    candidate = root / "pipe"
    os.mkfifo(candidate)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(candidate, root)


def test_safe_resolve_internal_symlink_is_rejected_by_default(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "target.py"
    target.write_text("", encoding="utf-8")
    link = root / "link.py"
    _create_symlink(link, target)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(link, root)


def test_safe_resolve_internal_symlink_is_accepted_when_enabled(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "target.py"
    target.write_text("", encoding="utf-8")
    link = root / "link.py"
    _create_symlink(link, target)

    # Act and Assert
    assert safe_resolve(link, root, follow_symlinks=True) == target.resolve()


def test_safe_resolve_symlinked_intermediate_component_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    real = root / "real"
    real.mkdir(parents=True)
    target = real / "target.py"
    target.write_text("", encoding="utf-8")
    link = root / "linked"
    _create_symlink(link, real, target_is_directory=True)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(Path("linked/target.py"), root)


def test_safe_resolve_external_symlink_is_rejected_even_when_enabled(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "outside.py"
    external.write_text("", encoding="utf-8")
    link = root / "link.py"
    _create_symlink(link, external)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        safe_resolve(link, root, follow_symlinks=True)


def test_validate_reset_target_exact_runtime_directory_is_accepted(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)

    # Act
    result = validate_reset_target(
        Path(".codescope"), repository_root=root, configured_runtime_path=runtime
    )

    # Assert
    assert result == runtime.resolve()


def test_validate_reset_target_equivalent_absolute_spelling_is_accepted(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)

    # Act and Assert
    assert (
        validate_reset_target(
            runtime.resolve(), repository_root=root, configured_runtime_path=Path(".codescope")
        )
        == runtime.resolve()
    )


def test_validate_reset_target_repository_root_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(root, repository_root=root, configured_runtime_path=root)


def test_validate_reset_target_outside_repository_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(outside, repository_root=root, configured_runtime_path=runtime)


def test_validate_reset_target_parent_of_repository_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "parent/repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(
            tmp_path / "parent", repository_root=root, configured_runtime_path=runtime
        )


def test_validate_reset_target_mismatched_runtime_directory_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    other = root / "other"
    runtime.mkdir(parents=True)
    other.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(other, repository_root=root, configured_runtime_path=runtime)


def test_validate_reset_target_symlink_escape_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runtime_link = root / ".codescope"
    _create_symlink(runtime_link, outside, target_is_directory=True)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(
            runtime_link, repository_root=root, configured_runtime_path=runtime_link
        )


def test_validate_reset_target_missing_directory_is_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    runtime = root / ".codescope"

    # Act and Assert
    with pytest.raises(InvalidPathError):
        validate_reset_target(runtime, repository_root=root, configured_runtime_path=runtime)


def test_path_error_does_not_leak_absolute_or_attacker_controlled_path(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    attacker_path = Path("../super-secret-attacker-value")

    # Act
    with pytest.raises(InvalidPathError) as error_info:
        safe_resolve(attacker_path, root)

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_PATH
    assert str(tmp_path) not in str(error_info.value)
    assert str(attacker_path) not in str(error_info.value)
