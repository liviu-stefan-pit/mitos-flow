"""Phase 24.5 — Cursor model listing + per-Skill --model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.cursor import CursorFeatureFlags, CursorModelsStatus
from mitos_api.domain.workflow import DEFAULT_CURSOR_SKILL_MODEL, Workflow
from mitos_api.main import app
from mitos_api.services.cursor.command_builder import BuiltCursorCommand, build_cursor_command
from mitos_api.services.cursor.executor import spawn_cursor_command
from mitos_api.services.cursor.models import (
    ensure_default_model,
    list_cursor_models,
    parse_list_models_output,
    set_cursor_models_override,
)
from mitos_api.services.cursor.probe import CommandResult
from mitos_api.services.runners.base import SkillExecutionRequest
from mitos_api.services.runners.cursor import CursorRunner
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runs import execute_run

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"
STUBS = FIXTURES / "cursor_stubs"

SAMPLE_LIST_MODELS = """
Available models:

auto - Auto
composer-2.5 - Composer 2.5
gpt-5.2 - GPT-5.2
claude-4.5-sonnet - Claude 4.5 Sonnet
"""


@pytest.fixture(autouse=True)
def clear_models_override():
    set_cursor_models_override(None)
    yield
    set_cursor_models_override(None)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _make_script_spawn(script_name: str, workspace: Path, captured: list):
    script = STUBS / script_name

    def spawn(argv, stdin, timeout_sec, cwd):
        captured.append(list(argv))
        built = BuiltCursorCommand(
            argv=[sys.executable, str(script), *list(argv[1:])],
            stdin=stdin,
            timeout_ms=int(timeout_sec * 1000),
            workspace=str(cwd or workspace),
            executable=sys.executable,
        )
        return spawn_cursor_command(built)

    return spawn


# --- Parse --list-models ----------------------------------------------------


def test_parse_list_models_filters_auto_keeps_composer():
    models = parse_list_models_output(SAMPLE_LIST_MODELS)
    ids = [m.id for m in models]
    assert "auto" not in ids
    assert "composer-2.5" in ids
    assert "gpt-5.2" in ids
    assert models[ids.index("composer-2.5")].label == "Composer 2.5"


def test_ensure_default_model_appends_when_missing():
    models = ensure_default_model([])
    assert any(m.id == DEFAULT_CURSOR_SKILL_MODEL for m in models)
    again = ensure_default_model(models)
    assert sum(1 for m in again if m.id == DEFAULT_CURSOR_SKILL_MODEL) == 1


def test_list_cursor_models_absent_still_has_default():
    report = list_cursor_models(which=lambda _name: None, environ={})
    assert report.status is CursorModelsStatus.ABSENT
    assert report.defaultModel == DEFAULT_CURSOR_SKILL_MODEL
    assert any(m.id == DEFAULT_CURSOR_SKILL_MODEL for m in report.models)


def test_list_cursor_models_available(tmp_path: Path):
    exe = str(tmp_path / "agent")

    def run(argv):
        assert argv[-1] == "--list-models"
        return CommandResult(0, SAMPLE_LIST_MODELS, "")

    report = list_cursor_models(
        environ={"MITOS_CURSOR_CLI": exe},
        which=lambda _n: None,
        run_command=run,
    )
    assert report.status is CursorModelsStatus.AVAILABLE
    ids = [m.id for m in report.models]
    assert "auto" not in ids
    assert "composer-2.5" in ids


def test_api_cursor_models_endpoint(monkeypatch: pytest.MonkeyPatch):
    from mitos_api.domain.cursor import CursorModelInfo, CursorModelsReport

    set_cursor_models_override(
        lambda **_kwargs: CursorModelsReport(
            status=CursorModelsStatus.AVAILABLE,
            models=[
                CursorModelInfo(id="composer-2.5", label="Composer 2.5"),
                CursorModelInfo(id="gpt-5.2", label="GPT-5.2"),
            ],
            defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
            message="ok",
        )
    )
    response = client.get("/api/cursor/models")
    assert response.status_code == 200
    body = response.json()
    assert body["defaultModel"] == "composer-2.5"
    assert body["status"] == "available"
    assert all(m["id"] != "auto" for m in body["models"])


# --- Always pass --model ----------------------------------------------------


def test_build_always_includes_model_even_without_feature_flag(tmp_path: Path):
    built = build_cursor_command(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputPayload="hi",
        ),
        executable="agent",
        workspace=tmp_path,
        features=CursorFeatureFlags(),  # model=False
        model=None,  # omitted → dry-run path uses default separately
        allowed_root=tmp_path,
    )
    # No model passed → no --model (caller must supply default).
    assert "--model" not in built.argv

    built_default = build_cursor_command(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputPayload="hi",
        ),
        executable="agent",
        workspace=tmp_path,
        features=CursorFeatureFlags(),
        model=DEFAULT_CURSOR_SKILL_MODEL,
        allowed_root=tmp_path,
    )
    assert built_default.argv[built_default.argv.index("--model") + 1] == (
        DEFAULT_CURSOR_SKILL_MODEL
    )


def test_cursor_skill_without_model_uses_composer_default(tmp_path: Path):
    """Gate: Cursor Skill with no model → argv contains --model composer-2.5."""
    captured: list[list[str]] = []
    workflow = Workflow.model_validate(_load_fixture("cursor_simple_linear.json"))
    # Fixture has no model field → Pydantic defaults to composer-2.5.
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    assert skill.settings.model == DEFAULT_CURSOR_SKILL_MODEL  # type: ignore[union-attr]

    cursor = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        model=None,  # runner-level unset; Skill request must supply default
        spawn=_make_script_spawn("stub_ok.py", tmp_path, captured),
    )
    result = execute_run(workflow, runner=cursor)
    assert result.status == "completed"
    assert len(captured) == 1
    argv = captured[0]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == DEFAULT_CURSOR_SKILL_MODEL
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].model == DEFAULT_CURSOR_SKILL_MODEL
    assert by_id["skill-1"].state.value == "completed"


def test_two_cursor_skills_different_models(tmp_path: Path):
    """Gate: two Cursor Skills with different models → each spawn gets its --model."""
    captured: list[list[str]] = []
    workflow = Workflow.model_validate(
        _load_fixture("cursor_two_skill_models.json")
    )
    cursor = CursorRunner(
        executable=sys.executable,
        features=CursorFeatureFlags(),
        workspace=tmp_path,
        allowed_root=tmp_path,
        timeout_ms=10_000,
        spawn=_make_script_spawn("stub_ok.py", tmp_path, captured),
    )
    result = execute_run(
        workflow,
        runner=FakeRunner(),
        cursor_runner=cursor,
    )
    assert result.status == "completed"
    assert len(captured) == 2
    models = [argv[argv.index("--model") + 1] for argv in captured]
    assert models == ["composer-2.5", "gpt-5.2"]
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].model == "composer-2.5"
    assert by_id["skill-2"].model == "gpt-5.2"
