"""Phase 19 — Basic KB resources without embeddings."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain import Workflow
from mitos_api.domain.library import AssetKind, LibraryImportRequest, LibraryPreviewRequest
from mitos_api.services.kb.retrieval import (
    chunk_document,
    retrieve_cited_chunks,
    tokenize,
)
from mitos_api.services.library.service import confirm_import, preview_import
from mitos_api.services.library.store import LibraryStore
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest
from mitos_api.services.runners.base import Runner
from mitos_api.services.runs import execute_run
from mitos_api.services.scheduler import (
    collect_attached_knowledge_bases,
)

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


def test_tokenize_drops_stopwords():
    tokens = tokenize("The Mitos Flow joins wait for all inputs")
    assert "mitos" in tokens
    assert "flow" in tokens
    assert "joins" in tokens
    assert "the" not in tokens
    assert "for" not in tokens


def test_chunk_document_splits_paragraphs():
    chunks = chunk_document(
        kb_node_id="kb-1",
        kb_label="Docs",
        content="First paragraph about widgets.\n\nSecond paragraph about modules.",
    )
    assert [c.chunk_id for c in chunks] == ["kb-1:c0", "kb-1:c1"]
    assert chunks[0].text.startswith("First")
    assert chunks[1].text.startswith("Second")


def test_retrieve_returns_cited_chunks_for_relevant_query():
    workflow = _load("kb_one_skill.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    attached = collect_attached_knowledge_bases(skill, workflow)
    assert [kb.kbNodeId for kb in attached] == ["kb-product"]

    chunks = retrieve_cited_chunks(
        attached,
        "What is Mitos Flow and how do joins work?",
    )
    assert len(chunks) >= 1
    assert all(c.kbNodeId == "kb-product" for c in chunks)
    assert all(c.citation.startswith("Product docs#") for c in chunks)
    assert all(c.chunkId.startswith("kb-product:c") for c in chunks)
    assert all(c.score > 0 for c in chunks)
    # Relevant paragraphs should rank above the unrelated gardening tip.
    assert any("Mitos Flow" in c.text or "wait-for-all" in c.text for c in chunks)


def test_kb_one_skill_runner_and_trace():
    workflow = _load("kb_one_skill.json")
    recorder: Runner = RecordingKbRunner()
    events: list[dict] = []

    def on_event(event_type, *, node_id=None, message=None, knowledge_chunks=None, **_):
        events.append(
            {
                "type": event_type.value if hasattr(event_type, "value") else event_type,
                "nodeId": node_id,
                "message": message,
                "knowledgeChunks": list(knowledge_chunks or []),
            }
        )

    result = execute_run(workflow, runner=recorder, on_event=on_event)

    assert result.status == "completed"
    assert len(recorder.requests) == 1
    chunks = recorder.requests[0].knowledgeChunks
    assert len(chunks) >= 1
    assert all(c.citation for c in chunks)

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["kb-product"].state.value == "completed"
    assert by_id["skill-1"].knowledgeChunks == chunks
    assert "::kb[" in (by_id["skill-1"].output or "")
    assert "Product docs#" in (by_id["skill-1"].output or "")

    skill_completed = [
        e
        for e in events
        if e["nodeId"] == "skill-1" and e["type"] == "completed"
    ]
    assert len(skill_completed) == 1
    assert "Retrieved" in (skill_completed[0]["message"] or "")
    assert len(skill_completed[0]["knowledgeChunks"]) == len(chunks)


def test_attachment_isolation_between_skills():
    workflow = _load("kb_isolation.json")
    recorder: Runner = RecordingKbRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert len(recorder.requests) == 2

    req_a = next(r for r in recorder.requests if r.skillNodeId == "skill-a")
    req_b = next(r for r in recorder.requests if r.skillNodeId == "skill-b")

    assert req_a.knowledgeChunks
    assert all(c.kbNodeId == "kb-alpha" for c in req_a.knowledgeChunks)
    assert all("beta" not in c.text.lower() or "never mentions beta" in c.text.lower()
               for c in req_a.knowledgeChunks)
    # Alpha skill must not see beta KB chunks.
    assert all(c.kbNodeId != "kb-beta" for c in req_a.knowledgeChunks)

    assert req_b.knowledgeChunks
    assert all(c.kbNodeId == "kb-beta" for c in req_b.knowledgeChunks)
    assert all(c.kbNodeId != "kb-alpha" for c in req_b.knowledgeChunks)

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["kb-alpha"].state.value == "completed"
    assert by_id["kb-beta"].state.value == "completed"


def test_many_kbs_one_skill_deduped_and_ordered():
    workflow = _load("many_kbs_one_skill.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    attached = collect_attached_knowledge_bases(skill, workflow)
    assert [kb.kbNodeId for kb in attached] == ["kb-a", "kb-b"]
    assert len(attached) == 2  # duplicate edge collapsed

    recorder: Runner = RecordingKbRunner()
    result = execute_run(workflow, runner=recorder)
    assert result.status == "completed"
    chunks = recorder.requests[0].knowledgeChunks
    kb_ids = {c.kbNodeId for c in chunks}
    assert kb_ids == {"kb-a", "kb-b"}
    citations = [c.citation for c in chunks]
    assert any(c.startswith("Pricing#") for c in citations)
    assert any(c.startswith("Shipping#") for c in citations)


def test_unattached_kb_is_skipped():
    data = json.loads((FIXTURES / "simple_linear.json").read_text(encoding="utf-8"))
    data["nodes"].append(
        {
            "id": "kb-orphan",
            "kind": "knowledgeBase",
            "label": "Orphan",
            "position": {"x": 0, "y": 200},
            "settings": {
                "description": "unused",
                "content": "Secret orphan facts about unicorns.",
            },
        }
    )
    workflow = Workflow.model_validate(data)
    result = execute_run(workflow)
    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["kb-orphan"].state.value == "skipped"
    assert by_id["skill-1"].knowledgeChunks == []
    assert "::kb[" not in (by_id["skill-1"].output or "")


def test_import_kb_txt_and_md(tmp_path: Path):
    store = LibraryStore(root=tmp_path / "lib")
    txt = (FIXTURES / "valid_kb.txt").read_text(encoding="utf-8")
    md = (FIXTURES / "valid_kb.md").read_text(encoding="utf-8")

    preview_txt = preview_import(
        LibraryPreviewRequest(filename="overview.txt", content=txt),
        store=store,
    )
    assert preview_txt.ok
    assert preview_txt.kind == AssetKind.KNOWLEDGE_BASE
    assert preview_txt.name == "overview"

    imported_txt = confirm_import(
        LibraryImportRequest(filename="overview.txt", content=txt),
        store=store,
    )
    assert imported_txt.ok and imported_txt.asset is not None
    assert imported_txt.asset.manifest.kind is AssetKind.KNOWLEDGE_BASE
    assert "Mitos Flow" in imported_txt.asset.manifest.body

    preview_md = preview_import(
        LibraryPreviewRequest(
            filename="handbook.md",
            content=md,
            kind=AssetKind.KNOWLEDGE_BASE,
        ),
        store=store,
    )
    assert preview_md.ok
    assert preview_md.kind == AssetKind.KNOWLEDGE_BASE

    imported_md = confirm_import(
        LibraryImportRequest(
            filename="handbook.md",
            content=md,
            kind=AssetKind.KNOWLEDGE_BASE,
        ),
        store=store,
    )
    assert imported_md.ok and imported_md.asset is not None
    assert (store.root / "kb" / imported_md.asset.manifest.id / "original.md").exists()

    listed = store.list_assets()
    kinds = {a.kind for a in listed}
    assert AssetKind.KNOWLEDGE_BASE in kinds


def test_txt_cannot_import_as_rules():
    preview = preview_import(
        LibraryPreviewRequest(
            filename="notes.txt",
            content="hello world",
            kind=AssetKind.RULES,
        )
    )
    assert preview.ok is False
    assert preview.errors[0].code == "kind_extension_mismatch"
