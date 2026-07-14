"""Central security-sensitive filesystem path validation."""

import stat
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from codescope.exceptions import InvalidPathError


def _raise_invalid_path(message: str, error: OSError | RuntimeError | None = None) -> NoReturn:
    if error is None:
        raise InvalidPathError(message)
    raise InvalidPathError(message) from error


def _strict_resolve(path: Path, message: str) -> Path:
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        _raise_invalid_path(message, error)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _candidate_beneath_root(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        _raise_invalid_path("The requested path is outside the repository root.")
    if any(part in {".", ".."} for part in relative.parts):
        _raise_invalid_path("Path traversal is not allowed.")
    return candidate


def _reject_symlink_components(candidate: Path, root: Path) -> None:
    try:
        relative = candidate.relative_to(root)
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink() or current.is_junction():
                _raise_invalid_path("Symbolic links are disabled for this operation.")
    except OSError as error:
        _raise_invalid_path("The requested path could not be inspected safely.", error)


def _resolved_contained_path(
    path: Path,
    root: Path,
    *,
    follow_symlinks: bool,
    missing_message: str,
) -> Path:
    candidate = _candidate_beneath_root(path, root)
    if not follow_symlinks:
        _reject_symlink_components(candidate, root)
    resolved = _strict_resolve(candidate, missing_message)
    if resolved == root or not _is_relative_to(resolved, root):
        _raise_invalid_path("The requested path is outside the repository root.")
    return resolved


def _require_mode(path: Path, predicate: Callable[[int], bool], message: str) -> None:
    try:
        mode = path.stat().st_mode
    except OSError as error:
        _raise_invalid_path("The requested path could not be inspected safely.", error)
    if not predicate(mode):
        _raise_invalid_path(message)


def validate_repository_root(root: Path) -> Path:
    """Resolve and validate an existing repository root directory.

    Args:
        root: Repository root to validate.

    Returns:
        The strictly resolved directory.

    Raises:
        InvalidPathError: If the root is missing or is not a directory.
    """
    resolved = _strict_resolve(root, "The repository root does not exist or is inaccessible.")
    _require_mode(resolved, stat.S_ISDIR, "The repository root must be a directory.")
    return resolved


def validate_config_file(path: Path) -> Path:
    """Resolve a configuration file without following symlink components.

    Filesystem state can change after validation. The caller must open the returned
    path immediately and must not cache a prior validation indefinitely.

    Args:
        path: Configuration file path to validate.

    Returns:
        The strictly resolved regular file.

    Raises:
        InvalidPathError: If the path is missing, not regular, or contains a symlink.
    """
    try:
        candidate = path if path.is_absolute() else Path.cwd() / path
    except OSError as error:
        _raise_invalid_path("The configuration path could not be inspected safely.", error)
    anchor = Path(candidate.anchor)
    if not candidate.is_absolute() or not candidate.anchor:
        _raise_invalid_path("The configuration path could not be resolved safely.")
    _reject_symlink_components(candidate, anchor)
    resolved = _strict_resolve(
        candidate,
        "The configuration file does not exist or is inaccessible.",
    )
    _require_mode(resolved, stat.S_ISREG, "The configuration path must be a regular file.")
    return resolved


def safe_resolve(path: Path, root: Path, *, follow_symlinks: bool = False) -> Path:
    """Resolve a candidate file and prove that it remains inside root.

    Filesystem state can change after validation. Callers must use the returned path
    immediately and must not cache a prior validation indefinitely.

    Args:
        path: Relative or absolute candidate file path.
        root: Trusted repository root.
        follow_symlinks: Whether contained symlink components may be followed.

    Returns:
        The strictly resolved contained regular file.

    Raises:
        InvalidPathError: If any containment, existence, type, or symlink check fails.
    """
    resolved_root = validate_repository_root(root)
    resolved = _resolved_contained_path(
        path,
        resolved_root,
        follow_symlinks=follow_symlinks,
        missing_message="The requested file does not exist or is inaccessible.",
    )
    _require_mode(resolved, stat.S_ISREG, "The requested path must be a regular file.")
    return resolved


def validate_reset_target(
    target: Path,
    *,
    repository_root: Path,
    configured_runtime_path: Path,
) -> Path:
    """Validate a future destructive reset target without modifying it.

    Filesystem state can change after validation. A future reset operation must validate
    again immediately before deletion and must not cache this result indefinitely.

    Args:
        target: Requested runtime directory to reset.
        repository_root: Trusted repository root.
        configured_runtime_path: Exact configured CodeScope runtime directory.

    Returns:
        The strictly resolved, contained runtime directory.

    Raises:
        InvalidPathError: If the target is missing, mismatched, or unsafe.
    """
    resolved_root = validate_repository_root(repository_root)
    resolved_configured = _resolved_contained_path(
        configured_runtime_path,
        resolved_root,
        follow_symlinks=False,
        missing_message="The configured runtime directory does not exist or is inaccessible.",
    )
    resolved_target = _resolved_contained_path(
        target,
        resolved_root,
        follow_symlinks=False,
        missing_message="The reset target does not exist or is inaccessible.",
    )
    _require_mode(
        resolved_configured,
        stat.S_ISDIR,
        "The configured runtime path must be a directory.",
    )
    _require_mode(resolved_target, stat.S_ISDIR, "The reset target must be a directory.")
    if resolved_target != resolved_configured:
        _raise_invalid_path("The reset target does not match the configured runtime directory.")
    return resolved_target
