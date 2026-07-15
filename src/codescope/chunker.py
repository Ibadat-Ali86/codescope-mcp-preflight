"""Tokenizer-budgeted, symbol-aware source chunking."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Final, Protocol, runtime_checkable

from codescope.models import CodeChunk, Symbol
from codescope.utils.language import SupportedLanguage, normalize_language

_CHUNK_SCHEMA: Final = "codescope-chunk-v1"
_CONFIG_ERROR: Final = "Chunk limits are invalid."
_INPUT_ERROR: Final = "Chunker input is invalid."
_SYMBOL_ERROR: Final = "Symbol ranges are inconsistent."
_TOKENIZER_ERROR: Final = "Tokenizer output is invalid."
_BUDGET_ERROR: Final = "Embedding context cannot fit within the configured chunk budget."
_PROGRESS_ERROR: Final = "Chunk splitting could not make safe progress."

type TokenOffset = tuple[int, int]
type OwnerKey = tuple[str, str, int, int]


class WordpieceTokenizer(Protocol):
    """Exact model-tokenizer seam used without loading model weights.

    Implementations must tokenize with special tokens disabled. Offsets must use
    Python character indices into the original input string.
    """

    def count_wordpieces(self, text: str) -> int:
        """Return the exact model wordpiece count without special tokens."""

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        """Return one original-character offset pair per model wordpiece."""


@runtime_checkable
class PrefixCachingWordpieceTokenizer(Protocol):
    """Optional exact counter that reuses immutable embedding context."""

    def count_prefixed_wordpieces(self, prefix: str, text: str) -> int:
        """Count ``prefix + text`` while safely reusing the prefix work."""


@dataclass(frozen=True, slots=True)
class _LineTable:
    text: tuple[str, ...]
    starts: tuple[int, ...]
    ends: tuple[int, ...]

    @classmethod
    def from_source(cls, source: str) -> _LineTable:
        lines = tuple(source.splitlines(keepends=True))
        if source and not lines:
            lines = (source,)
        starts: list[int] = []
        ends: list[int] = []
        cursor = 0
        for line in lines:
            starts.append(cursor)
            cursor += len(line)
            ends.append(cursor)
        return cls(lines, tuple(starts), tuple(ends))

    def source_span(self, start_line: int, end_line: int) -> tuple[int, int]:
        return self.starts[start_line - 1], self.ends[end_line - 1]

    def line_range(self, start: int, end: int) -> tuple[int, int]:
        if start < 0 or end <= start or end > (self.ends[-1] if self.ends else 0):
            raise ValueError(_INPUT_ERROR)
        start_line = bisect_right(self.starts, start)
        end_line = bisect_right(self.starts, end - 1)
        return start_line, end_line


@dataclass(frozen=True, slots=True)
class _Region:
    start: int
    end: int
    symbol: Symbol | None
    owner: OwnerKey

    @property
    def signature(self) -> str | None:
        return self.symbol.signature if self.symbol is not None else None

    @property
    def symbol_name(self) -> str | None:
        return self.symbol.name if self.symbol is not None else None

    @property
    def qualified_name(self) -> str | None:
        return self.symbol.qualified_name if self.symbol is not None else None


def _validate_public_file(file: str) -> None:
    if not isinstance(file, str) or not file or file.strip() != file or "\\" in file:
        raise ValueError(_INPUT_ERROR)
    segments = file.split("/")
    windows_path = PureWindowsPath(file)
    if (
        PurePosixPath(file).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError(_INPUT_ERROR)


def _embedding_prefix(
    *,
    file: str,
    language: SupportedLanguage,
    qualified_name: str | None,
    signature: str | None,
) -> str:
    fields = [f"language: {language}", f"file: {file}"]
    if qualified_name is None:
        if signature is not None:
            raise ValueError(_INPUT_ERROR)
    else:
        if signature is None or not signature.strip():
            raise ValueError(_INPUT_ERROR)
        fields.extend((f"symbol: {qualified_name}", f"signature: {signature}"))
    return "\n".join(fields) + "\n\n"


def _format_embedding_fields(
    *,
    text: str,
    file: str,
    language: SupportedLanguage,
    qualified_name: str | None,
    signature: str | None,
) -> str:
    return (
        _embedding_prefix(
            file=file,
            language=language,
            qualified_name=qualified_name,
            signature=signature,
        )
        + text
    )


def format_embedding_text(chunk: CodeChunk, *, signature: str | None) -> str:
    """Format canonical transient embedding input for one source chunk.

    Args:
        chunk: Immutable source-only chunk.
        signature: Owning symbol signature, or None for module fallback.

    Returns:
        Deterministic metadata context followed by the exact chunk source.

    Raises:
        ValueError: If symbol metadata and signature context are inconsistent.
    """
    if (chunk.symbol_name is None) != (chunk.qualified_name is None):
        raise ValueError(_INPUT_ERROR)
    return _format_embedding_fields(
        text=chunk.text,
        file=chunk.file,
        language=chunk.language,
        qualified_name=chunk.qualified_name,
        signature=signature,
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_id(
    *,
    file: str,
    language: SupportedLanguage,
    start_line: int,
    end_line: int,
    symbol_name: str | None,
    qualified_name: str | None,
    chunk_index: int,
    content_hash: str,
    signature: str | None,
) -> str:
    payload = {
        "chunk_index": chunk_index,
        "content_hash": content_hash,
        "end_line": end_line,
        "file": file,
        "language": language,
        "qualified_name": qualified_name or "",
        "schema": _CHUNK_SCHEMA,
        "signature": signature or "",
        "start_line": start_line,
        "symbol_name": symbol_name or "",
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CodeChunker:
    """Convert decoded Python source and parser symbols into deterministic chunks."""

    def __init__(
        self,
        *,
        tokenizer: WordpieceTokenizer,
        max_wordpieces: int,
        overlap_wordpieces: int,
    ) -> None:
        """Initialize a chunker with an externally managed exact tokenizer.

        Args:
            tokenizer: Exact wordpiece counter with original-character offsets.
            max_wordpieces: Maximum complete formatted embedding input size.
            overlap_wordpieces: Desired source overlap between split owner parts.

        Raises:
            ValueError: If the configured limits are invalid.
        """
        if (
            not isinstance(max_wordpieces, int)
            or isinstance(max_wordpieces, bool)
            or max_wordpieces <= 0
            or not isinstance(overlap_wordpieces, int)
            or isinstance(overlap_wordpieces, bool)
            or overlap_wordpieces < 0
            or overlap_wordpieces >= max_wordpieces
        ):
            raise ValueError(_CONFIG_ERROR)
        self._tokenizer = tokenizer
        self._max_wordpieces = max_wordpieces
        self._overlap_wordpieces = overlap_wordpieces

    def chunk(
        self,
        source: str,
        *,
        file: str,
        symbols: Sequence[Symbol],
        language: str = "python",
    ) -> list[CodeChunk]:
        """Create source-only chunks within the complete embedding-text budget.

        Args:
            source: Decoded Python source. It is never normalized or read from disk.
            file: Project-relative POSIX path shared by every supplied symbol.
            symbols: Parser-produced symbols for this exact source.
            language: Supported source language.

        Returns:
            Immutable chunks in deterministic source order.

        Raises:
            InvalidLanguageError: If the language is unsupported.
            ValueError: If source, symbols, tokenizer output, or budgets are invalid.
        """
        if not isinstance(source, str):
            raise ValueError(_INPUT_ERROR)
        normalized_language = normalize_language(language)
        _validate_public_file(file)
        line_table = _LineTable.from_source(source)
        regions = self._build_regions(
            file=file,
            symbols=symbols,
            language=normalized_language,
            line_table=line_table,
        )
        if not source.strip():
            return []

        chunks: list[CodeChunk] = []
        owner_indices: dict[OwnerKey, int] = {}
        for region in regions:
            next_index = owner_indices.get(region.owner, 0)
            region_chunks = self._chunk_region(
                source=source,
                file=file,
                language=normalized_language,
                line_table=line_table,
                region=region,
                first_index=next_index,
            )
            chunks.extend(region_chunks)
            owner_indices[region.owner] = next_index + len(region_chunks)
        return chunks

    def _build_regions(
        self,
        *,
        file: str,
        symbols: Sequence[Symbol],
        language: SupportedLanguage,
        line_table: _LineTable,
    ) -> list[_Region]:
        ordered = self._validate_symbols(
            symbols=symbols,
            file=file,
            language=language,
            line_count=len(line_table.text),
        )
        top_level = [symbol for symbol in ordered if symbol.kind != "method"]
        classes = [symbol for symbol in top_level if symbol.kind == "class"]
        methods_by_class = self._assign_methods(ordered, classes)
        regions: list[_Region] = []

        for symbol in top_level:
            owner = self._symbol_owner(symbol)
            methods = methods_by_class.get(symbol, [])
            if symbol.kind != "class" or not methods:
                self._append_line_region(
                    regions, line_table, symbol.start_line, symbol.end_line, symbol, owner
                )
                continue
            cursor = symbol.start_line
            for method in methods:
                self._append_line_region(
                    regions, line_table, cursor, method.start_line - 1, symbol, owner
                )
                self._append_line_region(
                    regions,
                    line_table,
                    method.start_line,
                    method.end_line,
                    method,
                    self._symbol_owner(method),
                )
                cursor = method.end_line + 1
            self._append_line_region(regions, line_table, cursor, symbol.end_line, symbol, owner)

        module_owner: OwnerKey = ("module", "", 0, 0)
        cursor = 1
        for symbol in top_level:
            self._append_line_region(
                regions, line_table, cursor, symbol.start_line - 1, None, module_owner
            )
            cursor = symbol.end_line + 1
        self._append_line_region(
            regions, line_table, cursor, len(line_table.text), None, module_owner
        )
        regions.sort(key=lambda region: (region.start, region.end))
        for previous, current in zip(regions, regions[1:], strict=False):
            if current.start < previous.end:
                raise ValueError(_SYMBOL_ERROR)
        return regions

    def _validate_symbols(
        self,
        *,
        symbols: Sequence[Symbol],
        file: str,
        language: SupportedLanguage,
        line_count: int,
    ) -> list[Symbol]:
        if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
            raise ValueError(_SYMBOL_ERROR)
        validated: list[Symbol] = []
        for symbol in symbols:
            if (
                not isinstance(symbol, Symbol)
                or symbol.file != file
                or symbol.language != language
                or symbol.start_line < 1
                or symbol.end_line < symbol.start_line
                or symbol.end_line > line_count
            ):
                raise ValueError(_SYMBOL_ERROR)
            validated.append(symbol)
        validated.sort(
            key=lambda symbol: (
                symbol.start_line,
                -symbol.end_line,
                symbol.kind == "method",
                symbol.qualified_name,
            )
        )
        top_level = [symbol for symbol in validated if symbol.kind != "method"]
        for previous, current in zip(top_level, top_level[1:], strict=False):
            if current.start_line <= previous.end_line:
                raise ValueError(_SYMBOL_ERROR)
        return validated

    def _assign_methods(
        self,
        symbols: Sequence[Symbol],
        classes: Sequence[Symbol],
    ) -> dict[Symbol, list[Symbol]]:
        assigned: dict[Symbol, list[Symbol]] = {class_symbol: [] for class_symbol in classes}
        for method in (symbol for symbol in symbols if symbol.kind == "method"):
            candidates = [
                class_symbol
                for class_symbol in classes
                if class_symbol.start_line <= method.start_line
                and method.end_line <= class_symbol.end_line
                and method.qualified_name == f"{class_symbol.qualified_name}.{method.name}"
            ]
            if len(candidates) != 1:
                raise ValueError(_SYMBOL_ERROR)
            assigned[candidates[0]].append(method)
        for methods in assigned.values():
            methods.sort(key=lambda method: (method.start_line, method.end_line))
            for previous, current in zip(methods, methods[1:], strict=False):
                if current.start_line <= previous.end_line:
                    raise ValueError(_SYMBOL_ERROR)
        return assigned

    @staticmethod
    def _symbol_owner(symbol: Symbol) -> OwnerKey:
        return (symbol.kind, symbol.qualified_name, symbol.start_line, symbol.end_line)

    @staticmethod
    def _append_line_region(
        regions: list[_Region],
        line_table: _LineTable,
        start_line: int,
        end_line: int,
        symbol: Symbol | None,
        owner: OwnerKey,
    ) -> None:
        if start_line > end_line or start_line < 1 or end_line > len(line_table.text):
            return
        while start_line <= end_line and not line_table.text[start_line - 1].strip():
            start_line += 1
        while start_line <= end_line and not line_table.text[end_line - 1].strip():
            end_line -= 1
        if start_line > end_line:
            return
        start, end = line_table.source_span(start_line, end_line)
        regions.append(_Region(start, end, symbol, owner))

    def _chunk_region(
        self,
        *,
        source: str,
        file: str,
        language: SupportedLanguage,
        line_table: _LineTable,
        region: _Region,
        first_index: int,
    ) -> list[CodeChunk]:
        text = source[region.start : region.end]
        if not text or not text.strip():
            return []
        if (
            self._formatted_count(
                text=text,
                file=file,
                language=language,
                region=region,
            )
            <= self._max_wordpieces
        ):
            return [
                self._make_chunk(
                    text=text,
                    file=file,
                    language=language,
                    line_table=line_table,
                    region=region,
                    local_start=0,
                    local_end=len(text),
                    chunk_index=first_index,
                )
            ]

        context_count = self._formatted_count(
            text="",
            file=file,
            language=language,
            region=region,
        )
        if context_count >= self._max_wordpieces:
            raise ValueError(_BUDGET_ERROR)
        source_capacity = self._max_wordpieces - context_count
        offsets = self._source_offsets(text)
        if not offsets:
            raise ValueError(_TOKENIZER_ERROR)
        line_ends = self._relative_line_ends(text)
        line_starts = (0, *line_ends[:-1])
        token_starts = tuple(start for start, _ in offsets)
        token_ends = tuple(end for _, end in offsets)
        chunks: list[CodeChunk] = []
        cursor = 0
        previous_end = 0

        while cursor < len(text):
            start_token = bisect_right(token_ends, cursor)
            if start_token >= len(offsets):
                raise ValueError(_PROGRESS_ERROR)
            local_end = self._largest_fitting_end(
                text=text,
                file=file,
                language=language,
                region=region,
                cursor=cursor,
                start_token=start_token,
                offsets=offsets,
                line_ends=line_ends,
            )
            if local_end <= cursor or local_end <= previous_end:
                if cursor < previous_end:
                    cursor = previous_end
                    continue
                raise ValueError(_PROGRESS_ERROR)
            chunk = self._make_chunk(
                text=text[cursor:local_end],
                file=file,
                language=language,
                line_table=line_table,
                region=region,
                local_start=cursor,
                local_end=local_end,
                chunk_index=first_index + len(chunks),
            )
            if (
                self._formatted_count(
                    text=chunk.text,
                    file=file,
                    language=language,
                    region=region,
                )
                > self._max_wordpieces
            ):
                raise ValueError(_BUDGET_ERROR)
            chunks.append(chunk)
            if local_end == len(text):
                break
            next_cursor = self._overlap_start(
                cursor=cursor,
                end=local_end,
                previous_end=previous_end,
                source_capacity=source_capacity,
                token_starts=token_starts,
                token_ends=token_ends,
                line_starts=line_starts,
            )
            previous_end = local_end
            cursor = next_cursor
        return chunks

    def _largest_fitting_end(
        self,
        *,
        text: str,
        file: str,
        language: SupportedLanguage,
        region: _Region,
        cursor: int,
        start_token: int,
        offsets: Sequence[TokenOffset],
        line_ends: Sequence[int],
    ) -> int:
        remaining_tokens = len(offsets) - start_token
        high = min(self._max_wordpieces, remaining_tokens)
        low = 1
        best = 0
        counted: dict[int, int] = {}
        while low <= high:
            token_count = (low + high) // 2
            candidate_end = self._candidate_end(
                text_length=len(text),
                cursor=cursor,
                start_token=start_token,
                token_count=token_count,
                offsets=offsets,
                line_ends=line_ends,
            )
            count = counted.get(candidate_end)
            if count is None:
                count = self._formatted_count(
                    text=text[cursor:candidate_end],
                    file=file,
                    language=language,
                    region=region,
                )
                counted[candidate_end] = count
            if count <= self._max_wordpieces:
                best = max(best, candidate_end)
                low = token_count + 1
            else:
                high = token_count - 1
        if best <= cursor:
            raise ValueError(_BUDGET_ERROR)
        return best

    @staticmethod
    def _candidate_end(
        *,
        text_length: int,
        cursor: int,
        start_token: int,
        token_count: int,
        offsets: Sequence[TokenOffset],
        line_ends: Sequence[int],
    ) -> int:
        final_token = start_token + token_count - 1
        required_end = offsets[final_token][1]
        next_token = final_token + 1
        raw_end = offsets[next_token][0] if next_token < len(offsets) else text_length
        line_index = bisect_right(line_ends, raw_end) - 1
        if line_index >= 0:
            line_end = line_ends[line_index]
            if cursor < line_end and line_end >= required_end:
                return line_end
        return raw_end

    def _overlap_start(
        self,
        *,
        cursor: int,
        end: int,
        previous_end: int,
        source_capacity: int,
        token_starts: Sequence[int],
        token_ends: Sequence[int],
        line_starts: Sequence[int],
    ) -> int:
        first_token = bisect_right(token_ends, cursor)
        final_token = bisect_right(token_ends, end)
        emitted_tokens = final_token - first_token
        desired = min(
            self._overlap_wordpieces,
            max(0, source_capacity - 1),
            max(0, emitted_tokens - 1),
        )
        if desired == 0:
            return end
        target = token_starts[final_token - desired]
        line_index = bisect_left(line_starts, target)
        if line_index < len(line_starts):
            logical_start = line_starts[line_index]
            if cursor < logical_start < end:
                target = logical_start
        if target <= cursor or target <= previous_end:
            return end
        return target

    @staticmethod
    def _relative_line_ends(text: str) -> tuple[int, ...]:
        ends: list[int] = []
        cursor = 0
        for line in text.splitlines(keepends=True):
            cursor += len(line)
            ends.append(cursor)
        if not ends or ends[-1] < len(text):
            ends.append(len(text))
        return tuple(ends)

    def _source_offsets(self, text: str) -> tuple[TokenOffset, ...]:
        offsets = self._wordpiece_offsets(text)
        if len(offsets) != self._count_wordpieces(text):
            raise ValueError(_TOKENIZER_ERROR)
        return offsets

    def _wordpiece_offsets(self, text: str) -> tuple[TokenOffset, ...]:
        try:
            raw_offsets = self._tokenizer.wordpiece_offsets(text)
        except (LookupError, RuntimeError, TypeError, ValueError) as error:
            raise ValueError(_TOKENIZER_ERROR) from error
        if isinstance(raw_offsets, (str, bytes)) or not isinstance(raw_offsets, Sequence):
            raise ValueError(_TOKENIZER_ERROR)
        validated: list[TokenOffset] = []
        previous_end = 0
        for raw_offset in raw_offsets:
            if (
                not isinstance(raw_offset, Sequence)
                or isinstance(raw_offset, (str, bytes))
                or len(raw_offset) != 2
            ):
                raise ValueError(_TOKENIZER_ERROR)
            start, end = raw_offset
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < previous_end
                or start < 0
                or end <= start
                or end > len(text)
            ):
                raise ValueError(_TOKENIZER_ERROR)
            validated.append((start, end))
            previous_end = end
        return tuple(validated)

    def _formatted_count(
        self,
        *,
        text: str,
        file: str,
        language: SupportedLanguage,
        region: _Region,
    ) -> int:
        prefix = _embedding_prefix(
            file=file,
            language=language,
            qualified_name=region.qualified_name,
            signature=region.signature,
        )
        if isinstance(self._tokenizer, PrefixCachingWordpieceTokenizer):
            try:
                count = self._tokenizer.count_prefixed_wordpieces(prefix, text)
            except (LookupError, RuntimeError, TypeError, ValueError) as error:
                raise ValueError(_TOKENIZER_ERROR) from error
            return self._validate_wordpiece_count(count)
        return self._count_wordpieces(prefix + text)

    def _count_wordpieces(self, text: str) -> int:
        try:
            count = self._tokenizer.count_wordpieces(text)
        except (LookupError, RuntimeError, TypeError, ValueError) as error:
            raise ValueError(_TOKENIZER_ERROR) from error
        return self._validate_wordpiece_count(count)

    @staticmethod
    def _validate_wordpiece_count(count: object) -> int:
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(_TOKENIZER_ERROR)
        return count

    def _make_chunk(
        self,
        *,
        text: str,
        file: str,
        language: SupportedLanguage,
        line_table: _LineTable,
        region: _Region,
        local_start: int,
        local_end: int,
        chunk_index: int,
    ) -> CodeChunk:
        if not text or not text.strip():
            raise ValueError(_PROGRESS_ERROR)
        start_line, end_line = line_table.line_range(
            region.start + local_start,
            region.start + local_end,
        )
        digest = _content_hash(text)
        chunk_identifier = _chunk_id(
            file=file,
            language=language,
            start_line=start_line,
            end_line=end_line,
            symbol_name=region.symbol_name,
            qualified_name=region.qualified_name,
            chunk_index=chunk_index,
            content_hash=digest,
            signature=region.signature,
        )
        return CodeChunk(
            id=chunk_identifier,
            text=text,
            file=file,
            start_line=start_line,
            end_line=end_line,
            language=language,
            symbol_name=region.symbol_name,
            qualified_name=region.qualified_name,
            chunk_index=chunk_index,
            content_hash=digest,
        )
