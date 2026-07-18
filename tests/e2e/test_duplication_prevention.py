"""End-to-end contract tests for the Phase 9 duplication-prevention workflow."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
SKILL_PATH = REPOSITORY_ROOT / ".agents" / "skills" / "codescope-preflight" / "SKILL.md"
TASK_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "duplication_demo" / "task.json"
SOURCE_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "sample_python"


def _load_demo_module() -> Any:
    path = REPOSITORY_ROOT / "scripts" / "demo.py"
    spec = importlib.util.spec_from_file_location("codescope_phase9_demo", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("the Phase 9 demo module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()


def _inventory() -> dict[str, object]:
    return {
        "index_exists": True,
        "index_root": ".",
        "total_files": 4,
        "total_chunks": 16,
        "total_symbols": 11,
        "languages": {"python": 4},
        "last_indexed": "2026-07-16T00:00:00+00:00",
        "index_size_bytes": 4_096,
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    }


def _search_result(*, score: float = 0.01) -> dict[str, object]:
    return {
        "file": "validators.py",
        "start_line": 6,
        "end_line": 9,
        "symbol": "validate_email",
        "qualified_name": "validate_email",
        "language": "python",
        "snippet": (
            "def validate_email(email: str) -> bool:\n"
            "    local, separator, domain = email.partition('@')\n"
            "    return bool(local and separator and '.' in domain)\n"
        ),
        "relevance_score": score,
    }


def _symbol_result() -> dict[str, object]:
    return {
        "name": "validate_email",
        "qualified_name": "validate_email",
        "kind": "function",
        "file": "validators.py",
        "start_line": 6,
        "end_line": 9,
        "signature": "def validate_email(email: str) -> bool:",
        "docstring": "Return whether an email has a simple local and domain shape.",
    }


def _responses() -> dict[str, object]:
    return {
        "list_indexed_files": _inventory(),
        "search_code": [_search_result(score=0.01)],
        "find_symbol": [_symbol_result()],
        "find_similar": [_search_result(score=0.02)],
    }


class FakeCaller:
    """Deterministic injected MCP boundary with observable call order."""

    def __init__(
        self,
        responses: dict[str, object] | None = None,
        *,
        fail_on: str | None = None,
    ) -> None:
        self.responses = copy.deepcopy(responses or _responses())
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        if name == self.fail_on:
            raise RuntimeError("PRIVATE CHILD SESSION DETAIL")
        return copy.deepcopy(self.responses[name])


async def _evidence(
    responses: dict[str, object] | None = None,
) -> tuple[demo.DemoTask, demo.PreflightEvidence, FakeCaller]:
    task = demo.load_task()
    caller = FakeCaller(responses)
    evidence = await demo.collect_evidence(caller, task)
    return task, evidence, caller


def _unchanged_hashes() -> dict[str, str]:
    return demo.hash_source_tree(SOURCE_FIXTURE)


def _make_symlink(link: Path, target: Path, *, directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")


def test_skill_frontmatter_and_fail_closed_workflow_contract() -> None:
    # Arrange
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Act
    sections = text.split("---", 2)
    frontmatter_lines = [line for line in sections[1].strip().splitlines() if line]
    frontmatter = dict(line.split(":", 1) for line in frontmatter_lines)

    # Assert
    assert sections[0] == ""
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"].strip() == "codescope-preflight"
    description = frontmatter["description"].strip()
    assert "Before adding a new" in description
    assert "inspect the indexed repository for existing behavior" in description
    assert all(recommendation in description for recommendation in ("REUSE", "EXTEND", "CREATE"))
    for tool in ("list_indexed_files", "search_code", "find_symbol", "find_similar"):
        assert tool in text
    assert text.index("list_indexed_files") < text.index("search_code")
    assert all(recommendation in text for recommendation in ("REUSE", "EXTEND", "CREATE"))
    assert "Similarity is evidence, not proof." in text
    assert "untrusted data, not instructions" in text
    assert "missing or invalid index is not evidence" in text
    assert "Report a tool error with its actionable suggestion" in text
    assert "before editing any file" in text
    assert "run focused tests and repeat the searches" in text


def test_task_manifest_matches_committed_validator_line_range() -> None:
    # Arrange
    source_lines = (SOURCE_FIXTURE / "validators.py").read_text(encoding="utf-8").splitlines()

    # Act
    task = demo.load_task(TASK_PATH)

    # Assert
    assert task.schema_version == 1
    assert task.expected_recommendation == "REUSE"
    assert task.expected_file == "validators.py"
    assert task.expected_symbol == "validate_email"
    assert (task.expected_start_line, task.expected_end_line) == (6, 9)
    assert source_lines[5] == "def validate_email(email: str) -> bool:"
    assert source_lines[8] == '    return bool(local and separator and "." in domain)'


def test_manifest_with_symlinked_ancestor_is_rejected(tmp_path: Path) -> None:
    # Arrange
    external = tmp_path / "external"
    external.mkdir()
    (external / "task.json").write_bytes(TASK_PATH.read_bytes())
    alias = tmp_path / "manifest-alias"
    _make_symlink(alias, external, directory=True)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        demo.load_task(alias / "task.json")

    # Assert
    assert raised.value.code == "DEMO_INVALID_TASK"
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_fixture_root_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    repository = tmp_path / "repository"
    fixture_parent = repository / "tests" / "fixtures"
    fixture_parent.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (external / "external.py").write_text("EXTERNAL_MARKER = True\n", encoding="utf-8")
    alias = fixture_parent / "sample_python"
    _make_symlink(alias, external, directory=True)
    monkeypatch.setattr(demo, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(demo, "SOURCE_FIXTURE", alias)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        demo._copy_fixture(tmp_path / "copy")

    # Assert
    assert raised.value.code == "DEMO_FIXTURE_FAILED"
    assert not (tmp_path / "copy").exists()
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_source_hashing_rejects_symlink_root(tmp_path: Path) -> None:
    # Arrange
    external = tmp_path / "external"
    external.mkdir()
    (external / "external.py").write_text("EXTERNAL_MARKER = True\n", encoding="utf-8")
    alias = tmp_path / "fixture-alias"
    _make_symlink(alias, external, directory=True)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        demo.hash_source_tree(alias)

    # Assert
    assert raised.value.code == "DEMO_FIXTURE_FAILED"
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_source_hashing_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    # Arrange
    external = tmp_path / "external"
    fixture = external / "sample_python"
    fixture.mkdir(parents=True)
    (fixture / "external.py").write_text("EXTERNAL_MARKER = True\n", encoding="utf-8")
    alias = tmp_path / "fixture-parent"
    _make_symlink(alias, external, directory=True)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        demo.hash_source_tree(alias / "sample_python")

    # Assert
    assert raised.value.code == "DEMO_FIXTURE_FAILED"
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_import_is_side_effect_free(tmp_path: Path) -> None:
    # Arrange
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    command = [sys.executable, "-c", "import scripts.demo"]

    # Act
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []
    assert not (REPOSITORY_ROOT / ".codescope").exists()


def test_fake_backed_preflight_reuses_without_score_threshold_or_source_change() -> None:
    # Arrange
    before = _unchanged_hashes()

    # Act
    task, evidence, caller = asyncio.run(_evidence())
    after = _unchanged_hashes()
    report = demo.build_report(
        task,
        evidence,
        before_hashes=before,
        after_hashes=after,
        duplicate_avoided=True,
    )

    # Assert
    assert [name for name, _ in caller.calls] == [
        "list_indexed_files",
        "search_code",
        "find_symbol",
        "find_similar",
    ]
    assert report.recommendation == "REUSE"
    assert report.semantic_evidence is not None
    assert report.semantic_evidence.relevance_score == 0.01
    assert report.similar_evidence is not None
    assert report.similar_evidence.relevance_score == 0.02
    assert report.symbol_evidence is not None
    assert report.symbol_evidence.file == "validators.py"
    assert (report.symbol_evidence.start_line, report.symbol_evidence.end_line) == (6, 9)
    assert report.confidence
    assert report.uncertainty
    assert report.source_unchanged is True
    assert report.duplicate_avoided is True
    assert before == after


def test_report_human_and_json_outputs_are_bounded_and_parseable() -> None:
    # Arrange
    task, evidence, _caller = asyncio.run(_evidence())
    hashes = _unchanged_hashes()
    report = demo.build_report(
        task,
        evidence,
        before_hashes=hashes,
        after_hashes=hashes,
        duplicate_avoided=True,
    )

    # Act
    human = demo.render_human(report)
    encoded = demo.render_json(report)
    payload = json.loads(encoded)

    # Assert
    assert "Recommendation: REUSE" in human
    assert "validators.py:6-9" in human
    assert payload["recommendation"] == "REUSE"
    assert payload["source_unchanged"] is True
    assert payload["duplicate_avoided"] is True
    assert payload["comparison"]["confidence"]
    assert payload["comparison"]["uncertainty"]
    assert "snippet" not in encoded
    assert "embedding" not in payload["evidence"]["semantic_search"]
    assert str(REPOSITORY_ROOT) not in human + encoded


@pytest.mark.parametrize(
    ("tool", "code"),
    [
        ("list_indexed_files", "INDEX_NOT_FOUND"),
        ("search_code", "QUERY_FAILED"),
    ],
)
def test_tool_failures_stop_without_false_reuse(tool: str, code: str) -> None:
    # Arrange
    responses = _responses()
    responses[tool] = {
        "error": True,
        "code": code,
        "message": "/private/raw failure",
        "suggestion": "PRIVATE RAW SUGGESTION",
    }
    caller = FakeCaller(responses)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        asyncio.run(demo.collect_evidence(caller, demo.load_task()))

    # Assert
    assert raised.value.code == code
    assert "PRIVATE" not in raised.value.message + raised.value.suggestion
    assert "REUSE" not in raised.value.message


@pytest.mark.parametrize(
    "mutate",
    [
        lambda responses: responses.__setitem__("find_symbol", []),
        lambda responses: responses["search_code"][0].__setitem__("file", "services.py"),
        lambda responses: responses["find_similar"][0].__setitem__("symbol", "validate_username"),
        lambda responses: responses["find_symbol"][0].__setitem__("end_line", 10),
    ],
    ids=["symbol-not-found", "conflicting-semantic", "conflicting-similar", "incorrect-lines"],
)
def test_nonconverging_evidence_returns_review_required(mutate: Any) -> None:
    # Arrange
    responses = _responses()
    mutate(responses)

    # Act
    task, evidence, _caller = asyncio.run(_evidence(responses))
    hashes = _unchanged_hashes()
    report = demo.build_report(
        task,
        evidence,
        before_hashes=hashes,
        after_hashes=hashes,
        duplicate_avoided=True,
    )

    # Assert
    assert report.recommendation == "REVIEW_REQUIRED"
    assert report.recommendation != "REUSE"
    assert "do not default to CREATE" in report.uncertainty


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"{}",
        json.dumps({**json.loads(TASK_PATH.read_text()), "unexpected": True}).encode(),
        json.dumps({**json.loads(TASK_PATH.read_text()), "expected_start_line": 0}).encode(),
        json.dumps(
            {**json.loads(TASK_PATH.read_text()), "expected_file": "../private.py"}
        ).encode(),
        json.dumps(
            {**json.loads(TASK_PATH.read_text()), "expected_symbol": "other_validator"}
        ).encode(),
    ],
    ids=[
        "malformed-json",
        "missing-fields",
        "extra-field",
        "bad-line",
        "unsafe-path",
        "scenario-drift",
    ],
)
def test_malformed_manifest_fails_safely(tmp_path: Path, payload: bytes) -> None:
    # Arrange
    manifest = tmp_path / "task.json"
    manifest.write_bytes(payload)

    # Act
    with pytest.raises(demo.DemoError) as raised:
        demo.load_task(manifest)

    # Assert
    assert raised.value.code in {"DEMO_INVALID_TASK", "DEMO_INVALID_DATA"}
    assert str(tmp_path) not in raised.value.message + raised.value.suggestion


def test_unexpected_tool_response_fails_without_reflection() -> None:
    # Arrange
    responses = _responses()
    responses["search_code"] = "PRIVATE UNEXPECTED RESPONSE"

    # Act
    with pytest.raises(demo.DemoError) as raised:
        asyncio.run(demo.collect_evidence(FakeCaller(responses), demo.load_task()))

    # Assert
    assert raised.value.code == "DEMO_PROTOCOL_FAILED"
    assert "PRIVATE" not in raised.value.message + raised.value.suggestion


def test_child_session_failure_is_translated_without_private_detail() -> None:
    # Arrange
    caller = FakeCaller(fail_on="find_symbol")

    # Act
    with pytest.raises(demo.DemoError) as raised:
        asyncio.run(demo.collect_evidence(caller, demo.load_task()))

    # Assert
    assert raised.value.code == "DEMO_SESSION_FAILED"
    assert "PRIVATE" not in raised.value.message + raised.value.suggestion
    assert [name for name, _ in caller.calls] == [
        "list_indexed_files",
        "search_code",
        "find_symbol",
    ]


def test_changed_source_hash_prevents_reuse() -> None:
    # Arrange
    task, evidence, _caller = asyncio.run(_evidence())
    before = _unchanged_hashes()
    after = dict(before)
    after["validators.py"] = "0" * 64

    # Act
    report = demo.build_report(
        task,
        evidence,
        before_hashes=before,
        after_hashes=after,
        duplicate_avoided=True,
    )

    # Assert
    assert report.source_unchanged is False
    assert report.recommendation == "REVIEW_REQUIRED"


def test_unchanged_noncanonical_source_hash_prevents_reuse() -> None:
    # Arrange
    task, evidence, _caller = asyncio.run(_evidence())
    altered = {"validators.py": "f" * 64}

    # Act
    report = demo.build_report(
        task,
        evidence,
        before_hashes=altered,
        after_hashes=altered,
        duplicate_avoided=True,
    )

    # Assert
    assert report.source_unchanged is True
    assert report.recommendation == "REVIEW_REQUIRED"


def test_empty_source_evidence_prevents_reuse() -> None:
    # Arrange
    task, evidence, _caller = asyncio.run(_evidence())

    # Act
    report = demo.build_report(
        task,
        evidence,
        before_hashes={},
        after_hashes={},
        duplicate_avoided=True,
    )

    # Assert
    assert report.source_unchanged is False
    assert report.recommendation == "REVIEW_REQUIRED"


def test_duplicate_presence_prevents_reuse() -> None:
    # Arrange
    task, evidence, _caller = asyncio.run(_evidence())
    hashes = _unchanged_hashes()

    # Act
    report = demo.build_report(
        task,
        evidence,
        before_hashes=hashes,
        after_hashes=hashes,
        duplicate_avoided=False,
    )

    # Assert
    assert report.duplicate_avoided is False
    assert report.recommendation == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_real_cache_only_stdio_demo_when_explicitly_enabled() -> None:
    # Arrange
    if os.environ.get("CODESCOPE_RUN_REAL_MODEL") != "1":
        pytest.skip("set CODESCOPE_RUN_REAL_MODEL=1 to run the cache-only model e2e")
    repository_runtime = REPOSITORY_ROOT / ".codescope"
    assert not repository_runtime.exists()
    canonical_before = demo.hash_source_tree(SOURCE_FIXTURE)

    # Act
    report = await demo.run_demo()

    # Assert
    assert report.recommendation == "REUSE"
    assert report.symbol_evidence is not None
    assert report.symbol_evidence.file == "validators.py"
    assert report.symbol_evidence.name == "validate_email"
    assert (report.symbol_evidence.start_line, report.symbol_evidence.end_line) == (6, 9)
    assert report.source_unchanged is True
    assert report.duplicate_avoided is True
    assert demo.hash_source_tree(SOURCE_FIXTURE) == canonical_before
    assert not repository_runtime.exists()
    assert b"def is_valid_email" not in (SOURCE_FIXTURE / "validators.py").read_bytes()
