import json
import os
from collections.abc import Iterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from mitos_api.domain import (
    CancelRunResponse,
    RunRequest,
    RunResponse,
    Workflow,
    WorkflowValidationResult,
    validate_workflow,
)
from mitos_api.services import cancel_run, get_run, run_store, start_run

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


@app.post("/api/workflows/validate", response_model=WorkflowValidationResult)
def validate_workflow_endpoint(workflow: Workflow) -> WorkflowValidationResult:
    """Validate a workflow document. Does not save or execute."""
    return validate_workflow(workflow)


@app.post("/api/runs", response_model=RunResponse)
def create_run(request: RunRequest) -> RunResponse:
    """
    Start a workflow run (fake runner).

    Returns immediately with status ``queued`` (or ``rejected``). Subscribe to
    ``GET /api/runs/{id}/events`` for live progress (Phase 15).
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
