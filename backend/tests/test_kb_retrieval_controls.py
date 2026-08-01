"""Phase 20 — KB retrieval controls (top-K, threshold, query in trace)."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain import Workflow
from mitos_api.domain.workflow import AttachedKnowledgeBase, ResourceAttachmentSettings
from mitos_api.services.kb.retrieval import retrieve_cited_chunks
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest
from mitos_api.services.runners.base import Runner
from mitos_api.services.runs import execute_run
from mitos_api.services.scheduler import collect_attached_knowledge_bases

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Workflow:
    return Workflow.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


class RecordingKbRunner:
    def __init__(self) -> None:
        self.requests: list[SkillExecutionRequest] = []
        self._inner = FakeRunner()

    def execute(self, request: SkillExecutionRequest):
        self.requests.append(request)
        return self._inner.execute(request)

    def cleanup(self, skill_node_id: str) -> None:
        self._inner.cleanup(skill_node_id)


def test_collect_reads_edge_topk_and_threshold():
    workflow = _load("kb_retrieval_controls.json")
    skill_a = next(n for n in workflow.nodes if n.id == "skill-a")
    skill_b = next(n for n in workflow.nodes if n.id == "skill-b")

    attached_a = collect_attached_knowledge_bases(skill_a, workflow)
    attached_b = collect_attached_knowledge_bases(skill_b, workflow)

    assert len(attached_a) == 1
    assert attached_a[0].kbNodeId == "kb-shared"
    assert attached_a[0].topK == 1
    assert attached_a[0].threshold == 0.0

    assert len(attached_b) == 1
    assert attached_b[0].kbNodeId == "kb-shared"
    assert attached_b[0].topK == 3
    assert attached_b[0].threshold == 0.0


def test_changing_one_attachment_controls_does_not_affect_other_link():
    """Gate: changing one Skill/KB link's controls affects only that link."""
    workflow = _load("kb_retrieval_controls.json")
    recorder: Runner = RecordingKbRunner()
    events: list[dict] = []

    def on_event(event_type, *, node_id=None, message=None, knowledge_chunks=None,
                 knowledge_query=None, **_):
        events.append(
            {
                "type": event_type.value if hasattr(event_type, "value") else event_type,
                "nodeId": node_id,
                "message": message,
                "knowledgeChunks": list(knowledge_chunks or []),
                "knowledgeQuery": knowledge_query,
            }
        )

    result = execute_run(workflow, runner=recorder, on_event=on_event)
    assert result.status == "completed"
    assert len(recorder.requests) == 2

    req_a = next(r for r in recorder.requests if r.skillNodeId == "skill-a")
    req_b = next(r for r in recorder.requests if r.skillNodeId == "skill-b")

    # skill-a attachment topK=1 → exactly one chunk
    assert len(req_a.knowledgeChunks) == 1
    # skill-b attachment topK=3 → three chunks (shared KB has 4 matching paragraphs)
    assert len(req_b.knowledgeChunks) == 3
    assert all(c.kbNodeId == "kb-shared" for c in req_a.knowledgeChunks)
    assert all(c.kbNodeId == "kb-shared" for c in req_b.knowledgeChunks)

    # Mutating skill-a's edge settings must not change skill-b's result shape.
    for edge in workflow.edges:
        if edge.id == "e-res-a":
            edge.settings = ResourceAttachmentSettings(topK=2, threshold=0)

    recorder2: Runner = RecordingKbRunner()
    result2 = execute_run(workflow, runner=recorder2)
    assert result2.status == "completed"
    req_a2 = next(r for r in recorder2.requests if r.skillNodeId == "skill-a")
    req_b2 = next(r for r in recorder2.requests if r.skillNodeId == "skill-b")
    assert len(req_a2.knowledgeChunks) == 2  # changed link only
    assert len(req_b2.knowledgeChunks) == 3  # unchanged link


def test_per_attachment_topk_on_same_skill():
    workflow = _load("kb_per_attachment_topk.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    attached = collect_attached_knowledge_bases(skill, workflow)
    by_kb = {kb.kbNodeId: kb for kb in attached}
    assert by_kb["kb-pricing"].topK == 1
    assert by_kb["kb-shipping"].topK == 2

    recorder: Runner = RecordingKbRunner()
    result = execute_run(workflow, runner=recorder)
    assert result.status == "completed"
    chunks = recorder.requests[0].knowledgeChunks
    pricing = [c for c in chunks if c.kbNodeId == "kb-pricing"]
    shipping = [c for c in chunks if c.kbNodeId == "kb-shipping"]
    assert len(pricing) == 1
    assert len(shipping) == 2


def test_threshold_filters_low_score_chunks():
    attached = [
        AttachedKnowledgeBase(
            kbNodeId="kb-1",
            label="Docs",
            content=(
                "Mitos Flow widgets join wait for all.\n\n"
                "Completely unrelated gardening tip about roses."
            ),
            order=0,
            topK=5,
            threshold=2.0,
        )
    ]
    # Query overlaps strongly with first paragraph, weakly/not with second.
    chunks = retrieve_cited_chunks(
        attached,
        "Mitos Flow widgets join wait",
    )
    assert len(chunks) >= 1
    assert all(c.score > 2.0 for c in chunks)
    assert all("gardening" not in c.text.lower() for c in chunks)


def test_run_trace_includes_query_chunk_ids_and_citations():
    workflow = _load("kb_one_skill.json")
    events: list[dict] = []

    def on_event(event_type, *, node_id=None, message=None, knowledge_chunks=None,
                 knowledge_query=None, **_):
        events.append(
            {
                "type": event_type.value if hasattr(event_type, "value") else event_type,
                "nodeId": node_id,
                "message": message,
                "knowledgeChunks": list(knowledge_chunks or []),
                "knowledgeQuery": knowledge_query,
            }
        )

    result = execute_run(workflow, on_event=on_event)
    assert result.status == "completed"

    by_id = {r.nodeId: r for r in result.nodeResults}
    skill = by_id["skill-1"]
    assert skill.knowledgeQuery == "What is Mitos Flow and how do joins work?"
    assert skill.knowledgeChunks
    assert all(c.chunkId for c in skill.knowledgeChunks)
    assert all(c.citation for c in skill.knowledgeChunks)

    skill_completed = [
        e
        for e in events
        if e["nodeId"] == "skill-1" and e["type"] == "completed"
    ]
    assert len(skill_completed) == 1
    event = skill_completed[0]
    assert event["knowledgeQuery"] == skill.knowledgeQuery
    assert "Query:" in (event["message"] or "")
    assert skill.knowledgeChunks[0].chunkId in (event["message"] or "")
    assert skill.knowledgeChunks[0].citation in (event["message"] or "")


def test_lower_topk_yields_fewer_chunks():
    """Manual-check companion: lower top-K → fewer chunks in retrieval."""
    workflow = _load("kb_retrieval_controls.json")
    # Force both attachments to high topK first, then compare.
    for edge in workflow.edges:
        if edge.id == "e-res-a":
            edge.settings = ResourceAttachmentSettings(topK=4, threshold=0)
        if edge.id == "e-res-b":
            edge.settings = ResourceAttachmentSettings(topK=4, threshold=0)

    high = execute_run(workflow, runner=RecordingKbRunner())
    high_a = next(
        r for r in high.nodeResults if r.nodeId == "skill-a"
    ).knowledgeChunks

    for edge in workflow.edges:
        if edge.id == "e-res-a":
            edge.settings = ResourceAttachmentSettings(topK=1, threshold=0)

    low = execute_run(workflow, runner=RecordingKbRunner())
    low_a = next(
        r for r in low.nodeResults if r.nodeId == "skill-a"
    ).knowledgeChunks

    assert len(high_a) > len(low_a)
    assert len(low_a) == 1
