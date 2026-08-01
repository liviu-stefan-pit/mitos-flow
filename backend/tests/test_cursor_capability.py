"""Phase 21 — Cursor CLI capability probe (absent / available / unsupported)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.cursor import CursorCapabilityStatus
from mitos_api.main import app
from mitos_api.services.cursor.probe import (
    CommandResult,
    discover_features,
    is_version_supported,
    parse_version_string,
    probe_cursor_capability,
    set_cursor_probe_override,
)

client = TestClient(app)

SAMPLE_HELP = """
Usage: agent [options] [command]

Options:
  -v, --version              Output the version number
  -p, --print                Print responses to console
  --output-format <format>   Output format (text, json, stream-json)
  --stream-partial-output    Stream partial output as text deltas
  --model <model>            Model to use
  --list-models              List all available models
  -f, --force                Force allow commands
  --trust                    Trust the workspace without prompting
  --workspace <path>         Workspace directory to use
  --api-key <key>            API key for authentication
  -h, --help                 Display help for command
"""


@pytest.fixture(autouse=True)
def clear_probe_override():
    set_cursor_probe_override(None)
    yield
    set_cursor_probe_override(None)


def _fake_runner(
    *,
    version_out: str = "1.2.3\n",
    help_out: str = SAMPLE_HELP,
    version_code: int = 0,
    help_code: int = 0,
):
    def run(argv: Sequence[str]) -> CommandResult:
        assert len(argv) >= 2
        flag = argv[-1]
        if flag == "--version":
            return CommandResult(version_code, version_out, "")
        if flag == "--help":
            return CommandResult(help_code, help_out, "")
        raise AssertionError(f"unexpected argv: {argv}")

    return run


def test_parse_version_string_extracts_dotted_version():
    assert parse_version_string("1.2.3") == "1.2.3"
    assert parse_version_string("agent 2026.7.20-abc") == "2026.7.20-abc"
    assert parse_version_string("no version here") is None


def test_is_version_supported_compares_numeric_tuples():
    assert is_version_supported("0.1.0", "0.1.0")
    assert is_version_supported("1.0.0", "0.1.0")
    assert not is_version_supported("0.0.9", "0.1.0")


def test_discover_features_from_help_only():
    features = discover_features(SAMPLE_HELP)
    assert features.printMode is True
    assert features.outputFormat is True
    assert features.workspace is True
    assert features.force is True
    assert features.model is True
    assert features.listModels is True
    assert features.trust is True
    assert features.apiKey is True
    assert features.streamPartialOutput is True

    empty = discover_features("Usage: mystery-cli\n  -h, --help")
    assert empty.printMode is False
    assert empty.workspace is False


def test_probe_absent_when_not_on_path():
    report = probe_cursor_capability(
        environ={},
        which=lambda _name: None,
        run_command=_fake_runner(),
    )
    assert report.status == CursorCapabilityStatus.ABSENT
    assert report.executable is None
    assert "not found" in report.message.lower()


def test_probe_available_with_help_features():
    report = probe_cursor_capability(
        environ={"MITOS_CURSOR_CLI": "C:\\tools\\agent.exe"},
        which=lambda _name: None,
        run_command=_fake_runner(version_out="1.2.3\n"),
        minimum_version="0.1.0",
    )
    assert report.status == CursorCapabilityStatus.AVAILABLE
    assert report.executable == "C:\\tools\\agent.exe"
    assert report.version == "1.2.3"
    assert report.features.printMode is True
    assert report.features.workspace is True
    assert report.helpExcerpt is not None
    assert "--print" in (report.helpExcerpt or "")


def test_probe_unsupported_version():
    report = probe_cursor_capability(
        environ={"MITOS_CURSOR_CLI": "/usr/bin/agent"},
        which=lambda _name: None,
        run_command=_fake_runner(version_out="0.0.1\n"),
        minimum_version="0.1.0",
    )
    assert report.status == CursorCapabilityStatus.UNSUPPORTED_VERSION
    assert report.version == "0.0.1"
    assert report.minimumVersion == "0.1.0"
    assert "below the minimum" in report.message.lower()


def test_probe_prefers_env_override_over_which():
    seen: list[str] = []

    def which(name: str) -> str | None:
        seen.append(name)
        return f"/path/{name}"

    report = probe_cursor_capability(
        environ={"MITOS_CURSOR_CLI": "/custom/agent"},
        which=which,
        run_command=_fake_runner(),
    )
    assert report.executable == "/custom/agent"
    assert seen == []  # override short-circuits PATH lookup


def test_probe_falls_back_to_cursor_agent_name():
    def which(name: str) -> str | None:
        if name == "cursor-agent":
            return "/bin/cursor-agent"
        return None

    report = probe_cursor_capability(
        environ={},
        which=which,
        run_command=_fake_runner(version_out="2.0.0\n"),
    )
    assert report.status == CursorCapabilityStatus.AVAILABLE
    assert report.executable == "/bin/cursor-agent"


def test_probe_falls_back_to_known_windows_install_path(tmp_path):
    agent = tmp_path / "cursor-agent" / "agent.cmd"
    agent.parent.mkdir(parents=True)
    agent.write_text("@echo off\n", encoding="utf-8")

    report = probe_cursor_capability(
        environ={"LOCALAPPDATA": str(tmp_path)},
        which=lambda _name: None,
        run_command=_fake_runner(version_out="2026.07.23-e383d2b\n"),
    )
    assert report.status == CursorCapabilityStatus.AVAILABLE
    assert report.executable == str(agent)
    assert report.version == "2026.07.23-e383d2b"


def test_api_absent_case():
    set_cursor_probe_override(
        lambda **_kwargs: probe_cursor_capability(
            environ={},
            which=lambda _n: None,
            run_command=_fake_runner(),
        )
    )
    response = client.get("/api/cursor/capability")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "absent"
    assert body["executable"] is None
    assert body["minimumVersion"]


def test_api_available_case():
    set_cursor_probe_override(
        lambda **_kwargs: probe_cursor_capability(
            environ={"MITOS_CURSOR_CLI": "agent"},
            which=lambda _n: None,
            run_command=_fake_runner(version_out="3.1.0\n"),
            minimum_version="0.1.0",
        )
    )
    response = client.get("/api/cursor/capability")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["version"] == "3.1.0"
    assert body["features"]["printMode"] is True


def test_api_unsupported_version_case():
    set_cursor_probe_override(
        lambda **_kwargs: probe_cursor_capability(
            environ={"MITOS_CURSOR_CLI": "agent"},
            which=lambda _n: None,
            run_command=_fake_runner(version_out="0.0.2\n"),
            minimum_version="1.0.0",
        )
    )
    response = client.get("/api/cursor/capability")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unsupported_version"
    assert body["version"] == "0.0.2"
    assert body["minimumVersion"] == "1.0.0"
