import { getApiUrl } from "../../lib/api";
import type {
  CancelRunResponse,
  RunEvent,
  RunOptions,
  RunResponse,
} from "../../domain/run";
import type { Workflow } from "../../domain/workflow";

export class RunApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "RunApiError";
  }
}

export async function createRun(
  workflow: Workflow,
  options: RunOptions = {},
): Promise<RunResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow, options }),
    });
  } catch {
    throw new RunApiError("Could not reach the backend to start a run.");
  }

  if (!response.ok) {
    throw new RunApiError(`Start run failed (${response.status}).`, response.status);
  }

  return (await response.json()) as RunResponse;
}

export async function getRun(runId: string): Promise<RunResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/runs/${runId}`);
  } catch {
    throw new RunApiError("Could not reach the backend to fetch the run.");
  }

  if (!response.ok) {
    throw new RunApiError(`Get run failed (${response.status}).`, response.status);
  }

  return (await response.json()) as RunResponse;
}

export async function cancelRun(runId: string): Promise<CancelRunResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/runs/${runId}/cancel`, {
      method: "POST",
    });
  } catch {
    throw new RunApiError("Could not reach the backend to cancel the run.");
  }

  if (!response.ok) {
    throw new RunApiError(`Cancel run failed (${response.status}).`, response.status);
  }

  return (await response.json()) as CancelRunResponse;
}

export type SubscribeHandlers = {
  onEvent: (event: RunEvent) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
};

/**
 * Subscribe to run SSE. Returns an unsubscribe function.
 * EventSource reconnects with Last-Event-ID automatically.
 */
export function subscribeToRunEvents(
  runId: string,
  handlers: SubscribeHandlers,
): () => void {
  const url = `${getApiUrl()}/api/runs/${runId}/events`;
  const source = new EventSource(url);

  const handleMessage = (message: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(message.data) as RunEvent;
      handlers.onEvent(parsed);
    } catch {
      // Ignore malformed payloads.
    }
  };

  // Named event types from the server (`event: queued`, etc.) plus default.
  const types = [
    "queued",
    "running",
    "completed",
    "failed",
    "skipped",
    "blocked",
    "cancelled",
    "timeout",
    "message",
  ];
  for (const type of types) {
    source.addEventListener(type, handleMessage as EventListener);
  }

  source.onopen = () => {
    handlers.onOpen?.();
  };
  source.onerror = (error) => {
    handlers.onError?.(error);
  };

  return () => {
    source.close();
  };
}
