"""In-memory run store with SSE event fan-out (Phases 15–16)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.run import (
    NodeRunResult,
    RunEvent,
    RunEventScope,
    RunEventType,
    RunResponse,
    RunStatus,
)
from mitos_api.domain.workflow import AttachedRule, CitedChunk, ValidationIssue


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    id: str
    status: RunStatus
    node_results: list[NodeRunResult] = field(default_factory=list)
    errors: list[ValidationIssue] = field(default_factory=list)
    output: str | None = None
    media_type: str | None = None
    events: list[RunEvent] = field(default_factory=list)
    cancel_requested: bool = False
    terminal: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _subscribers: list[Queue] = field(default_factory=list)
    _seq: int = 0

    def snapshot(self, *, include_events: bool = True) -> RunResponse:
        with self._lock:
            return RunResponse(
                id=self.id,
                status=self.status,
                nodeResults=list(self.node_results),
                errors=list(self.errors),
                output=self.output,
                mediaType=self.media_type,
                events=list(self.events) if include_events else [],
            )


class RunStore:
    """Process-local store for live runs and their event logs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        run_id: str | None = None,
        status: RunStatus = "queued",
    ) -> RunRecord:
        rid = run_id or str(uuid.uuid4())
        record = RunRecord(id=rid, status=status)
        with self._lock:
            self._runs[rid] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()

    def request_cancel(self, run_id: str) -> RunRecord | None:
        record = self.get(run_id)
        if record is None:
            return None
        with record._lock:
            if record.terminal:
                return record
            record.cancel_requested = True
        return record

    def is_cancel_requested(self, run_id: str) -> bool:
        record = self.get(run_id)
        if record is None:
            return False
        with record._lock:
            return record.cancel_requested

    def append_event(
        self,
        run_id: str,
        *,
        event_type: RunEventType,
        scope: RunEventScope,
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
    ) -> RunEvent | None:
        record = self.get(run_id)
        if record is None:
            return None

        with record._lock:
            # Never re-emit a terminal run-scoped event (reconnect safety).
            if scope is RunEventScope.RUN and event_type in (
                RunEventType.COMPLETED,
                RunEventType.FAILED,
                RunEventType.CANCELLED,
            ):
                for existing in record.events:
                    if (
                        existing.scope is RunEventScope.RUN
                        and existing.type
                        in (
                            RunEventType.COMPLETED,
                            RunEventType.FAILED,
                            RunEventType.CANCELLED,
                        )
                    ):
                        return existing

            record._seq += 1
            event = RunEvent(
                id=f"{run_id}:{record._seq}",
                seq=record._seq,
                type=event_type,
                scope=scope,
                runId=run_id,
                nodeId=node_id,
                message=message,
                output=output,
                mediaType=media_type,
                error=error,
                attachedRules=list(attached_rules or []),
                knowledgeChunks=list(knowledge_chunks or []),
                knowledgeQuery=knowledge_query,
                stdout=stdout,
                stderr=stderr,
                exitCode=exit_code,
                elapsedMs=elapsed_ms,
                usage=usage,
                timestamp=_utc_now_iso(),
            )
            record.events.append(event)
            for queue in list(record._subscribers):
                queue.put(event)
            return event

    def update_status(self, run_id: str, status: RunStatus) -> None:
        record = self.get(run_id)
        if record is None:
            return
        with record._lock:
            record.status = status

    def set_results(
        self,
        run_id: str,
        *,
        status: RunStatus,
        node_results: list[NodeRunResult],
        errors: list[ValidationIssue] | None = None,
        output: str | None = None,
        media_type: str | None = None,
    ) -> None:
        record = self.get(run_id)
        if record is None:
            return
        with record._lock:
            record.status = status
            record.node_results = list(node_results)
            record.errors = list(errors or [])
            record.output = output
            record.media_type = media_type
            if status in ("completed", "failed", "cancelled", "rejected"):
                record.terminal = True
                for queue in list(record._subscribers):
                    queue.put(None)

    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> Iterator[RunEvent]:
        """
        Yield events for a run, replaying from after ``last_event_id``.

        Terminal run events are never duplicated on reconnect when the client
        passes Last-Event-ID; each stored event is yielded at most once per
        subscription.
        """
        record = self.get(run_id)
        if record is None:
            return iter(())

        queue: Queue = Queue()
        with record._lock:
            after_seq = 0
            if last_event_id:
                for event in record.events:
                    if event.id == last_event_id:
                        after_seq = event.seq
                        break
            replay = [e for e in record.events if e.seq > after_seq]
            already_terminal = record.terminal
            record._subscribers.append(queue)

        def _generate() -> Iterator[RunEvent]:
            try:
                for event in replay:
                    yield event
                if already_terminal:
                    return
                while True:
                    try:
                        item = queue.get(timeout=0.5)
                    except Empty:
                        current = self.get(run_id)
                        if current is None:
                            return
                        with current._lock:
                            if current.terminal:
                                return
                        continue
                    if item is None:
                        return
                    yield item
            finally:
                with record._lock:
                    if queue in record._subscribers:
                        record._subscribers.remove(queue)

        return _generate()

    def event_callback(self, run_id: str) -> Callable[..., Any]:
        """Return an on_event callback bound to this store/run."""

        def _emit(
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
        ) -> None:
            self.append_event(
                run_id,
                event_type=event_type,
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
            )

        return _emit


# Process-wide default store (single-worker local dev).
run_store = RunStore()
