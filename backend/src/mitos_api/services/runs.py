"""Run orchestration with live events, cancel, and timeouts (Phases 11–16)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from mitos_api.domain.run import (
    NodeRunResult,
    NodeRunState,
    RunEventScope,
    RunEventType,
    RunOptions,
    RunResponse,
)
from mitos_api.domain.validation import validate_workflow
from mitos_api.domain.workflow import (
    AttachedKnowledgeBase,
    AttachedRule,
    CitedChunk,
    InputNodeSettings,
    NodeKind,
    ValidationIssue,
    Workflow,
)
from mitos_api.services.kb.retrieval import (
    build_retrieval_query,
    retrieve_cited_chunks,
)
from mitos_api.services.run_store import RunStore, run_store
from mitos_api.services.runners.base import Runner, SkillExecutionRequest
from mitos_api.services.runners.fake import FakeRunner
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
    options: RunOptions | None = None,
    on_event: EventCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    run_id: str | None = None,
) -> RunResponse:
    """
    Execute a Phase-14-supported graph, optionally emitting live events.

    Supported shape: one or more Inputs → Skills (linear path and/or
    wait_for_all joins on named ports) → one or more pass-through Artifact
    Outputs. Skills run in topological order; each Skill waits for every
    declared data-in port. Phase 18 resolves Rules resource attachments into
    the Skill runner request (ordered, de-duplicated). Phase 19 resolves
    Knowledge Base attachments and runs deterministic keyword retrieval so
    cited chunks are available to the runner and run trace. Phase 20 applies
    per-attachment top-K / threshold and records the retrieval query in the
    Skill run trace. Failure, timeout,
    blocked join, or cancel stops the chain so no downstream node starts.
    """
    rid = run_id or str(uuid.uuid4())
    active_runner: Runner = runner if runner is not None else FakeRunner()
    opts = options or RunOptions()
    cancel_check: CancelCheck = is_cancelled or (lambda: False)

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
        emit(
            RunEventType.CANCELLED,
            scope=RunEventScope.RUN,
            message=reason,
            error=reason,
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
        emit(
            event_type if event_type is RunEventType.FAILED else RunEventType.FAILED,
            scope=RunEventScope.RUN,
            message=issue.message,
            error=issue.message,
        )
        return RunResponse(
            id=rid,
            status="failed",
            nodeResults=node_results,
            errors=[issue],
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
        try:
            skill_result = _execute_skill_with_timeout(
                active_runner,
                SkillExecutionRequest(
                    skillNodeId=skill_node.id,
                    skillLabel=skill_node.label,
                    description=getattr(skill_node.settings, "description", "") or "",
                    inputPayload=primary.payload,
                    inputMediaType=primary.mediaType,
                    inputs=envelopes,
                    rules=attached_rules,
                    knowledgeChunks=knowledge_chunks,
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
        )

    if cancel_check():
        return mark_cancelled_remaining(
            [],
            reason="Run cancelled before outputs completed",
        )

    # Passive Artifact Outputs: each branch gets the same upstream payload.
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
            emit(
                RunEventType.CANCELLED,
                scope=RunEventScope.RUN,
                message="Run cancelled during output fan-out",
                error="Run cancelled during output fan-out",
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
            )

        node_results.append(
            NodeRunResult(
                nodeId=output_node.id,
                state=NodeRunState.COMPLETED,
                output=terminal_payload,
                mediaType=terminal_media,
            )
        )
        emit(
            RunEventType.COMPLETED,
            node_id=output_node.id,
            output=terminal_payload,
            media_type=terminal_media,
        )

    finalize_unused_resources()
    emit(
        RunEventType.COMPLETED,
        scope=RunEventScope.RUN,
        message="Run completed",
        output=terminal_payload,
        media_type=terminal_media,
    )
    return RunResponse(
        id=rid,
        status="completed",
        nodeResults=node_results,
        output=terminal_payload,
        mediaType=terminal_media,
    )


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

    record = active_store.create(status="queued")
    rid = record.id
    active_runner: Runner = runner if runner is not None else FakeRunner()
    # Snapshot before starting the worker so POST always returns queued
    # (avoids a race when delayMs=0 finishes instantly).
    initial = record.snapshot(include_events=False)

    def _worker() -> None:
        try:
            active_store.update_status(rid, "running")
            result = execute_run(
                workflow,
                runner=active_runner,
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
