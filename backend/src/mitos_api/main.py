import json
import os
from collections.abc import Iterator

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from mitos_api.domain import (
    CancelRunResponse,
    CursorCapabilityReport,
    CursorDryRunRequest,
    CursorDryRunResponse,
    CursorModelsReport,
    FlowExportPreviewResponse,
    FlowExportRequest,
    FlowImportResponse,
    LibraryAsset,
    LibraryBatchImportRequest,
    LibraryBatchImportResponse,
    LibraryImportRequest,
    LibraryImportResponse,
    LibraryListResponse,
    LibraryPreviewRequest,
    LibraryPreviewResponse,
    RunRequest,
    RunResponse,
    Workflow,
    WorkflowValidationResult,
    validate_workflow,
)
from mitos_api.services import cancel_run, get_run, run_store, start_run
from mitos_api.services.cursor import (
    dry_run_cursor_command,
    get_cursor_capability,
    get_cursor_models,
)
from mitos_api.services.flow_package import (
    FlowPackageError,
    export_flow_package,
    import_flow_package,
    preview_flow_package,
)
from mitos_api.services.library import (
    confirm_import,
    get_library_asset,
    import_batch,
    list_library,
    preview_import,
)
from mitos_api.services.library.service import allowed_upload_extension

app = FastAPI(title="Mitos Flow API", version="0.1.0")

extra_origins = os.getenv("CORS_ORIGINS", "").split(",")
extra_origins = [o.strip() for o in extra_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=extra_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/cursor/capability", response_model=CursorCapabilityReport)
def cursor_capability() -> CursorCapabilityReport:
    """
    Read-only Cursor CLI capability probe (Phase 21).

    Locates the CLI, runs ``--version`` / ``--help`` only (no user prompts),
    and reports discovered features from help text.
    """
    return get_cursor_capability()


@app.get("/api/cursor/models", response_model=CursorModelsReport)
def cursor_models() -> CursorModelsReport:
    """
    List Cursor CLI models via ``agent --list-models`` (Phase 24.5).

    Filters out ``auto``. Always includes default ``composer-2.5``.
    Never runs user prompts.
    """
    return get_cursor_models()


@app.post("/api/cursor/dry-run", response_model=CursorDryRunResponse)
def cursor_dry_run(body: CursorDryRunRequest) -> CursorDryRunResponse:
    """
    Build a Cursor CLI command preview from a Skill request (Phase 22).

    Returns redacted argv + stdin and enforces workspace boundary checks.
    Never spawns the CLI (``spawned`` is always false).
    """
    return dry_run_cursor_command(body)


@app.post("/api/workflows/validate", response_model=WorkflowValidationResult)
def validate_workflow_endpoint(workflow: Workflow) -> WorkflowValidationResult:
    """Validate a workflow document. Does not save or execute."""
    return validate_workflow(workflow)


@app.post("/api/workflows/export/preview", response_model=FlowExportPreviewResponse)
def export_workflow_preview_endpoint(body: FlowExportRequest) -> FlowExportPreviewResponse:
    """
    Inventory preview for a planned ``.flow`` export (Phase 30).

    Returns member paths, per-asset sizes, and size/sensitivity warnings
    without writing a zip. Bundle contents of a subsequent export should
    match this preview's ``memberPaths``.
    """
    try:
        return preview_flow_package(body)
    except FlowPackageError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": exc.message}
        ) from exc


@app.post("/api/workflows/export")
def export_workflow_endpoint(body: FlowExportRequest) -> Response:
    """
    Export a workflow as a versioned ``.flow`` zip (Phases 29–30).

    Packaging modes:
    - ``reference`` — graph + manifests + checksums (no source docs)
    - ``snapshot`` — also embeds Skill/Rules ``original.*``
    - ``embedded`` — also embeds KB source documents
    """
    try:
        zip_bytes, _referenced, _warnings = export_flow_package(body)
    except FlowPackageError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    name = (body.workflow.metadata.name or "workflow").strip() or "workflow"
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)[:80]
    filename = f"{safe}.flow"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/workflows/import", response_model=FlowImportResponse)
async def import_workflow_endpoint(
    file: UploadFile = File(...),
) -> FlowImportResponse:
    """
    Import a ``.flow`` zip (Phases 29–30).

    Validates archive paths, sizes, format version, packaging-mode original
    rules, and checksums before restoring library assets. Returns the
    workflow graph.
    """
    archive_bytes = await file.read()
    return import_flow_package(archive_bytes)


@app.post("/api/runs", response_model=RunResponse)
def create_run(request: RunRequest) -> RunResponse:
    """
    Start a workflow run (fake or Cursor runner).

    Returns immediately with status ``queued`` (or ``rejected``). Subscribe to
    ``GET /api/runs/{id}/events`` for live progress (Phase 15).
    Phase 23: set ``options.runner`` to ``cursor`` with confirmed Cursor options
    to spawn the CLI for Input → Skill → Output.
    """
    return start_run(request.workflow, options=request.options)


@app.get("/api/runs/{run_id}", response_model=RunResponse)
def get_run_endpoint(run_id: str) -> RunResponse:
    """Return the current snapshot for a run (including event log)."""
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.post("/api/runs/{run_id}/cancel", response_model=CancelRunResponse)
def cancel_run_endpoint(run_id: str) -> CancelRunResponse:
    """Request cancellation of an in-flight run (Phase 16)."""
    result = cancel_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    record = run_store.get(run_id)
    return CancelRunResponse(
        id=result.id,
        status=result.status,
        cancelRequested=bool(record and record.cancel_requested),
    )


@app.get("/api/runs/{run_id}/events")
def run_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """
    Server-Sent Events stream for a run (Phase 15).

    Replays events after ``Last-Event-ID`` so reconnect does not duplicate
    events the client already processed (including terminal run events).
    """
    if run_store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    def event_stream() -> Iterator[str]:
        for event in run_store.subscribe(run_id, last_event_id=last_event_id):
            if getattr(request, "is_disconnected", None):
                # Best-effort; TestClient may not set this.
                pass
            payload = event.model_dump(mode="json")
            yield f"id: {event.id}\nevent: {event.type.value}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Phase 17: managed Skill / Rules library ---------------------------------


def _reject_disallowed_filename(filename: str) -> None:
    if not allowed_upload_extension(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                "Only Markdown skill/rule files (.md, .mdc, .markdown) and "
                "Knowledge Base files (.txt, .md) can be imported."
            ),
        )


@app.post("/api/library/preview", response_model=LibraryPreviewResponse)
def library_preview(request: LibraryPreviewRequest) -> LibraryPreviewResponse:
    """Parse and normalize a file without writing to the managed library."""
    _reject_disallowed_filename(request.filename)
    return preview_import(request)


@app.post("/api/library/import", response_model=LibraryImportResponse)
def library_import(request: LibraryImportRequest) -> LibraryImportResponse:
    """Confirm import: preserve original + write normalized manifest."""
    _reject_disallowed_filename(request.filename)
    return confirm_import(request)


@app.post("/api/library/import/batch", response_model=LibraryBatchImportResponse)
def library_import_batch(
    request: LibraryBatchImportRequest,
) -> LibraryBatchImportResponse:
    """Import one Skill + multiple Rules (or any mix) in a single request."""
    for file_req in request.files:
        _reject_disallowed_filename(file_req.filename)
    return import_batch(request)


@app.get("/api/library", response_model=LibraryListResponse)
def library_list() -> LibraryListResponse:
    """List assets in the managed local library."""
    return list_library()


@app.get("/api/library/{asset_id}", response_model=LibraryAsset)
def library_get(asset_id: str) -> LibraryAsset:
    """Return original content + normalized manifest for one asset."""
    asset = get_library_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Library asset not found")
    return asset
