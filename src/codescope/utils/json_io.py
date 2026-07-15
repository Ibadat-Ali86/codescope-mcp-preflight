"""Atomic JSON I/O restricted to CodeScope's two metadata files."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Final, Literal

from codescope.exceptions import InvalidPathError
from codescope.utils.path_guard import validate_runtime_directory

type MetadataFileName = Literal["symbols.json", "index_meta.json"]

_KNOWN_METADATA_FILES: Final = frozenset({"symbols.json", "index_meta.json"})
_METADATA_PATH_ERROR: Final = "The metadata path is unsafe or invalid."


def _metadata_path(runtime_root: Path, name: MetadataFileName) -> Path:
    if name not in _KNOWN_METADATA_FILES:
        raise ValueError(_METADATA_PATH_ERROR)
    resolved_root = validate_runtime_directory(runtime_root)
    if not resolved_root.exists():
        raise InvalidPathError(_METADATA_PATH_ERROR)
    candidate = resolved_root / name
    try:
        if candidate.is_symlink() or candidate.is_junction():
            raise InvalidPathError(_METADATA_PATH_ERROR)
        if candidate.exists() and not stat.S_ISREG(candidate.stat(follow_symlinks=False).st_mode):
            raise InvalidPathError(_METADATA_PATH_ERROR)
    except OSError as error:
        raise InvalidPathError(_METADATA_PATH_ERROR) from error
    return candidate


def _cleanup_temporary(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)


def atomic_write_metadata_json(
    runtime_root: Path,
    name: MetadataFileName,
    payload: object,
) -> None:
    """Serialize and atomically replace one known CodeScope metadata file.

    Args:
        runtime_root: Validated CodeScope runtime directory.
        name: One of the two fixed metadata file names.
        payload: JSON-serializable value.

    Raises:
        InvalidPathError: If the destination is unsafe.
        OSError: If the atomic write cannot complete.
        TypeError: If the payload is not JSON serializable.
        ValueError: If the payload contains unsupported JSON values.
    """
    path = _metadata_path(runtime_root, name)
    serialized = (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            descriptor = -1
            output.write(serialized)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except (OSError, TypeError, UnicodeError, ValueError):
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            _cleanup_temporary(temporary)
        raise


def read_metadata_json(runtime_root: Path, name: MetadataFileName) -> object:
    """Read and parse one known CodeScope metadata file as UTF-8 JSON."""
    path = _metadata_path(runtime_root, name)
    return json.loads(path.read_text(encoding="utf-8"))


def remove_metadata_file(runtime_root: Path, name: MetadataFileName) -> None:
    """Remove one known metadata file without traversing or deleting directories."""
    path = _metadata_path(runtime_root, name)
    path.unlink(missing_ok=True)
