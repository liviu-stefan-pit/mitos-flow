import { getApiUrl } from "../../lib/api";
import type {
  CursorCapabilityReport,
  CursorDryRunRequest,
  CursorDryRunResponse,
} from "../../domain/cursor";

export class CursorApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "CursorApiError";
  }
}

/** Fetch the read-only Cursor CLI capability probe result. */
export async function fetchCursorCapability(): Promise<CursorCapabilityReport> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/cursor/capability`);
  } catch {
    throw new CursorApiError(
      "Could not reach the backend to probe Cursor CLI.",
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new CursorApiError(
      detail || `Cursor capability probe failed (${response.status}).`,
      response.status,
    );
  }

  return (await response.json()) as CursorCapabilityReport;
}

/** Build a redacted Cursor command preview without spawning (Phase 22). */
export async function postCursorDryRun(
  body: CursorDryRunRequest,
): Promise<CursorDryRunResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/cursor/dry-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new CursorApiError(
      "Could not reach the backend to build a Cursor dry-run preview.",
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new CursorApiError(
      detail || `Cursor dry-run failed (${response.status}).`,
      response.status,
    );
  }

  return (await response.json()) as CursorDryRunResponse;
}
