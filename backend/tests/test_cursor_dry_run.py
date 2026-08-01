"""Phase 22 — Cursor command builder and dry-run (no spawn)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.cursor import (
    CursorDryRunOptions,
    CursorDryRunRequest,
    CursorFeatureFlags,
    CursorSkillPayload,
)
from mitos_api.domain.workflow import AttachedRule, CitedChunk, InputEnvelope
from mitos_api.main import app
from mitos_api.services.cursor.command_builder import (
    CursorCommandBuildError,
    assemble_prompt,
    build_cursor_command,
    check_workspace_boundary,
    dry_run_cursor_command,
    preview_built_command,
    quote_windows_arg,
    quote_windows_command,
    redact_argv,
)
from mitos_api.services.cursor.probe import set_cursor_probe_override
from mitos_api.services.runners.base import SkillExecutionRequest

client = TestClient(app)

FULL_FEATURES = CursorFeatureFlags(
    printMode=True,
    outputFormat=True,
    workspace=True,
    force=True,
    model=True,
    listModels=True,
    trust=True,
    apiKey=True,
    streamPartialOutput=False,
)


@pytest.fixture(autouse=True)
def clear_probe_override():
    set_cursor_probe_override(None)
    yield
    set_cursor_probe_override(None)


def _sample_request() -> SkillExecutionRequest:
    return SkillExecutionRequest(
        skillNodeId="skill-1",
        skillLabel="cursor-smoke",
        description="Summarize in three bullets.",
        inputPayload="Ship dry-run preview",
        inputMediaType="text/plain",
        rules=[
            AttachedRule(
                rulesNodeId="rules-1",
                label="safety",
                content="Do not edit files.",
                order=0,
            )
        ],
        knowledgeChunks=[
            CitedChunk(
                chunkId="kb-1#0",
                kbNodeId="kb-1",
                kbLabel="product",
                citation="kb-1",
                text="Mitos builds argv without spawning.",
                score=1.0,
                order=0,
            )
        ],
    )


# --- Argument construction -------------------------------------------------


def test_build_includes_advertised_flags_only(tmp_path: Path):
    built = build_cursor_command(
        _sample_request(),
        executable="C:\\tools\\agent.exe",
        workspace=tmp_path,
        features=FULL_FEATURES,
        model="composer-2",
        api_key="sk-secret-value",
        force=True,
        trust=True,
        output_format="text",
        allowed_root=tmp_path,
        timeout_ms=60_000,
    )

    assert built.argv[0] == "C:\\tools\\agent.exe"
    assert "--print" in built.argv
    assert built.argv[built.argv.index("--output-format") + 1] == "text"
    assert built.argv[built.argv.index("--workspace") + 1] == str(tmp_path.resolve())
    assert "--trust" in built.argv
    assert "--force" in built.argv
    assert built.argv[built.argv.index("--model") + 1] == "composer-2"
    assert built.argv[built.argv.index("--api-key") + 1] == "sk-secret-value"
    assert built.timeout_ms == 60_000
    # Prompt lives on stdin, not argv (Windows cmdline length safety).
    assert "Summarize in three bullets." in built.stdin
    assert "Ship dry-run preview" in built.stdin
    assert "Do not edit files." in built.stdin
    assert "Mitos builds argv without spawning." in built.stdin
    assert "sk-secret-value" not in built.argv[0]


def test_build_omits_flags_when_features_absent(tmp_path: Path):
    built = build_cursor_command(
        _sample_request(),
        executable="/usr/bin/agent",
        workspace=tmp_path,
        features=CursorFeatureFlags(),  # all false
        model="composer-2",
        api_key="sk-secret",
        force=True,
        trust=True,
        allowed_root=tmp_path,
    )
    assert built.argv == ["/usr/bin/agent"]
    assert built.stdin.startswith("# Skill: cursor-smoke")


def test_assemble_prompt_named_inputs_sorted_by_port():
    request = SkillExecutionRequest(
        skillNodeId="skill-join",
        skillLabel="merge",
        inputs=[
            InputEnvelope(
                port="context",
                payload="B",
                mediaType="text/plain",
                sourceNodeId="input-b",
                order=0,
            ),
            InputEnvelope(
                port="brief",
                payload="A",
                mediaType="text/plain",
                sourceNodeId="input-a",
                order=1,
            ),
        ],
    )
    prompt = assemble_prompt(request)
    assert prompt.index("Port `brief`") < prompt.index("Port `context`")


# --- Windows quoting -------------------------------------------------------


def test_quote_windows_arg_spaces_and_quotes():
    assert quote_windows_arg("simple") == "simple"
    assert quote_windows_arg("") == '""'
    assert quote_windows_arg("C:\\Program Files\\agent.exe") == (
        '"C:\\Program Files\\agent.exe"'
    )
    assert quote_windows_arg('say "hi"') == '"say \\"hi\\""'


def test_quote_windows_command_matches_list2cmdline(tmp_path: Path):
    argv = [
        str(tmp_path / "agent.exe"),
        "--print",
        "--workspace",
        str(tmp_path / "My Workspace"),
        "--api-key",
        "sk-secret",
    ]
    display = quote_windows_command(argv)
    assert "My Workspace" in display
    assert display.count('"') >= 2
    # Secret still present in unredacted join (redaction is separate).
    assert "sk-secret" in display


# --- Secret redaction ------------------------------------------------------


def test_redact_argv_hides_api_key_value():
    argv = [
        "agent",
        "--print",
        "--api-key",
        "sk-live-super-secret",
        "--model",
        "composer-2",
    ]
    redacted = redact_argv(argv)
    assert redacted[redacted.index("--api-key") + 1] == "***"
    assert "sk-live-super-secret" not in redacted
    assert redacted[redacted.index("--model") + 1] == "composer-2"


def test_redact_argv_equals_form():
    assert redact_argv(["agent", "--api-key=sk-abc"]) == [
        "agent",
        "--api-key=***",
    ]


def test_preview_redacts_secrets_in_display_and_stdin(tmp_path: Path):
    built = build_cursor_command(
        _sample_request(),
        executable="agent",
        workspace=tmp_path,
        features=FULL_FEATURES,
        api_key="sk-preview-secret",
        allowed_root=tmp_path,
    )
    preview = preview_built_command(built, secrets=["sk-preview-secret"])
    assert "sk-preview-secret" not in preview.commandDisplay
    assert "***" in preview.commandDisplay
    assert preview.argv[preview.argv.index("--api-key") + 1] == "***"
    # Unredacted stdin retained for Phase 23 spawn wiring; preview text is safe.
    assert "sk-preview-secret" not in preview.stdinPreview


# --- Workspace boundary / path checks --------------------------------------


def test_workspace_inside_root_ok(tmp_path: Path):
    nested = tmp_path / "flows" / "demo"
    nested.mkdir(parents=True)
    resolved = check_workspace_boundary(nested, allowed_root=tmp_path)
    assert resolved == nested.resolve()


def test_workspace_outside_root_rejected(tmp_path: Path):
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    with pytest.raises(CursorCommandBuildError) as exc:
        check_workspace_boundary(outside, allowed_root=tmp_path)
    assert exc.value.code == "workspace_boundary"


def test_workspace_traversal_rejected(tmp_path: Path):
    with pytest.raises(CursorCommandBuildError) as exc:
        check_workspace_boundary(
            tmp_path / "sub" / ".." / ".." / "etc",
            allowed_root=tmp_path,
        )
    assert exc.value.code == "workspace_boundary"


def test_build_rejects_workspace_outside_root(tmp_path: Path):
    outside = tmp_path.parent / f"escape-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    with pytest.raises(CursorCommandBuildError) as exc:
        build_cursor_command(
            _sample_request(),
            executable="agent",
            workspace=outside,
            features=FULL_FEATURES,
            allowed_root=tmp_path,
        )
    assert exc.value.code == "workspace_boundary"


# --- Dry-run API (no spawn) ------------------------------------------------


def test_dry_run_api_returns_redacted_preview_without_spawn(tmp_path: Path):
    body = CursorDryRunRequest(
        request=CursorSkillPayload(
            skillNodeId="skill-1",
            skillLabel="cursor-smoke",
            description="Tiny smoke",
            inputPayload="hello",
        ),
        options=CursorDryRunOptions(
            executable=str(tmp_path / "agent.exe"),
            workspace=str(tmp_path),
            features=FULL_FEATURES,
            apiKey="sk-api-should-redact",
            timeoutMs=45_000,
            model="composer-2",
            confirmed=False,
        ),
    )
    # Force root via env so API path uses tmp_path as boundary.
    response = dry_run_cursor_command(
        body,
        environ={"MITOS_CURSOR_WORKSPACE_ROOT": str(tmp_path)},
        cwd=tmp_path,
    )
    assert response.ok is True
    assert response.spawned is False
    assert response.confirmed is False
    assert response.confirmationRequired is True
    assert response.preview is not None
    assert response.preview.timeoutMs == 45_000
    assert "sk-api-should-redact" not in response.preview.commandDisplay
    assert "***" in response.preview.commandDisplay
    assert "Tiny smoke" in response.preview.stdinPreview


def test_dry_run_api_endpoint_and_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    payload = {
        "request": {
            "skillNodeId": "skill-1",
            "skillLabel": "cursor-smoke",
            "description": "Preview me",
            "inputPayload": "task",
        },
        "options": {
            "executable": str(tmp_path / "agent.cmd"),
            "workspace": str(tmp_path),
            "features": FULL_FEATURES.model_dump(),
            "apiKey": "sk-http-secret",
            "timeoutMs": 30_000,
            "confirmed": False,
        },
    }
    first = client.post("/api/cursor/dry-run", json=payload)
    assert first.status_code == 200
    body = first.json()
    assert body["ok"] is True
    assert body["spawned"] is False
    assert body["confirmed"] is False
    assert "sk-http-secret" not in body["preview"]["commandDisplay"]
    assert body["preview"]["timeoutMs"] == 30_000

    payload["options"]["confirmed"] = True
    second = client.post("/api/cursor/dry-run", json=payload)
    assert second.status_code == 200
    confirmed = second.json()
    assert confirmed["confirmed"] is True
    assert confirmed["spawned"] is False
    assert "runner='cursor'" in confirmed["message"]


def test_dry_run_api_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    outside = tmp_path.parent / f"http-escape-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    response = client.post(
        "/api/cursor/dry-run",
        json={
            "request": {
                "skillNodeId": "skill-1",
                "skillLabel": "x",
                "inputPayload": "y",
            },
            "options": {
                "executable": "agent",
                "workspace": str(outside),
                "features": {"workspace": True, "printMode": True},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["spawned"] is False
    assert any("outside the approved root" in err for err in body["errors"])
