"""Spawn Cursor CLI from a built command and capture process results (Phase 23)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.services.cursor.command_builder import BuiltCursorCommand

SpawnCommand = Callable[
    [Sequence[str], str, float, str | None],
    "CursorProcessResult",
]


class CursorExecutionError(RuntimeError):
    """Raised when the Cursor process exits non-zero or cannot start."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        elapsed_ms: int = 0,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.elapsed_ms = elapsed_ms


@dataclass(frozen=True)
class CursorProcessResult:
    """Captured stdout/stderr/exit/elapsed from one Cursor spawn."""

    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    usage: RunnerUsage | None = None
    timed_out: bool = False


_TOKEN_KEYS = {
    "inputTokens": ("inputTokens", "input_tokens", "promptTokens", "prompt_tokens"),
    "outputTokens": (
        "outputTokens",
        "output_tokens",
        "completionTokens",
        "completion_tokens",
    ),
    "totalTokens": ("totalTokens", "total_tokens"),
}


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _usage_from_mapping(data: Mapping[str, object], *, source: str) -> RunnerUsage | None:
    usage_obj: object | None = data.get("usage")
    if isinstance(usage_obj, Mapping):
        data = usage_obj  # type: ignore[assignment]

    input_tokens = None
    output_tokens = None
    total_tokens = None
    for field, keys in _TOKEN_KEYS.items():
        for key in keys:
            if key in data:
                parsed = _as_int(data[key])
                if parsed is not None:
                    if field == "inputTokens":
                        input_tokens = parsed
                    elif field == "outputTokens":
                        output_tokens = parsed
                    else:
                        total_tokens = parsed
                    break

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return RunnerUsage(
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        totalTokens=total_tokens,
        source=source,
    )


def _try_parse_json_usage(text: str, *, source: str) -> RunnerUsage | None:
    stripped = text.strip()
    if not stripped:
        return None
    # Whole-document JSON
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            usage = _usage_from_mapping(parsed, source=source)
            if usage is not None:
                return usage
    except json.JSONDecodeError:
        pass
    # Last JSON object line (stream-json / trailing usage)
    for line in reversed(stripped.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            usage = _usage_from_mapping(parsed, source=source)
            if usage is not None:
                return usage
    return None


_USAGE_LINE_RE = re.compile(
    r"(?i)(?:tokens?|usage)[^\d]*"
    r"(?:in(?:put)?[^\d]*(?P<input>\d+))?[^\d]*"
    r"(?:out(?:put)?[^\d]*(?P<output>\d+))?[^\d]*"
    r"(?:total[^\d]*(?P<total>\d+))?"
)


def parse_usage_metadata(stdout: str, stderr: str) -> RunnerUsage | None:
    """
    Best-effort usage extraction. Returns None when unavailable.

    Recognizes JSON objects with common token field names and a simple
    text ``tokens: in=N out=M`` style line. Never invents numbers.
    """
    for text, source in ((stdout, "stdout"), (stderr, "stderr")):
        usage = _try_parse_json_usage(text, source=source)
        if usage is not None:
            return usage

    for text, source in ((stdout, "stdout"), (stderr, "stderr")):
        for line in text.splitlines():
            match = _USAGE_LINE_RE.search(line)
            if not match:
                continue
            input_tokens = _as_int(match.group("input")) if match.group("input") else None
            output_tokens = (
                _as_int(match.group("output")) if match.group("output") else None
            )
            total_tokens = _as_int(match.group("total")) if match.group("total") else None
            if input_tokens is None and output_tokens is None and total_tokens is None:
                continue
            if (
                total_tokens is None
                and input_tokens is not None
                and output_tokens is not None
            ):
                total_tokens = input_tokens + output_tokens
            return RunnerUsage(
                inputTokens=input_tokens,
                outputTokens=output_tokens,
                totalTokens=total_tokens,
                source=source,
            )
    return None


def _decode_captured(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
    """Best-effort kill of proc and children (needed for Windows .cmd wrappers)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _default_spawn(
    argv: Sequence[str],
    stdin: str,
    timeout_sec: float,
    cwd: str | None,
) -> CursorProcessResult:
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
    except OSError as exc:
        elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
        raise CursorExecutionError(
            f"Failed to spawn Cursor CLI: {exc}",
            exit_code=None,
            elapsed_ms=elapsed_ms,
        ) from exc

    try:
        stdout, stderr = proc.communicate(input=stdin, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            stdout, stderr = "", ""
        elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
        stdout_s = _decode_captured(stdout)
        stderr_s = _decode_captured(stderr)
        return CursorProcessResult(
            stdout=stdout_s,
            stderr=stderr_s,
            exit_code=-1,
            elapsed_ms=elapsed_ms,
            usage=parse_usage_metadata(stdout_s, stderr_s),
            timed_out=True,
        )

    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    stdout_s = stdout or ""
    stderr_s = stderr or ""
    return CursorProcessResult(
        stdout=stdout_s,
        stderr=stderr_s,
        exit_code=int(proc.returncode if proc.returncode is not None else -1),
        elapsed_ms=elapsed_ms,
        usage=parse_usage_metadata(stdout_s, stderr_s),
        timed_out=False,
    )


def spawn_cursor_command(
    built: BuiltCursorCommand,
    *,
    spawn: SpawnCommand | None = None,
) -> CursorProcessResult:
    """
    Spawn the unredacted built command, capturing stdout/stderr/exit/elapsed.

    Raises ``TimeoutError`` when the process exceeds ``built.timeout_ms``.
    Does not raise on non-zero exit — callers inspect ``exit_code``.
    """
    timeout_sec = built.timeout_ms / 1000.0
    runner = spawn or _default_spawn
    result = runner(built.argv, built.stdin, timeout_sec, built.workspace)
    if result.timed_out:
        raise TimeoutError(
            f"Cursor CLI exceeded timeout of {built.timeout_ms}ms "
            f"(skill process timed out after {result.elapsed_ms}ms)"
        )
    return result
