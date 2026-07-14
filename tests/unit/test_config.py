"""Tests for immutable validated application configuration."""

from pathlib import Path
from typing import Any, BinaryIO

import pytest
from pydantic import ValidationError

import codescope.config as config_module
from codescope.config import AppConfig, load_config
from codescope.exceptions import ErrorCode, InvalidConfigError, InvalidPathError

VALID_CONFIG = """\
[server]
name = "codescope"
transport = "stdio"

[index]
root = "."
languages = ["python"]
include_extensions = [".py", ".pyi"]
exclude = [".git", ".codescope"]
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


def _write_config(directory: Path, content: str = VALID_CONFIG) -> Path:
    config_path = directory / "codescope.toml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def _replace(content: str, old: str, new: str) -> str:
    replaced = content.replace(old, new)
    if replaced == content:
        raise AssertionError("test fixture replacement did not match")
    return replaced


def test_load_config_valid_configuration_resolves_immutable_models(tmp_path: Path) -> None:
    # Arrange
    config_path = _write_config(tmp_path)

    # Act
    result = load_config(config_path)

    # Assert
    assert isinstance(result, AppConfig)
    assert result.index.root == tmp_path.resolve()
    assert result.index.languages == ("python",)


def test_load_config_resolves_paths_relative_to_config_directory(tmp_path: Path) -> None:
    # Arrange
    repository = tmp_path / "repository"
    repository.mkdir()
    content = _replace(VALID_CONFIG, 'root = "."', 'root = "repository"')
    content = _replace(content, 'path = ".codescope"', 'path = "runtime/index"')
    config_path = _write_config(tmp_path, content)

    # Act
    result = load_config(config_path)

    # Assert
    assert result.index.root == repository.resolve()
    assert result.storage.path == (tmp_path / "runtime/index").resolve()


def test_load_config_uses_binary_tomllib_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    config_path = _write_config(tmp_path)
    original_load = config_module.tomllib.load
    observed_binary = False

    def spy_load(file: BinaryIO) -> dict[str, Any]:
        nonlocal observed_binary
        observed_binary = file.read(0) == b""
        return original_load(file)

    monkeypatch.setattr(config_module.tomllib, "load", spy_load)

    # Act
    load_config(config_path)

    # Assert
    assert observed_binary is True


@pytest.mark.parametrize(
    ("content", "replacement"),
    [
        ("missing_section", VALID_CONFIG.split("[storage]", maxsplit=1)[0]),
        ("extra_field", VALID_CONFIG + "\nunknown = true\n"),
        ("invalid_transport", _replace(VALID_CONFIG, 'transport = "stdio"', 'transport = "http"')),
        ("empty_server_name", _replace(VALID_CONFIG, 'name = "codescope"', 'name = "   "')),
        ("duplicate_language", _replace(VALID_CONFIG, '["python"]', '["python", "PYTHON"]')),
        ("duplicate_extension", _replace(VALID_CONFIG, '[".py", ".pyi"]', '[".py", ".py"]')),
        ("empty_extensions", _replace(VALID_CONFIG, '[".py", ".pyi"]', "[]")),
        ("uppercase_extension", _replace(VALID_CONFIG, '".pyi"', '".PY"')),
        ("empty_exclusion", _replace(VALID_CONFIG, '[".git", ".codescope"]', '[".git", " "]')),
        ("unsupported_device", _replace(VALID_CONFIG, 'device = "cpu"', 'device = "mps"')),
        (
            "empty_model",
            _replace(
                VALID_CONFIG, 'model = "sentence-transformers/all-MiniLM-L6-v2"', 'model = " "'
            ),
        ),
        (
            "empty_collection",
            _replace(VALID_CONFIG, 'collection = "codescope_chunks"', 'collection = " "'),
        ),
    ],
)
def test_load_config_structural_errors_raise_safe_config_error(
    tmp_path: Path, content: str, replacement: str
) -> None:
    # Arrange
    config_path = _write_config(tmp_path, replacement)

    # Act
    with pytest.raises(InvalidConfigError) as error_info:
        load_config(config_path)

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_CONFIG
    assert str(tmp_path) not in str(error_info.value)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("max_file_size_kb = 500", "max_file_size_kb = 0"),
        ("max_chunk_wordpieces = 220", "max_chunk_wordpieces = -1"),
        ("chunk_overlap_wordpieces = 30", "chunk_overlap_wordpieces = -1"),
        ("batch_size = 32", "batch_size = 0"),
        ("default_limit = 5", "default_limit = 0"),
        ("maximum_limit = 20", "maximum_limit = -1"),
        ("minimum_query_characters = 2", "minimum_query_characters = 0"),
        ("chunk_overlap_wordpieces = 30", "chunk_overlap_wordpieces = 220"),
        ("chunk_overlap_wordpieces = 30", "chunk_overlap_wordpieces = 221"),
        ("default_limit = 5", "default_limit = 21"),
    ],
)
def test_load_config_invalid_limits_raise_config_error(tmp_path: Path, old: str, new: str) -> None:
    # Arrange
    config_path = _write_config(tmp_path, _replace(VALID_CONFIG, old, new))

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(config_path)


@pytest.mark.parametrize("language", ["typescript", "", "python3"])
def test_load_config_unsupported_language_raises_config_error(
    tmp_path: Path, language: str
) -> None:
    # Arrange
    content = _replace(VALID_CONFIG, '["python"]', f'["{language}"]')
    config_path = _write_config(tmp_path, content)

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(config_path)


def test_load_config_missing_file_raises_safe_config_error(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "secret-config.toml"

    # Act
    with pytest.raises(InvalidConfigError) as error_info:
        load_config(missing)

    # Assert
    assert str(missing) not in str(error_info.value)


def test_load_config_directory_path_raises_safe_config_error(tmp_path: Path) -> None:
    # Arrange and Act
    with pytest.raises(InvalidConfigError) as error_info:
        load_config(tmp_path)

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_CONFIG


def test_load_config_malformed_toml_does_not_echo_contents(tmp_path: Path) -> None:
    # Arrange
    secret_marker = "DO_NOT_LEAK_THIS_VALUE"
    config_path = _write_config(tmp_path, f"[server\nsecret = '{secret_marker}'")

    # Act
    with pytest.raises(InvalidConfigError) as error_info:
        load_config(config_path)

    # Assert
    assert secret_marker not in str(error_info.value)


def test_load_config_symlink_file_is_rejected(tmp_path: Path) -> None:
    # Arrange
    target = _write_config(tmp_path)
    link = tmp_path / "linked.toml"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(link)


def test_load_config_symlinked_parent_directory_is_rejected(tmp_path: Path) -> None:
    # Arrange
    trusted = tmp_path / "trusted"
    outside = tmp_path / "outside"
    trusted.mkdir()
    outside.mkdir()
    _write_config(outside)
    alias = trusted / "config-alias"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(alias / "codescope.toml")


def test_load_config_missing_index_root_raises_config_error(tmp_path: Path) -> None:
    # Arrange
    content = _replace(VALID_CONFIG, 'root = "."', 'root = "missing"')
    config_path = _write_config(tmp_path, content)

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(config_path)


def test_load_config_index_root_file_raises_config_error(tmp_path: Path) -> None:
    # Arrange
    root_file = tmp_path / "root.py"
    root_file.write_text("", encoding="utf-8")
    content = _replace(VALID_CONFIG, 'root = "."', 'root = "root.py"')
    config_path = _write_config(tmp_path, content)

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(config_path)


def test_load_config_absent_storage_path_is_accepted(tmp_path: Path) -> None:
    # Arrange
    config_path = _write_config(tmp_path)

    # Act
    result = load_config(config_path)

    # Assert
    assert result.storage.path == (tmp_path / ".codescope").resolve()
    assert not result.storage.path.exists()


def test_load_config_existing_storage_directory_is_accepted(tmp_path: Path) -> None:
    # Arrange
    storage = tmp_path / ".codescope"
    storage.mkdir()
    config_path = _write_config(tmp_path)

    # Act
    result = load_config(config_path)

    # Assert
    assert result.storage.path == storage.resolve()


def test_load_config_existing_storage_file_is_rejected(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / ".codescope").write_text("not a directory", encoding="utf-8")
    config_path = _write_config(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidConfigError):
        load_config(config_path)


def test_app_config_is_frozen_and_collections_are_tuples(tmp_path: Path) -> None:
    # Arrange
    config = load_config(_write_config(tmp_path))

    # Act and Assert
    with pytest.raises(ValidationError):
        config.server = config.server  # type: ignore[misc]
    assert isinstance(config.index.languages, tuple)
    assert isinstance(config.index.include_extensions, tuple)
    assert isinstance(config.index.exclude, tuple)


def test_with_index_root_returns_new_config_without_mutating_original(tmp_path: Path) -> None:
    # Arrange
    config = load_config(_write_config(tmp_path))
    override = tmp_path / "override"
    override.mkdir()

    # Act
    result = config.with_index_root(override)

    # Assert
    assert result is not config
    assert result.index.root == override.resolve()
    assert config.index.root == tmp_path.resolve()
    assert result.storage is config.storage


def test_with_index_root_relative_override_uses_invocation_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = load_config(_write_config(config_dir))
    invocation_dir = tmp_path / "invocation"
    override = invocation_dir / "repository"
    override.mkdir(parents=True)
    monkeypatch.chdir(invocation_dir)

    # Act
    result = config.with_index_root(Path("repository"))

    # Assert
    assert result.index.root == override.resolve()
    assert config.index.root == config_dir.resolve()


def test_with_index_root_invalid_override_raises_path_error(tmp_path: Path) -> None:
    # Arrange
    config = load_config(_write_config(tmp_path))

    # Act and Assert
    with pytest.raises(InvalidPathError):
        config.with_index_root(tmp_path / "missing")
