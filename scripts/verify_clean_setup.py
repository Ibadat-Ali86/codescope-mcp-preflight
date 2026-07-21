"""Verify the current Phase 10 candidate from an isolated real Git clone."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Final, Protocol

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
REAL_VERIFICATION_VARIABLE: Final = "CODESCOPE_RUN_CLEAN_SETUP"
_MAX_OUTPUT_BYTES: Final = 2 * 1024 * 1024
_MAX_PATCH_BYTES: Final = 16 * 1024 * 1024
_MAX_CANDIDATE_FILE_BYTES: Final = 2 * 1024 * 1024
_MIN_TIMEOUT_SECONDS: Final = 30
_MAX_TIMEOUT_SECONDS: Final = 900
_SETUP_ACCEPTANCE_SECONDS: Final = 300
_CANDIDATE_PATCH_ARGUMENTS: Final = ("diff", "--binary", "--no-ext-diff", "HEAD", "--")
_EXPECTED_TOOLS: Final = (
    "search_code",
    "find_symbol",
    "find_similar",
    "list_indexed_files",
)
AUTHORIZED_UNTRACKED_PATHS: Final = frozenset(
    {
        "scripts/benchmark.py",
        "scripts/verify_clean_setup.py",
        "tests/release/test_benchmark.py",
        "tests/release/test_clean_setup.py",
        "tests/security/test_phase10_safety.py",
        "docs/SECURITY.md",
        "docs/ARCHITECTURE.md",
        "docs/API.md",
        "docs/SETUP.md",
        "docs/BENCHMARKS.md",
        "docs/COVERAGE.md",
        "docs/TROUBLESHOOTING.md",
    }
)

_MCP_PROBE_SOURCE: Final = """
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    executable = Path(sys.executable).with_name(
        "codescope.exe" if os.name == "nt" else "codescope"
    )
    parameters = StdioServerParameters(
        command=str(executable), args=["serve"], cwd=Path.cwd(), env=dict(os.environ)
    )
    with Path(os.devnull).open("w", encoding="utf-8") as diagnostics:
        async with asyncio.timeout(120):
            async with stdio_client(parameters, errlog=diagnostics) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.list_tools()
    print(json.dumps([tool.name for tool in result.tools], separators=(",", ":")))

asyncio.run(main())
""".strip()


class SetupVerificationError(Exception):
    """Safe expected failure at the clean-setup boundary."""

    def __init__(self, code: str, message: str, suggestion: str) -> None:
        self.code = code
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded subprocess result used by the verifier."""

    returncode: int
    stdout: str
    stderr: str
    duration_ns: int


class CommandRunner(Protocol):
    """Injected subprocess boundary for deterministic release tests."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
        input_text: str | None = None,
    ) -> CommandResult: ...

    def run_candidate_patch(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
    ) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class VerificationTiming:
    """Measured clean-candidate setup durations."""

    clone_ms: float
    dependency_sync_ms: float
    setup_to_demo_ms: float
    total_ms: float


@dataclass(frozen=True, slots=True)
class CleanSetupReport:
    """Sanitized clean-candidate verification report."""

    schema_version: int
    candidate: Mapping[str, object]
    commands: tuple[str, ...]
    checks: Mapping[str, object]
    timing: VerificationTiming
    cleanup: Mapping[str, bool]

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic JSON object contract."""
        return {
            "schema_version": self.schema_version,
            "candidate": dict(self.candidate),
            "commands": list(self.commands),
            "checks": dict(self.checks),
            "timing": asdict(self.timing),
            "cleanup": dict(self.cleanup),
        }


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    head: str
    status_digest: str
    tracked_diff_digest: str
    untracked_digests: tuple[tuple[str, str], ...]


class SubprocessRunner:
    """Run fixed argv commands with bounded output and process-group cleanup."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
        input_text: str | None = None,
    ) -> CommandResult:
        """Run one command without a shell and translate failures safely."""
        return self._run_with_output_limit(
            command,
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
            output_limit_bytes=_MAX_OUTPUT_BYTES,
        )

    def run_candidate_patch(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
    ) -> CommandResult:
        """Capture only the bounded binary Git patch used for candidate materialization."""
        if (
            len(command) != len(_CANDIDATE_PATCH_ARGUMENTS) + 1
            or tuple(command[1:]) != _CANDIDATE_PATCH_ARGUMENTS
        ):
            raise SetupVerificationError(
                "CLEAN_SETUP_COMMAND_FAILED",
                "The candidate patch command is invalid.",
                "Restore the fixed candidate patch command and retry.",
            )
        return self._run_with_output_limit(
            command,
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
            output_limit_bytes=_MAX_PATCH_BYTES,
        )

    def _run_with_output_limit(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
        output_limit_bytes: int,
        input_text: str | None = None,
    ) -> CommandResult:
        """Run one fixed command with its authorized bounded output limit."""
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise SetupVerificationError(
                "CLEAN_SETUP_COMMAND_FAILED",
                "An internal clean-setup command is invalid.",
                "Restore the verifier and retry.",
            )
        if not _MIN_TIMEOUT_SECONDS <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise SetupVerificationError(
                "CLEAN_SETUP_INVALID_ARGUMENT",
                "The subprocess timeout is outside the supported range.",
                (
                    f"Use a timeout from {_MIN_TIMEOUT_SECONDS} through "
                    f"{_MAX_TIMEOUT_SECONDS} seconds."
                ),
            )
        started = time.perf_counter_ns()
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            creationflags = 0
            start_new_session = os.name != "nt"
            if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=cwd,
                    env=dict(environment),
                    stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    shell=False,
                    close_fds=True,
                    start_new_session=start_new_session,
                    creationflags=creationflags,
                )
            except OSError as error:
                raise SetupVerificationError(
                    "CLEAN_SETUP_COMMAND_FAILED",
                    "A required clean-setup command could not be started.",
                    "Verify Git, uv, and Python are installed, then retry.",
                ) from error
            timed_out = False
            try:
                process.communicate(input=input_text, timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill_process_tree(process)
                    process.wait(timeout=5)
            finally:
                _terminate_surviving_group(process)
            if timed_out:
                raise SetupVerificationError(
                    "CLEAN_SETUP_TIMEOUT",
                    "A clean-setup command exceeded its bounded timeout.",
                    "Inspect the documented prerequisite and retry with a bounded timeout.",
                )
            stdout = _read_bounded_output(stdout_file, maximum_bytes=output_limit_bytes)
            stderr = _read_bounded_output(stderr_file, maximum_bytes=output_limit_bytes)
            return CommandResult(
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ns=time.perf_counter_ns() - started,
            )


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except OSError:
        pass


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except OSError:
        pass


def _terminate_surviving_group(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        return
    try:
        os.killpg(process.pid, 0)
    except OSError:
        return
    _terminate_process_tree(process)


def _read_bounded_output(stream: BinaryIO, *, maximum_bytes: int = _MAX_OUTPUT_BYTES) -> str:
    """Read UTF-8 child output without exceeding the authorized capture limit."""
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    if not isinstance(size, int) or size > maximum_bytes:
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "A clean-setup command produced excessive output.",
            "Inspect the local tool failure and retry after correcting it.",
        )
    stream.seek(0)
    payload = stream.read()
    try:
        return payload.decode("utf-8")
    except UnicodeError as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "A clean-setup command produced invalid text output.",
            "Verify the local executable and retry.",
        ) from error


def _require_success(result: CommandResult, *, label: str) -> CommandResult:
    if result.returncode != 0:
        raise SetupVerificationError(
            "CLEAN_SETUP_COMMAND_FAILED",
            f"The {label} step failed.",
            "Review the documented prerequisites and retry the isolated verification.",
        )
    return result


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    label: str,
    input_text: str | None = None,
) -> CommandResult:
    return _require_success(
        runner.run(
            command,
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        ),
        label=label,
    )


def _safe_executable(name: str) -> Path:
    located = shutil.which(name)
    if located is None:
        raise SetupVerificationError(
            "CLEAN_SETUP_PREREQUISITE_FAILED",
            "A required local executable is unavailable.",
            "Install Git and uv, then retry.",
        )
    try:
        resolved = Path(located).resolve(strict=True)
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise OSError("executable is not regular")
        return resolved
    except OSError as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_PREREQUISITE_FAILED",
            "A required local executable is invalid.",
            "Install Git and uv from a trusted source, then retry.",
        ) from error


def _validated_model_cache(source_root: Path) -> Path:
    value = os.environ.get("CODESCOPE_MODEL_CACHE_DIR")
    try:
        if not value:
            raise OSError("cache is not configured")
        cache = Path(value).expanduser().resolve(strict=True)
        source = source_root.resolve(strict=True)
        if not cache.is_dir() or cache == source or cache.is_relative_to(source):
            raise OSError("cache boundary is unsafe")
        return cache
    except OSError as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_MODEL_UNAVAILABLE",
            "The prepared external model cache is unavailable.",
            "Set CODESCOPE_MODEL_CACHE_DIR to the prepared external cache and retry offline.",
        ) from error


def _sanitized_environment(
    inherited: Mapping[str, str],
    *,
    workspace: Path,
    model_cache: Path,
    uv_cache: Path,
    executables: Sequence[Path],
) -> dict[str, str]:
    """Create the minimum child environment without inherited secrets or Python state."""
    path_entries = [str(executable.parent) for executable in executables]
    path_entries.extend(os.defpath.split(os.pathsep))
    unique_path = list(dict.fromkeys(entry for entry in path_entries if entry))
    locale = inherited.get("LC_ALL") or inherited.get("LANG") or "C.UTF-8"
    environment = {
        "PATH": os.pathsep.join(unique_path),
        "HOME": str(workspace / "home"),
        "TMPDIR": str(workspace / "tmp"),
        "TEMP": str(workspace / "tmp"),
        "TMP": str(workspace / "tmp"),
        "LANG": locale,
        "LC_ALL": locale,
        "UV_CACHE_DIR": str(uv_cache),
        "CODESCOPE_MODEL_CACHE_DIR": str(model_cache),
        "HF_HOME": str(model_cache),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "TQDM_DISABLE": "1",
        REAL_VERIFICATION_VARIABLE: "1",
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if value := inherited.get(name):
                environment[name] = value
    return environment


def _validated_uv_cache(uv: Path, *, source_root: Path, workspace: Path) -> Path:
    """Resolve uv's external package cache without inheriting secret variables."""
    minimal_environment = {
        "PATH": os.pathsep.join((str(uv.parent), os.defpath)),
        "HOME": os.environ.get("HOME", str(workspace / "home")),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", os.environ.get("LANG", "C.UTF-8")),
    }
    if value := os.environ.get("XDG_CACHE_HOME"):
        minimal_environment["XDG_CACHE_HOME"] = value
    try:
        result = subprocess.run(
            [str(uv), "cache", "dir"],
            cwd=workspace,
            env=minimal_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout.encode("utf-8")) > 4_096:
            raise OSError("uv cache lookup failed")
        cache = Path(result.stdout.strip()).resolve(strict=True)
        source = source_root.resolve(strict=True)
        if not cache.is_dir() or cache == source or cache.is_relative_to(source):
            raise OSError("uv cache boundary is unsafe")
        return cache
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_PREREQUISITE_FAILED",
            "The external uv package cache could not be resolved safely.",
            "Verify the local uv installation and retry.",
        ) from error


def _safe_candidate_path(value: str) -> str:
    windows_path = PureWindowsPath(value)
    pure = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or pure.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "The candidate contains an unsafe untracked path.",
            "Remove the unexpected path and retry.",
        )
    return pure.as_posix()


def _validate_untracked_paths(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(_safe_candidate_path(value) for value in values))
    if len(normalized) != len(set(normalized)):
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "The candidate untracked-file list is inconsistent.",
            "Refresh the working tree and retry.",
        )
    unexpected = set(normalized).difference(AUTHORIZED_UNTRACKED_PATHS)
    if unexpected:
        raise SetupVerificationError(
            "CLEAN_SETUP_UNEXPECTED_FILE",
            "The candidate contains an unauthorized untracked file.",
            "Remove or explicitly review the unexpected file before retrying.",
        )
    return normalized


def _git_text(
    runner: CommandRunner,
    git: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    label: str,
    input_text: str | None = None,
) -> str:
    return _run(
        runner,
        [str(git), *arguments],
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label=label,
        input_text=input_text,
    ).stdout


def _candidate_patch_text(
    runner: CommandRunner,
    git: Path,
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> str:
    """Capture the only binary Git diff authorized to use the patch output limit."""
    return _require_success(
        runner.run_candidate_patch(
            [str(git), *_CANDIDATE_PATCH_ARGUMENTS],
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
        ),
        label="candidate patch",
    ).stdout


def _untracked_paths(
    runner: CommandRunner,
    git: Path,
    *,
    source_root: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> tuple[str, ...]:
    payload = _git_text(
        runner,
        git,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="candidate inventory",
    )
    values = tuple(value for value in payload.split("\0") if value)
    return _validate_untracked_paths(values)


def _candidate_file(source_root: Path, relative: str) -> Path:
    path = source_root / relative
    try:
        if path.is_symlink() or path.is_junction():
            raise OSError("candidate is a link")
        details = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
        source = source_root.resolve(strict=True)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_size > _MAX_CANDIDATE_FILE_BYTES
            or not resolved.is_relative_to(source)
        ):
            raise OSError("candidate file is unsafe")
        return resolved
    except OSError as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "An authorized candidate file is unsafe or invalid.",
            "Restore the candidate file as a bounded regular file and retry.",
        ) from error


def _digest(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _capture_source_snapshot(
    runner: CommandRunner,
    git: Path,
    *,
    source_root: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> _SourceSnapshot:
    head = _git_text(
        runner,
        git,
        ["rev-parse", "HEAD"],
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="source revision",
    ).strip()
    status = _git_text(
        runner,
        git,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="source status",
    )
    tracked_diff = _candidate_patch_text(
        runner,
        git,
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    if len(tracked_diff.encode("utf-8")) > _MAX_PATCH_BYTES:
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "The candidate tracked patch exceeds the safe verification limit.",
            "Reduce the candidate to the authorized Phase 10 scope and retry.",
        )
    untracked = _untracked_paths(
        runner,
        git,
        source_root=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    digests = tuple(
        (relative, _digest(_candidate_file(source_root, relative).read_bytes()))
        for relative in untracked
    )
    return _SourceSnapshot(
        head=head,
        status_digest=_digest(status),
        tracked_diff_digest=_digest(tracked_diff),
        untracked_digests=digests,
    )


def _materialize_candidate(
    runner: CommandRunner,
    git: Path,
    *,
    source_root: Path,
    clone_root: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> tuple[str, int]:
    """Clone HEAD, apply the tracked patch, and copy only authorized untracked files."""
    head = _git_text(
        runner,
        git,
        ["rev-parse", "HEAD"],
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="source revision",
    ).strip()
    patch = _candidate_patch_text(
        runner,
        git,
        cwd=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    if len(patch.encode("utf-8")) > _MAX_PATCH_BYTES:
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "The candidate tracked patch exceeds the safe verification limit.",
            "Reduce the candidate to the authorized Phase 10 scope and retry.",
        )
    untracked = _untracked_paths(
        runner,
        git,
        source_root=source_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    _git_text(
        runner,
        git,
        [
            "clone",
            "--no-local",
            "--no-tags",
            "--single-branch",
            "--branch",
            "main",
            str(source_root),
            str(clone_root),
        ],
        cwd=clone_root.parent,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="candidate clone",
    )
    cloned_head = _git_text(
        runner,
        git,
        ["rev-parse", "HEAD"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="cloned revision",
    ).strip()
    if cloned_head != head:
        raise SetupVerificationError(
            "CLEAN_SETUP_CANDIDATE_FAILED",
            "The isolated clone does not match the source revision.",
            "Synchronize main and retry.",
        )
    if patch:
        _git_text(
            runner,
            git,
            ["apply", "--binary", "--whitespace=nowarn", "-"],
            cwd=clone_root,
            environment=environment,
            timeout_seconds=timeout_seconds,
            label="candidate patch application",
            input_text=patch,
        )
    for relative in untracked:
        source = _candidate_file(source_root, relative)
        destination = clone_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    _git_text(
        runner,
        git,
        ["diff", "--check"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="candidate whitespace audit",
    )
    return head, len(untracked)


def _fixture_hashes(root: Path) -> dict[str, str]:
    try:
        resolved = root.resolve(strict=True)
        values: dict[str, str] = {}
        for path in sorted(resolved.rglob("*")):
            if path.is_symlink() or path.is_junction():
                raise OSError("fixture contains a link")
            if path.is_file():
                values[path.relative_to(resolved).as_posix()] = _digest(path.read_bytes())
        return values
    except OSError as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_FIXTURE_FAILED",
            "The candidate sample fixture is unsafe or unavailable.",
            "Restore the committed fixture and retry.",
        ) from error


def _json_object(value: str, *, label: str) -> object:
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            f"The {label} step did not produce valid JSON.",
            "Inspect the candidate command and retry.",
        ) from error


def _run_candidate_sequence(
    runner: CommandRunner,
    uv: Path,
    *,
    clone_root: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> tuple[int, int, int]:
    fixture = clone_root / "tests" / "fixtures" / "sample_python"
    before = _fixture_hashes(fixture)
    setup_started = time.perf_counter_ns()
    synchronized = _run(
        runner,
        [str(uv), "sync", "--locked"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="locked dependency synchronization",
    )
    dependency_sync_ns = synchronized.duration_ns
    version = _run(
        runner,
        [str(uv), "run", "codescope", "version"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="CLI version",
    )
    if version.stdout.strip() != "CodeScope 0.1.0":
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The installed CodeScope version is unexpected.",
            "Restore the Phase 10 version contract and retry.",
        )
    help_result = _run(
        runner,
        [str(uv), "run", "codescope", "--help"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="CLI help",
    )
    if not all(command in help_result.stdout for command in ("index", "status", "search", "serve")):
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The installed CLI help is incomplete.",
            "Verify the candidate CLI and retry.",
        )
    _run(
        runner,
        [
            str(uv),
            "run",
            "codescope",
            "index",
            "tests/fixtures/sample_python",
        ],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="fixture indexing",
    )
    status_result = _run(
        runner,
        [str(uv), "run", "codescope", "status"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="authoritative status",
    )
    if "Ready" not in status_result.stdout or "validate_email" in status_result.stdout:
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The candidate status output is invalid.",
            "Verify the isolated index and retry.",
        )
    search_result = _run(
        runner,
        [str(uv), "run", "codescope", "search", "email validation", "--json"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="semantic search",
    )
    search_payload = _json_object(search_result.stdout, label="semantic search")
    if not isinstance(search_payload, list) or not any(
        isinstance(item, dict)
        and item.get("file") == "validators.py"
        and item.get("symbol") == "validate_email"
        and item.get("start_line") == 6
        and item.get("end_line") == 9
        for item in search_payload
    ):
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The candidate search did not return the expected fixture evidence.",
            "Verify the prepared model and isolated index, then retry.",
        )
    mcp_result = _run(
        runner,
        [str(uv), "run", "python", "-c", _MCP_PROBE_SOURCE],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="MCP initialization",
    )
    mcp_payload = _json_object(mcp_result.stdout, label="MCP initialization")
    if mcp_payload != list(_EXPECTED_TOOLS):
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The candidate MCP tool surface is unexpected.",
            "Verify the read-only server contract and retry.",
        )
    demo_result = _run(
        runner,
        [str(uv), "run", "python", "scripts/demo.py", "--json"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="fixed duplication-prevention demo",
    )
    demo_payload = _json_object(demo_result.stdout, label="fixed demo")
    if (
        not isinstance(demo_payload, dict)
        or demo_payload.get("recommendation") != "REUSE"
        or demo_payload.get("source_unchanged") is not True
        or demo_payload.get("duplicate_avoided") is not True
    ):
        raise SetupVerificationError(
            "CLEAN_SETUP_OUTPUT_FAILED",
            "The fixed demo did not produce the required safe result.",
            "Inspect the candidate Phase 9 workflow and retry.",
        )
    setup_to_demo_ns = time.perf_counter_ns() - setup_started
    if setup_to_demo_ns >= _SETUP_ACCEPTANCE_SECONDS * 1_000_000_000:
        raise SetupVerificationError(
            "CLEAN_SETUP_TOO_SLOW",
            "The measured setup-to-demo path exceeded five minutes.",
            "Inspect dependency synchronization and local cache readiness before retrying.",
        )
    _run(
        runner,
        [str(uv), "run", "codescope", "reset", "--yes"],
        cwd=clone_root,
        environment=environment,
        timeout_seconds=timeout_seconds,
        label="validated runtime cleanup",
    )
    if (clone_root / ".codescope").exists() or _fixture_hashes(fixture) != before:
        raise SetupVerificationError(
            "CLEAN_SETUP_CLEANUP_FAILED",
            "The candidate verification left runtime state or changed the fixture.",
            "Inspect the reset and read-only workflow before retrying.",
        )
    return dependency_sync_ns, setup_to_demo_ns, len(before)


def verify_clean_setup(
    *,
    timeout_seconds: int,
    runner: CommandRunner | None = None,
    source_root: Path = REPOSITORY_ROOT,
) -> CleanSetupReport:
    """Verify the candidate diff from a temporary no-local clone."""
    if os.environ.get(REAL_VERIFICATION_VARIABLE) != "1":
        raise SetupVerificationError(
            "CLEAN_SETUP_OPT_IN_REQUIRED",
            "The real clean-candidate verification is not enabled.",
            f"Set {REAL_VERIFICATION_VARIABLE}=1 after preparing the external model cache.",
        )
    if not _MIN_TIMEOUT_SECONDS <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
        raise SetupVerificationError(
            "CLEAN_SETUP_INVALID_ARGUMENT",
            "The command timeout is outside the supported range.",
            f"Use a timeout from {_MIN_TIMEOUT_SECONDS} through {_MAX_TIMEOUT_SECONDS} seconds.",
        )
    process_runner = runner or SubprocessRunner()
    source = source_root.resolve(strict=True)
    git = _safe_executable("git")
    uv = _safe_executable("uv")
    model_cache = _validated_model_cache(source)
    total_started = time.perf_counter_ns()
    clone_removed = False
    runtime_removed = False
    source_unchanged = False
    head = ""
    untracked_count = 0
    dependency_sync_ns = 0
    setup_to_demo_ns = 0
    fixture_count = 0
    clone_ns = 0
    with tempfile.TemporaryDirectory(prefix="codescope-clean-setup-") as temporary:
        workspace = Path(temporary)
        for directory in (workspace / "home", workspace / "tmp"):
            directory.mkdir()
        uv_cache = _validated_uv_cache(uv, source_root=source, workspace=workspace)
        environment = _sanitized_environment(
            os.environ,
            workspace=workspace,
            model_cache=model_cache,
            uv_cache=uv_cache,
            executables=(git, uv),
        )
        before = _capture_source_snapshot(
            process_runner,
            git,
            source_root=source,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        clone = workspace / "candidate"
        clone_started = time.perf_counter_ns()
        head, untracked_count = _materialize_candidate(
            process_runner,
            git,
            source_root=source,
            clone_root=clone,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        clone_ns = time.perf_counter_ns() - clone_started
        dependency_sync_ns, setup_to_demo_ns, fixture_count = _run_candidate_sequence(
            process_runner,
            uv,
            clone_root=clone,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        runtime_removed = not (clone / ".codescope").exists()
        after = _capture_source_snapshot(
            process_runner,
            git,
            source_root=source,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        source_unchanged = before == after
        if not source_unchanged:
            raise SetupVerificationError(
                "CLEAN_SETUP_SOURCE_CHANGED",
                "The source working tree changed during clean verification.",
                "Inspect concurrent repository processes before retrying.",
            )
    clone_removed = not Path(temporary).exists()
    total_ns = time.perf_counter_ns() - total_started
    return CleanSetupReport(
        schema_version=1,
        candidate={
            "base_revision": head,
            "tracked_patch_applied": True,
            "authorized_untracked_files": untracked_count,
        },
        commands=(
            "uv sync --locked",
            "codescope version",
            "codescope --help",
            "codescope index tests/fixtures/sample_python",
            "codescope status",
            'codescope search "email validation" --json',
            "MCP initialize and list four tools",
            "python scripts/demo.py --json",
            "codescope reset --yes",
        ),
        checks={
            "python_fixture_files": fixture_count,
            "expected_email_validator_found": True,
            "mcp_tools": list(_EXPECTED_TOOLS),
            "demo_recommendation": "REUSE",
            "source_repository_unchanged": source_unchanged,
            "model_download_included": False,
        },
        timing=VerificationTiming(
            clone_ms=round(clone_ns / 1_000_000, 3),
            dependency_sync_ms=round(dependency_sync_ns / 1_000_000, 3),
            setup_to_demo_ms=round(setup_to_demo_ns / 1_000_000, 3),
            total_ms=round(total_ns / 1_000_000, 3),
        ),
        cleanup={
            "clone_removed": clone_removed,
            "runtime_removed": runtime_removed,
            "source_repository_unchanged": source_unchanged,
        },
    )


def _bounded_timeout(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be an integer") from error
    if not _MIN_TIMEOUT_SECONDS <= parsed <= _MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError(
            f"timeout must be between {_MIN_TIMEOUT_SECONDS} and {_MAX_TIMEOUT_SECONDS}"
        )
    return parsed


def _terminal_safe(value: str) -> str:
    return "".join(
        "�"
        if unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        else character
        for character in value
    )


def render_json(report: CleanSetupReport) -> str:
    """Render one sanitized deterministic JSON object."""
    return (
        json.dumps(
            report.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def render_human(report: CleanSetupReport) -> str:
    """Render a concise path-free clean-candidate summary."""
    lines = [
        "CodeScope clean-candidate verification",
        f"Revision: {report.candidate['base_revision']}",
        f"Clone: {report.timing.clone_ms} ms",
        f"Dependency sync: {report.timing.dependency_sync_ms} ms",
        f"Setup to demo: {report.timing.setup_to_demo_ms} ms",
        f"Total: {report.timing.total_ms} ms",
        "MCP tools: 4 read-only tools verified",
        "Demo: REUSE; source unchanged; duplicate avoided",
        "Cleanup: temporary clone and runtime removed",
    ]
    return "\n".join(_terminal_safe(line) for line in lines) + "\n"


def _error_json(error: SetupVerificationError) -> str:
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
        description="Verify the current candidate from an isolated real Git clone."
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_bounded_timeout,
        default=300,
        help="per-command timeout in seconds (30-900; default: 300)",
    )
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run candidate verification with safe deterministic output."""
    arguments = _parser().parse_args(argv)
    try:
        report = verify_clean_setup(timeout_seconds=arguments.timeout_seconds)
    except SetupVerificationError as error:
        if arguments.json:
            sys.stdout.write(_error_json(error))
        else:
            sys.stderr.write(
                f"Error [{_terminal_safe(error.code)}]: {_terminal_safe(error.message)}\n"
                f"Suggestion: {_terminal_safe(error.suggestion)}\n"
            )
        return 1
    except Exception as error:
        unexpected = SetupVerificationError(
            "CLEAN_SETUP_FAILED",
            "The clean-candidate verification could not complete safely.",
            "Verify Git, uv, the model prerequisite, and the candidate state, then retry.",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
