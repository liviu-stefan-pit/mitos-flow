import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mitos_api.domain import (
    RunRequest,
    RunResponse,
    Workflow,
    WorkflowValidationResult,
    validate_workflow,
)
from mitos_api.services import execute_run

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
    """Execute a supported workflow synchronously (fake runner, Phase 11)."""
    return execute_run(request.workflow)
