"""Run orchestration with live events, cancel, and timeouts (Phases 11–16)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.run import (
    NodeRunResult,
    NodeRunState,
    RunEventScope,
    RunEventType,
    RunOptions,
    RunResponse,
    RunSummary,
    RunnerKind,
)
from mitos_api.domain.validation import validate_workflow
from mitos_api.domain.workflow import (
    ArtifactDestinationKind,
    ArtifactOutputMode,
    ArtifactOutputNodeSettings,
    AttachedKnowledgeBase,
    AttachedRule,
    CitedChunk,
    DEFAULT_CURSOR_SKILL_MODEL,
    InputNodeSettings,
    MissingDataPolicy,
    NodeKind,
    SkillNodeSettings,
    ValidationIssue,
    Workflow,
    WorkflowNode,
)
from mitos_api.services.artifacts import (
    ArtifactWriteError,
    SelectorError,
    SelectorMatch,
    SelectorMiss,
    apply_selector,
    resolve_missing_payload,
    write_artifact,
)
from mitos_api.services.cost import build_run_summary, normalize_usage
from mitos_api.services.kb.retrieval import (
    build_retrieval_query,
    retrieve_cited_chunks,
)
from mitos_api.services.run_store import RunStore, run_store
from mitos_api.services.runners.base import Runner, SkillExecutionRequest
from mitos_api.services.runners.cursor import CursorRunner
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.cursor.command_builder import CursorCommandBuildError
from mitos_api.services.scheduler import (
    collect_attached_knowledge_bases,
    collect_attached_rules,
    collect_input_envelopes,
    plan_linear_chain,
)

EventCallback = Callable[..., Any]
CancelCheck = Callable[[], bool]


class RunCancelled(Exception):
    """Raised when a run is cancelled before a node starts."""


def _interruptible_sleep(delay_ms: int, is_cancelled: CancelCheck) -> None:
    if delay_ms <= 0:
        return
    deadline = time.monotonic() + (delay_ms / 1000.0)
    while time.monotonic() < deadline:
        if is_cancelled():
            raise RunCancelled()
        remaining = deadline - time.monotonic()
        time.sleep(min(0.05, max(remaining, 0.0)))


def _call_cleanup(runner: Runner, skill_node_id: str) -> None:
    cleanup = getattr(runner, "cleanup", None)
    if callable(cleanup):
        cleanup(skill_node_id)


def _deliver_artifact_output(
    output_node: WorkflowNode,
    *,
    payload: str,
    media_type: str,
) -> NodeRunResult:
    """
    Deliver an Artifact Output after optional Phase 26 selection.

    Preview: keep projected bytes in the node result (no disk write).
    Managed file: write under the approved output root (overwrite or timestamped).
    """
    settings = output_node.settings
    if not isinstance(settings, ArtifactOutputNodeSettings):
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error="Artifact Output node has invalid settings",
        )

    destination = settings.destination
    if destination is ArtifactDestinationKind.PREVIEW:
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.COMPLETED,
            output=payload,
            mediaType=media_type,
        )

    if destination is ArtifactDestinationKind.MANAGED_FILE:
        try:
            written = write_artifact(
                payload,
                relative_path=settings.filePath or "",
                write_mode=settings.writeMode,
            )
        except ArtifactWriteError as exc:
            return NodeRunResult(
                nodeId=output_node.id,
                state=NodeRunState.FAILED,
                output=payload,
                mediaType=media_type,
                error=exc.message,
            )
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.COMPLETED,
            output=payload,
            mediaType=media_type,
            artifactPath=written.relative_path,
            artifactAbsolutePath=str(written.absolute_path),
            bytesWritten=written.bytes_written,
        )

    return NodeRunResult(
        nodeId=output_node.id,
        state=NodeRunState.FAILED,
        error=f"Unsupported artifact destination: {destination}",
    )


def _project_output_payload(
    output_node: WorkflowNode,
    *,
    upstream_payload: str,
    upstream_media_type: str,
) -> tuple[str, str] | NodeRunResult:
    """
    Apply pass-through or Phase 26 selector projection.

    Returns ``(payload, media_type)`` when delivery should proceed, or a
    finished ``NodeRunResult`` for skip / fail missing-data policies (and
    invalid selector configuration / expression errors).
    """
    settings = output_node.settings
    if not isinstance(settings, ArtifactOutputNodeSettings):
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error="Artifact Output node has invalid settings",
        )

    if settings.mode is ArtifactOutputMode.PASS_THROUGH:
        return upstream_payload, upstream_media_type

    if settings.mode is ArtifactOutputMode.PROMPTED:
        # Prompted projections are executed separately (second runner call).
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error="Prompted mode must be executed via runner, not projected passively",
        )

    if settings.mode is not ArtifactOutputMode.SELECTOR:
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error=f"Unsupported Artifact Output mode: {settings.mode.value}",
        )

    kind = settings.selectorKind
    expression = (settings.selectorExpression or "").strip()
    if kind is None or not expression:
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error="Selector requires selectorKind and selectorExpression",
        )

    try:
        selected = apply_selector(
            upstream_payload,
            kind=kind,
            expression=expression,
            media_type=upstream_media_type,
        )
    except SelectorError as exc:
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error=exc.message,
        )

    if isinstance(selected, SelectorMatch):
        return selected.payload, selected.media_type

    assert isinstance(selected, SelectorMiss)
    policy = settings.missingDataPolicy
    if policy is MissingDataPolicy.SKIP:
        reason = (
            f"Selector {kind.value} '{expression}' matched no data "
            f"({selected.reason}); skipped per missingDataPolicy"
        )
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.SKIPPED,
            error=reason,
        )
    if policy is MissingDataPolicy.FAIL:
        reason = (
            f"Selector {kind.value} '{expression}' matched no data "
            f"({selected.reason})"
        )
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error=reason,
        )

    resolved_payload, resolved_media = resolve_missing_payload(
        policy=policy,
        kind=kind,
        expression=expression,
        reason=selected.reason,
    )
    if resolved_payload is None or resolved_media is None:
        return NodeRunResult(
            nodeId=output_node.id,
            state=NodeRunState.FAILED,
            error=selected.reason,
        )
    return resolved_payload, resolved_media


def _artifact_write_mode_label(output_node: WorkflowNode) -> str:
    settings = output_node.settings
    if isinstance(settings, ArtifactOutputNodeSettings):
        return settings.writeMode.value
    return "unknown"


def _artifact_mode_label(output_node: WorkflowNode) -> str:
    settings = output_node.settings
    if isinstance(settings, ArtifactOutputNodeSettings):
        return settings.mode.value
    return "unknown"


def _skill_runner_kind(
    skill_node: WorkflowNode,
    options: RunOptions,
) -> RunnerKind:
    """
    Resolve Fake vs Cursor for one Skill (Phase 24).

    Per-node ``settings.runner='cursor'`` selects Cursor. Whole-run
    ``options.runner='cursor'`` (Phase 23) still forces Cursor for every Skill.
    """
    settings = skill_node.settings
    if isinstance(settings, SkillNodeSettings) and settings.runner == "cursor":
        return "cursor"
    return options.runner


def _output_runner_kind(
    output_node: WorkflowNode,
    options: RunOptions,
) -> RunnerKind:
    """
    Resolve Fake vs Cursor for one prompted Artifact Output (Phase 27).

    Per-node ``settings.runner='cursor'`` selects Cursor. Whole-run
    ``options.runner='cursor'`` still forces Cursor for prompted projections.
    """
    settings = output_node.settings
    if (
        isinstance(settings, ArtifactOutputNodeSettings)
        and settings.runner == "cursor"
    ):
        return "cursor"
    return options.runner


def _workflow_needs_cursor(workflow: Workflow, options: RunOptions) -> bool:
    if options.runner == "cursor":
        return True
    for node in workflow.nodes:
        if node.kind is NodeKind.SKILL:
            if (
                isinstance(node.settings, SkillNodeSettings)
                and node.settings.runner == "cursor"
            ):
                return True
        elif node.kind is NodeKind.ARTIFACT_OUTPUT:
            if (
                isinstance(node.settings, ArtifactOutputNodeSettings)
                and node.settings.mode is ArtifactOutputMode.PROMPTED
                and node.settings.runner == "cursor"
            ):
                return True
    return False


def _resolve_skill_model(
    skill_node: WorkflowNode,
    options: RunOptions,
) -> str:
    """
    Resolve the Cursor model for one Skill (Phase 24.5).

    Skill ``settings.model`` wins; then run-level ``options.cursor.model``;
    finally ``composer-2.5``. Never returns empty.
    """
    settings = skill_node.settings
    if isinstance(settings, SkillNodeSettings):
        skill_model = (settings.model or "").strip()
        if skill_model:
            return skill_model
    cursor_opts = options.cursor
    if cursor_opts is not None:
        run_model = (cursor_opts.model or "").strip()
        if run_model:
            return run_model
    return DEFAULT_CURSOR_SKILL_MODEL


def _resolve_output_model(
    output_node: WorkflowNode,
    options: RunOptions,
) -> str:
    """
    Resolve the Cursor model for one prompted Artifact Output (Phase 27).

    Output ``settings.model`` wins; then run-level ``options.cursor.model``;
    finally ``composer-2.5``. Never returns empty.
    """
    settings = output_node.settings
    if isinstance(settings, ArtifactOutputNodeSettings):
        output_model = (settings.model or "").strip()
        if output_model:
            return output_model
    cursor_opts = options.cursor
    if cursor_opts is not None:
        run_model = (cursor_opts.model or "").strip()
        if run_model:
            return run_model
    return DEFAULT_CURSOR_SKILL_MODEL


def _execute_skill_with_timeout(
    runner: Runner,
    request: SkillExecutionRequest,
    *,
    timeout_ms: int | None,
) -> Any:
    if timeout_ms is None:
        return runner.execute(request)

    timeout_sec = timeout_ms / 1000.0
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.execute, request)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeout as exc:
            future.cancel()
            raise TimeoutError(
                f"Skill '{request.skillNodeId}' exceeded timeout of {timeout_ms}ms"
            ) from exc


def execute_run(
    workflow: Workflow,
    *,
    runner: Runner | None = None,
    cursor_runner: Runner | None = None,
    options: RunOptions | None = None,
    on_event: EventCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    run_id: str | None = None,
) -> RunResponse:
    """
    Execute a Phase-14-supported graph, optionally emitting live events.

    Supported shape: one or more Inputs → Skills (linear path and/or
    wait_for_all joins on named ports) → one or more Artifact Outputs
    (pass-through, Phase 26 selectors, or Phase 27 prompted projections).
    Skills run in topological order; each Skill waits for every declared
    data-in port. Phase 18 resolves Rules resource attachments into the Skill
    runner request (ordered, de-duplicated). Phase 19 resolves Knowledge Base
    attachments and runs deterministic keyword retrieval so cited chunks
    are available to the runner and run trace. Phase 20 applies
    per-attachment top-K / threshold and records the retrieval query in the
    Skill run trace. Phase 24 selects Fake or Cursor per Skill via
    ``settings.runner`` (scheduler semantics unchanged). Phase 26 applies
    JSONPath / named-section selectors on Artifact Outputs with zero extra
    runner calls. Phase 27 executes prompted outputs as an explicit second
    runner call with their own runner/model/timeout/usage. Failure, timeout,
    blocked join, or cancel stops the chain so no downstream node starts.

    When ``runner`` is provided without ``cursor_runner``, that single runner
    is used for every Skill and prompted output (test injection / Phase 23
    whole-run).
    """
    rid = run_id or str(uuid.uuid4())
    opts = options or RunOptions()
    fake_runner: Runner = FakeRunner()
    # Explicit ``runner`` alone = whole-run override (tests + Phase 23 inject).
    forced_runner: Runner | None = None
    if runner is not None and cursor_runner is None:
        forced_runner = runner
    elif runner is not None:
        fake_runner = runner
    active_cursor: Runner | None = cursor_runner
    cancel_check: CancelCheck = is_cancelled or (lambda: False)

    def pick_runner_for_skill(skill_node: WorkflowNode) -> Runner:
        if forced_runner is not None:
            return forced_runner
        kind = _skill_runner_kind(skill_node, opts)
        if kind == "cursor":
            if active_cursor is None:
                raise RuntimeError(
                    f"Cursor runner required for Skill '{skill_node.id}' "
                    "but was not resolved."
                )
            return active_cursor
        return fake_runner

    def pick_runner_for_output(output_node: WorkflowNode) -> Runner:
        if forced_runner is not None:
            return forced_runner
        kind = _output_runner_kind(output_node, opts)
        if kind == "cursor":
            if active_cursor is None:
                raise RuntimeError(
                    f"Cursor runner required for prompted Output "
                    f"'{output_node.id}' but was not resolved."
                )
            return active_cursor
        return fake_runner

    def emit(
        event_type: RunEventType,
        *,
        scope: RunEventScope = RunEventScope.NODE,
        node_id: str | None = None,
        message: str | None = None,
        output: str | None = None,
        media_type: str | None = None,
        error: str | None = None,
        attached_rules: list[AttachedRule] | None = None,
        knowledge_chunks: list[CitedChunk] | None = None,
        knowledge_query: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        elapsed_ms: int | None = None,
        usage: RunnerUsage | None = None,
        model: str | None = None,
        artifact_path: str | None = None,
        artifact_absolute_path: str | None = None,
        bytes_written: int | None = None,
        prompt_template: str | None = None,
        summary: RunSummary | None = None,
    ) -> None:
        if on_event is not None:
            on_event(
                event_type,
                scope=scope,
                node_id=node_id,
                message=message,
                output=output,
                media_type=media_type,
                error=error,
                attached_rules=attached_rules,
                knowledge_chunks=knowledge_chunks,
                knowledge_query=knowledge_query,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                elapsed_ms=elapsed_ms,
                usage=usage,
                model=model,
                artifact_path=artifact_path,
                artifact_absolute_path=artifact_absolute_path,
                bytes_written=bytes_written,
                prompt_template=prompt_template,
                summary=summary,
            )

    validation = validate_workflow(workflow)
    if not validation.valid:
        return RunResponse(
            id=rid,
            status="rejected",
            errors=list(validation.errors),
        )

    plan, shape_errors = plan_linear_chain(workflow)
    if shape_errors or plan is None:
        return RunResponse(
            id=rid,
            status="rejected",
            errors=shape_errors,
        )

    emit(
        RunEventType.QUEUED,
        scope=RunEventScope.RUN,
        message="Run queued",
    )
    emit(
        RunEventType.RUNNING,
        scope=RunEventScope.RUN,
        message="Run started",
    )

    node_results: list[NodeRunResult] = []
    completed_outputs: dict[str, tuple[str, str]] = {}
    arrival_order: dict[str, int] = {}
    arrival_counter = 0
    failed_upstream: str | None = None

    def finalize_unused_resources() -> None:
        """Mark Rules/KB nodes never attached to an executed Skill as skipped."""
        already = {r.nodeId for r in node_results}
        for node in workflow.nodes:
            if node.id in already:
                continue
            if node.kind is NodeKind.RULES:
                node_results.append(
                    NodeRunResult(
                        nodeId=node.id,
                        state=NodeRunState.SKIPPED,
                    )
                )
                emit(
                    RunEventType.SKIPPED,
                    node_id=node.id,
                    message="Rules node not attached to an executed Skill",
                )
            elif node.kind is NodeKind.KNOWLEDGE_BASE:
                node_results.append(
                    NodeRunResult(
                        nodeId=node.id,
                        state=NodeRunState.SKIPPED,
                    )
                )
                emit(
                    RunEventType.SKIPPED,
                    node_id=node.id,
                    message="Knowledge Base not attached to an executed Skill",
                )

    def record_attached_rules(attached: list[AttachedRule]) -> None:
        """Mark attached Rules nodes completed (once) so content is in the trace."""
        already = {r.nodeId for r in node_results}
        for rule in attached:
            if rule.rulesNodeId in already:
                continue
            node_results.append(
                NodeRunResult(
                    nodeId=rule.rulesNodeId,
                    state=NodeRunState.COMPLETED,
                    output=rule.content,
                    mediaType="text/markdown",
                )
            )
            emit(
                RunEventType.COMPLETED,
                node_id=rule.rulesNodeId,
                message=f"Rules attached: {rule.label}",
                output=rule.content,
                media_type="text/markdown",
            )
            already.add(rule.rulesNodeId)

    def record_attached_knowledge(
        attached: list[AttachedKnowledgeBase],
        chunks: list[CitedChunk],
    ) -> None:
        """Mark attached KB nodes completed (once); include cited chunks on first use."""
        already = {r.nodeId for r in node_results}
        chunks_by_kb: dict[str, list[CitedChunk]] = {}
        for chunk in chunks:
            chunks_by_kb.setdefault(chunk.kbNodeId, []).append(chunk)

        for kb in attached:
            if kb.kbNodeId in already:
                continue
            kb_chunks = chunks_by_kb.get(kb.kbNodeId, [])
            citations = ", ".join(c.citation for c in kb_chunks) if kb_chunks else ""
            message = (
                f"KB attached: {kb.label} ({len(kb_chunks)} cited chunk(s))"
                if kb_chunks
                else f"KB attached: {kb.label} (no keyword matches)"
            )
            node_results.append(
                NodeRunResult(
                    nodeId=kb.kbNodeId,
                    state=NodeRunState.COMPLETED,
                    output=citations or kb.content,
                    mediaType="text/plain",
                    knowledgeChunks=kb_chunks,
                )
            )
            emit(
                RunEventType.COMPLETED,
                node_id=kb.kbNodeId,
                message=message,
                output=citations or kb.content,
                media_type="text/plain",
                knowledge_chunks=kb_chunks,
            )
            already.add(kb.kbNodeId)

    def mark_cancelled_remaining(
        remaining_skills: list,
        *,
        reason: str,
    ) -> RunResponse:
        for skipped in remaining_skills:
            node_results.append(
                NodeRunResult(
                    nodeId=skipped.id,
                    state=NodeRunState.CANCELLED,
                    error=reason,
                )
            )
            emit(
                RunEventType.CANCELLED,
                node_id=skipped.id,
                message=reason,
                error=reason,
            )
        for output_node in plan.output_nodes:
            # Skip outputs that were never reached; report branch failure.
            already = {r.nodeId for r in node_results}
            if output_node.id in already:
                continue
            msg = f"Branch stopped: {reason}"
            node_results.append(
                NodeRunResult(
                    nodeId=output_node.id,
                    state=NodeRunState.CANCELLED,
                    error=msg,
                )
            )
            emit(
                RunEventType.CANCELLED,
                node_id=output_node.id,
                message=msg,
                error=msg,
            )
        finalize_unused_resources()
        summary = build_run_summary(node_results)
        emit(
            RunEventType.CANCELLED,
            scope=RunEventScope.RUN,
            message=reason,
            error=reason,
            summary=summary,
        )
        return RunResponse(
            id=rid,
            status="cancelled",
            nodeResults=node_results,
            errors=[
                ValidationIssue(
                    code="cancelled",
                    message=reason,
                )
            ],
            summary=summary,
        )

    def mark_failed_remaining(
        remaining_skills: list,
        *,
        failed_node_id: str,
        issue: ValidationIssue,
        skill_state: NodeRunState = NodeRunState.FAILED,
        event_type: RunEventType = RunEventType.FAILED,
    ) -> RunResponse:
        nonlocal failed_upstream
        failed_upstream = failed_node_id
        for skipped in remaining_skills:
            reason = f"Skipped due to upstream failure on '{failed_node_id}'"
            node_results.append(
                NodeRunResult(
                    nodeId=skipped.id,
                    state=NodeRunState.SKIPPED,
                    error=reason,
                )
            )
            emit(
                RunEventType.SKIPPED,
                node_id=skipped.id,
                message=reason,
                error=reason,
            )
        for output_node in plan.output_nodes:
            already = {r.nodeId for r in node_results}
            if output_node.id in already:
                continue
            reason = (
                f"Branch failed: upstream '{failed_node_id}' did not complete"
            )
            node_results.append(
                NodeRunResult(
                    nodeId=output_node.id,
                    state=NodeRunState.SKIPPED,
                    error=reason,
                )
            )
            emit(
                RunEventType.SKIPPED,
                node_id=output_node.id,
                message=reason,
                error=reason,
            )
        finalize_unused_resources()
        summary = build_run_summary(node_results)
        emit(
            event_type if event_type is RunEventType.FAILED else RunEventType.FAILED,
            scope=RunEventScope.RUN,
            message=issue.message,
            error=issue.message,
            summary=summary,
        )
        return RunResponse(
            id=rid,
            status="failed",
            nodeResults=node_results,
            errors=[issue],
            summary=summary,
        )

    # Complete Inputs first (deterministic id order from the plan).
    for input_node in plan.input_nodes:
        if cancel_check():
            return mark_cancelled_remaining(
                list(plan.skill_nodes),
                reason="Run cancelled before inputs completed",
            )
        assert isinstance(input_node.settings, InputNodeSettings)
        emit(RunEventType.QUEUED, node_id=input_node.id)
        emit(RunEventType.RUNNING, node_id=input_node.id)
        try:
            _interruptible_sleep(opts.delayMs, cancel_check)
        except RunCancelled:
            node_results.append(
                NodeRunResult(
                    nodeId=input_node.id,
                    state=NodeRunState.CANCELLED,
                    error="Cancelled during input delay",
                )
            )
            emit(
                RunEventType.CANCELLED,
                node_id=input_node.id,
                message="Cancelled during input delay",
                error="Cancelled during input delay",
            )
            remaining = [
                s for s in plan.skill_nodes if s.id not in {r.nodeId for r in node_results}
            ]
            return mark_cancelled_remaining(
                remaining,
                reason="Run cancelled during input processing",
            )

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
        emit(
            RunEventType.COMPLETED,
            node_id=input_node.id,
            output=payload,
            media_type=media_type,
        )

    remaining_skills = list(plan.skill_nodes)
    while remaining_skills:
        if cancel_check():
            return mark_cancelled_remaining(
                remaining_skills,
                reason="Run cancelled before next Skill started",
            )

        skill_node = remaining_skills.pop(0)
        active_runner = pick_runner_for_skill(skill_node)
        emit(RunEventType.QUEUED, node_id=skill_node.id)

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
            emit(
                RunEventType.BLOCKED,
                node_id=skill_node.id,
                message=blocked.message if blocked else "blocked",
                error=blocked.message if blocked else "blocked",
            )
            return mark_failed_remaining(
                remaining_skills,
                failed_node_id=skill_node.id,
                issue=blocked
                if blocked is not None
                else ValidationIssue(
                    code="blocked",
                    message="Skill blocked on missing inputs.",
                    nodeId=skill_node.id,
                ),
                skill_state=NodeRunState.BLOCKED,
                event_type=RunEventType.BLOCKED,
            )

        attached_rules = collect_attached_rules(skill_node, workflow)
        record_attached_rules(attached_rules)

        attached_kbs = collect_attached_knowledge_bases(skill_node, workflow)
        query = build_retrieval_query(
            envelopes[0].payload if envelopes else "",
            envelopes,
        )
        knowledge_chunks = retrieve_cited_chunks(attached_kbs, query)
        record_attached_knowledge(attached_kbs, knowledge_chunks)
        # Surface query in the Skill run trace whenever KBs are attached.
        knowledge_query = query if attached_kbs else None

        emit(RunEventType.RUNNING, node_id=skill_node.id)
        try:
            _interruptible_sleep(opts.delayMs, cancel_check)
        except RunCancelled:
            node_results.append(
                NodeRunResult(
                    nodeId=skill_node.id,
                    state=NodeRunState.CANCELLED,
                    error="Cancelled before Skill execution",
                    attachedRules=attached_rules,
                    knowledgeChunks=knowledge_chunks,
                    knowledgeQuery=knowledge_query,
                )
            )
            emit(
                RunEventType.CANCELLED,
                node_id=skill_node.id,
                message="Cancelled before Skill execution",
                error="Cancelled before Skill execution",
                attached_rules=attached_rules,
                knowledge_chunks=knowledge_chunks,
                knowledge_query=knowledge_query,
            )
            _call_cleanup(active_runner, skill_node.id)
            return mark_cancelled_remaining(
                remaining_skills,
                reason="Run cancelled before Skill execution",
            )

        primary = envelopes[0]
        runner_kind = (
            _skill_runner_kind(skill_node, opts)
            if forced_runner is None
            else (
                "cursor"
                if isinstance(active_runner, CursorRunner)
                else opts.runner
            )
        )
        skill_model = (
            _resolve_skill_model(skill_node, opts)
            if runner_kind == "cursor" or isinstance(active_runner, CursorRunner)
            else None
        )
        try:
            skill_result = _execute_skill_with_timeout(
                active_runner,
                SkillExecutionRequest(
                    skillNodeId=skill_node.id,
                    skillLabel=skill_node.label,
                    description=getattr(skill_node.settings, "description", "") or "",
                    content=getattr(skill_node.settings, "content", "") or "",
                    inputPayload=primary.payload,
                    inputMediaType=primary.mediaType,
                    inputs=envelopes,
                    rules=attached_rules,
                    knowledgeChunks=knowledge_chunks,
                    model=skill_model,
                ),
                timeout_ms=opts.nodeTimeoutMs,
            )
        except TimeoutError as exc:
            msg = str(exc)
            node_results.append(
                NodeRunResult(
                    nodeId=skill_node.id,
                    state=NodeRunState.TIMEOUT,
                    error=msg,
                    attachedRules=attached_rules,
                    knowledgeChunks=knowledge_chunks,
                    knowledgeQuery=knowledge_query,
                )
            )
            emit(
                RunEventType.TIMEOUT,
                node_id=skill_node.id,
                message=msg,
                error=msg,
                attached_rules=attached_rules,
                knowledge_chunks=knowledge_chunks,
                knowledge_query=knowledge_query,
            )
            _call_cleanup(active_runner, skill_node.id)
            return mark_failed_remaining(
                remaining_skills,
                failed_node_id=skill_node.id,
                issue=ValidationIssue(
                    code="timeout",
                    message=msg,
                    nodeId=skill_node.id,
                ),
                skill_state=NodeRunState.TIMEOUT,
                event_type=RunEventType.TIMEOUT,
            )
        except Exception as exc:
            node_results.append(
                NodeRunResult(
                    nodeId=skill_node.id,
                    state=NodeRunState.FAILED,
                    error=str(exc),
                    attachedRules=attached_rules,
                    knowledgeChunks=knowledge_chunks,
                    knowledgeQuery=knowledge_query,
                )
            )
            emit(
                RunEventType.FAILED,
                node_id=skill_node.id,
                message=str(exc),
                error=str(exc),
                attached_rules=attached_rules,
                knowledge_chunks=knowledge_chunks,
                knowledge_query=knowledge_query,
            )
            _call_cleanup(active_runner, skill_node.id)
            return mark_failed_remaining(
                remaining_skills,
                failed_node_id=skill_node.id,
                issue=ValidationIssue(
                    code="runner_failed",
                    message=str(exc),
                    nodeId=skill_node.id,
                ),
            )

        _call_cleanup(active_runner, skill_node.id)

        payload = skill_result.outputPayload
        media_type = skill_result.mediaType
        message_parts: list[str] = []
        if attached_rules:
            labels = ", ".join(rule.label for rule in attached_rules)
            message_parts.append(
                f"Attached {len(attached_rules)} rule(s): {labels}"
            )
        if attached_kbs:
            chunk_ids = ", ".join(chunk.chunkId for chunk in knowledge_chunks)
            citations = ", ".join(chunk.citation for chunk in knowledge_chunks)
            message_parts.append(f"Query: {query}")
            if knowledge_chunks:
                message_parts.append(
                    f"Retrieved {len(knowledge_chunks)} KB chunk(s)"
                    f" [{chunk_ids}]: {citations}"
                )
            else:
                kb_labels = ", ".join(kb.label for kb in attached_kbs)
                message_parts.append(
                    f"Attached {len(attached_kbs)} KB(s) with no keyword matches: {kb_labels}"
                )
        if skill_result.elapsedMs is not None:
            message_parts.append(f"elapsed {skill_result.elapsedMs}ms")
        if skill_result.exitCode is not None:
            message_parts.append(f"exit {skill_result.exitCode}")
        resolved_model = skill_result.model or skill_model
        if resolved_model:
            message_parts.append(f"model {resolved_model}")
        if skill_result.usage is not None:
            usage = normalize_usage(skill_result.usage) or skill_result.usage
            token_bits: list[str] = []
            if usage.inputTokens is not None:
                token_bits.append(f"in={usage.inputTokens}")
            if usage.outputTokens is not None:
                token_bits.append(f"out={usage.outputTokens}")
            if usage.totalTokens is not None:
                token_bits.append(f"total={usage.totalTokens}")
            if token_bits:
                message_parts.append(f"usage [{', '.join(token_bits)}]")
        else:
            usage = None
        skill_message = "; ".join(message_parts) if message_parts else None
        node_results.append(
            NodeRunResult(
                nodeId=skill_node.id,
                state=NodeRunState.COMPLETED,
                output=payload,
                mediaType=media_type,
                attachedRules=attached_rules,
                knowledgeChunks=knowledge_chunks,
                knowledgeQuery=knowledge_query,
                stdout=skill_result.stdout,
                stderr=skill_result.stderr,
                exitCode=skill_result.exitCode,
                elapsedMs=skill_result.elapsedMs,
                usage=usage,
                model=resolved_model,
            )
        )
        completed_outputs[skill_node.id] = (payload, media_type)
        arrival_order[skill_node.id] = arrival_counter
        arrival_counter += 1
        emit(
            RunEventType.COMPLETED,
            node_id=skill_node.id,
            message=skill_message,
            output=payload,
            media_type=media_type,
            attached_rules=attached_rules,
            knowledge_chunks=knowledge_chunks,
            knowledge_query=knowledge_query,
            stdout=skill_result.stdout,
            stderr=skill_result.stderr,
            exit_code=skill_result.exitCode,
            elapsed_ms=skill_result.elapsedMs,
            usage=usage,
            model=resolved_model,
        )

    if cancel_check():
        return mark_cancelled_remaining(
            [],
            reason="Run cancelled before outputs completed",
        )

    # Artifact Outputs: pass-through / selector project passively; prompted
    # projections make an explicit second runner call (Phase 27).
    terminal_payload, terminal_media = completed_outputs[plan.skill_nodes[-1].id]
    for output_node in plan.output_nodes:
        if cancel_check():
            return mark_cancelled_remaining(
                [],
                reason="Run cancelled during output fan-out",
            )
        emit(RunEventType.QUEUED, node_id=output_node.id)
        emit(RunEventType.RUNNING, node_id=output_node.id)
        try:
            _interruptible_sleep(opts.delayMs, cancel_check)
        except RunCancelled:
            node_results.append(
                NodeRunResult(
                    nodeId=output_node.id,
                    state=NodeRunState.CANCELLED,
                    error="Cancelled during output processing",
                )
            )
            emit(
                RunEventType.CANCELLED,
                node_id=output_node.id,
                message="Cancelled during output processing",
                error="Cancelled during output processing",
            )
            remaining_outputs = [
                o
                for o in plan.output_nodes
                if o.id not in {r.nodeId for r in node_results}
            ]
            for o in remaining_outputs:
                reason = "Branch stopped: run cancelled"
                node_results.append(
                    NodeRunResult(
                        nodeId=o.id,
                        state=NodeRunState.CANCELLED,
                        error=reason,
                    )
                )
                emit(
                    RunEventType.CANCELLED,
                    node_id=o.id,
                    message=reason,
                    error=reason,
                )
            finalize_unused_resources()
            summary = build_run_summary(node_results)
            emit(
                RunEventType.CANCELLED,
                scope=RunEventScope.RUN,
                message="Run cancelled during output fan-out",
                error="Run cancelled during output fan-out",
                summary=summary,
            )
            return RunResponse(
                id=rid,
                status="cancelled",
                nodeResults=node_results,
                errors=[
                    ValidationIssue(
                        code="cancelled",
                        message="Run cancelled during output fan-out",
                    )
                ],
                summary=summary,
            )

        output_settings = output_node.settings
        if (
            isinstance(output_settings, ArtifactOutputNodeSettings)
            and output_settings.mode is ArtifactOutputMode.PROMPTED
        ):
            prompt_template = (output_settings.promptTemplate or "").strip()
            if not prompt_template:
                result = NodeRunResult(
                    nodeId=output_node.id,
                    state=NodeRunState.FAILED,
                    error="Prompted Artifact Output requires promptTemplate",
                )
                node_results.append(result)
                emit(
                    RunEventType.FAILED,
                    node_id=output_node.id,
                    error=result.error,
                    message=result.error,
                )
                continue

            active_output_runner = pick_runner_for_output(output_node)
            runner_kind = (
                _output_runner_kind(output_node, opts)
                if forced_runner is None
                else (
                    "cursor"
                    if isinstance(active_output_runner, CursorRunner)
                    else opts.runner
                )
            )
            resolved_model = (
                _resolve_output_model(output_node, opts)
                if runner_kind == "cursor"
                or isinstance(active_output_runner, CursorRunner)
                else None
            )
            try:
                projection_result = _execute_skill_with_timeout(
                    active_output_runner,
                    SkillExecutionRequest(
                        skillNodeId=output_node.id,
                        skillLabel=output_node.label,
                        description=prompt_template,
                        inputPayload=terminal_payload,
                        inputMediaType=terminal_media,
                        inputs=[],
                        model=resolved_model,
                        promptTemplate=prompt_template,
                    ),
                    timeout_ms=opts.nodeTimeoutMs,
                )
            except TimeoutError as exc:
                msg = str(exc)
                node_results.append(
                    NodeRunResult(
                        nodeId=output_node.id,
                        state=NodeRunState.TIMEOUT,
                        error=msg,
                        promptTemplate=prompt_template,
                        model=resolved_model,
                    )
                )
                emit(
                    RunEventType.TIMEOUT,
                    node_id=output_node.id,
                    message=msg,
                    error=msg,
                    prompt_template=prompt_template,
                    model=resolved_model,
                )
                _call_cleanup(active_output_runner, output_node.id)
                continue
            except Exception as exc:
                node_results.append(
                    NodeRunResult(
                        nodeId=output_node.id,
                        state=NodeRunState.FAILED,
                        error=str(exc),
                        promptTemplate=prompt_template,
                        model=resolved_model,
                    )
                )
                emit(
                    RunEventType.FAILED,
                    node_id=output_node.id,
                    message=str(exc),
                    error=str(exc),
                    prompt_template=prompt_template,
                    model=resolved_model,
                )
                _call_cleanup(active_output_runner, output_node.id)
                continue

            _call_cleanup(active_output_runner, output_node.id)
            branch_payload = projection_result.outputPayload
            branch_media = projection_result.mediaType or "text/plain"
            result = _deliver_artifact_output(
                output_node,
                payload=branch_payload,
                media_type=branch_media,
            )
            # Attach projection capture metadata onto the delivered result.
            normalized_usage = normalize_usage(projection_result.usage)
            result = result.model_copy(
                update={
                    "promptTemplate": prompt_template,
                    "stdout": projection_result.stdout,
                    "stderr": projection_result.stderr,
                    "exitCode": projection_result.exitCode,
                    "elapsedMs": projection_result.elapsedMs,
                    "usage": normalized_usage,
                    "model": resolved_model or projection_result.model,
                }
            )
            node_results.append(result)
            if result.state is NodeRunState.FAILED:
                emit(
                    RunEventType.FAILED,
                    node_id=output_node.id,
                    output=result.output,
                    media_type=result.mediaType,
                    error=result.error,
                    message=result.error,
                    prompt_template=prompt_template,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exitCode,
                    elapsed_ms=result.elapsedMs,
                    usage=result.usage,
                    model=result.model,
                )
            else:
                mode_label = _artifact_mode_label(output_node)
                if result.artifactPath is not None:
                    message = (
                        f"{mode_label}: wrote {result.bytesWritten} bytes to "
                        f"{result.artifactPath} "
                        f"({_artifact_write_mode_label(output_node)}); "
                        f"prompt applied"
                    )
                else:
                    message = (
                        f"{mode_label}: preview (no file write); prompt applied"
                    )
                emit(
                    RunEventType.COMPLETED,
                    node_id=output_node.id,
                    output=result.output,
                    media_type=result.mediaType,
                    message=message,
                    artifact_path=result.artifactPath,
                    artifact_absolute_path=result.artifactAbsolutePath,
                    bytes_written=result.bytesWritten,
                    prompt_template=prompt_template,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exitCode,
                    elapsed_ms=result.elapsedMs,
                    usage=result.usage,
                    model=result.model,
                )
            continue

        projected = _project_output_payload(
            output_node,
            upstream_payload=terminal_payload,
            upstream_media_type=terminal_media,
        )
        if isinstance(projected, NodeRunResult):
            result = projected
            node_results.append(result)
            if result.state is NodeRunState.SKIPPED:
                emit(
                    RunEventType.SKIPPED,
                    node_id=output_node.id,
                    message=result.error,
                    error=result.error,
                )
            else:
                emit(
                    RunEventType.FAILED,
                    node_id=output_node.id,
                    output=result.output,
                    media_type=result.mediaType,
                    error=result.error,
                    message=result.error,
                )
            continue

        branch_payload, branch_media = projected
        result = _deliver_artifact_output(
            output_node,
            payload=branch_payload,
            media_type=branch_media,
        )
        node_results.append(result)
        if result.state is NodeRunState.FAILED:
            emit(
                RunEventType.FAILED,
                node_id=output_node.id,
                output=result.output,
                media_type=result.mediaType,
                error=result.error,
                message=result.error,
            )
        else:
            mode_label = _artifact_mode_label(output_node)
            if result.artifactPath is not None:
                message = (
                    f"{mode_label}: wrote {result.bytesWritten} bytes to "
                    f"{result.artifactPath} "
                    f"({_artifact_write_mode_label(output_node)})"
                )
            else:
                message = f"{mode_label}: preview (no file write)"
            emit(
                RunEventType.COMPLETED,
                node_id=output_node.id,
                output=result.output,
                media_type=result.mediaType,
                message=message,
                artifact_path=result.artifactPath,
                artifact_absolute_path=result.artifactAbsolutePath,
                bytes_written=result.bytesWritten,
            )

    output_failures = [
        r
        for r in node_results
        if r.nodeId in {o.id for o in plan.output_nodes}
        and r.state
        in (NodeRunState.FAILED, NodeRunState.TIMEOUT)
    ]
    finalize_unused_resources()
    if output_failures:
        first = output_failures[0]
        fail_code = (
            "selector_miss"
            if (first.error or "").startswith("Selector ")
            else "artifact_write_failed"
        )
        if first.state is NodeRunState.TIMEOUT:
            fail_code = "timeout"
        elif first.error and "JSONPath selector requires" in first.error:
            fail_code = "selector_error"
        elif first.error and first.error.startswith("Invalid JSONPath"):
            fail_code = "selector_error"
        elif first.error and "Selector requires" in first.error:
            fail_code = "selector_error"
        elif first.error and "promptTemplate" in (first.error or ""):
            fail_code = "prompted_projection_failed"
        elif first.promptTemplate is not None and first.state is NodeRunState.FAILED:
            fail_code = "prompted_projection_failed"
        summary = build_run_summary(node_results)
        emit(
            RunEventType.FAILED,
            scope=RunEventScope.RUN,
            message=first.error or "Artifact Output failed",
            error=first.error,
            output=terminal_payload,
            media_type=terminal_media,
            summary=summary,
        )
        return RunResponse(
            id=rid,
            status="failed",
            nodeResults=node_results,
            errors=[
                ValidationIssue(
                    code=fail_code,
                    message=first.error or "Artifact Output failed",
                    nodeId=first.nodeId,
                )
            ],
            output=terminal_payload,
            mediaType=terminal_media,
            summary=summary,
        )

    summary = build_run_summary(node_results)
    emit(
        RunEventType.COMPLETED,
        scope=RunEventScope.RUN,
        message="Run completed",
        output=terminal_payload,
        media_type=terminal_media,
        summary=summary,
    )
    return RunResponse(
        id=rid,
        status="completed",
        nodeResults=node_results,
        output=terminal_payload,
        mediaType=terminal_media,
        summary=summary,
    )


def _reject_cursor_unconfirmed() -> RunResponse:
    rid = str(uuid.uuid4())
    return RunResponse(
        id=rid,
        status="rejected",
        errors=[
            ValidationIssue(
                code="cursor_confirmation_required",
                message=(
                    "Cursor runner requires options.cursor.confirmed=true "
                    "after reviewing the dry-run command preview."
                ),
            )
        ],
    )


def _resolve_cursor_runner(
    options: RunOptions,
) -> Runner | RunResponse:
    """Build a CursorRunner from run options, or a rejected response."""
    cursor_opts = options.cursor
    if cursor_opts is None or not cursor_opts.confirmed:
        return _reject_cursor_unconfirmed()

    try:
        return CursorRunner.from_options(cursor_opts)
    except CursorCommandBuildError as exc:
        rid = str(uuid.uuid4())
        return RunResponse(
            id=rid,
            status="rejected",
            errors=[
                ValidationIssue(
                    code=exc.code,
                    message=exc.message,
                )
            ],
        )


def _resolve_runners(
    workflow: Workflow,
    options: RunOptions,
    *,
    explicit: Runner | None,
) -> tuple[Runner | None, Runner | None] | RunResponse:
    """
    Resolve Fake + optional Cursor runners for a run (Phase 24).

    Returns ``(fake_or_forced, cursor_or_none)``:
    - When ``explicit`` is set, it is used as a whole-run forced runner
      (second element None) — Phase 23 / test injection.
    - Otherwise Fake is always available; Cursor is built when any Skill or
      prompted Artifact Output needs it (``options.runner='cursor'`` or
      ``settings.runner='cursor'``).
    """
    if explicit is not None:
        return (explicit, None)

    needs_cursor = _workflow_needs_cursor(workflow, options)
    if not needs_cursor:
        return (FakeRunner(), None)

    cursor = _resolve_cursor_runner(options)
    if isinstance(cursor, RunResponse):
        return cursor
    return (FakeRunner(), cursor)


def start_run(
    workflow: Workflow,
    *,
    options: RunOptions | None = None,
    runner: Runner | None = None,
    store: RunStore | None = None,
) -> RunResponse:
    """
    Validate and start a background run. Returns immediately with queued/rejected.

    Live progress is available via the run store / SSE endpoint.
    Phase 23: set ``options.runner="cursor"`` with confirmed Cursor options to
    spawn the Cursor CLI for each Skill (Input → Skill → Output).
    Phase 24: set ``skill.settings.runner="cursor"`` on individual Skills for
    mixed Fake/Cursor chains and joins (scheduler semantics unchanged).
    """
    active_store = store or run_store
    opts = options or RunOptions()

    # Validate up-front so rejected runs never enter the store as live runs.
    validation = validate_workflow(workflow)
    if not validation.valid:
        rid = str(uuid.uuid4())
        return RunResponse(
            id=rid,
            status="rejected",
            errors=list(validation.errors),
        )

    plan, shape_errors = plan_linear_chain(workflow)
    if shape_errors or plan is None:
        rid = str(uuid.uuid4())
        return RunResponse(
            id=rid,
            status="rejected",
            errors=shape_errors,
        )

    resolved = _resolve_runners(workflow, opts, explicit=runner)
    if isinstance(resolved, RunResponse):
        return resolved
    fake_or_forced, cursor_runner = resolved

    record = active_store.create(status="queued")
    rid = record.id
    # Snapshot before starting the worker so POST always returns queued
    # (avoids a race when delayMs=0 finishes instantly).
    initial = record.snapshot(include_events=False)

    def _worker() -> None:
        try:
            active_store.update_status(rid, "running")
            # Whole-run forced runner when cursor_runner is None and explicit
            # was provided; otherwise pass Fake + Cursor for per-node pick.
            if cursor_runner is None and runner is not None:
                result = execute_run(
                    workflow,
                    runner=fake_or_forced,
                    options=opts,
                    on_event=active_store.event_callback(rid),
                    is_cancelled=lambda: active_store.is_cancel_requested(rid),
                    run_id=rid,
                )
            else:
                result = execute_run(
                    workflow,
                    runner=fake_or_forced,
                    cursor_runner=cursor_runner,
                    options=opts,
                    on_event=active_store.event_callback(rid),
                    is_cancelled=lambda: active_store.is_cancel_requested(rid),
                    run_id=rid,
                )
            active_store.set_results(
                rid,
                status=result.status,
                node_results=result.nodeResults,
                errors=result.errors,
                output=result.output,
                media_type=result.mediaType,
                summary=result.summary,
            )
        except Exception as exc:  # pragma: no cover - defensive
            active_store.append_event(
                rid,
                event_type=RunEventType.FAILED,
                scope=RunEventScope.RUN,
                message=str(exc),
                error=str(exc),
            )
            active_store.set_results(
                rid,
                status="failed",
                node_results=[],
                errors=[
                    ValidationIssue(
                        code="internal_error",
                        message=str(exc),
                    )
                ],
            )

    thread = threading.Thread(target=_worker, name=f"mitos-run-{rid}", daemon=True)
    thread.start()
    return initial


def cancel_run(
    run_id: str,
    *,
    store: RunStore | None = None,
) -> RunResponse | None:
    """Request cancellation of an in-flight run."""
    active_store = store or run_store
    record = active_store.request_cancel(run_id)
    if record is None:
        return None
    return record.snapshot(include_events=True)


def get_run(
    run_id: str,
    *,
    store: RunStore | None = None,
) -> RunResponse | None:
    active_store = store or run_store
    record = active_store.get(run_id)
    if record is None:
        return None
    return record.snapshot(include_events=True)
