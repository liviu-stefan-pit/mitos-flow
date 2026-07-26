import { getApiUrl } from "../../lib/api";
import type { Workflow, WorkflowValidationResult } from "../../domain/workflow";

export class WorkflowValidateError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "WorkflowValidateError";
  }
}

/** POST the domain workflow to `/api/workflows/validate`. */
export async function validateWorkflow(
  workflow: Workflow,
): Promise<WorkflowValidationResult> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/workflows/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workflow),
    });
  } catch {
    throw new WorkflowValidateError(
      "Could not reach the backend to validate the workflow.",
    );
  }

  if (!response.ok) {
    throw new WorkflowValidateError(
      `Validation request failed (${response.status}).`,
      response.status,
    );
  }

  return (await response.json()) as WorkflowValidationResult;
}
