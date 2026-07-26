"""Synchronous run orchestration with named-input joins (Phase 14)."""

from __future__ import annotations

import uuid

from mitos_api.domain.run import (
    NodeRunResult,
    NodeRunState,
    RunResponse,
)
from mitos_api.domain.validation import validate_workflow
from mitos_api.domain.workflow import (
    InputNodeSettings,
    NodeKind,
    ValidationIssue,
    Workflow,
)
from mitos_api.services.runners.base import Runner, SkillExecutionRequest
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.scheduler import collect_input_envelopes, plan_linear_chain


def execute_run(
    workflow: Workflow,
    *,
    runner: Runner | None = None,
) -> RunResponse:
    """
    Execute a Phase-14-supported graph synchronously.

    Supported shape: one or more Inputs → Skills (linear path and/or
    wait_for_all joins on named ports) → one or more pass-through Artifact
    Outputs. Skills run in topological order; each Skill waits for every
    declared data-in port. Failure or blocked join stops the chain.
    Optional Knowledge Base / Rules nodes are skipped.
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

    plan, shape_errors = plan_linear_chain(workflow)
    if shape_errors or plan is None:
        return RunResponse(
            id=run_id,
            status="rejected",
            errors=shape_errors,
        )

    node_results: list[NodeRunResult] = []
    completed_outputs: dict[str, tuple[str, str]] = {}
    arrival_order: dict[str, int] = {}
    arrival_counter = 0

    # Optional resource nodes are present but not executed in Phase 14.
    for node in workflow.nodes:
        if node.kind in (NodeKind.KNOWLEDGE_BASE, NodeKind.RULES):
            node_results.append(
                NodeRunResult(
                    nodeId=node.id,
                    state=NodeRunState.SKIPPED,
                )
            )

    # Complete Inputs first (deterministic id order from the plan).
    for input_node in plan.input_nodes:
        assert isinstance(input_node.settings, InputNodeSettings)
        payload = input_node.settings.content
        media_type = input_node.settings.mediaType
        node_results.append(
            NodeRunResult(
                nodeId=input_node.id,
                state=NodeRunState.COMPLETED,
                output=payload,
                mediaType=media_type,
            )
        )
        completed_outputs[input_node.id] = (payload, media_type)
        arrival_order[input_node.id] = arrival_counter
        arrival_counter += 1

    remaining_skills = list(plan.skill_nodes)
    while remaining_skills:
        skill_node = remaining_skills.pop(0)

        envelopes, blocked = collect_input_envelopes(
            skill_node,
            workflow,
            completed_outputs,
            arrival_order,
        )
        if blocked is not None or envelopes is None:
            node_results.append(
                NodeRunResult(
                    nodeId=skill_node.id,
                    state=NodeRunState.BLOCKED,
                    error=blocked.message if blocked else "blocked",
                )
            )
            for skipped in remaining_skills:
                node_results.append(
                    NodeRunResult(
                        nodeId=skipped.id,
                        state=NodeRunState.SKIPPED,
                    )
                )
            for output_node in plan.output_nodes:
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
                    blocked
                    if blocked is not None
                    else ValidationIssue(
                        code="blocked",
                        message="Skill blocked on missing inputs.",
                        nodeId=skill_node.id,
                    )
                ],
            )

        primary = envelopes[0]
        try:
            skill_result = active_runner.execute(
                SkillExecutionRequest(
                    skillNodeId=skill_node.id,
                    skillLabel=skill_node.label,
                    description=getattr(skill_node.settings, "description", "") or "",
                    inputPayload=primary.payload,
                    inputMediaType=primary.mediaType,
                    inputs=envelopes,
                )
            )
        except Exception as exc:
            node_results.append(
                NodeRunResult(
                    nodeId=skill_node.id,
                    state=NodeRunState.FAILED,
                    error=str(exc),
                )
            )
            for skipped in remaining_skills:
                node_results.append(
                    NodeRunResult(
                        nodeId=skipped.id,
                        state=NodeRunState.SKIPPED,
                    )
                )
            for output_node in plan.output_nodes:
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

        payload = skill_result.outputPayload
        media_type = skill_result.mediaType
        node_results.append(
            NodeRunResult(
                nodeId=skill_node.id,
                state=NodeRunState.COMPLETED,
                output=payload,
                mediaType=media_type,
            )
        )
        completed_outputs[skill_node.id] = (payload, media_type)
        arrival_order[skill_node.id] = arrival_counter
        arrival_counter += 1

    # Passive Artifact Outputs: each branch gets the same upstream payload.
    terminal_payload, terminal_media = completed_outputs[plan.skill_nodes[-1].id]
    for output_node in plan.output_nodes:
        node_results.append(
            NodeRunResult(
                nodeId=output_node.id,
                state=NodeRunState.COMPLETED,
                output=terminal_payload,
                mediaType=terminal_media,
            )
        )

    return RunResponse(
        id=run_id,
        status="completed",
        nodeResults=node_results,
        output=terminal_payload,
        mediaType=terminal_media,
    )
