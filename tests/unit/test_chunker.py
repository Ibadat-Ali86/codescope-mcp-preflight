"""Tests for tokenizer-budgeted symbol-aware source chunking."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence

import pytest

from codescope.chunker import CodeChunker, TokenOffset, format_embedding_text
from codescope.exceptions import ErrorCode, InvalidLanguageError
from codescope.models import CodeChunk, Symbol
from codescope.parser import CodeParser

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


class FakeWordpieceTokenizer:
    """Deterministic offset-aware tokenizer used without external model files."""

    def __init__(self) -> None:
        self.count_calls = 0
        self.offset_calls = 0
        self.processed_characters = 0

    def count_wordpieces(self, text: str) -> int:
        self.count_calls += 1
        self.processed_characters += len(text)
        return len(TOKEN_PATTERN.findall(text))

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        self.offset_calls += 1
        self.processed_characters += len(text)
        return tuple(match.span() for match in TOKEN_PATTERN.finditer(text))


def _chunker(
    tokenizer: FakeWordpieceTokenizer | None = None,
    *,
    maximum: int = 80,
    overlap: int = 5,
) -> CodeChunker:
    return CodeChunker(
        tokenizer=tokenizer or FakeWordpieceTokenizer(),
        max_wordpieces=maximum,
        overlap_wordpieces=overlap,
    )


def _symbols(source: str, *, file: str = "src/example.py") -> list[Symbol]:
    return CodeParser().parse(source.encode("utf-8"), file=file)


def _manual_symbol(
    *,
    name: str,
    kind: str,
    start_line: int,
    end_line: int,
    file: str = "src/example.py",
    qualified_name: str | None = None,
    signature: str | None = None,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=file,
        start_line=start_line,
        end_line=end_line,
        signature=signature or f"def {name}():",
        qualified_name=qualified_name or name,
        docstring=None,
        language="python",
    )


def _merge_overlaps(parts: Sequence[str]) -> str:
    merged = parts[0]
    for part in parts[1:]:
        overlap = max(
            (
                size
                for size in range(1, min(len(merged), len(part)) + 1)
                if merged.endswith(part[:size])
            ),
            default=0,
        )
        merged += part[overlap:]
    return merged


def _assert_budget(
    chunks: Sequence[CodeChunk],
    symbols: Sequence[Symbol],
    tokenizer: FakeWordpieceTokenizer,
    maximum: int,
) -> None:
    signatures = {symbol.qualified_name: symbol.signature for symbol in symbols}
    for chunk in chunks:
        signature = signatures[chunk.qualified_name] if chunk.qualified_name is not None else None
        assert (
            tokenizer.count_wordpieces(format_embedding_text(chunk, signature=signature)) <= maximum
        )


def test_chunker_accepts_valid_configuration() -> None:
    # Arrange and Act
    chunker = _chunker(maximum=20, overlap=3)

    # Assert
    assert isinstance(chunker, CodeChunker)


@pytest.mark.parametrize(
    ("maximum", "overlap"),
    [(0, 0), (-1, 0), (20, -1), (20, 20), (20, 21), (True, 0), (20, False)],
)
def test_chunker_rejects_invalid_configuration(maximum: int, overlap: int) -> None:
    # Arrange and Act and Assert
    with pytest.raises(ValueError, match="Chunk limits are invalid"):
        _chunker(maximum=maximum, overlap=overlap)


def test_chunker_rejects_invalid_tokenizer_count() -> None:
    # Arrange
    class InvalidTokenizer(FakeWordpieceTokenizer):
        def count_wordpieces(self, text: str) -> int:
            return -1

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(InvalidTokenizer()).chunk("value = 1\n", file="value.py", symbols=[])


@pytest.mark.parametrize("invalid_count", [True, 1.5, "1"])
def test_chunker_rejects_non_integer_tokenizer_counts(invalid_count: object) -> None:
    # Arrange
    class InvalidTokenizer(FakeWordpieceTokenizer):
        def count_wordpieces(self, text: str) -> int:
            return invalid_count  # type: ignore[return-value]

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(InvalidTokenizer()).chunk("value = 1\n", file="value.py", symbols=[])


def test_chunker_translates_expected_tokenizer_failures_safely() -> None:
    # Arrange
    class FailingTokenizer(FakeWordpieceTokenizer):
        def count_wordpieces(self, text: str) -> int:
            raise RuntimeError("backend contained secret source")

    # Act
    with pytest.raises(ValueError) as error_info:
        _chunker(FailingTokenizer()).chunk("SECRET = 1\n", file="value.py", symbols=[])

    # Assert
    assert str(error_info.value) == "Tokenizer output is invalid."
    assert isinstance(error_info.value.__cause__, RuntimeError)
    assert "secret" not in str(error_info.value).lower()


def test_chunker_rejects_invalid_or_mismatched_tokenizer_offsets() -> None:
    # Arrange
    class InvalidTokenizer(FakeWordpieceTokenizer):
        def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
            return ((0, len(text) + 1),)

    source = "\n".join(f"value_{index} = {index}" for index in range(50))

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(InvalidTokenizer(), maximum=20).chunk(source, file="values.py", symbols=[])


def test_chunker_rejects_offset_count_mismatch() -> None:
    # Arrange
    class MismatchedTokenizer(FakeWordpieceTokenizer):
        def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
            return super().wordpiece_offsets(text)[:-1]

    source = "\n".join(f"value_{index} = {index}" for index in range(50))

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(MismatchedTokenizer(), maximum=20).chunk(source, file="values.py", symbols=[])


def test_chunker_rejects_empty_offsets_for_over_budget_source() -> None:
    # Arrange
    class MissingOffsetTokenizer(FakeWordpieceTokenizer):
        def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
            return ()

        def count_wordpieces(self, text: str) -> int:
            if not text.startswith("language:"):
                return 0
            return 2 if text.endswith("\n\n") else 50

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(MissingOffsetTokenizer(), maximum=40).chunk(
            "value = 1\n", file="value.py", symbols=[]
        )


@pytest.mark.parametrize(
    "invalid_offsets",
    [
        "not-offsets",
        ((0,),),
        ((0, True),),
        ((2, 4), (3, 5)),
    ],
)
def test_chunker_rejects_malformed_tokenizer_offsets(invalid_offsets: object) -> None:
    # Arrange
    class InvalidTokenizer(FakeWordpieceTokenizer):
        def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
            return invalid_offsets  # type: ignore[return-value]

    source = "\n".join(f"value_{index} = {index}" for index in range(50))

    # Act and Assert
    with pytest.raises(ValueError, match="Tokenizer output is invalid"):
        _chunker(InvalidTokenizer(), maximum=20).chunk(source, file="values.py", symbols=[])


def test_chunker_translates_expected_offset_failures_safely() -> None:
    # Arrange
    class FailingTokenizer(FakeWordpieceTokenizer):
        def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
            raise LookupError("backend contained source")

    source = "\n".join(f"value_{index} = {index}" for index in range(50))

    # Act
    with pytest.raises(ValueError) as error_info:
        _chunker(FailingTokenizer(), maximum=20).chunk(source, file="values.py", symbols=[])

    # Assert
    assert str(error_info.value) == "Tokenizer output is invalid."
    assert isinstance(error_info.value.__cause__, LookupError)


def test_chunker_unsupported_language_uses_existing_domain_error() -> None:
    # Arrange and Act
    with pytest.raises(InvalidLanguageError) as error_info:
        _chunker().chunk("", file="empty.py", symbols=[], language="typescript")

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_LANGUAGE


@pytest.mark.parametrize("source", ["", " \t\r\n\n"])
def test_chunker_empty_or_whitespace_source_returns_empty(source: str) -> None:
    # Arrange and Act
    result = _chunker().chunk(source, file="empty.py", symbols=[])

    # Assert
    assert result == []


def test_chunker_rejects_non_string_source_and_non_sequence_symbols() -> None:
    # Arrange and Act and Assert
    with pytest.raises(ValueError, match="Chunker input is invalid"):
        _chunker().chunk(b"value = 1\n", file="value.py", symbols=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(
            "value = 1\n",
            file="value.py",
            symbols=(symbol for symbol in []),  # type: ignore[arg-type]
        )


def test_small_top_level_function_remains_one_exact_source_chunk() -> None:
    # Arrange
    source = "def ready(value: int) -> bool:\n    return value > 0\n"
    symbols = _symbols(source)
    tokenizer = FakeWordpieceTokenizer()

    # Act
    result = _chunker(tokenizer).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert len(result) == 1
    assert result[0].text == source
    assert result[0].symbol_name == "ready"
    assert result[0].qualified_name == "ready"
    assert (result[0].start_line, result[0].end_line) == (1, 2)
    _assert_budget(result, symbols, tokenizer, 80)


def test_small_async_function_remains_one_chunk() -> None:
    # Arrange
    source = "async def load(value: int) -> int:\n    return value\n"
    symbols = _symbols(source)

    # Act
    result = _chunker().chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert len(result) == 1
    assert result[0].text.startswith("async def load")
    assert result[0].symbol_name == "load"


def test_decorated_function_chunk_includes_original_decorators() -> None:
    # Arrange
    source = '@first\n@second("task")\ndef task() -> str:\n    return "done"\n'
    symbols = _symbols(source)

    # Act
    result = _chunker().chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert result[0].text == source
    assert result[0].start_line == 1
    assert result[0].text.startswith("@first\n@second")


def test_small_direct_method_remains_separate_source_chunk() -> None:
    # Arrange
    source = (
        "class Service:\n    version = 1\n\n    def ready(self) -> bool:\n        return True\n"
    )
    symbols = _symbols(source)

    # Act
    result = _chunker().chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    method = next(chunk for chunk in result if chunk.qualified_name == "Service.ready")
    assert method.text == "    def ready(self) -> bool:\n        return True\n"
    assert method.chunk_index == 0


def test_embedding_formatter_keeps_context_transient_and_canonical() -> None:
    # Arrange
    source = "def ready() -> bool:\n    return True\n"
    symbol = _symbols(source)[0]
    chunk = _chunker().chunk(source, file="src/example.py", symbols=[symbol])[0]

    # Act
    formatted = format_embedding_text(chunk, signature=symbol.signature)

    # Assert
    assert formatted == (
        "language: python\n"
        "file: src/example.py\n"
        "symbol: ready\n"
        "signature: def ready() -> bool:\n\n" + source
    )
    assert chunk.text == source
    assert "language: python" not in chunk.text


def test_module_embedding_formatter_omits_symbol_and_signature() -> None:
    # Arrange
    chunk = _chunker().chunk("VALUE = 1\n", file="src/constants.py", symbols=[])[0]

    # Act
    formatted = format_embedding_text(chunk, signature=None)

    # Assert
    assert formatted == "language: python\nfile: src/constants.py\n\nVALUE = 1\n"
    assert "symbol:" not in formatted
    assert "signature:" not in formatted


def test_module_embedding_formatter_rejects_unowned_signature() -> None:
    # Arrange
    chunk = _chunker().chunk("VALUE = 1\n", file="src/constants.py", symbols=[])[0]

    # Act and Assert
    with pytest.raises(ValueError, match="Chunker input is invalid"):
        format_embedding_text(chunk, signature="def unrelated():")


def test_formatter_rejects_missing_symbol_signature_safely() -> None:
    # Arrange
    source = "def ready():\n    pass\n"
    chunk = _chunker().chunk(source, file="src/example.py", symbols=_symbols(source))[0]

    # Act and Assert
    with pytest.raises(ValueError, match="Chunker input is invalid"):
        format_embedding_text(chunk, signature=None)


def test_formatter_rejects_inconsistent_symbol_metadata_safely() -> None:
    # Arrange
    source = "def ready():\n    return True\n"
    valid = _chunker().chunk(source, file="src/example.py", symbols=_symbols(source))[0]
    inconsistent = valid.model_copy(update={"qualified_name": None})

    # Act and Assert
    with pytest.raises(ValueError, match="Chunker input is invalid"):
        format_embedding_text(inconsistent, signature="def ready():")


def test_class_ownership_preserves_declaration_gaps_and_direct_methods() -> None:
    # Arrange
    source = (
        "class Service:\n"
        '    """Service docs."""\n'
        "    version = 1\n\n"
        "    def first(self) -> int:\n"
        "        return 1\n\n"
        "    between = 2\n\n"
        "    def second(self) -> int:\n"
        "        return 2\n\n"
        "    tail = 3\n"
    )
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=100).chunk(
        source, file="src/example.py", symbols=list(reversed(symbols))
    )

    # Assert
    assert [chunk.qualified_name for chunk in result] == [
        "Service",
        "Service.first",
        "Service",
        "Service.second",
        "Service",
    ]
    class_chunks = [chunk for chunk in result if chunk.qualified_name == "Service"]
    assert [chunk.chunk_index for chunk in class_chunks] == [0, 1, 2]
    assert class_chunks[0].text.startswith("class Service:")
    assert "Service docs." in class_chunks[0].text
    assert "between = 2" in class_chunks[1].text
    assert "tail = 3" in class_chunks[2].text
    assert all("def first" not in chunk.text for chunk in class_chunks)
    assert all("def second" not in chunk.text for chunk in class_chunks)


def test_expected_class_method_nesting_uses_range_and_metadata() -> None:
    # Arrange
    source = "class Service:\n    def run(self):\n        return 1\n"
    symbols = _symbols(source)

    # Act
    result = _chunker().chunk(source, file="src/example.py", symbols=[symbols[1], symbols[0]])

    # Assert
    assert [chunk.qualified_name for chunk in result] == ["Service", "Service.run"]


def test_impossible_crossing_top_level_intervals_are_rejected_safely() -> None:
    # Arrange
    source = "one\ntwo\nthree\nfour\nfive\nsix\n"
    symbols = [
        _manual_symbol(name="first", kind="function", start_line=1, end_line=4),
        _manual_symbol(name="second", kind="function", start_line=3, end_line=6),
    ]

    # Act and Assert
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(source, file="src/example.py", symbols=symbols)


def test_method_without_coherent_class_owner_is_rejected() -> None:
    # Arrange
    source = "class Service:\n    def run(self):\n        return 1\n"
    method = _manual_symbol(
        name="run",
        kind="method",
        start_line=2,
        end_line=3,
        qualified_name="Other.run",
    )
    class_symbol = _manual_symbol(
        name="Service",
        kind="class",
        start_line=1,
        end_line=3,
        signature="class Service:",
    )

    # Act and Assert
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(source, file="src/example.py", symbols=[class_symbol, method])


def test_overlapping_direct_method_ranges_are_rejected_safely() -> None:
    # Arrange
    source = (
        "class Service:\n"
        "    value = 1\n"
        "    def first(self):\n"
        "        pass\n"
        "    def second(self):\n"
        "        pass\n"
    )
    class_symbol = _manual_symbol(
        name="Service",
        kind="class",
        start_line=1,
        end_line=6,
        signature="class Service:",
    )
    first = _manual_symbol(
        name="first",
        kind="method",
        start_line=3,
        end_line=5,
        qualified_name="Service.first",
    )
    second = _manual_symbol(
        name="second",
        kind="method",
        start_line=5,
        end_line=6,
        qualified_name="Service.second",
    )

    # Act and Assert
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(
            source,
            file="src/example.py",
            symbols=[class_symbol, first, second],
        )


def test_oversized_function_splits_with_bounded_same_owner_overlap() -> None:
    # Arrange
    body = "".join(f"    value_{index} = {index}\n" for index in range(30))
    source = "def large() -> int:\n" + body + "    return value_29\n"
    symbols = _symbols(source)
    tokenizer = FakeWordpieceTokenizer()

    # Act
    result = _chunker(tokenizer, maximum=40, overlap=5).chunk(
        source, file="src/example.py", symbols=symbols
    )

    # Assert
    assert len(result) > 1
    assert [chunk.chunk_index for chunk in result] == list(range(len(result)))
    assert all(chunk.qualified_name == "large" for chunk in result)
    assert _merge_overlaps([chunk.text for chunk in result]) == source
    assert all(chunk.text.strip() for chunk in result)
    for previous, current in zip(result, result[1:], strict=False):
        assert previous.text != current.text
        overlap_characters = max(
            (
                size
                for size in range(1, min(len(previous.text), len(current.text)) + 1)
                if previous.text.endswith(current.text[:size])
            ),
            default=0,
        )
        overlap_wordpieces = tokenizer.count_wordpieces(current.text[:overlap_characters])
        assert 0 < overlap_wordpieces <= 5
    _assert_budget(result, symbols, tokenizer, 40)


def test_every_split_embedding_context_retains_signature_and_qualified_name() -> None:
    # Arrange
    source = "def large() -> int:\n" + "".join(
        f"    value_{index} = {index}\n" for index in range(20)
    )
    symbol = _symbols(source)[0]
    chunks = _chunker(maximum=40).chunk(source, file="src/example.py", symbols=[symbol])

    # Act
    formatted = [format_embedding_text(chunk, signature=symbol.signature) for chunk in chunks]

    # Assert
    assert len(formatted) > 1
    assert all("symbol: large\n" in text for text in formatted)
    assert all(f"signature: {symbol.signature}\n" in text for text in formatted)


def test_multiline_unicode_source_splits_without_character_corruption() -> None:
    # Arrange
    body = "".join(f'    café_{index} = "雪-{index}"\n' for index in range(25))
    source = "def unicode_values():\n" + body
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=40, overlap=4).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert len(result) > 1
    assert _merge_overlaps([chunk.text for chunk in result]) == source
    assert "雪-24" in result[-1].text
    assert all("\ufffd" not in chunk.text for chunk in result)


def test_one_overlong_line_splits_on_character_offsets_with_same_line_metadata() -> None:
    # Arrange
    expression = " + ".join(f"value_{index}" for index in range(50))
    source = f"def wide():\n    return {expression}\n"
    symbols = _symbols(source)
    tokenizer = FakeWordpieceTokenizer()

    # Act
    result = _chunker(tokenizer, maximum=38, overlap=3).chunk(
        source, file="src/example.py", symbols=symbols
    )

    # Assert
    assert len(result) > 2
    assert _merge_overlaps([chunk.text for chunk in result]) == source
    assert any(chunk.start_line == chunk.end_line == 2 for chunk in result)
    assert all(chunk.text for chunk in result)
    _assert_budget(result, symbols, tokenizer, 38)


def test_zero_overlap_splits_without_duplicate_source() -> None:
    # Arrange
    source = "def large():\n" + "".join(f"    value_{index} = {index}\n" for index in range(20))
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=35, overlap=0).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert len(result) > 1
    assert "".join(chunk.text for chunk in result) == source


def test_completed_split_part_is_recounted_before_return() -> None:
    # Arrange
    class InconsistentTokenizer(FakeWordpieceTokenizer):
        def __init__(self) -> None:
            super().__init__()
            self.seen_formatted: set[str] = set()

        def count_wordpieces(self, text: str) -> int:
            count = super().count_wordpieces(text)
            if not text.startswith("language:") or text.endswith("\n\n"):
                return count
            if text in self.seen_formatted:
                return count + 100
            self.seen_formatted.add(text)
            return count

    source = "def large():\n" + "".join(f"    value_{index} = {index}\n" for index in range(20))

    # Act and Assert
    with pytest.raises(
        ValueError,
        match="Embedding context cannot fit within the configured chunk budget",
    ):
        _chunker(InconsistentTokenizer(), maximum=35).chunk(
            source, file="src/example.py", symbols=_symbols(source)
        )


def test_mandatory_context_that_cannot_fit_fails_with_fixed_message() -> None:
    # Arrange
    source = "def ready():\n    return True\n"
    symbol = _symbols(source)[0]

    # Act
    with pytest.raises(ValueError) as error_info:
        _chunker(maximum=5, overlap=0).chunk(source, file="src/example.py", symbols=[symbol])

    # Assert
    assert str(error_info.value) == (
        "Embedding context cannot fit within the configured chunk budget."
    )
    assert source not in str(error_info.value)
    assert symbol.signature not in str(error_info.value)


def test_no_symbol_module_retains_docstring_imports_and_assignments() -> None:
    # Arrange
    source = '"""Module docs."""\n\nimport os\nfrom pathlib import Path\n\nVALUE = 3\n'

    # Act
    result = _chunker(maximum=100).chunk(source, file="src/constants.py", symbols=[])

    # Assert
    assert len(result) == 1
    assert result[0].text == source
    assert result[0].symbol_name is None
    assert result[0].qualified_name is None
    assert (result[0].start_line, result[0].end_line) == (1, 6)


def test_blank_only_module_regions_are_skipped_and_lines_adjusted() -> None:
    # Arrange
    source = "\n\nVALUE = 1\n\n\n"

    # Act
    result = _chunker().chunk(source, file="src/constants.py", symbols=[])

    # Assert
    assert len(result) == 1
    assert result[0].text == "VALUE = 1\n"
    assert (result[0].start_line, result[0].end_line) == (3, 3)


def test_imports_combine_with_adjacent_module_context_when_they_fit() -> None:
    # Arrange
    source = "import os\nimport sys\n\nVALUE = 1\n"

    # Act
    result = _chunker(maximum=100).chunk(source, file="src/constants.py", symbols=[])

    # Assert
    assert len(result) == 1
    assert result[0].text == source


def test_imports_only_module_is_deterministic() -> None:
    # Arrange
    source = "import os\nfrom pathlib import Path\n"
    chunker = _chunker()

    # Act
    first = chunker.chunk(source, file="src/imports.py", symbols=[])
    second = chunker.chunk(source, file="src/imports.py", symbols=[])

    # Assert
    assert first == second
    assert first[0].text == source


def test_oversized_module_fallback_splits_within_budget() -> None:
    # Arrange
    source = "".join(f"VALUE_{index} = {index}\n" for index in range(40))
    tokenizer = FakeWordpieceTokenizer()

    # Act
    result = _chunker(tokenizer, maximum=25, overlap=3).chunk(
        source, file="src/constants.py", symbols=[]
    )

    # Assert
    assert len(result) > 1
    assert all(chunk.symbol_name is None for chunk in result)
    assert _merge_overlaps([chunk.text for chunk in result]) == source
    _assert_budget(result, [], tokenizer, 25)


def test_module_fallback_never_duplicates_symbol_owned_lines() -> None:
    # Arrange
    source = "import os\nVALUE = 1\n\ndef ready():\n    return VALUE\n\nTAIL = 2\n"
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=100).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    fallback = [chunk for chunk in result if chunk.symbol_name is None]
    symbol_chunk = next(chunk for chunk in result if chunk.symbol_name == "ready")
    assert [chunk.chunk_index for chunk in fallback] == [0, 1]
    assert all("def ready" not in chunk.text for chunk in fallback)
    assert "import os" not in symbol_chunk.text
    assert "TAIL = 2" not in symbol_chunk.text


def test_repeated_calls_preserve_models_order_ids_and_hashes() -> None:
    # Arrange
    source = "VALUE = 1\n\ndef ready():\n    return VALUE\n"
    symbols = _symbols(source)
    chunker = _chunker()

    # Act
    first = chunker.chunk(source, file="src/example.py", symbols=symbols)
    second = chunker.chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert first == second
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.content_hash for chunk in first] == [chunk.content_hash for chunk in second]


def test_source_change_changes_content_hash() -> None:
    # Arrange
    first_source = "VALUE = 1\n"
    second_source = "VALUE = 2\n"

    # Act
    first = _chunker().chunk(first_source, file="src/constants.py", symbols=[])[0]
    second = _chunker().chunk(second_source, file="src/constants.py", symbols=[])[0]

    # Assert
    assert first.content_hash != second.content_hash
    assert first.content_hash == hashlib.sha256(first_source.encode()).hexdigest()


def test_file_change_changes_id_without_changing_content_hash() -> None:
    # Arrange
    source = "VALUE = 1\n"

    # Act
    first = _chunker().chunk(source, file="src/one.py", symbols=[])[0]
    second = _chunker().chunk(source, file="src/two.py", symbols=[])[0]

    # Assert
    assert first.content_hash == second.content_hash
    assert first.id != second.id


def test_line_range_change_changes_id_for_identical_symbol_text() -> None:
    # Arrange
    symbol_text = "def ready():\n    return True\n"
    first_symbols = _symbols(symbol_text)
    shifted_source = "# module context\n\n" + symbol_text
    shifted_symbols = _symbols(shifted_source)

    # Act
    first = _chunker().chunk(symbol_text, file="src/example.py", symbols=first_symbols)[-1]
    shifted = _chunker().chunk(shifted_source, file="src/example.py", symbols=shifted_symbols)[-1]

    # Assert
    assert first.text == shifted.text
    assert first.content_hash == shifted.content_hash
    assert first.start_line != shifted.start_line
    assert first.id != shifted.id


def test_signature_context_change_changes_id() -> None:
    # Arrange
    source = "def ready():\n    return True\n"
    symbol = _symbols(source)[0]
    changed = symbol.model_copy(update={"signature": "def ready(flag: bool = True):"})

    # Act
    first = _chunker().chunk(source, file="src/example.py", symbols=[symbol])[0]
    second = _chunker().chunk(source, file="src/example.py", symbols=[changed])[0]

    # Assert
    assert first.text == second.text
    assert first.content_hash == second.content_hash
    assert first.id != second.id


def test_ownership_change_changes_id_for_identical_source_location() -> None:
    # Arrange
    source = "VALUE = 1\n"
    symbol = _manual_symbol(
        name="VALUE",
        kind="function",
        start_line=1,
        end_line=1,
        signature="def VALUE():",
    )

    # Act
    module_chunk = _chunker().chunk(source, file="src/example.py", symbols=[])[0]
    symbol_chunk = _chunker().chunk(source, file="src/example.py", symbols=[symbol])[0]

    # Assert
    assert module_chunk.text == symbol_chunk.text
    assert module_chunk.start_line == symbol_chunk.start_line
    assert module_chunk.end_line == symbol_chunk.end_line
    assert module_chunk.content_hash == symbol_chunk.content_hash
    assert module_chunk.id != symbol_chunk.id


def test_ids_and_hashes_are_lowercase_sha256_hex() -> None:
    # Arrange and Act
    chunks = _chunker().chunk("VALUE = 1\n", file="src/constants.py", symbols=[])

    # Assert
    assert HEX_DIGEST.fullmatch(chunks[0].id)
    assert HEX_DIGEST.fullmatch(chunks[0].content_hash)


def test_chunk_indices_are_zero_based_per_logical_owner() -> None:
    # Arrange
    source = "VALUE = 1\n\ndef first():\n    return 1\n\ndef second():\n    return 2\n\nTAIL = 3\n"
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=100).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    fallback = [chunk for chunk in result if chunk.symbol_name is None]
    functions = [chunk for chunk in result if chunk.symbol_name is not None]
    assert [chunk.chunk_index for chunk in fallback] == [0, 1]
    assert [chunk.chunk_index for chunk in functions] == [0, 0]


def test_crlf_source_preserves_exact_text_and_one_based_lines() -> None:
    # Arrange
    source = "def ready():\r\n    value = 1\r\n    return value\r\n"
    symbols = _symbols(source)

    # Act
    result = _chunker(maximum=100).chunk(source, file="src/example.py", symbols=symbols)

    # Assert
    assert result[0].text == source
    assert "\r\n" in result[0].text
    assert (result[0].start_line, result[0].end_line) == (1, 3)


def test_chunks_serialize_through_public_model_contract() -> None:
    # Arrange
    chunk = _chunker().chunk("VALUE = 1\n", file="src/constants.py", symbols=[])[0]

    # Act
    dumped = chunk.model_dump()
    json_payload = json.loads(chunk.model_dump_json())

    # Assert
    assert dumped == json_payload
    assert dumped["file"] == "src/constants.py"
    assert dumped["chunk_index"] == 0


@pytest.mark.parametrize(
    "file",
    ["/home/user/private.py", "../secret.py", "src/../secret.py", r"C:\secret.py"],
)
def test_input_errors_do_not_echo_unsafe_paths_or_source(file: str) -> None:
    # Arrange
    source = "TOP_SECRET_SOURCE = 1\n"

    # Act
    with pytest.raises(ValueError) as error_info:
        _chunker().chunk(source, file=file, symbols=[])

    # Assert
    assert str(error_info.value) == "Chunker input is invalid."
    assert file not in str(error_info.value)
    assert source not in str(error_info.value)


def test_symbol_file_or_range_mismatch_is_rejected_safely() -> None:
    # Arrange
    source = "def ready():\n    pass\n"
    symbol = _manual_symbol(
        name="ready",
        kind="function",
        start_line=1,
        end_line=3,
        file="src/other.py",
    )

    # Act and Assert
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(source, file="src/example.py", symbols=[symbol])


def test_symbol_language_mismatch_is_rejected_safely() -> None:
    # Arrange
    source = "def ready():\n    pass\n"
    symbol = _symbols(source)[0].model_copy(update={"language": "javascript"})

    # Act and Assert
    with pytest.raises(ValueError, match="Symbol ranges are inconsistent"):
        _chunker().chunk(source, file="src/example.py", symbols=[symbol])


def test_large_multiline_source_has_bounded_tokenizer_work() -> None:
    # Arrange
    source = "".join(f"VALUE_{index} = {index}\n" for index in range(600))
    tokenizer = FakeWordpieceTokenizer()

    # Act
    result = _chunker(tokenizer, maximum=35, overlap=4).chunk(
        source, file="src/constants.py", symbols=[]
    )

    # Assert
    assert len(result) > 1
    assert tokenizer.offset_calls == 1
    assert tokenizer.count_calls < 1_200
    assert tokenizer.processed_characters < len(source) * 20
    assert _merge_overlaps([chunk.text for chunk in result]) == source


def test_complete_embedding_budget_not_source_only_budget_controls_splitting() -> None:
    # Arrange
    source = "def compact():\n" + "".join(f"    value_{index} = {index}\n" for index in range(8))
    symbol = _symbols(source)[0]
    tokenizer = FakeWordpieceTokenizer()
    source_only_count = tokenizer.count_wordpieces(source)

    # Act
    result = _chunker(tokenizer, maximum=source_only_count + 1, overlap=2).chunk(
        source, file="src/example.py", symbols=[symbol]
    )

    # Assert
    assert len(result) > 1
    _assert_budget(result, [symbol], tokenizer, source_only_count + 1)


def test_no_filesystem_model_or_network_api_is_exposed_by_chunker() -> None:
    # Arrange
    public_names = set(dir(CodeChunker))

    # Act and Assert
    assert "from_pretrained" not in public_names
    assert "encode" not in public_names
    assert "read" not in public_names
    assert "write" not in public_names
