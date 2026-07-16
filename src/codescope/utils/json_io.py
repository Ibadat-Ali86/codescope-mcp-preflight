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
_METADATA_READ_ERROR: Final = "The metadata file is invalid or exceeds its safe size limit."
# Index metadata is a small fixed-shape object. Symbols may be numerous, but the
# Python-only MVP still caps their JSON representation to limit local allocation.
INDEX_METADATA_MAX_BYTES: Final = 64 * 1024
SYMBOLS_METADATA_MAX_BYTES: Final = 16 * 1024 * 1024
_METADATA_LIMITS: Final[dict[MetadataFileName, int]] = {
    "index_meta.json": INDEX_METADATA_MAX_BYTES,
    "symbols.json": SYMBOLS_METADATA_MAX_BYTES,
}


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
    """Read one known metadata file through a bounded regular-file descriptor.

    The before/after descriptor checks reduce the metadata validation-to-use race.
    They cannot prevent a privileged local process from changing the filesystem
    after this function returns, so callers must validate parsed models promptly.
    """
    path = _metadata_path(runtime_root, name)
    maximum = _METADATA_LIMITS[name]
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise InvalidPathError(_METADATA_READ_ERROR)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        after = os.fstat(descriptor)
        payload = b"".join(chunks)
        if (
            len(payload) > maximum
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise InvalidPathError(_METADATA_READ_ERROR)
        return json.loads(payload.decode("utf-8"))
    except InvalidPathError:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise InvalidPathError(_METADATA_READ_ERROR) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def remove_metadata_file(runtime_root: Path, name: MetadataFileName) -> None:
    """Remove one known metadata file without traversing or deleting directories."""
    path = _metadata_path(runtime_root, name)
    path.unlink(missing_ok=True)
