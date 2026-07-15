"""Tree-sitter Python parsing and bounded symbol extraction."""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import PurePosixPath, PureWindowsPath
from typing import Final, Literal

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from codescope.exceptions import ParseFailedError
from codescope.models import Symbol
from codescope.utils.language import SupportedLanguage, normalize_language

_FUNCTION_NODE: Final = "function_definition"
_ASYNC_FUNCTION_NODE: Final = "async_function_definition"
_CLASS_NODE: Final = "class_definition"
_DECORATED_NODE: Final = "decorated_definition"
_SAFE_PARSE_MESSAGE: Final = "Python source parsing could not be completed safely."
_SAFE_PATH_MESSAGE: Final = "The parser file name must be a project-relative POSIX path."

type SymbolKind = Literal["function", "async_function", "class", "method"]


def _build_python_parser() -> Parser:
    try:
        language = Language(tree_sitter_python.language())
        return Parser(language)
    except (ImportError, OSError, RuntimeError, SystemError, TypeError, ValueError) as error:
        raise ParseFailedError(_SAFE_PARSE_MESSAGE) from error


def _validate_file_name(file: str) -> None:
    if not isinstance(file, str) or not file or file.strip() != file or "\\" in file:
        raise ParseFailedError(_SAFE_PATH_MESSAGE)
    segments = file.split("/")
    windows_path = PureWindowsPath(file)
    if (
        PurePosixPath(file).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ParseFailedError(_SAFE_PATH_MESSAGE)


def _decode_identifier(node: Node, source: bytes) -> str | None:
    if node.type != "identifier" or node.is_error or node.is_missing:
        return None
    try:
        value = source[node.start_byte : node.end_byte].decode("utf-8")
    except UnicodeDecodeError:
        return None
    return value if value else None


def _line_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets


def _point_offset(offsets: list[int], row: int, column: int) -> int:
    if row >= len(offsets) - 1:
        return offsets[-1]
    return offsets[row] + column


def _normalize_signature(signature: str) -> str | None:
    """Join declaration lines without rewriting string-literal token contents."""
    lines = signature.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    pieces: list[str] = []
    previous_end = 0
    previous_token = ""
    ignored = {
        tokenize.COMMENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    try:
        tokens = tokenize.generate_tokens(io.StringIO(signature).readline)
        for token in tokens:
            if token.type in ignored:
                continue
            start = _point_offset(offsets, token.start[0] - 1, token.start[1])
            end = _point_offset(offsets, token.end[0] - 1, token.end[1])
            gap = signature[previous_end:start]
            if "\n" in gap or "\r" in gap:
                normalized_gap = (
                    ""
                    if previous_token in {"(", "[", "{"} or token.string in {")", "]", "}"}
                    else " "
                )
            else:
                normalized_gap = gap
            pieces.append(normalized_gap)
            pieces.append(token.string)
            previous_end = end
            previous_token = token.string
    except (IndentationError, tokenize.TokenError):
        return None
    normalized = "".join(pieces).strip()
    return normalized if normalized else None


def _signature(definition: Node, source: bytes) -> str | None:
    body = definition.child_by_field_name("body")
    if body is None or body.is_error or body.is_missing:
        return None
    header_colon = next(
        (
            child
            for child in definition.children
            if child.type == ":" and child.end_byte <= body.start_byte
        ),
        None,
    )
    if header_colon is None or header_colon.is_missing:
        return None
    decoded = source[definition.start_byte : header_colon.end_byte].decode(
        "utf-8", errors="replace"
    )
    return _normalize_signature(decoded)


def _docstring(definition: Node, source: bytes) -> str | None:
    body = definition.child_by_field_name("body")
    if body is None or body.is_error or body.is_missing:
        return None
    statement = next(
        (child for child in body.named_children if child.type != "comment"),
        None,
    )
    if statement is None or statement.type != "expression_statement":
        return None
    expressions = statement.named_children
    if len(expressions) != 1 or expressions[0].type != "string":
        return None
    string_node = expressions[0]
    if string_node.has_error or string_node.is_error or string_node.is_missing:
        return None
    try:
        literal = source[string_node.start_byte : string_node.end_byte].decode("utf-8")
        value = ast.literal_eval(literal)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _is_async_function(definition: Node) -> bool:
    if definition.type == _ASYNC_FUNCTION_NODE:
        return True
    return bool(definition.children and definition.children[0].type == "async")


def _is_reliable_definition(definition: Node) -> bool:
    if definition.is_error or definition.is_missing:
        return False
    name = definition.child_by_field_name("name")
    body = definition.child_by_field_name("body")
    if name is None or body is None or name.is_error or name.is_missing or body.is_missing:
        return False
    if definition.type in {_FUNCTION_NODE, _ASYNC_FUNCTION_NODE}:
        parameters = definition.child_by_field_name("parameters")
        return parameters is not None and not parameters.has_error and not parameters.is_missing
    if definition.type == _CLASS_NODE:
        superclasses = definition.child_by_field_name("superclasses")
        return superclasses is None or (not superclasses.has_error and not superclasses.is_missing)
    return False


def _unwrap_definition(node: Node) -> tuple[Node, Node] | None:
    if node.type == _DECORATED_NODE:
        definition = node.child_by_field_name("definition")
        if definition is None:
            return None
        return definition, node
    if node.type in {_FUNCTION_NODE, _ASYNC_FUNCTION_NODE, _CLASS_NODE}:
        return node, node
    return None


class CodeParser:
    """Parse supported source code into immutable CodeScope symbols."""

    def __init__(self) -> None:
        """Initialize and retain one stable Tree-sitter Python parser."""
        self._parser = _build_python_parser()

    def parse(
        self,
        source: bytes,
        *,
        file: str,
        language: str = "python",
    ) -> list[Symbol]:
        """Parse Python source bytes into deterministic symbols.

        The caller is responsible for validating and reading a repository file, then
        passing its bytes and project-relative POSIX path here. This method performs
        no filesystem access.

        Args:
            source: Python source that has already been read by a validated caller.
            file: Project-relative POSIX path used in public symbol output.
            language: Supported language name, normalized through the language contract.

        Returns:
            Symbols in source order. Each class is followed by its direct methods.

        Raises:
            InvalidLanguageError: If language is not Python.
            ParseFailedError: If the path contract or parser binding fails safely.
        """
        normalized_language = normalize_language(language)
        _validate_file_name(file)
        if not isinstance(source, bytes):
            raise ParseFailedError(_SAFE_PARSE_MESSAGE)
        if not source:
            return []
        try:
            root = self._parser.parse(source).root_node
        except (RuntimeError, SystemError, TypeError, ValueError) as error:
            raise ParseFailedError(_SAFE_PARSE_MESSAGE) from error
        return self._extract_module_symbols(root, source, file, normalized_language)

    def _extract_module_symbols(
        self,
        root: Node,
        source: bytes,
        file: str,
        language: SupportedLanguage,
    ) -> list[Symbol]:
        symbols: list[Symbol] = []
        for node in root.named_children:
            unwrapped = _unwrap_definition(node)
            if unwrapped is None:
                continue
            definition, range_node = unwrapped
            if definition.type == _CLASS_NODE:
                class_symbol = self._make_symbol(
                    definition, range_node, source, file, language, qualified_parent=None
                )
                if class_symbol is None:
                    continue
                symbols.append(class_symbol)
                symbols.extend(
                    self._extract_direct_methods(
                        definition, source, file, language, class_symbol.name
                    )
                )
            elif definition.type in {_FUNCTION_NODE, _ASYNC_FUNCTION_NODE}:
                symbol = self._make_symbol(
                    definition, range_node, source, file, language, qualified_parent=None
                )
                if symbol is not None:
                    symbols.append(symbol)
        return symbols

    def _extract_direct_methods(
        self,
        class_definition: Node,
        source: bytes,
        file: str,
        language: SupportedLanguage,
        class_name: str,
    ) -> list[Symbol]:
        body = class_definition.child_by_field_name("body")
        if body is None:
            return []
        methods: list[Symbol] = []
        for node in body.named_children:
            unwrapped = _unwrap_definition(node)
            if unwrapped is None:
                continue
            definition, range_node = unwrapped
            if definition.type not in {_FUNCTION_NODE, _ASYNC_FUNCTION_NODE}:
                continue
            symbol = self._make_symbol(
                definition, range_node, source, file, language, qualified_parent=class_name
            )
            if symbol is not None:
                methods.append(symbol)
        return methods

    def _make_symbol(
        self,
        definition: Node,
        range_node: Node,
        source: bytes,
        file: str,
        language: SupportedLanguage,
        qualified_parent: str | None,
    ) -> Symbol | None:
        if not _is_reliable_definition(definition):
            return None
        name_node = definition.child_by_field_name("name")
        if name_node is None:
            return None
        name = _decode_identifier(name_node, source)
        signature = _signature(definition, source)
        if name is None or signature is None:
            return None
        kind: SymbolKind
        if qualified_parent is not None:
            kind = "method"
        elif definition.type == _CLASS_NODE:
            kind = "class"
        elif _is_async_function(definition):
            kind = "async_function"
        else:
            kind = "function"
        qualified_name = f"{qualified_parent}.{name}" if qualified_parent else name
        return Symbol(
            name=name,
            kind=kind,
            file=file,
            start_line=range_node.start_point.row + 1,
            end_line=range_node.end_point.row + 1,
            signature=signature,
            qualified_name=qualified_name,
            docstring=_docstring(definition, source),
            language=language,
        )
