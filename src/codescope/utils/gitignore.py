"""Root-level Git-ignore matching for deterministic repository scans."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from pathspec import GitIgnoreSpec

from codescope.exceptions import InvalidPathError
from codescope.utils.path_guard import safe_resolve, validate_repository_root

_GITIGNORE_NAME: Final = ".gitignore"
_MAX_GITIGNORE_BYTES: Final = 1024 * 1024
_GITIGNORE_ERROR: Final = "The root .gitignore could not be loaded safely."
_PATTERN_ERROR: Final = "Repository exclusion patterns are invalid."


def _normalize_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise ValueError(_PATTERN_ERROR)
    return pure.as_posix()


def _bounded_read_lines(path: Path) -> tuple[str, ...]:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_GITIGNORE_BYTES:
            raise InvalidPathError(_GITIGNORE_ERROR)
        chunks: list[bytes] = []
        remaining = _MAX_GITIGNORE_BYTES + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        after = os.fstat(descriptor)
        payload = b"".join(chunks)
        if (
            len(payload) > _MAX_GITIGNORE_BYTES
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise InvalidPathError(_GITIGNORE_ERROR)
        return tuple(payload.decode("utf-8").splitlines())
    except InvalidPathError:
        raise
    except (OSError, UnicodeError) as error:
        raise InvalidPathError(_GITIGNORE_ERROR) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class GitIgnoreMatcher:
    """Combine configured exclusions with repository-root Git-ignore rules.

    Nested ``.gitignore`` discovery is intentionally outside the Python-only MVP.
    Configured exclusions are evaluated separately so repository negation rules
    can never re-enable a configured exclusion.
    """

    configured: GitIgnoreSpec
    repository: GitIgnoreSpec

    @classmethod
    def from_root(
        cls,
        root: Path,
        *,
        configured_exclusions: tuple[str, ...],
    ) -> GitIgnoreMatcher:
        """Load root ignore rules without following an unsafe ignore-file link."""
        resolved_root = validate_repository_root(root)
        try:
            configured = GitIgnoreSpec.from_lines(configured_exclusions)
        except (TypeError, ValueError) as error:
            raise ValueError(_PATTERN_ERROR) from error

        ignore_path = resolved_root / _GITIGNORE_NAME
        if not ignore_path.exists():
            return cls(configured=configured, repository=GitIgnoreSpec.from_lines(()))
        resolved_ignore = safe_resolve(
            Path(_GITIGNORE_NAME),
            resolved_root,
            follow_symlinks=False,
        )
        try:
            repository = GitIgnoreSpec.from_lines(_bounded_read_lines(resolved_ignore))
        except InvalidPathError:
            raise
        except (TypeError, ValueError) as error:
            raise InvalidPathError(_GITIGNORE_ERROR) from error
        return cls(configured=configured, repository=repository)

    def configured_match(self, relative_path: str, *, is_directory: bool) -> bool:
        """Return whether immutable configuration excludes a relative path."""
        normalized = _normalize_relative_path(relative_path)
        candidate = f"{normalized}/" if is_directory else normalized
        return self.configured.match_file(candidate)

    def repository_match(self, relative_path: str, *, is_directory: bool) -> bool:
        """Return whether the root Git-ignore rules exclude a relative path."""
        normalized = _normalize_relative_path(relative_path)
        candidate = f"{normalized}/" if is_directory else normalized
        return self.repository.match_file(candidate)
