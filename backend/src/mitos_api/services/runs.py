"""Synchronous run orchestration for Input → Skill → Output (Phase 11)."""

from __future__ import annotations

import uuid

from mitos_api.domain.run import (
    NodeRunResult,
    NodeRunState,
    RunResponse,
)
from mitos_api.domain.validation import validate_workflow
from mitos_api.domain.workflow import (
    ArtifactOutputMode,
    ArtifactOutputNodeSettings,
    EdgeKind,
    InputNodeSettings,
    NodeKind,
    ValidationIssue,
    Workflow,
    WorkflowNode,
)
from mitos_api.services.runners.base import Runner, SkillExecutionRequest
from mitos_api.services.runners.fake import FakeRunner


def execute_run(
    workflow: Workflow,
    *,
    runner: Runner | None = None,
) -> RunResponse:
    """
    Execute a Phase-11-supported graph synchronously.

    Supported shape: exactly one Input → one Skill → one Artifact Output
    (pass-through). Optional Knowledge Base / Rules nodes are skipped.
    """
    run_id = str(uuid.uuid4())
    active_runner: Runner = runner if runner is not None else FakeRunner()

    validation = validate_workflow(workflow)
    if not validation.valid:
        return RunResponse(
            id=run_id,
            status="rejected",
            errors=list(validation.errors),
        )

    shape_errors = _check_phase11_shape(workflow)
    if shape_errors:
        return RunResponse(
            id=run_id,
            status="rejected",
            errors=shape_errors,
        )

    input_node = _exactly_one(workflow, NodeKind.INPUT)
    skill_node = _exactly_one(workflow, NodeKind.SKILL)
    output_node = _exactly_one(workflow, NodeKind.ARTIFACT_OUTPUT)
    assert input_node is not None and skill_node is not None and output_node is not None

    assert isinstance(input_node.settings, InputNodeSettings)
    input_payload = input_node.settings.content
    input_media_type = input_node.settings.mediaType

    node_results: list[NodeRunResult] = []

    # Optional resource nodes are present but not executed in Phase 11.
    for node in workflow.nodes:
        if node.kind in (NodeKind.KNOWLEDGE_BASE, NodeKind.RULES):
            node_results.append(
                NodeRunResult(
                    nodeId=node.id,
                    state=NodeRunState.SKIPPED,
                )
            )

    node_results.append(
        NodeRunResult(
            nodeId=input_node.id,
            state=NodeRunState.COMPLETED,
            output=input_payload,
            mediaType=input_media_type,
        )
    )

    try:
        skill_result = active_runner.execute(
            SkillExecutionRequest(
                skillNodeId=skill_node.id,
                skillLabel=skill_node.label,
                description=getattr(skill_node.settings, "description", "") or "",
                inputPayload=input_payload,
                inputMediaType=input_media_type,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive; FakeRunner does not raise
        node_results.append(
            NodeRunResult(
                nodeId=skill_node.id,
                state=NodeRunState.FAILED,
                error=str(exc),
            )
        )
        node_results.append(
            NodeRunResult(
                nodeId=output_node.id,
                state=NodeRunState.SKIPPED,
            )
        )
        return RunResponse(
            id=run_id,
            status="failed",
            nodeResults=node_results,
            errors=[
                ValidationIssue(
                    code="runner_failed",
                    message=str(exc),
                    nodeId=skill_node.id,
                )
            ],
        )

    node_results.append(
        NodeRunResult(
            nodeId=skill_node.id,
            state=NodeRunState.COMPLETED,
            output=skill_result.outputPayload,
            mediaType=skill_result.mediaType,
        )
    )

    # Phase 11: Artifact Output is passive pass-through only.
    node_results.append(
        NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.COMPLETED,
            output=skill_result.outputPayload,
            mediaType=skill_result.mediaType,
        )
    )

    return RunResponse(
        id=run_id,
        status="completed",
        nodeResults=node_results,
        output=skill_result.outputPayload,
        mediaType=skill_result.mediaType,
    )


def _exactly_one(workflow: Workflow, kind: NodeKind) -> WorkflowNode | None:
    matches = [n for n in workflow.nodes if n.kind is kind]
    return matches[0] if len(matches) == 1 else None


def _check_phase11_shape(workflow: Workflow) -> list[ValidationIssue]:
    """Reject graphs that Phase 11 cannot execute."""
    errors: list[ValidationIssue] = []

    by_kind: dict[NodeKind, list[WorkflowNode]] = {
        NodeKind.INPUT: [],
        NodeKind.SKILL: [],
        NodeKind.ARTIFACT_OUTPUT: [],
        NodeKind.KNOWLEDGE_BASE: [],
        NodeKind.RULES: [],
    }
    for node in workflow.nodes:
        by_kind[node.kind].append(node)

    if len(by_kind[NodeKind.INPUT]) != 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 11 requires exactly one Input node "
                    f"(found {len(by_kind[NodeKind.INPUT])})."
                ),
            )
        )
    if len(by_kind[NodeKind.SKILL]) != 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 11 requires exactly one Skill node "
                    f"(found {len(by_kind[NodeKind.SKILL])})."
                ),
            )
        )
    if len(by_kind[NodeKind.ARTIFACT_OUTPUT]) != 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 11 requires exactly one Artifact Output node "
                    f"(found {len(by_kind[NodeKind.ARTIFACT_OUTPUT])})."
                ),
            )
        )

    if errors:
        return errors

    input_node = by_kind[NodeKind.INPUT][0]
    skill_node = by_kind[NodeKind.SKILL][0]
    output_node = by_kind[NodeKind.ARTIFACT_OUTPUT][0]

    if not isinstance(output_node.settings, ArtifactOutputNodeSettings):
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message="Artifact Output settings are invalid.",
                nodeId=output_node.id,
            )
        )
        return errors

    if output_node.settings.mode is not ArtifactOutputMode.PASS_THROUGH:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 11 only supports pass-through Artifact Output "
                    f"(got '{output_node.settings.mode.value}')."
                ),
                nodeId=output_node.id,
            )
        )

    data_edges = [e for e in workflow.edges if e.kind is EdgeKind.DATA_FLOW]
    if len(data_edges) != 2:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 11 requires exactly two data-flow edges "
                    f"(Input→Skill, Skill→Output); found {len(data_edges)}."
                ),
            )
        )
        return errors

    has_input_to_skill = any(
        e.sourceNodeId == input_node.id and e.targetNodeId == skill_node.id
        for e in data_edges
    )
    has_skill_to_output = any(
        e.sourceNodeId == skill_node.id and e.targetNodeId == output_node.id
        for e in data_edges
    )

    if not has_input_to_skill:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message="Missing data-flow edge from Input to Skill.",
            )
        )
    if not has_skill_to_output:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message="Missing data-flow edge from Skill to Artifact Output.",
            )
        )

    return errors
