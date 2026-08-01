"""Phase 25 — Artifact Output destinations (preview + managed file)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.workflow import (
    ArtifactDestinationKind,
    ArtifactFileWriteMode,
    ArtifactOutputNodeSettings,
    Workflow,
)
from mitos_api.main import app
from mitos_api.services.artifacts import (
    ArtifactWriteError,
    get_output_root,
    resolve_under_output_root,
    set_output_root_override,
    write_artifact,
)
from mitos_api.services.runs import execute_run

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def output_root(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    set_output_root_override(root)
    yield root
    set_output_root_override(None)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _with_destination(
    workflow_data: dict,
    *,
    destination: str,
    file_path: str | None = None,
    write_mode: str = "timestamped",
    output_id: str = "output-1",
) -> Workflow:
    data = json.loads(json.dumps(workflow_data))
    for node in data["nodes"]:
        if node["id"] == output_id:
            node["settings"]["destination"] = destination
            if file_path is not None:
                node["settings"]["filePath"] = file_path
            node["settings"]["writeMode"] = write_mode
    return Workflow.model_validate(data)


# --- Path boundary unit tests -------------------------------------------------


def test_resolve_rejects_path_traversal(output_root: Path):
    with pytest.raises(ArtifactWriteError) as exc:
        resolve_under_output_root("../escape.txt", root=output_root)
    assert exc.value.code == "artifact_path_traversal"


def test_resolve_rejects_absolute_path(output_root: Path, tmp_path: Path):
    absolute = str(tmp_path / "outside.txt")
    with pytest.raises(ArtifactWriteError) as exc:
        resolve_under_output_root(absolute, root=output_root)
    assert exc.value.code in {"artifact_path_absolute", "artifact_path_traversal"}


def test_resolve_rejects_empty_path(output_root: Path):
    with pytest.raises(ArtifactWriteError) as exc:
        resolve_under_output_root("  ", root=output_root)
    assert exc.value.code == "artifact_path_required"


def test_resolve_accepts_nested_relative(output_root: Path):
    path, normalized = resolve_under_output_root(
        "reports/out.txt", root=output_root
    )
    assert normalized == "reports/out.txt"
    assert path == (output_root / "reports" / "out.txt").resolve()


# --- Atomic overwrite / timestamped ------------------------------------------


def test_overwrite_replaces_existing_bytes(output_root: Path):
    target = output_root / "reply.txt"
    target.write_text("OLD", encoding="utf-8")

    first = write_artifact(
        "NEW-CONTENT",
        relative_path="reply.txt",
        write_mode=ArtifactFileWriteMode.OVERWRITE,
        root=output_root,
    )
    assert first.relative_path == "reply.txt"
    assert target.read_text(encoding="utf-8") == "NEW-CONTENT"
    assert first.bytes_written == len("NEW-CONTENT".encode("utf-8"))

    second = write_artifact(
        "REPLACED",
        relative_path="reply.txt",
        write_mode=ArtifactFileWriteMode.OVERWRITE,
        root=output_root,
    )
    assert second.relative_path == "reply.txt"
    assert target.read_text(encoding="utf-8") == "REPLACED"


def test_timestamped_does_not_clobber_existing(output_root: Path):
    original = output_root / "reply.txt"
    original.write_text("KEEP", encoding="utf-8")

    written = write_artifact(
        "COPY",
        relative_path="reply.txt",
        write_mode=ArtifactFileWriteMode.TIMESTAMPED,
        root=output_root,
    )
    assert original.read_text(encoding="utf-8") == "KEEP"
    assert written.relative_path.startswith("reply-")
    assert written.relative_path.endswith(".txt")
    assert written.absolute_path.read_text(encoding="utf-8") == "COPY"
    assert written.absolute_path != original


# --- Run integration: preview matches upstream bytes -------------------------


def test_preview_destination_matches_upstream_bytes(output_root: Path):
    workflow = _with_destination(
        _load_fixture("simple_linear.json"),
        destination="preview",
    )
    result = execute_run(workflow)
    assert result.status == "completed"
    assert result.output == "fake::Draft::Hello from input"
    out = next(r for r in result.nodeResults if r.nodeId == "output-1")
    assert out.state.value == "completed"
    assert out.output == result.output
    assert out.artifactPath is None
    assert out.bytesWritten is None
    # Preview must not create files under the output root.
    assert list(output_root.rglob("*")) == []


def test_managed_file_overwrite_run(output_root: Path):
    workflow = _with_destination(
        _load_fixture("simple_linear.json"),
        destination="managedFile",
        file_path="saves/reply.txt",
        write_mode="overwrite",
    )
    result = execute_run(workflow)
    assert result.status == "completed"
    out = next(r for r in result.nodeResults if r.nodeId == "output-1")
    assert out.state.value == "completed"
    assert out.output == "fake::Draft::Hello from input"
    assert out.artifactPath == "saves/reply.txt"
    assert out.bytesWritten == len(out.output.encode("utf-8"))
    saved = output_root / "saves" / "reply.txt"
    assert saved.read_text(encoding="utf-8") == out.output
    assert out.artifactAbsolutePath == str(saved.resolve())


def test_managed_file_path_traversal_fails_run(output_root: Path):
    workflow = _with_destination(
        _load_fixture("simple_linear.json"),
        destination="managedFile",
        file_path="../escape.txt",
        write_mode="overwrite",
    )
    result = execute_run(workflow)
    assert result.status == "failed"
    out = next(r for r in result.nodeResults if r.nodeId == "output-1")
    assert out.state.value == "failed"
    assert out.error is not None
    assert "outside" in out.error.lower() or "traversal" in out.error.lower()
    assert not (output_root.parent / "escape.txt").exists()


def test_managed_file_requires_filepath_in_settings():
    with pytest.raises(ValueError, match="filePath"):
        ArtifactOutputNodeSettings(
            mode="pass-through",
            destination=ArtifactDestinationKind.MANAGED_FILE,
            filePath=None,
        )


def test_api_run_writes_managed_file(output_root: Path):
    assert get_output_root() == output_root.resolve()
    body = {
        "workflow": _with_destination(
            _load_fixture("simple_linear.json"),
            destination="managedFile",
            file_path="api-out.txt",
            write_mode="overwrite",
        ).model_dump(mode="json"),
        "options": {"delayMs": 0},
    }
    create = client.post("/api/runs", json=body)
    assert create.status_code == 200
    run_id = create.json()["id"]
    # Poll until terminal (delayMs=0 should finish quickly).
    snapshot = None
    for _ in range(50):
        snapshot = client.get(f"/api/runs/{run_id}").json()
        if snapshot["status"] in {"completed", "failed", "cancelled", "rejected"}:
            break
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    out = next(r for r in snapshot["nodeResults"] if r["nodeId"] == "output-1")
    assert out["artifactPath"] == "api-out.txt"
    assert (output_root / "api-out.txt").read_text(encoding="utf-8") == out["output"]
