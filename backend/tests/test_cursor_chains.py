"""Phase 24 — Cursor execution for chains and joins (per-node Fake/Cursor)."""

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
from mitos_api.services.cursor.executor import spawn_cursor_command
from mitos_api.services.runners.cursor import CursorRunner
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runs import execute_run

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"
STUBS = FIXTURES / "cursor_stubs"

TERMINAL = {"completed", "failed", "cancelled", "rejected"}


def _wait_run(run_id: str, *, timeout: float = 10.0) -> dict:
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


def _make_script_spawn(script_name: str, workspace: Path):
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
    if sys.platform == "win32":
        wrapper = tmp_path / f"{wrapper_stem}.cmd"
        if script_name == "stub_ok.py":
            body = "@echo off\r\necho STUB_OK:Hello from input\r\nexit /b 0\r\n"
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


def _cursor_opts(executable: str, workspace: Path) -> dict:
    return {
        "executable": executable,
        "workspace": str(workspace),
        "features": {"printMode": False},
        "timeoutMs": 10_000,
        "confirmed": True,
    }


# --- Gate: two-Skill chain (Cursor then Fake) ---------------------------------


def test_cursor_two_skill_chain_mixed_runners(tmp_path: Path):
    """Gate: two-Skill chain completes; only skill-1 uses Cursor (stub)."""
    workflow = Workflow.model_validate(_load_fixture("cursor_two_skill_chain.json"))
    cursor = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_ok.py", tmp_path),
    )
    result = execute_run(
        workflow,
        runner=FakeRunner(),
        cursor_runner=cursor,
    )
    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].exitCode == 0
    assert by_id["skill-1"].stdout is not None
    assert "STUB_OK" in (by_id["skill-1"].stdout or "")
    assert by_id["skill-1"].output == "STUB_OK:Hello from input"
    # Fake runner for skill-2 — no Cursor capture fields.
    assert by_id["skill-2"].state.value == "completed"
    assert by_id["skill-2"].exitCode is None
    assert by_id["skill-2"].output == "fake::Polish::STUB_OK:Hello from input"
    assert result.output == "fake::Polish::STUB_OK:Hello from input"


def test_api_cursor_two_skill_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_ok.py", "stub_chain")
    workflow = _load_fixture("cursor_two_skill_chain.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "fake",
                "delayMs": 0,
                "cursor": _cursor_opts(executable, tmp_path),
            },
        },
    )
    assert response.status_code == 200
    finished = _wait_run(response.json()["id"])
    assert finished["status"] == "completed", finished
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["exitCode"] == 0
    assert "STUB_OK" in (by_id["skill-1"]["stdout"] or "")
    assert by_id["skill-2"]["exitCode"] is None
    assert finished["output"] == "fake::Polish::STUB_OK:Hello from input"


# --- Gate: two-input wait_for_all join with Cursor Skill ---------------------


def test_cursor_two_input_join_completes(tmp_path: Path):
    """Gate: two-input join completes with Cursor on the Skill (stub)."""
    workflow = Workflow.model_validate(_load_fixture("cursor_two_input_join.json"))
    cursor = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_ok.py", tmp_path),
    )
    result = execute_run(
        workflow,
        runner=FakeRunner(),
        cursor_runner=cursor,
    )
    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].exitCode == 0
    assert "STUB_OK" in (by_id["skill-1"].stdout or "")
    assert by_id["output-1"].state.value == "completed"
    assert result.output is not None
    assert result.output.startswith("STUB_OK:")


def test_api_cursor_two_input_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_ok.py", "stub_join")
    workflow = _load_fixture("cursor_two_input_join.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "fake",
                "delayMs": 0,
                "cursor": _cursor_opts(executable, tmp_path),
            },
        },
    )
    assert response.status_code == 200
    finished = _wait_run(response.json()["id"])
    assert finished["status"] == "completed", finished
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["state"] == "completed"
    assert by_id["skill-1"]["exitCode"] == 0
    assert by_id["output-1"]["state"] == "completed"


def test_api_per_node_cursor_requires_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Per-node Cursor Skill still requires options.cursor.confirmed."""
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    workflow = _load_fixture("cursor_two_skill_chain.json")
    response = client.post(
        "/api/runs",
        json={
            "workflow": workflow,
            "options": {
                "runner": "fake",
                "delayMs": 0,
                "cursor": {
                    "executable": str(tmp_path / "agent.exe"),
                    "workspace": str(tmp_path),
                    "features": {},
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
