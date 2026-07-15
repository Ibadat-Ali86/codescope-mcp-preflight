"""Tests for Tree-sitter Python symbol extraction."""

import json
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest

import codescope.parser as parser_module
from codescope.exceptions import ErrorCode, InvalidLanguageError, ParseFailedError
from codescope.models import Symbol
from codescope.parser import CodeParser

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "sample_python"


def _parse_fixture(name: str) -> list[Symbol]:
    path = FIXTURE_ROOT / name
    return CodeParser().parse(path.read_bytes(), file=f"tests/fixtures/sample_python/{name}")


def _symbol(symbols: list[Symbol], name: str) -> Symbol:
    return next(symbol for symbol in symbols if symbol.name == name)


def test_parser_initializes_with_installed_python_grammar() -> None:
    # Arrange and Act
    parser = CodeParser()

    # Assert
    assert parser._parser.language is not None


def test_parser_empty_source_returns_empty_symbols() -> None:
    # Arrange
    parser = CodeParser()

    # Act
    result = parser.parse(b"", file="empty.py")

    # Assert
    assert result == []


def test_parser_normalizes_python_language() -> None:
    # Arrange
    parser = CodeParser()

    # Act
    result = parser.parse(b"def ready():\n    pass\n", file="ready.py", language=" PYTHON ")

    # Assert
    assert result[0].language == "python"


def test_parser_unsupported_language_raises_stable_error() -> None:
    # Arrange
    parser = CodeParser()

    # Act
    with pytest.raises(InvalidLanguageError) as error_info:
        parser.parse(b"", file="empty.py", language="typescript")

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_LANGUAGE


def test_parser_reuses_initialized_parser_across_calls() -> None:
    # Arrange
    parser = CodeParser()
    initialized_parser = parser._parser

    # Act
    parser.parse(b"def first():\n    pass\n", file="first.py")
    parser.parse(b"def second():\n    pass\n", file="second.py")

    # Assert
    assert parser._parser is initialized_parser


def test_parser_results_are_deterministic_across_repeated_parses() -> None:
    # Arrange
    parser = CodeParser()
    source = (FIXTURE_ROOT / "services.py").read_bytes()

    # Act
    first = parser.parse(source, file="services.py")
    second = parser.parse(source, file="services.py")

    # Assert
    assert first == second


def test_parser_extracts_top_level_sync_and_async_functions() -> None:
    # Arrange and Act
    validator = _symbol(_parse_fixture("validators.py"), "validate_email")
    authenticate = _symbol(_parse_fixture("auth.py"), "authenticate")

    # Assert
    assert (validator.kind, validator.qualified_name) == ("function", "validate_email")
    assert (authenticate.kind, authenticate.qualified_name) == (
        "async_function",
        "authenticate",
    )
    assert authenticate.signature.startswith("async def ")


def test_parser_normalizes_large_multiline_signature_deterministically() -> None:
    # Arrange
    parameters = b"".join(f"    value_{index}: int = {index},\n".encode() for index in range(200))
    source = b"def wide(\n" + parameters + b") -> int:\n    return 1\n"

    # Act
    result = CodeParser().parse(source, file="wide.py")

    # Assert
    assert len(result) == 1
    assert result[0].signature.startswith("def wide(value_0: int = 0,")
    assert result[0].signature.endswith("value_199: int = 199,) -> int:")


def test_parser_extracts_typed_multiline_signature_without_body() -> None:
    # Arrange
    source = b"""def convert(
    value: str = "a  b",
    *,
    strict: bool = True,
) -> tuple[str, bool]:
    return value, strict
"""

    # Act
    result = CodeParser().parse(source, file="convert.py")

    # Assert
    assert result[0].signature == (
        'def convert(value: str = "a  b", *, strict: bool = True,) -> tuple[str, bool]:'
    )
    assert "return value" not in result[0].signature


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (b'def one():\n    "One line."\n    return 1\n', "One line."),
        (
            b'def multi():\n    """First line.\n\n    Second line.\n    """\n    return 1\n',
            "First line.\n\n    Second line.\n    ",
        ),
        (b"def missing():\n    return 1\n", None),
        (b'def bytes_doc():\n    b"Not text."\n    return 1\n', None),
        (b'def not_first():\n    value = 1\n    "Not a docstring."\n', None),
        (b'def malformed():\n    "\\x"\n', None),
    ],
)
def test_parser_extracts_only_reliable_docstrings(source: bytes, expected: str | None) -> None:
    # Arrange and Act
    result = CodeParser().parse(source, file="docstrings.py")

    # Assert
    assert result[0].docstring == expected


def test_parser_extracts_class_and_direct_methods_in_documented_order() -> None:
    # Arrange and Act
    symbols = _parse_fixture("auth.py")

    # Assert
    assert [symbol.name for symbol in symbols] == [
        "authenticate",
        "AuthService",
        "__init__",
        "validate_token",
    ]
    assert _symbol(symbols, "AuthService").docstring == "Provide authentication operations."
    initializer = _symbol(symbols, "__init__")
    assert initializer.qualified_name == "AuthService.__init__"
    assert initializer.docstring == "Store the expected issuer."


def test_parser_class_signature_preserves_bases_and_keywords() -> None:
    # Arrange and Act
    service = _symbol(_parse_fixture("services.py"), "UserService")

    # Assert
    assert service.kind == "class"
    assert service.signature == "class UserService(BaseService, metaclass=ServiceMeta):"


def test_parser_async_and_decorated_methods_remain_method_kind() -> None:
    # Arrange and Act
    symbols = _parse_fixture("services.py")
    display_name = _symbol(symbols, "display_name")
    load = _symbol(symbols, "load")

    # Assert
    assert (display_name.kind, display_name.qualified_name) == (
        "method",
        "UserService.display_name",
    )
    assert (load.kind, load.qualified_name) == ("method", "UserService.load")
    assert load.signature.startswith("async def ")


def test_parser_decorated_ranges_include_decorators_without_duplicate_symbols() -> None:
    # Arrange
    source = b'''@first
@second("task")
async def task(
    value: int,
) -> bool:
    """Task docs."""
    return bool(value)

@sealed
class Example(Base):
    """Class docs."""

    @property
    def value(self) -> int:
        return 1
'''

    # Act
    symbols = CodeParser().parse(source, file="decorated.py")

    # Assert
    assert [(symbol.name, symbol.start_line, symbol.end_line) for symbol in symbols] == [
        ("task", 1, 7),
        ("Example", 9, 15),
        ("value", 13, 15),
    ]
    assert len({(symbol.name, symbol.qualified_name) for symbol in symbols}) == len(symbols)
    assert all("@" not in symbol.signature for symbol in symbols)


def test_parser_decorated_sync_function_uses_outer_range_once() -> None:
    # Arrange and Act
    symbols = _parse_fixture("validators.py")
    username = _symbol(symbols, "validate_username")

    # Assert
    assert (username.start_line, username.end_line) == (12, 19)
    assert username.kind == "function"
    assert sum(symbol.name == "validate_username" for symbol in symbols) == 1
    assert "@" not in username.signature


def test_parser_reports_exact_one_based_fixture_lines_and_relative_file() -> None:
    # Arrange and Act
    symbol = _symbol(_parse_fixture("validators.py"), "validate_email")

    # Assert
    assert (symbol.start_line, symbol.end_line) == (6, 9)
    assert symbol.file == "tests/fixtures/sample_python/validators.py"
    assert not symbol.file.startswith("/")


def test_parser_excludes_non_symbol_and_nested_function_nodes() -> None:
    # Arrange
    source = b"""import os
assigned = lambda value: value

def outer():
    nested_value = 1
    def nested():
        return nested_value
    return nested()

class Example:
    value = lambda self: 1

if assigned:
    def conditional():
        pass
"""

    # Act
    symbols = CodeParser().parse(source, file="scope.py")

    # Assert
    assert [(symbol.name, symbol.kind) for symbol in symbols] == [
        ("outer", "function"),
        ("Example", "class"),
    ]


def test_parser_recovers_valid_definition_before_malformed_syntax() -> None:
    # Arrange
    source = b"""def recovered(value: int) -> int:
    return value

def incomplete(
    value: int,
"""

    # Act
    symbols = CodeParser().parse(source, file="malformed.py")

    # Assert
    assert [(symbol.name, symbol.kind) for symbol in symbols] == [("recovered", "function")]


@pytest.mark.parametrize(
    ("source", "expected_names"),
    [
        (b"def (\n@@@", []),
        (b"class :\n    ???\n", []),
        (b"def broken(value:):\n    pass\n", []),
        (b"def incomplete(\n    value: int,\n", []),
        (b"class Broken:\n    def method(\n", ["Broken"]),
    ],
)
def test_parser_malformed_syntax_returns_only_strictly_valid_partial_results(
    source: bytes, expected_names: list[str]
) -> None:
    # Arrange and Act
    result = CodeParser().parse(source, file="malformed.py")

    # Assert
    assert [symbol.name for symbol in result] == expected_names


def test_parser_symbol_serialization_preserves_public_contract() -> None:
    # Arrange
    result = _symbol(_parse_fixture("validators.py"), "validate_email")

    # Act
    dumped = result.model_dump()
    json_payload = json.loads(result.model_dump_json())

    # Assert
    assert isinstance(result, Symbol)
    assert dumped == json_payload
    assert dumped["language"] == "python"
    assert dumped["start_line"] == 6


@pytest.mark.parametrize(
    "file",
    [
        "/home/user/secret.py",
        "../secret.py",
        "src/../secret.py",
        r"C:\secret.py",
        r"\\server\share\secret.py",
    ],
)
def test_parser_rejects_unsafe_public_file_names_without_echoing_input(file: str) -> None:
    # Arrange
    parser = CodeParser()

    # Act
    with pytest.raises(ParseFailedError) as error_info:
        parser.parse(b"def safe():\n    pass\n", file=file)

    # Assert
    assert error_info.value.code is ErrorCode.PARSE_FAILED
    assert file not in str(error_info.value)


def test_parser_initialization_failure_translates_to_safe_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    secret = "/home/user/private/source.py"

    def fail_language(_binding: object) -> NoReturn:
        raise RuntimeError(secret)

    monkeypatch.setattr(parser_module, "Language", fail_language)

    # Act
    with pytest.raises(ParseFailedError) as error_info:
        CodeParser()

    # Assert
    assert str(error_info.value) == "Python source parsing could not be completed safely."
    assert secret not in str(error_info.value)
    assert isinstance(error_info.value.__cause__, RuntimeError)


def test_parser_binding_failure_does_not_leak_source_or_path() -> None:
    # Arrange
    secret_source = b"TOP_SECRET_SOURCE"
    secret_path = "/home/user/private.py"
    parser = CodeParser()

    class FailingParser:
        def parse(self, source: bytes) -> NoReturn:
            raise ValueError(source.decode())

    parser._parser = cast(Any, FailingParser())

    # Act
    with pytest.raises(ParseFailedError) as error_info:
        parser.parse(secret_source, file="safe.py")

    # Assert
    assert str(error_info.value) == "Python source parsing could not be completed safely."
    assert secret_source.decode() not in str(error_info.value)
    assert secret_path not in str(error_info.value)
    assert isinstance(error_info.value.__cause__, ValueError)


def test_parser_rejects_non_bytes_source_safely() -> None:
    # Arrange
    parser = CodeParser()

    # Act and Assert
    with pytest.raises(ParseFailedError):
        parser.parse("def invalid(): pass", file="invalid.py")  # type: ignore[arg-type]
