"""Phase 28.5 — Skill library apply fields + dual resource-in + prompt body."""

from __future__ import annotations

from mitos_api.domain.workflow import NodeKind, SkillNodeSettings, WorkflowNode, default_ports_for_kind
from mitos_api.services.cursor.command_builder import assemble_prompt
from mitos_api.services.runners.base import SkillExecutionRequest


def test_skill_settings_accept_content_and_library_asset_id():
    settings = SkillNodeSettings(
        description="short",
        content="# Body\n\nDo the thing.",
        libraryAssetId="skill-asset-1",
    )
    assert settings.content.startswith("# Body")
    assert settings.libraryAssetId == "skill-asset-1"


def test_skill_default_ports_include_resource_in_top():
    ports = default_ports_for_kind(NodeKind.SKILL)
    ids = {p.id for p in ports}
    assert "resource-in" in ids
    assert "resource-in-top" in ids


def test_skill_node_with_top_resource_port_validates():
    node = WorkflowNode(
        id="skill-1",
        kind=NodeKind.SKILL,
        label="Draft",
        position={"x": 0, "y": 0},
        settings=SkillNodeSettings(content="Body text"),
    )
    assert any(p.id == "resource-in-top" for p in node.ports)


def test_assemble_prompt_includes_skill_content_under_instructions():
    prompt = assemble_prompt(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="extract-structured",
            description="Turn notes into JSON",
            content="# Extract structured\n\nEmit JSON only.",
            inputPayload="hello notes",
        )
    )
    assert "## Description" in prompt
    assert "Turn notes into JSON" in prompt
    assert "## Instructions" in prompt
    assert "Emit JSON only." in prompt
    assert "## Task" in prompt
    assert "hello notes" in prompt
