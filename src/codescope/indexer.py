"""Secure deterministic repository scanning and full-index rebuild orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from codescope import __version__
from codescope.chunker import CodeChunker, WordpieceTokenizer, format_embedding_text
from codescope.config import AppConfig, IndexConfig, StorageConfig
from codescope.embedder import LocalEmbedder
from codescope.exceptions import (
    CodeScopeError,
    IndexNotFoundError,
    InvalidPathError,
    ParseFailedError,
    StorageFailedError,
)
from codescope.models import CodeChunk, IndexStatus, Symbol
from codescope.parser import CodeParser
from codescope.storage import ChromaStorage, IndexMetadata
from codescope.utils.gitignore import GitIgnoreMatcher
from codescope.utils.language import SupportedLanguage, language_from_extension
from codescope.utils.path_guard import (
    safe_resolve,
    validate_repository_root,
    validate_runtime_directory,
)

_INDEX_ERROR: Final = "Repository indexing could not be completed safely."
_STATUS_ERROR: Final = "No complete usable CodeScope index exists."
_SCANNER_ERROR: Final = "The repository could not be scanned safely."
_GENERATED_PATH_ERROR: Final = "The generated runtime path is unsafe."
_MODEL_UNAVAILABLE_ERROR: Final = "The embedding model is unavailable locally."
_FINGERPRINT_SCHEMA: Final = "codescope-index-config-v1"
_MAX_SCAN_DIRECTORIES: Final = 100_000
_MAX_SCAN_ENTRIES: Final = 1_000_000
_MAX_RUNTIME_ENTRIES: Final = 100_000
_READ_BLOCK_BYTES: Final = 64 * 1024
_GENERATED_NAME = re.compile(r"^[A-Za-z0-9._-]+\.(?:build|backup)-[A-Za-z0-9_-]{6,}$")

_HARD_DIRECTORY_NAMES: Final = frozenset(
    {
        ".cache",
        ".chroma",
        ".codescope",
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "env",
        "node_modules",
        "site-packages",
        "venv",
    }
)
_MODEL_CACHE_NAMES: Final = frozenset(
    {"huggingface", "sentence_transformers", "transformers", "model-cache", "model_cache"}
)
_PRIVATE_KEY_NAMES: Final = frozenset(
    {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "private-key", "private_key"}
)
_SENSITIVE_SUFFIXES: Final = frozenset(
    {
        ".7z",
        ".bz2",
        ".cer",
        ".crt",
        ".db",
        ".der",
        ".gif",
        ".gz",
        ".jpeg",
        ".jpg",
        ".jks",
        ".key",
        ".onnx",
        ".p12",
        ".pem",
        ".pfx",
        ".png",
        ".pt",
        ".pth",
        ".rar",
        ".safetensors",
        ".sqlite",
        ".sqlite3",
        ".tar",
        ".webp",
        ".xz",
        ".zip",
    }
)

type ProgressStage = Literal["scan", "skip", "file", "batch", "verify", "promote", "complete"]
type ProgressCallback = Callable[["ProgressEvent"], None]
type FileIdentity = tuple[int, int]


class SkipReason(StrEnum):
    """Stable source-scan skip categories without sensitive detail."""

    EXCLUDED = "excluded"
    GITIGNORED = "gitignored"
    UNSUPPORTED_EXTENSION = "unsupported extension"
    SYMLINK_DISABLED = "symlink disabled"
    OUTSIDE_ROOT = "outside root"
    OVERSIZED = "oversized"
    NOT_REGULAR = "not regular"
    BINARY = "binary"
    UNDECODABLE = "undecodable"
    UNREADABLE = "unreadable"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Private absolute source identity plus safe public scan metadata."""

    absolute_path: Path
    relative_path: str
    language: SupportedLanguage
    size_bytes: int
    device: int
    inode: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class LoadedSource:
    """One bounded source payload retained only for its per-file pipeline."""

    source_file: SourceFile
    source_bytes: bytes
    source_text: str


@dataclass(frozen=True, slots=True)
class SkippedFile:
    """Safe deterministic skip record."""

    relative_path: str
    reason: SkipReason


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Deterministic discovery result before descriptor-bound reads."""

    files: tuple[SourceFile, ...]
    skipped: tuple[SkippedFile, ...]


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Bounded progress event safe for local CLI display."""

    stage: ProgressStage
    current: int
    total: int | None = None
    file: str | None = None
    reason: SkipReason | None = None


@dataclass(frozen=True, slots=True)
class IndexSummary:
    """Immutable result of one successful full repository rebuild."""

    root: str
    total_files: int
    total_symbols: int
    total_chunks: int
    skipped_files: int
    language_counts: Mapping[str, int]
    elapsed_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "language_counts", MappingProxyType(dict(self.language_counts)))


class _EmbeddingBackend(Protocol):
    @property
    def tokenizer(self) -> WordpieceTokenizer: ...

    def encode(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class _StorageFactory(Protocol):
    def __call__(self, config: StorageConfig, *, create: bool = True) -> ChromaStorage: ...


class _DirectoryEntryLimitExceeded(RuntimeError):
    """Signal that a directory iterator exceeded its remaining safe allowance."""


def _default_storage_factory(
    config: StorageConfig,
    *,
    create: bool = True,
) -> ChromaStorage:
    return ChromaStorage(config, create=create)


def _bounded_sorted_entries(
    directory: Path,
    *,
    remaining: int,
) -> list[os.DirEntry[str]]:
    """Return deterministic entries without materializing beyond a global bound."""
    if remaining < 0:
        raise _DirectoryEntryLimitExceeded
    entries: list[os.DirEntry[str]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= remaining:
                raise _DirectoryEntryLimitExceeded
            entries.append(entry)
    entries.sort(key=lambda entry: entry.name)
    return entries


def _relative_posix(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as error:
        raise InvalidPathError(_SCANNER_ERROR) from error
    if (
        not relative
        or PurePosixPath(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise InvalidPathError(_SCANNER_ERROR)
    return relative


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _is_junction(path: Path) -> bool:
    try:
        return path.is_junction()
    except (OSError, AttributeError):
        return False


def _hard_excluded(relative_path: str, *, is_directory: bool) -> bool:
    parts = tuple(part.casefold() for part in PurePosixPath(relative_path).parts)
    if any(part in _HARD_DIRECTORY_NAMES for part in parts):
        return True
    if any(part in _MODEL_CACHE_NAMES or part.startswith("models--") for part in parts):
        return True
    name = parts[-1]
    if name == ".env" or name.startswith(".env."):
        return True
    if is_directory:
        return False
    path = PurePosixPath(name)
    if path.stem in _PRIVATE_KEY_NAMES or any(
        name.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES
    ):
        return True
    return name in {"pyvenv.cfg", "pip-selfcheck.json"}


class RepositoryScanner:
    """Discover and descriptor-read Python files beneath one trusted root."""

    def __init__(
        self,
        config: IndexConfig,
        *,
        runtime_path: Path,
    ) -> None:
        self._config = config
        self._runtime_path = runtime_path
        self._maximum_bytes = config.max_file_size_kb * 1024

    def discover(self, root: Path) -> ScanResult:
        """Return sorted contained source candidates and safe discovery skips."""
        resolved_root = validate_repository_root(root)
        matcher = GitIgnoreMatcher.from_root(
            resolved_root,
            configured_exclusions=self._config.exclude,
        )
        runtime = validate_runtime_directory(self._runtime_path)
        files: list[SourceFile] = []
        skipped: list[SkippedFile] = []
        visited_directories: set[FileIdentity] = set()
        visited_files: set[FileIdentity] = set()
        root_stat = resolved_root.stat()
        visited_directories.add((root_stat.st_dev, root_stat.st_ino))
        entries_seen = 0

        def record(path: str, reason: SkipReason) -> None:
            skipped.append(SkippedFile(path, reason))

        def walk(actual_directory: Path, logical_directory: str) -> None:
            nonlocal entries_seen
            try:
                entries = _bounded_sorted_entries(
                    actual_directory,
                    remaining=_MAX_SCAN_ENTRIES - entries_seen,
                )
                entries_seen += len(entries)
            except _DirectoryEntryLimitExceeded as error:
                raise InvalidPathError(_SCANNER_ERROR) from error
            except OSError as error:
                if logical_directory:
                    record(logical_directory, SkipReason.UNREADABLE)
                    return
                raise InvalidPathError(_SCANNER_ERROR) from error

            for entry in entries:
                logical = f"{logical_directory}/{entry.name}" if logical_directory else entry.name
                logical = logical.replace("\\", "/")
                entry_path = Path(entry.path)
                try:
                    is_link = entry.is_symlink() or _is_junction(entry_path)
                    if is_link:
                        self._handle_symlink(
                            entry_path=entry_path,
                            logical=logical,
                            root=resolved_root,
                            runtime=runtime,
                            matcher=matcher,
                            files=files,
                            visited_files=visited_files,
                            visited_directories=visited_directories,
                            record=record,
                            walk=walk,
                        )
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if PurePosixPath(logical).suffix in self._config.include_extensions:
                            record(logical, SkipReason.NOT_REGULAR)
                            continue
                        if self._excluded(logical, True, matcher):
                            record(logical, self._exclusion_reason(logical, True, matcher))
                            continue
                        resolved_directory = entry_path.resolve(strict=True)
                        if self._is_runtime_path(resolved_directory, runtime):
                            record(logical, SkipReason.EXCLUDED)
                            continue
                        directory_stat = entry.stat(follow_symlinks=False)
                        identity = (directory_stat.st_dev, directory_stat.st_ino)
                        if identity in visited_directories:
                            record(logical, SkipReason.DUPLICATE)
                            continue
                        if len(visited_directories) >= _MAX_SCAN_DIRECTORIES:
                            raise InvalidPathError(_SCANNER_ERROR)
                        visited_directories.add(identity)
                        walk(entry_path, logical)
                        continue

                    if not entry.is_file(follow_symlinks=False):
                        record(logical, SkipReason.NOT_REGULAR)
                        continue
                    self._add_file(
                        entry_path=entry_path,
                        logical=logical,
                        root=resolved_root,
                        runtime=runtime,
                        matcher=matcher,
                        files=files,
                        visited_files=visited_files,
                        record=record,
                        follow_symlinks=False,
                    )
                except (OSError, RuntimeError):
                    record(logical, SkipReason.UNREADABLE)

        walk(resolved_root, "")
        files.sort(key=lambda item: item.relative_path)
        skipped.sort(key=lambda item: (item.relative_path, item.reason.value))
        return ScanResult(tuple(files), tuple(skipped))

    def _handle_symlink(
        self,
        *,
        entry_path: Path,
        logical: str,
        root: Path,
        runtime: Path,
        matcher: GitIgnoreMatcher,
        files: list[SourceFile],
        visited_files: set[FileIdentity],
        visited_directories: set[FileIdentity],
        record: Callable[[str, SkipReason], None],
        walk: Callable[[Path, str], None],
    ) -> None:
        if not self._config.follow_symlinks:
            record(logical, SkipReason.SYMLINK_DISABLED)
            return
        if self._excluded(logical, False, matcher):
            record(logical, self._exclusion_reason(logical, False, matcher))
            return
        try:
            resolved = entry_path.resolve(strict=True)
            if resolved == root or not _is_relative_to(resolved, root):
                record(logical, SkipReason.OUTSIDE_ROOT)
                return
            target_stat = entry_path.stat()
        except (OSError, RuntimeError):
            record(logical, SkipReason.UNREADABLE)
            return
        identity = (target_stat.st_dev, target_stat.st_ino)
        if stat.S_ISDIR(target_stat.st_mode):
            if self._excluded(logical, True, matcher) or self._is_runtime_path(resolved, runtime):
                record(logical, self._exclusion_reason(logical, True, matcher))
                return
            if identity in visited_directories:
                record(logical, SkipReason.DUPLICATE)
                return
            if len(visited_directories) >= _MAX_SCAN_DIRECTORIES:
                raise InvalidPathError(_SCANNER_ERROR)
            visited_directories.add(identity)
            walk(entry_path, logical)
            return
        if not stat.S_ISREG(target_stat.st_mode):
            record(logical, SkipReason.NOT_REGULAR)
            return
        self._add_file(
            entry_path=entry_path,
            logical=logical,
            root=root,
            runtime=runtime,
            matcher=matcher,
            files=files,
            visited_files=visited_files,
            record=record,
            follow_symlinks=True,
            known_stat=target_stat,
        )

    def _add_file(
        self,
        *,
        entry_path: Path,
        logical: str,
        root: Path,
        runtime: Path,
        matcher: GitIgnoreMatcher,
        files: list[SourceFile],
        visited_files: set[FileIdentity],
        record: Callable[[str, SkipReason], None],
        follow_symlinks: bool,
        known_stat: os.stat_result | None = None,
    ) -> None:
        if self._excluded(logical, False, matcher):
            record(logical, self._exclusion_reason(logical, False, matcher))
            return
        if self._is_runtime_path(entry_path.resolve(strict=True), runtime):
            record(logical, SkipReason.EXCLUDED)
            return
        extension = PurePosixPath(logical).suffix
        if extension not in self._config.include_extensions:
            record(logical, SkipReason.UNSUPPORTED_EXTENSION)
            return
        language = language_from_extension(extension)
        file_stat = known_stat or entry_path.stat(follow_symlinks=follow_symlinks)
        if not stat.S_ISREG(file_stat.st_mode):
            record(logical, SkipReason.NOT_REGULAR)
            return
        identity = (file_stat.st_dev, file_stat.st_ino)
        if identity in visited_files:
            record(logical, SkipReason.DUPLICATE)
            return
        visited_files.add(identity)
        if file_stat.st_size > self._maximum_bytes:
            record(logical, SkipReason.OVERSIZED)
            return
        files.append(
            SourceFile(
                absolute_path=entry_path,
                relative_path=_relative_posix(entry_path, root),
                language=language,
                size_bytes=file_stat.st_size,
                device=file_stat.st_dev,
                inode=file_stat.st_ino,
                modified_ns=file_stat.st_mtime_ns,
            )
        )

    @staticmethod
    def _is_runtime_path(candidate: Path, runtime: Path) -> bool:
        if not runtime.exists():
            return candidate == runtime or _is_relative_to(candidate, runtime)
        try:
            resolved_runtime = runtime.resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        return candidate == resolved_runtime or _is_relative_to(candidate, resolved_runtime)

    @staticmethod
    def _excluded(relative: str, is_directory: bool, matcher: GitIgnoreMatcher) -> bool:
        return (
            _hard_excluded(relative, is_directory=is_directory)
            or matcher.configured_match(relative, is_directory=is_directory)
            or matcher.repository_match(relative, is_directory=is_directory)
        )

    @staticmethod
    def _exclusion_reason(
        relative: str,
        is_directory: bool,
        matcher: GitIgnoreMatcher,
    ) -> SkipReason:
        if _hard_excluded(relative, is_directory=is_directory) or matcher.configured_match(
            relative, is_directory=is_directory
        ):
            return SkipReason.EXCLUDED
        return SkipReason.GITIGNORED

    def read(self, source_file: SourceFile, root: Path) -> LoadedSource | SkippedFile:
        """Read a discovered source through one bounded verified descriptor."""
        resolved_root = validate_repository_root(root)
        descriptor = -1
        try:
            resolved = safe_resolve(
                Path(source_file.relative_path),
                resolved_root,
                follow_symlinks=self._config.follow_symlinks,
            )
            flags = os.O_RDONLY
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(resolved, flags)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                return SkippedFile(source_file.relative_path, SkipReason.NOT_REGULAR)
            if (
                (before.st_dev, before.st_ino) != (source_file.device, source_file.inode)
                or before.st_size != source_file.size_bytes
                or before.st_mtime_ns != source_file.modified_ns
            ):
                return SkippedFile(source_file.relative_path, SkipReason.UNREADABLE)
            chunks: list[bytes] = []
            remaining = self._maximum_bytes + 1
            while remaining > 0:
                block = os.read(descriptor, min(_READ_BLOCK_BYTES, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                len(payload) > self._maximum_bytes
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or len(payload) != after.st_size
            ):
                return SkippedFile(source_file.relative_path, SkipReason.OVERSIZED)
            if b"\x00" in payload:
                return SkippedFile(source_file.relative_path, SkipReason.BINARY)
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                return SkippedFile(source_file.relative_path, SkipReason.UNDECODABLE)
            return LoadedSource(source_file, payload, text)
        except (CodeScopeError, OSError, RuntimeError):
            return SkippedFile(source_file.relative_path, SkipReason.UNREADABLE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _configuration_fingerprint(config: AppConfig) -> str:
    payload = {
        "collection": config.storage.collection,
        "embedding_model": config.embeddings.model,
        "exclude": list(config.index.exclude),
        "follow_symlinks": config.index.follow_symlinks,
        "include_extensions": list(config.index.include_extensions),
        "languages": list(config.index.languages),
        "max_chunk_wordpieces": config.index.max_chunk_wordpieces,
        "max_file_size_kb": config.index.max_file_size_kb,
        "normalize_embeddings": config.embeddings.normalize,
        "overlap_wordpieces": config.index.chunk_overlap_wordpieces,
        "schema": _FINGERPRINT_SCHEMA,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generated_path_valid(
    candidate: Path,
    *,
    parent: Path,
    live_name: str,
) -> bool:
    return (
        candidate.parent == parent
        and candidate.name.startswith(f"{live_name}.")
        and _GENERATED_NAME.fullmatch(candidate.name) is not None
        and candidate != parent
    )


def _cleanup_generated_directory(
    candidate: Path,
    *,
    runtime_parent: Path,
    repository_root: Path,
    live_name: str,
) -> None:
    """Remove only an exact generated build/backup sibling without following links."""
    parent = validate_runtime_directory(runtime_parent)
    root = validate_repository_root(repository_root)
    if not candidate.exists() and not candidate.is_symlink():
        return
    if not _generated_path_valid(candidate, parent=parent, live_name=live_name):
        raise InvalidPathError(_GENERATED_PATH_ERROR)
    if candidate.is_symlink() or _is_junction(candidate):
        raise InvalidPathError(_GENERATED_PATH_ERROR)
    resolved = validate_runtime_directory(candidate)
    if (
        resolved == root
        or resolved == parent
        or not _is_relative_to(resolved, parent)
        or resolved.parent != parent
    ):
        raise InvalidPathError(_GENERATED_PATH_ERROR)
    try:
        shutil.rmtree(resolved)
    except OSError as error:
        raise InvalidPathError(_GENERATED_PATH_ERROR) from error


def _new_generated_path(parent: Path, live_name: str, kind: Literal["build", "backup"]) -> Path:
    if kind == "build":
        created = Path(tempfile.mkdtemp(prefix=f"{live_name}.build-", dir=parent))
        try:
            created.chmod(0o700)
        except OSError:
            pass
        return validate_runtime_directory(created)
    descriptor, name = tempfile.mkstemp(prefix=f"{live_name}.backup-", dir=parent)
    os.close(descriptor)
    candidate = Path(name)
    candidate.unlink()
    if not _generated_path_valid(candidate, parent=parent, live_name=live_name):
        raise InvalidPathError(_GENERATED_PATH_ERROR)
    return candidate


def _runtime_size(runtime_root: Path) -> int:
    root = validate_runtime_directory(runtime_root)
    total = 0
    entries_seen = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = _bounded_sorted_entries(
                directory,
                remaining=_MAX_RUNTIME_ENTRIES - entries_seen,
            )
            entries_seen += len(entries)
        except _DirectoryEntryLimitExceeded as error:
            raise StorageFailedError(_STATUS_ERROR) from error
        except OSError as error:
            raise StorageFailedError(_STATUS_ERROR) from error
        for entry in entries:
            path = Path(entry.path)
            try:
                if entry.is_symlink() or _is_junction(path):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError as error:
                raise StorageFailedError(_STATUS_ERROR) from error
    return total


class RepositoryIndexer:
    """Build and validate one complete local CodeScope repository index."""

    def __init__(
        self,
        config: AppConfig,
        *,
        parser: CodeParser | None = None,
        embedder: _EmbeddingBackend | None = None,
        progress: ProgressCallback | None = None,
        storage_factory: _StorageFactory = _default_storage_factory,
    ) -> None:
        """Store immutable dependencies without scanning, loading, or deleting."""
        self._config = config
        self._parser = parser
        self._embedder = embedder
        self._progress = progress
        self._storage_factory = storage_factory

    def rebuild(
        self,
        root: Path | None = None,
        *,
        allow_model_download: bool = False,
    ) -> IndexSummary:
        """Build, verify, and rollback-safely promote a complete local index."""
        started = time.monotonic()
        run_config = self._config.with_index_root(root) if root is not None else self._config
        repository_root = run_config.index.root
        live = run_config.storage.path
        parent = validate_runtime_directory(live.parent, create=True)
        temporary = _new_generated_path(parent, live.name, "build")
        temp_config = StorageConfig(path=temporary, collection=run_config.storage.collection)
        storage: ChromaStorage | None = None
        try:
            scanner = RepositoryScanner(run_config.index, runtime_path=live)
            self._emit(ProgressEvent("scan", 0))
            scan = scanner.discover(repository_root)
            skipped_count = len(scan.skipped)
            for skipped in scan.skipped:
                self._emit(
                    ProgressEvent(
                        "skip",
                        skipped_count,
                        total=len(scan.files) + len(scan.skipped),
                        file=skipped.relative_path,
                        reason=skipped.reason,
                    )
                )

            parser = self._parser or CodeParser()
            embedder = self._embedder or LocalEmbedder(
                run_config.embeddings,
                allow_download=allow_model_download,
            )
            chunker = CodeChunker(
                tokenizer=embedder.tokenizer,
                max_wordpieces=run_config.index.max_chunk_wordpieces,
                overlap_wordpieces=run_config.index.chunk_overlap_wordpieces,
            )
            storage = self._storage_factory(temp_config, create=True)
            build_storage = storage
            build_storage.initialize_collection()
            symbols: list[Symbol] = []
            pending_chunks: list[CodeChunk] = []
            pending_texts: list[str] = []
            seen_ids: set[str] = set()
            file_count = 0
            chunk_count = 0
            language_counts: dict[str, int] = {}

            def flush() -> None:
                nonlocal chunk_count
                if not pending_chunks:
                    return
                vectors = embedder.encode(tuple(pending_texts))
                build_storage.add_chunks(tuple(pending_chunks), vectors)
                chunk_count += len(pending_chunks)
                self._emit(ProgressEvent("batch", chunk_count))
                pending_chunks.clear()
                pending_texts.clear()

            for position, source_file in enumerate(scan.files, start=1):
                loaded = scanner.read(source_file, repository_root)
                if isinstance(loaded, SkippedFile):
                    skipped_count += 1
                    self._emit(
                        ProgressEvent(
                            "skip",
                            position,
                            total=len(scan.files),
                            file=loaded.relative_path,
                            reason=loaded.reason,
                        )
                    )
                    continue
                try:
                    file_symbols = parser.parse(
                        loaded.source_bytes,
                        file=source_file.relative_path,
                        language=source_file.language,
                    )
                except ParseFailedError:
                    skipped_count += 1
                    self._emit(
                        ProgressEvent(
                            "skip",
                            position,
                            total=len(scan.files),
                            file=source_file.relative_path,
                            reason=SkipReason.UNREADABLE,
                        )
                    )
                    continue
                file_chunks = chunker.chunk(
                    loaded.source_text,
                    file=source_file.relative_path,
                    symbols=file_symbols,
                    language=source_file.language,
                )
                signatures = {symbol.qualified_name: symbol.signature for symbol in file_symbols}
                for chunk in file_chunks:
                    if chunk.id in seen_ids:
                        raise ValueError(_INDEX_ERROR)
                    seen_ids.add(chunk.id)
                    signature = (
                        signatures.get(chunk.qualified_name)
                        if chunk.qualified_name is not None
                        else None
                    )
                    pending_chunks.append(chunk)
                    pending_texts.append(format_embedding_text(chunk, signature=signature))
                    if len(pending_chunks) == run_config.embeddings.batch_size:
                        flush()
                symbols.extend(file_symbols)
                file_count += 1
                language_counts[source_file.language] = (
                    language_counts.get(source_file.language, 0) + 1
                )
                self._emit(
                    ProgressEvent(
                        "file",
                        position,
                        total=len(scan.files),
                        file=source_file.relative_path,
                    )
                )
            flush()
            metadata = IndexMetadata(
                codescope_version=__version__,
                index_root=".",
                embedding_model=run_config.embeddings.model,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                file_count=file_count,
                symbol_count=len(symbols),
                chunk_count=chunk_count,
                language_counts=language_counts,
                configuration_fingerprint=_configuration_fingerprint(run_config),
            )
            build_storage.write_symbols(symbols)
            build_storage.write_index_metadata(metadata)
            build_storage.close()
            storage = None
            self._emit(ProgressEvent("verify", 0))
            self._verify(temp_config, metadata)
            self._emit(ProgressEvent("promote", 0))
            self._promote(
                temporary=temporary,
                live=live,
                parent=parent,
                repository_root=repository_root,
                run_config=run_config,
                expected=metadata,
            )
            elapsed = max(0.0, time.monotonic() - started)
            summary = IndexSummary(
                root=".",
                total_files=file_count,
                total_symbols=len(symbols),
                total_chunks=chunk_count,
                skipped_files=skipped_count,
                language_counts=language_counts,
                elapsed_seconds=elapsed,
            )
            self._emit(ProgressEvent("complete", file_count, total=file_count))
            return summary
        except (CodeScopeError, OSError, RuntimeError, UnicodeError, ValueError) as error:
            if storage is not None:
                try:
                    storage.close()
                except StorageFailedError:
                    pass
            if temporary.exists() or temporary.is_symlink():
                try:
                    _cleanup_generated_directory(
                        temporary,
                        runtime_parent=parent,
                        repository_root=repository_root,
                        live_name=live.name,
                    )
                except CodeScopeError:
                    pass
            if isinstance(error, StorageFailedError) and str(error) == _INDEX_ERROR:
                raise
            if (
                isinstance(error, RuntimeError)
                and "embedding model is unavailable locally" in str(error).casefold()
            ):
                raise StorageFailedError(
                    _MODEL_UNAVAILABLE_ERROR,
                    suggestion=(
                        "Prepare the model with --allow-model-download once, then retry "
                        "cache-only indexing."
                    ),
                ) from error
            raise StorageFailedError(_INDEX_ERROR) from error
        finally:
            if storage is not None:
                try:
                    storage.close()
                except StorageFailedError:
                    pass
            if temporary.exists() or temporary.is_symlink():
                try:
                    _cleanup_generated_directory(
                        temporary,
                        runtime_parent=parent,
                        repository_root=repository_root,
                        live_name=live.name,
                    )
                except CodeScopeError:
                    pass

    def status(self) -> IndexStatus:
        """Validate persisted metadata and Chroma without loading the model."""
        config = self._config
        try:
            runtime = validate_runtime_directory(config.storage.path)
            if not runtime.is_dir():
                raise IndexNotFoundError(_STATUS_ERROR)
            storage = self._storage_factory(config.storage, create=False)
            try:
                metadata = storage.read_index_metadata()
                symbols = storage.read_symbols()
                count = storage.count()
            finally:
                storage.close()
            if (
                metadata.index_root != "."
                or metadata.embedding_model != config.embeddings.model
                or metadata.configuration_fingerprint != _configuration_fingerprint(config)
                or metadata.file_count != sum(metadata.language_counts.values())
                or metadata.symbol_count != len(symbols)
                or metadata.chunk_count != count
            ):
                raise IndexNotFoundError(_STATUS_ERROR)
            return IndexStatus(
                index_exists=True,
                index_root=".",
                total_files=metadata.file_count,
                total_chunks=count,
                total_symbols=len(symbols),
                languages=metadata.language_counts,
                last_indexed=metadata.timestamp,
                index_size_bytes=_runtime_size(runtime),
                embedding_model=metadata.embedding_model,
            )
        except IndexNotFoundError:
            raise
        except (CodeScopeError, OSError, RuntimeError, UnicodeError, ValueError) as error:
            raise IndexNotFoundError(_STATUS_ERROR) from error

    def _verify(self, storage_config: StorageConfig, expected: IndexMetadata) -> None:
        storage = self._storage_factory(storage_config, create=False)
        try:
            metadata = storage.read_index_metadata()
            symbols = storage.read_symbols()
            count = storage.count()
        finally:
            storage.close()
        if (
            metadata != expected
            or metadata.file_count != sum(metadata.language_counts.values())
            or metadata.symbol_count != len(symbols)
            or metadata.chunk_count != count
            or metadata.embedding_model != self._config.embeddings.model
            or metadata.index_root != "."
        ):
            raise StorageFailedError(_INDEX_ERROR)

    def _promote(
        self,
        *,
        temporary: Path,
        live: Path,
        parent: Path,
        repository_root: Path,
        run_config: AppConfig,
        expected: IndexMetadata,
    ) -> None:
        backup: Path | None = None
        promoted = False
        had_live = live.exists()
        if had_live:
            validate_runtime_directory(live)
            backup = _new_generated_path(parent, live.name, "backup")
        try:
            if backup is not None:
                os.replace(live, backup)
            os.replace(temporary, live)
            promoted = True
            promoted_config = StorageConfig(path=live, collection=run_config.storage.collection)
            self._verify(promoted_config, expected)
            if backup is not None:
                _cleanup_generated_directory(
                    backup,
                    runtime_parent=parent,
                    repository_root=repository_root,
                    live_name=live.name,
                )
        except (CodeScopeError, OSError, RuntimeError, ValueError) as error:
            if promoted and live.exists():
                try:
                    os.replace(live, temporary)
                except OSError:
                    pass
            if backup is not None and backup.exists() and not live.exists():
                try:
                    os.replace(backup, live)
                except OSError as restore_error:
                    raise StorageFailedError(_INDEX_ERROR) from restore_error
            if temporary.exists():
                try:
                    _cleanup_generated_directory(
                        temporary,
                        runtime_parent=parent,
                        repository_root=repository_root,
                        live_name=live.name,
                    )
                except CodeScopeError:
                    pass
            if not had_live and live.exists() and not promoted:
                raise StorageFailedError(_INDEX_ERROR) from error
            raise StorageFailedError(_INDEX_ERROR) from error

    def _emit(self, event: ProgressEvent) -> None:
        if self._progress is not None:
            self._progress(event)
