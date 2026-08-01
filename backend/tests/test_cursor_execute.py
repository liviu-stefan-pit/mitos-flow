"""Phase 23 — Execute one Cursor Skill (stub executable for failure/timeout)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.cursor import CursorFeatureFlags
from mitos_api.domain import Workflow
from mitos_api.main import app
from mitos_api.services.cursor.command_builder import BuiltCursorCommand
from mitos_api.services.cursor.executor import parse_usage_metadata, spawn_cursor_command
from mitos_api.services.runners.base import SkillExecutionRequest
from mitos_api.services.runners.cursor import CursorRunner
from mitos_api.services.runs import execute_run

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"
STUBS = FIXTURES / "cursor_stubs"

FULL_FEATURES = CursorFeatureFlags(
    printMode=True,
    outputFormat=True,
    workspace=True,
    force=False,
    model=False,
    listModels=False,
    trust=True,
    apiKey=False,
    streamPartialOutput=False,
)

TERMINAL = {"completed", "failed", "cancelled", "rejected"}


def _wait_run(run_id: str, *, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in TERMINAL:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish; last={last}")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _results_by_id(body: dict) -> dict[str, dict]:
    return {r["nodeId"]: r for r in body["nodeResults"]}


def _sample_request() -> SkillExecutionRequest:
    return SkillExecutionRequest(
        skillNodeId="skill-1",
        skillLabel="Draft",
        description="Draft the reply",
        inputPayload="Hello from input",
        inputMediaType="text/plain",
    )


def _make_script_spawn(script_name: str, workspace: Path):
    """Spawn helper that runs a stub script with python, ignoring built argv[0]."""

    script = STUBS / script_name

    def spawn(argv, stdin, timeout_sec, cwd):
        built = BuiltCursorCommand(
            argv=[sys.executable, str(script), *list(argv[1:])],
            stdin=stdin,
            timeout_ms=int(timeout_sec * 1000),
            workspace=str(cwd or workspace),
            executable=sys.executable,
        )
        return spawn_cursor_command(built)

    return spawn


def _write_stub_wrapper(tmp_path: Path, script_name: str, wrapper_stem: str) -> str:
    """
    Create a spawnable stub executable.

    On Windows, use a pure ``.cmd`` body (no nested python) so ``subprocess``
    timeouts reliably kill the process tree. On POSIX, use a shell wrapper
    around the Python stub scripts.
    """
    if sys.platform == "win32":
        wrapper = tmp_path / f"{wrapper_stem}.cmd"
        if script_name == "stub_ok.py":
            body = "@echo off\r\necho STUB_OK:Hello from input\r\nexit /b 0\r\n"
        elif script_name == "stub_fail.py":
            body = (
                "@echo off\r\n"
                "echo STUB_FAIL: intentional failure 1>&2\r\n"
                "exit /b 2\r\n"
            )
        elif script_name == "stub_hang.py":
            # ping ignores redirected stdin (unlike `timeout /t`).
            body = "@echo off\r\nping -n 3600 127.0.0.1 >nul\r\nexit /b 0\r\n"
        else:
            raise AssertionError(f"unsupported stub for cmd wrapper: {script_name}")
        wrapper.write_text(body, encoding="utf-8")
        return str(wrapper)

    launcher = tmp_path / f"{wrapper_stem}.py"
    launcher.write_text(
        (STUBS / script_name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    wrapper = tmp_path / wrapper_stem
    wrapper.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{launcher}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return str(wrapper)


# --- Usage parsing ----------------------------------------------------------


def test_parse_usage_from_json_stdout():
    usage = parse_usage_metadata(
        '{"result":"ok","usage":{"input_tokens":11,"output_tokens":7}}',
        "",
    )
    assert usage is not None
    assert usage.inputTokens == 11
    assert usage.outputTokens == 7
    assert usage.totalTokens == 18
    assert usage.source == "stdout"


def test_parse_usage_missing_returns_none():
    assert parse_usage_metadata("plain answer only\n", "noise") is None


# --- Stub executable: success / failure / timeout ---------------------------


def test_cursor_runner_success_captures_stdout_exit_elapsed(tmp_path: Path):
    runner = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_ok.py", tmp_path),
    )
    result = runner.execute(_sample_request())
    assert result.outputPayload == "STUB_OK:Hello from input"
    assert result.exitCode == 0
    assert result.elapsedMs is not None and result.elapsedMs >= 1
    assert result.stdout is not None and "STUB_OK" in result.stdout
    assert result.stderr == ""
    runner.cleanup("skill-1")
    assert runner.cleaned_up == ["skill-1"]


def test_cursor_runner_failure_raises_with_stderr(tmp_path: Path):
    runner = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_fail.py", tmp_path),
    )
    with pytest.raises(Exception) as exc:
        runner.execute(_sample_request())
    assert "2" in str(exc.value) or getattr(exc.value, "exit_code", None) == 2


def test_cursor_runner_timeout_raises(tmp_path: Path):
    runner = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=200,
        spawn=_make_script_spawn("stub_hang.py", tmp_path),
    )
    with pytest.raises(TimeoutError):
        runner.execute(_sample_request())


def test_cursor_runner_captures_usage_when_available(tmp_path: Path):
    runner = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_usage.py", tmp_path),
    )
    result = runner.execute(_sample_request())
    assert result.outputPayload.startswith("STUB_USAGE")
    assert result.usage is not None
    assert result.usage.inputTokens == 3
    assert result.usage.outputTokens == 5
    assert result.usage.totalTokens == 8


# --- Input → Skill → Output end-to-end with stub ----------------------------


def test_cursor_simple_linear_fixture_end_to_end(tmp_path: Path):
    """Gate: one fixture end-to-end using a stub executable."""
    workflow = _load_fixture("cursor_simple_linear.json")
    runner = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_ok.py", tmp_path),
    )
    result = execute_run(Workflow.model_validate(workflow), runner=runner)
    assert result.status == "completed"
    assert result.output == "STUB_OK:Hello from input"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].exitCode == 0
    assert by_id["skill-1"].elapsedMs is not None
    assert by_id["skill-1"].stdout is not None
    assert "STUB_OK" in (by_id["skill-1"].stdout or "")
    assert by_id["output-1"].output == "STUB_OK:Hello from input"


def test_api_cursor_run_requires_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    workflow = _load_fixture("cursor_simple_linear.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "cursor",
                "delayMs": 0,
                "cursor": {
                    "executable": str(tmp_path / "agent.exe"),
                    "workspace": str(tmp_path),
                    "features": FULL_FEATURES.model_dump(),
                    "timeoutMs": 5_000,
                    "confirmed": False,
                },
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["errors"][0]["code"] == "cursor_confirmation_required"


def test_api_cursor_run_with_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Gate: POST /api/runs with runner=cursor + stub executable wrapper."""
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_ok.py", "stub_agent")
    workflow = _load_fixture("cursor_simple_linear.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "cursor",
                "delayMs": 0,
                "cursor": {
                    "executable": executable,
                    "workspace": str(tmp_path),
                    "features": {"printMode": False},
                    "timeoutMs": 10_000,
                    "confirmed": True,
                },
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    finished = _wait_run(body["id"], timeout=10.0)
    assert finished["status"] == "completed", finished
    assert finished["output"] == "STUB_OK:Hello from input"
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["exitCode"] == 0
    assert by_id["skill-1"]["elapsedMs"] >= 1
    assert "STUB_OK" in (by_id["skill-1"]["stdout"] or "")


def test_api_cursor_failure_with_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_fail.py", "stub_fail")
    workflow = _load_fixture("cursor_simple_linear.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "cursor",
                "delayMs": 0,
                "cursor": {
                    "executable": executable,
                    "workspace": str(tmp_path),
                    "features": {},
                    "timeoutMs": 10_000,
                    "confirmed": True,
                },
            },
        },
    )
    assert response.status_code == 200
    finished = _wait_run(response.json()["id"], timeout=10.0)
    assert finished["status"] == "failed"
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["state"] == "failed"
    assert by_id["output-1"]["state"] == "skipped"


def test_api_cursor_timeout_with_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_hang.py", "stub_hang")
    workflow = _load_fixture("cursor_simple_linear.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "cursor",
                "delayMs": 0,
                "cursor": {
                    "executable": executable,
                    "workspace": str(tmp_path),
                    "features": {},
                    "timeoutMs": 300,
                    "confirmed": True,
                },
            },
        },
    )
    assert response.status_code == 200
    finished = _wait_run(response.json()["id"], timeout=10.0)
    assert finished["status"] == "failed"
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["state"] == "timeout", by_id["skill-1"]
