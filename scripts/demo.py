"""Fixed Phase 9 duplication-prevention demonstration for CodeScope."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, Protocol

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from codescope.config import load_config
from codescope.exceptions import CodeScopeError
from codescope.indexer import RepositoryIndexer
from codescope.utils.path_guard import validate_config_file, validate_runtime_directory

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
TASK_MANIFEST: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "duplication_demo" / "task.json"
SOURCE_FIXTURE: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "sample_python"
_SOURCE_EXTENSIONS: Final = frozenset({".py", ".pyi"})
_MAX_MANIFEST_BYTES: Final = 8_192
_MAX_SOURCE_BYTES: Final = 512 * 1_024
_MAX_RESULT_ITEMS: Final = 20
_MAX_PUBLIC_PATH: Final = 512
_MAX_PUBLIC_TEXT: Final = 16_384
# Fixed-fixture trust anchor; update only with an intentional reviewed fixture change.
_EXPECTED_SOURCE_TREE_HASH: Final = (
    "1d4a52a33a83ef31102ad525598af921c4bf84b539fe1488371fc9ed6e4c1d24"
)
_DUPLICATE_PATTERN: Final = re.compile(
    rb"(?m)^[ \t]*(?:async[ \t]+)?def[ \t]+is_valid_email[ \t]*\("
)
_EXPECTED_FIELDS: Final = frozenset(
    {
        "schema_version",
        "task_id",
        "requested_behavior",
        "semantic_query",
        "likely_symbol",
        "planned_signature",
        "expected_recommendation",
        "expected_file",
        "expected_symbol",
        "expected_start_line",
        "expected_end_line",
    }
)
_ISOLATED_CONFIG: Final = """[server]
name = "codescope"
transport = "stdio"

[index]
root = "repository"
languages = ["python"]
include_extensions = [".py", ".pyi"]
exclude = [".git", ".codescope", ".venv", "__pycache__"]
max_file_size_kb = 500
max_chunk_wordpieces = 220
chunk_overlap_wordpieces = 30
follow_symlinks = false

[embeddings]
model = "sentence-transformers/all-MiniLM-L6-v2"
batch_size = 32
device = "cpu"
normalize = true

[storage]
path = ".codescope"
collection = "codescope_chunks"

[search]
default_limit = 5
maximum_limit = 20
minimum_query_characters = 2
"""


class DemoError(Exception):
    """Safe expected failure from the fixed demonstration boundary."""

    def __init__(self, code: str, message: str, suggestion: str) -> None:
        self.code = code
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DemoTask:
    """Validated fixed duplication-prevention task."""

    schema_version: int
    task_id: str
    requested_behavior: str
    semantic_query: str
    likely_symbol: str
    planned_signature: str
    expected_recommendation: str
    expected_file: str
    expected_symbol: str
    expected_start_line: int
    expected_end_line: int


@dataclass(frozen=True, slots=True)
class InventoryEvidence:
    """Bounded public index inventory returned through MCP."""

    index_root: str
    total_files: int
    total_chunks: int
    total_symbols: int
    languages: tuple[tuple[str, int], ...]
    embedding_model: str

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic public JSON shape."""
        return {
            "index_exists": True,
            "index_root": self.index_root,
            "total_files": self.total_files,
            "total_chunks": self.total_chunks,
            "total_symbols": self.total_symbols,
            "languages": dict(self.languages),
            "embedding_model": self.embedding_model,
        }


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Source-free normalized semantic or similar-code evidence."""

    file: str
    start_line: int
    end_line: int
    symbol: str | None
    qualified_name: str | None
    relevance_score: float

    def to_dict(self) -> dict[str, object]:
        """Return bounded evidence without the retrieved source snippet."""
        return {
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
            "qualified_name": self.qualified_name,
            "relevance_score": self.relevance_score,
        }


@dataclass(frozen=True, slots=True)
class SymbolEvidence:
    """Normalized exact-symbol evidence."""

    name: str
    qualified_name: str
    kind: str
    file: str
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, object]:
        """Return bounded symbol metadata without docstring or source text."""
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True, slots=True)
class PreflightEvidence:
    """Normalized results from the four required MCP calls."""

    inventory: InventoryEvidence
    semantic: tuple[SearchEvidence, ...]
    symbols: tuple[SymbolEvidence, ...]
    similar: tuple[SearchEvidence, ...]


@dataclass(frozen=True, slots=True)
class DemoReport:
    """Deterministic judge-facing before/after report."""

    task_id: str
    requested_behavior: str
    index_status: InventoryEvidence
    semantic_evidence: SearchEvidence | None
    symbol_evidence: SymbolEvidence | None
    similar_evidence: SearchEvidence | None
    behavioral_overlap: str
    important_differences: str
    ownership_and_architectural_fit: str
    confidence: str
    uncertainty: str
    recommendation: str
    rationale: str
    source_unchanged: bool
    duplicate_avoided: bool

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON without host paths or protocol frames."""
        return {
            "schema_version": 1,
            "task_id": self.task_id,
            "requested_behavior": self.requested_behavior,
            "index_status": self.index_status.to_dict(),
            "evidence": {
                "semantic_search": (
                    self.semantic_evidence.to_dict() if self.semantic_evidence else None
                ),
                "symbol_search": self.symbol_evidence.to_dict() if self.symbol_evidence else None,
                "similar_code_search": (
                    self.similar_evidence.to_dict() if self.similar_evidence else None
                ),
            },
            "comparison": {
                "behavioral_overlap": self.behavioral_overlap,
                "important_differences": self.important_differences,
                "ownership_and_architectural_fit": self.ownership_and_architectural_fit,
                "confidence": self.confidence,
                "uncertainty": self.uncertainty,
            },
            "recommendation": self.recommendation,
            "rationale": self.rationale,
            "source_unchanged": self.source_unchanged,
            "duplicate_avoided": self.duplicate_avoided,
        }


class McpCaller(Protocol):
    """Small injected boundary for the four read-only MCP calls."""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object: ...


class _SessionCaller:
    """Normalize installed MCP client responses to their structured result payload."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        result = await self._session.call_tool(name, arguments)
        structured = result.structuredContent
        if not isinstance(structured, dict) or set(structured) != {"result"}:
            raise DemoError(
                "DEMO_PROTOCOL_FAILED",
                "The CodeScope tool response was not in the expected structured form.",
                "Verify the installed CodeScope and MCP versions, then retry.",
            )
        return structured["result"]


def _bounded_text(value: object, *, maximum: int, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > maximum:
        raise DemoError(
            "DEMO_INVALID_DATA",
            f"The {label} value is invalid.",
            "Restore the committed Phase 9 fixture and retry.",
        )
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise DemoError(
            "DEMO_INVALID_DATA",
            f"The {label} value is invalid.",
            "Restore the committed Phase 9 fixture and retry.",
        )
    return value


def _public_path(value: object) -> str:
    path = _bounded_text(value, maximum=_MAX_PUBLIC_PATH, label="public path")
    parts = path.split("/")
    windows_path = PureWindowsPath(path)
    if (
        "\\" in path
        or PurePosixPath(path).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise DemoError(
            "DEMO_INVALID_DATA",
            "A CodeScope result contained an unsafe public path.",
            "Rebuild the local index and retry the preflight.",
        )
    return path


def _positive_line(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DemoError(
            "DEMO_INVALID_DATA",
            f"The {label} value is invalid.",
            "Restore the committed fixture or rebuild the index, then retry.",
        )
    return value


def load_task(path: Path = TASK_MANIFEST) -> DemoTask:
    """Load and validate the fixed bounded Phase 9 task manifest."""
    try:
        resolved_path = validate_config_file(path)
        with resolved_path.open("rb") as stream:
            payload_bytes = stream.read(_MAX_MANIFEST_BYTES + 1)
        if len(payload_bytes) > _MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds limit")
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (CodeScopeError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task could not be loaded safely.",
            "Restore the committed Phase 9 task manifest and retry.",
        ) from error
    if not isinstance(payload, dict) or set(payload) != _EXPECTED_FIELDS:
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task has an invalid schema.",
            "Restore the committed Phase 9 task manifest and retry.",
        )
    schema_version = payload["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task has an unsupported schema.",
            "Restore the committed Phase 9 task manifest and retry.",
        )
    expected_start = _positive_line(payload["expected_start_line"], label="start line")
    expected_end = _positive_line(payload["expected_end_line"], label="end line")
    if expected_end < expected_start:
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task has an invalid line range.",
            "Restore the committed Phase 9 task manifest and retry.",
        )
    recommendation = _bounded_text(
        payload["expected_recommendation"], maximum=16, label="expected recommendation"
    )
    if recommendation != "REUSE":
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task has an invalid expected recommendation.",
            "Restore the committed Phase 9 task manifest and retry.",
        )
    fixed_text = {
        "task_id": "email-validator-reuse",
        "requested_behavior": "Validate an email address before creating a user account.",
        "semantic_query": (
            "email address validation with a local part, at sign, and dotted domain"
        ),
        "likely_symbol": "validate_email",
        "planned_signature": "def is_valid_email(email: str) -> bool: ...",
        "expected_file": "validators.py",
        "expected_symbol": "validate_email",
    }
    if any(payload[name] != value for name, value in fixed_text.items()) or (
        expected_start,
        expected_end,
    ) != (6, 9):
        raise DemoError(
            "DEMO_INVALID_TASK",
            "The fixed demonstration task does not match the committed scenario.",
            "Restore the committed Phase 9 task manifest and retry.",
        )
    return DemoTask(
        schema_version=schema_version,
        task_id=_bounded_text(payload["task_id"], maximum=64, label="task identifier"),
        requested_behavior=_bounded_text(
            payload["requested_behavior"], maximum=256, label="requested behavior"
        ),
        semantic_query=_bounded_text(
            payload["semantic_query"], maximum=256, label="semantic query"
        ),
        likely_symbol=_bounded_text(payload["likely_symbol"], maximum=128, label="likely symbol"),
        planned_signature=_bounded_text(
            payload["planned_signature"], maximum=512, label="planned signature"
        ),
        expected_recommendation=recommendation,
        expected_file=_public_path(payload["expected_file"]),
        expected_symbol=_bounded_text(
            payload["expected_symbol"], maximum=128, label="expected symbol"
        ),
        expected_start_line=expected_start,
        expected_end_line=expected_end,
    )


def _tool_error(payload: object) -> None:
    if not isinstance(payload, Mapping) or payload.get("error") is not True:
        return
    raw_code = payload.get("code")
    code = (
        raw_code
        if isinstance(raw_code, str) and re.fullmatch(r"[A-Z_]{1,64}", raw_code)
        else "DEMO_TOOL_FAILED"
    )
    suggestions = {
        "INDEX_NOT_FOUND": "Build a complete local index, then retry the preflight.",
        "STORAGE_FAILED": "Verify the local index storage and retry the preflight.",
        "QUERY_FAILED": "Prepare the configured model locally, verify the index, and retry.",
    }
    raise DemoError(
        code,
        "A required CodeScope tool could not complete the demonstration.",
        suggestions.get(code, "Review the CodeScope configuration and retry the preflight."),
    )


def _mapping(payload: object, *, expected: frozenset[str]) -> Mapping[str, object]:
    _tool_error(payload)
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "A CodeScope tool returned an unexpected result shape.",
            "Verify the local index and installed CodeScope version, then retry.",
        )
    return payload


def _nonnegative_count(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            f"The {label} count returned by CodeScope is invalid.",
            "Rebuild the local index and retry the preflight.",
        )
    return value


def _normalize_inventory(payload: object) -> InventoryEvidence:
    values = _mapping(
        payload,
        expected=frozenset(
            {
                "index_exists",
                "index_root",
                "total_files",
                "total_chunks",
                "total_symbols",
                "languages",
                "last_indexed",
                "index_size_bytes",
                "embedding_model",
            }
        ),
    )
    if values["index_exists"] is not True:
        raise DemoError(
            "INDEX_NOT_FOUND",
            "The fixed demonstration does not have a valid CodeScope index.",
            "Build a complete local index, then retry the preflight.",
        )
    root = values["index_root"]
    if root != ".":
        _public_path(root)
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "The index inventory does not identify the isolated demonstration root.",
            "Rebuild the isolated demonstration index and retry.",
        )
    languages_value = values["languages"]
    if not isinstance(languages_value, Mapping) or len(languages_value) > 8:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "The index language inventory is invalid.",
            "Rebuild the local index and retry the preflight.",
        )
    total_files = _nonnegative_count(values["total_files"], label="file")
    languages: list[tuple[str, int]] = []
    for language, count in sorted(languages_value.items(), key=lambda item: str(item[0])):
        canonical = _bounded_text(language, maximum=32, label="language")
        languages.append((canonical, _nonnegative_count(count, label="language")))
    if languages != [("python", total_files)]:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "The index language inventory does not match the Python demonstration.",
            "Rebuild the isolated demonstration index and retry.",
        )
    _nonnegative_count(values["index_size_bytes"], label="index size")
    last_indexed = values["last_indexed"]
    if last_indexed is not None:
        _bounded_text(last_indexed, maximum=128, label="last indexed time")
    return InventoryEvidence(
        index_root=".",
        total_files=total_files,
        total_chunks=_nonnegative_count(values["total_chunks"], label="chunk"),
        total_symbols=_nonnegative_count(values["total_symbols"], label="symbol"),
        languages=tuple(languages),
        embedding_model=_bounded_text(
            values["embedding_model"], maximum=256, label="embedding model"
        ),
    )


def _optional_name(value: object) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, maximum=1_024, label="symbol name")


def _normalize_search_results(payload: object) -> tuple[SearchEvidence, ...]:
    _tool_error(payload)
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "A CodeScope search returned an unexpected result shape.",
            "Verify the local index and retry the preflight.",
        )
    if len(payload) > _MAX_RESULT_ITEMS:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "A CodeScope search returned too many results.",
            "Verify the local configuration and retry the preflight.",
        )
    normalized: list[SearchEvidence] = []
    expected = frozenset(
        {
            "file",
            "start_line",
            "end_line",
            "symbol",
            "qualified_name",
            "language",
            "snippet",
            "relevance_score",
        }
    )
    for item in payload:
        values = _mapping(item, expected=expected)
        start = _positive_line(values["start_line"], label="search start line")
        end = _positive_line(values["end_line"], label="search end line")
        if end < start or values["language"] != "python":
            raise DemoError(
                "DEMO_PROTOCOL_FAILED",
                "A CodeScope search result is invalid.",
                "Rebuild the local index and retry the preflight.",
            )
        snippet = values["snippet"]
        if not isinstance(snippet, str) or not snippet or len(snippet) > 8_192:
            raise DemoError(
                "DEMO_PROTOCOL_FAILED",
                "A CodeScope search snippet is invalid.",
                "Rebuild the local index and retry the preflight.",
            )
        score = values["relevance_score"]
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
            or not 0.0 <= float(score) <= 1.0
        ):
            raise DemoError(
                "DEMO_PROTOCOL_FAILED",
                "A CodeScope relevance score is invalid.",
                "Rebuild the local index and retry the preflight.",
            )
        normalized.append(
            SearchEvidence(
                file=_public_path(values["file"]),
                start_line=start,
                end_line=end,
                symbol=_optional_name(values["symbol"]),
                qualified_name=_optional_name(values["qualified_name"]),
                relevance_score=float(score),
            )
        )
    return tuple(normalized)


def _normalize_symbol_results(payload: object) -> tuple[SymbolEvidence, ...]:
    _tool_error(payload)
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "CodeScope symbol search returned an unexpected result shape.",
            "Verify the local index and retry the preflight.",
        )
    if len(payload) > _MAX_RESULT_ITEMS:
        raise DemoError(
            "DEMO_PROTOCOL_FAILED",
            "CodeScope symbol search returned too many results.",
            "Verify the local configuration and retry the preflight.",
        )
    normalized: list[SymbolEvidence] = []
    expected = frozenset(
        {
            "name",
            "qualified_name",
            "kind",
            "file",
            "start_line",
            "end_line",
            "signature",
            "docstring",
        }
    )
    for item in payload:
        values = _mapping(item, expected=expected)
        start = _positive_line(values["start_line"], label="symbol start line")
        end = _positive_line(values["end_line"], label="symbol end line")
        signature = values["signature"]
        docstring = values["docstring"]
        if (
            end < start
            or not isinstance(signature, str)
            or not signature
            or len(signature) > _MAX_PUBLIC_TEXT
            or (
                docstring is not None
                and (not isinstance(docstring, str) or len(docstring) > _MAX_PUBLIC_TEXT)
            )
        ):
            raise DemoError(
                "DEMO_PROTOCOL_FAILED",
                "A CodeScope symbol result is invalid.",
                "Rebuild the local index and retry the preflight.",
            )
        normalized.append(
            SymbolEvidence(
                name=_bounded_text(values["name"], maximum=1_024, label="symbol name"),
                qualified_name=_bounded_text(
                    values["qualified_name"], maximum=1_024, label="qualified name"
                ),
                kind=_bounded_text(values["kind"], maximum=32, label="symbol kind"),
                file=_public_path(values["file"]),
                start_line=start,
                end_line=end,
            )
        )
    return tuple(normalized)


async def _call_tool(
    caller: McpCaller,
    name: str,
    arguments: dict[str, object],
) -> object:
    try:
        return await caller.call_tool(name, arguments)
    except DemoError:
        raise
    except Exception as error:
        raise DemoError(
            "DEMO_SESSION_FAILED",
            "The local CodeScope MCP session ended before the preflight completed.",
            "Verify local MCP connectivity and retry the demonstration.",
        ) from error


async def collect_evidence(caller: McpCaller, task: DemoTask) -> PreflightEvidence:
    """Call all four tools in preflight order and normalize their public evidence."""
    inventory = _normalize_inventory(
        await _call_tool(caller, "list_indexed_files", {"language": "python"})
    )
    semantic = _normalize_search_results(
        await _call_tool(
            caller,
            "search_code",
            {"query": task.semantic_query, "language": "python", "limit": 5},
        )
    )
    symbols = _normalize_symbol_results(
        await _call_tool(
            caller,
            "find_symbol",
            {"name": task.likely_symbol, "kind": "function", "limit": 20},
        )
    )
    similar = _normalize_search_results(
        await _call_tool(
            caller,
            "find_similar",
            {"code_snippet": task.planned_signature, "language": "python", "limit": 3},
        )
    )
    return PreflightEvidence(
        inventory=inventory,
        semantic=semantic,
        symbols=symbols,
        similar=similar,
    )


def _matching_search(values: Sequence[SearchEvidence], task: DemoTask) -> SearchEvidence | None:
    return next(
        (
            item
            for item in values
            if item.file == task.expected_file
            and item.symbol == task.expected_symbol
            and item.start_line == task.expected_start_line
            and item.end_line == task.expected_end_line
        ),
        None,
    )


def _matching_symbol(values: Sequence[SymbolEvidence], task: DemoTask) -> SymbolEvidence | None:
    return next(
        (
            item
            for item in values
            if item.file == task.expected_file
            and item.name == task.expected_symbol
            and item.start_line == task.expected_start_line
            and item.end_line == task.expected_end_line
        ),
        None,
    )


def _is_public_source_path(value: object) -> bool:
    try:
        path = _public_path(value)
    except DemoError:
        return False
    return Path(path).suffix in _SOURCE_EXTENSIONS


def _valid_hash_map(values: Mapping[str, str]) -> bool:
    return all(
        _is_public_source_path(path) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        for path, digest in values.items()
    )


def _source_tree_hash(values: Mapping[str, str]) -> str:
    payload = json.dumps(
        dict(values),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def build_report(
    task: DemoTask,
    evidence: PreflightEvidence,
    *,
    before_hashes: Mapping[str, str],
    after_hashes: Mapping[str, str],
    duplicate_avoided: bool,
) -> DemoReport:
    """Apply the fixed evidence-convergence rule without a score threshold."""
    source_unchanged = (
        bool(before_hashes)
        and _valid_hash_map(before_hashes)
        and _valid_hash_map(after_hashes)
        and dict(before_hashes) == dict(after_hashes)
    )
    canonical_fixture = (
        _valid_hash_map(before_hashes)
        and _source_tree_hash(before_hashes) == _EXPECTED_SOURCE_TREE_HASH
    )
    semantic_match = _matching_search(evidence.semantic, task)
    symbol_match = _matching_symbol(evidence.symbols, task)
    similar_match = _matching_search(evidence.similar, task)
    converged = all(
        (
            evidence.inventory.total_files > 0,
            semantic_match is not None,
            symbol_match is not None,
            similar_match is not None,
            canonical_fixture,
            source_unchanged,
            duplicate_avoided is True,
        )
    )
    if converged:
        recommendation = "REUSE"
        rationale = (
            "All four read-only checks converge on the existing validate_email function at "
            "validators.py:6-9, and the source tree remained unchanged."
        )
        behavioral_overlap = (
            "The existing function implements the requested local-part, at-sign, and "
            "dotted-domain check."
        )
        important_differences = (
            "The proposed name differs, but no demonstrated behavior requires a second "
            "implementation."
        )
        ownership = "The validator already belongs to the fixture's validation module."
        confidence = (
            "High because inventory, semantic, exact-symbol, and similar-code evidence converge."
        )
        uncertainty = (
            "Similarity remains evidence, not proof; callers must still verify "
            "product-specific policy."
        )
    else:
        recommendation = "REVIEW_REQUIRED"
        rationale = (
            "The required inventory, location, symbol, similar-code, and "
            "source-integrity evidence did not all converge."
        )
        behavioral_overlap = (
            "Insufficient converging evidence for the fixed demonstration decision."
        )
        important_differences = "One or more required evidence checks is missing or conflicting."
        ownership = "Ownership cannot be confirmed from the available evidence."
        confidence = "Insufficient for REUSE."
        uncertainty = "Resolve the failed evidence checks; do not default to CREATE."
    return DemoReport(
        task_id=task.task_id,
        requested_behavior=task.requested_behavior,
        index_status=evidence.inventory,
        semantic_evidence=semantic_match or (evidence.semantic[0] if evidence.semantic else None),
        symbol_evidence=symbol_match or (evidence.symbols[0] if evidence.symbols else None),
        similar_evidence=similar_match or (evidence.similar[0] if evidence.similar else None),
        behavioral_overlap=behavioral_overlap,
        important_differences=important_differences,
        ownership_and_architectural_fit=ownership,
        confidence=confidence,
        uncertainty=uncertainty,
        recommendation=recommendation,
        rationale=rationale,
        source_unchanged=source_unchanged,
        duplicate_avoided=duplicate_avoided,
    )


def _safe_source_root(root: Path) -> Path:
    try:
        resolved_root = validate_runtime_directory(root)
        if not resolved_root.exists() or not resolved_root.is_dir():
            raise OSError("source root is not a directory")
        return resolved_root
    except (CodeScopeError, OSError, RuntimeError) as error:
        raise DemoError(
            "DEMO_FIXTURE_FAILED",
            "The committed demonstration fixture could not be inspected safely.",
            "Restore the committed sample fixture and retry.",
        ) from error


def _iter_source_files(root: Path) -> tuple[Path, ...]:
    try:
        resolved_root = _safe_source_root(root)
        sources: list[Path] = []
        for current, directory_names, file_names in os.walk(resolved_root, followlinks=False):
            directory_names.sort()
            file_names.sort()
            current_path = Path(current)
            for directory_name in directory_names:
                candidate = current_path / directory_name
                if candidate.is_symlink() or candidate.is_junction():
                    raise OSError("source fixture contains a symlink")
            for file_name in file_names:
                candidate = current_path / file_name
                details = candidate.lstat()
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                    raise OSError("source fixture contains a non-regular file")
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(resolved_root):
                    raise OSError("source fixture path escaped")
                if candidate.suffix in _SOURCE_EXTENSIONS:
                    sources.append(candidate)
        return tuple(sorted(sources, key=lambda item: item.relative_to(resolved_root).as_posix()))
    except OSError as error:
        raise DemoError(
            "DEMO_FIXTURE_FAILED",
            "The committed demonstration fixture could not be inspected safely.",
            "Restore the committed sample fixture and retry.",
        ) from error


def _read_source(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(_MAX_SOURCE_BYTES + 1)
        if len(content) > _MAX_SOURCE_BYTES:
            raise OSError("source file exceeds fixed limit")
        return content
    except OSError as error:
        raise DemoError(
            "DEMO_FIXTURE_FAILED",
            "A demonstration source file could not be read safely.",
            "Restore the committed sample fixture and retry.",
        ) from error


def hash_source_tree(root: Path) -> dict[str, str]:
    """Hash exact bytes for every regular Python source file beneath one fixture root."""
    sources = _iter_source_files(root)
    resolved_root = root.resolve(strict=True)
    return {
        path.relative_to(resolved_root).as_posix(): hashlib.sha256(_read_source(path)).hexdigest()
        for path in sources
    }


def _copy_fixture(destination: Path) -> None:
    try:
        repository = REPOSITORY_ROOT.resolve(strict=True)
        source_root = _safe_source_root(SOURCE_FIXTURE)
        if source_root == repository or not source_root.is_relative_to(repository):
            raise OSError("source fixture escaped the repository")
    except (DemoError, OSError, RuntimeError, ValueError) as error:
        raise DemoError(
            "DEMO_FIXTURE_FAILED",
            "The committed demonstration fixture could not be inspected safely.",
            "Restore the committed sample fixture and retry.",
        ) from error
    destination.mkdir(parents=True, exist_ok=False)
    for source in _iter_source_files(source_root):
        relative = source.relative_to(source_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_read_source(source))


def _duplicate_avoided(root: Path) -> bool:
    return all(
        _DUPLICATE_PATTERN.search(_read_source(path)) is None for path in _iter_source_files(root)
    )


@contextmanager
def _offline_model_environment() -> Iterator[dict[str, str]]:
    cache_value = os.environ.get("CODESCOPE_MODEL_CACHE_DIR")
    try:
        if not cache_value:
            raise OSError("cache is not configured")
        cache = Path(cache_value).expanduser().resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        if not cache.is_dir() or cache == repository or cache.is_relative_to(repository):
            raise OSError("cache is unsafe")
    except OSError as error:
        raise DemoError(
            "DEMO_MODEL_UNAVAILABLE",
            "The cached embedding model is not available for the fixed demonstration.",
            "Set CODESCOPE_MODEL_CACHE_DIR to the prepared external cache and retry offline.",
        ) from error
    names = (
        "HF_HOME",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_HUB_DISABLE_PROGRESS_BARS",
        "TQDM_DISABLE",
    )
    previous = {name: os.environ.get(name) for name in names}
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    try:
        yield dict(os.environ)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _codescope_command() -> str:
    executable_name = "codescope.exe" if os.name == "nt" else "codescope"
    adjacent = Path(sys.executable).with_name(executable_name)
    if adjacent.is_file():
        return str(adjacent)
    located = shutil.which("codescope")
    if located is None:
        raise DemoError(
            "DEMO_SERVER_UNAVAILABLE",
            "The CodeScope command is unavailable in the current environment.",
            "Run the demonstration through the locked uv environment.",
        )
    return located


async def run_demo() -> DemoReport:
    """Run the isolated cache-only real MCP demonstration and clean all temporary state."""
    task = load_task()
    with tempfile.TemporaryDirectory(prefix="codescope-phase9-") as temporary:
        workspace = Path(temporary).resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        if workspace == repository or workspace.is_relative_to(repository):
            raise DemoError(
                "DEMO_WORKSPACE_FAILED",
                "The isolated demonstration workspace is unsafe.",
                "Use a temporary directory outside the repository and retry.",
            )
        fixture = workspace / "repository"
        _copy_fixture(fixture)
        before_hashes = hash_source_tree(fixture)
        config_path = workspace / "codescope.toml"
        config_path.write_text(_ISOLATED_CONFIG, encoding="utf-8", newline="\n")
        try:
            config = load_config(config_path)
        except CodeScopeError as error:
            raise DemoError(
                error.code.value,
                error.message,
                error.suggestion,
            ) from error
        with _offline_model_environment() as child_environment:
            try:
                RepositoryIndexer(config).rebuild(allow_model_download=False)
            except CodeScopeError as error:
                raise DemoError(
                    error.code.value,
                    error.message,
                    error.suggestion,
                ) from error
            parameters = StdioServerParameters(
                command=_codescope_command(),
                args=["serve"],
                cwd=workspace,
                env=child_environment,
            )
            with Path(os.devnull).open("w", encoding="utf-8") as diagnostics:
                async with asyncio.timeout(120):
                    async with stdio_client(parameters, errlog=diagnostics) as (
                        read_stream,
                        write_stream,
                    ):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            evidence = await collect_evidence(_SessionCaller(session), task)
        after_hashes = hash_source_tree(fixture)
        duplicate_avoided = _duplicate_avoided(fixture)
        return build_report(
            task,
            evidence,
            before_hashes=before_hashes,
            after_hashes=after_hashes,
            duplicate_avoided=duplicate_avoided,
        )


def _terminal_safe(value: str) -> str:
    sanitized: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if category.startswith("C") or category in {"Zl", "Zp"}:
            sanitized.append("�")
        else:
            sanitized.append(character)
    return "".join(sanitized)


def render_human(report: DemoReport) -> str:
    """Render the concise judge-facing report with terminal controls neutralized."""
    semantic = report.semantic_evidence
    symbol = report.symbol_evidence
    similar = report.similar_evidence

    def location(item: SearchEvidence | SymbolEvidence | None) -> str:
        if item is None:
            return "No converging evidence"
        owner = getattr(item, "symbol", None) or getattr(item, "name", "module")
        return f"{item.file}:{item.start_line}-{item.end_line} ({owner})"

    lines = [
        "CodeScope Duplication-Prevention Demo",
        f"Task: {report.requested_behavior}",
        (
            "Inventory: "
            f"files={report.index_status.total_files}; "
            f"symbols={report.index_status.total_symbols}; "
            f"chunks={report.index_status.total_chunks}"
        ),
        f"Semantic evidence: {location(semantic)}",
        f"Exact symbol evidence: {location(symbol)}",
        f"Similar-code evidence: {location(similar)}",
        f"Recommendation: {report.recommendation}",
        f"Rationale: {report.rationale}",
        f"Source unchanged: {'yes' if report.source_unchanged else 'no'}",
        f"Duplicate avoided: {'yes' if report.duplicate_avoided else 'no'}",
    ]
    return "\n".join(_terminal_safe(line) for line in lines) + "\n"


def render_json(report: DemoReport) -> str:
    """Render one deterministic JSON object and no protocol output."""
    return (
        json.dumps(report.to_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    )


def _error_json(error: DemoError) -> str:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "error": True,
                "code": error.code,
                "message": error.message,
                "suggestion": error.suggestion,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed cache-only CodeScope duplication-prevention demo."
    )
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line demo with safe deterministic failure output."""
    arguments = _parser().parse_args(argv)
    try:
        report = asyncio.run(run_demo())
    except DemoError as error:
        if arguments.json:
            sys.stdout.write(_error_json(error))
        else:
            sys.stderr.write(
                f"Error [{_terminal_safe(error.code)}]: {_terminal_safe(error.message)}\n"
                f"Suggestion: {_terminal_safe(error.suggestion)}\n"
            )
        return 1
    except Exception as error:
        unexpected = DemoError(
            "DEMO_FAILED",
            "The fixed CodeScope demonstration could not complete safely.",
            "Verify the local installation and retry the isolated demonstration.",
        )
        unexpected.__cause__ = error
        if arguments.json:
            sys.stdout.write(_error_json(unexpected))
        else:
            sys.stderr.write(
                f"Error [{unexpected.code}]: {unexpected.message}\n"
                f"Suggestion: {unexpected.suggestion}\n"
            )
        return 1
    sys.stdout.write(render_json(report) if arguments.json else render_human(report))
    return 0 if report.recommendation == "REUSE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
