import { useCallback, useEffect, useRef, useState } from "react";

import type {
  NodeRunState,
  RunEvent,
  RunOptions,
  RunStatus,
  RunSummary,
} from "../../domain/run";
import { DEFAULT_LIVE_DELAY_MS } from "../../domain/run";
import type { Workflow } from "../../domain/workflow";
import {
  cancelRun,
  createRun,
  RunApiError,
  subscribeToRunEvents,
} from "./runsApi";

export type WorkflowRunState = {
  runId: string | null;
  status: RunStatus | "idle";
  events: RunEvent[];
  nodeStates: Record<string, NodeRunState>;
  activeEdgeNodeIds: Set<string>;
  output: string | null;
  errorMessage: string | null;
  isLive: boolean;
  summary: RunSummary | null;
};

const initialState: WorkflowRunState = {
  runId: null,
  status: "idle",
  events: [],
  nodeStates: {},
  activeEdgeNodeIds: new Set(),
  output: null,
  errorMessage: null,
  isLive: false,
  summary: null,
};

function applyEvent(
  prev: WorkflowRunState,
  event: RunEvent,
): WorkflowRunState {
  // Deduplicate by event id (reconnect safety).
  if (prev.events.some((existing) => existing.id === event.id)) {
    return prev;
  }

  const events = [...prev.events, event];
  const nodeStates = { ...prev.nodeStates };
  let status = prev.status;
  let output = prev.output;
  let errorMessage = prev.errorMessage;
  let summary = prev.summary;
  const activeEdgeNodeIds = new Set(prev.activeEdgeNodeIds);

  if (event.scope === "run") {
    if (event.type === "queued") status = "queued";
    if (event.type === "running") status = "running";
    if (event.type === "completed") {
      status = "completed";
      output = event.output ?? output;
      activeEdgeNodeIds.clear();
      if (event.summary) summary = event.summary;
    }
    if (event.type === "failed") {
      status = "failed";
      errorMessage = event.error ?? event.message ?? "Run failed";
      activeEdgeNodeIds.clear();
      if (event.summary) summary = event.summary;
    }
    if (event.type === "cancelled") {
      status = "cancelled";
      errorMessage = event.message ?? "Run cancelled";
      activeEdgeNodeIds.clear();
      if (event.summary) summary = event.summary;
    }
  }

  if (event.scope === "node" && event.nodeId) {
    const map: Record<string, NodeRunState> = {
      queued: "queued",
      running: "running",
      completed: "completed",
      failed: "failed",
      skipped: "skipped",
      blocked: "blocked",
      cancelled: "cancelled",
      timeout: "timeout",
    };
    const nextState = map[event.type];
    if (nextState) {
      nodeStates[event.nodeId] = nextState;
    }
    if (event.type === "running") {
      activeEdgeNodeIds.add(event.nodeId);
    }
    if (
      event.type === "completed" ||
      event.type === "failed" ||
      event.type === "skipped" ||
      event.type === "blocked" ||
      event.type === "cancelled" ||
      event.type === "timeout"
    ) {
      activeEdgeNodeIds.delete(event.nodeId);
    }
  }

  return {
    ...prev,
    events,
    nodeStates,
    status,
    output,
    errorMessage,
    activeEdgeNodeIds,
    summary,
  };
}

export function useWorkflowRun() {
  const [state, setState] = useState<WorkflowRunState>(initialState);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  const reset = useCallback(() => {
    unsubscribeRef.current?.();
    unsubscribeRef.current = null;
    setState(initialState);
  }, []);

  useEffect(() => {
    return () => {
      unsubscribeRef.current?.();
    };
  }, []);

  const start = useCallback(
    async (workflow: Workflow, options?: RunOptions) => {
      unsubscribeRef.current?.();
      unsubscribeRef.current = null;
      setState({
        ...initialState,
        status: "queued",
        isLive: true,
      });

      try {
        const created = await createRun(workflow, {
          delayMs: DEFAULT_LIVE_DELAY_MS,
          ...options,
        });

        if (created.status === "rejected") {
          setState({
            ...initialState,
            status: "rejected",
            errorMessage:
              created.errors[0]?.message ?? "Workflow rejected for execution.",
            isLive: false,
          });
          return created;
        }

        setState((prev) => ({
          ...prev,
          runId: created.id,
          status: "queued",
          isLive: true,
        }));

        unsubscribeRef.current = subscribeToRunEvents(created.id, {
          onEvent: (event) => {
            const terminal =
              event.scope === "run" &&
              (event.type === "completed" ||
                event.type === "failed" ||
                event.type === "cancelled");
            setState((prev) => {
              const next = applyEvent(prev, event);
              return terminal ? { ...next, isLive: false } : next;
            });
            // Close SSE after terminal so EventSource does not reconnect-loop.
            if (terminal) {
              unsubscribeRef.current?.();
              unsubscribeRef.current = null;
            }
          },
          onError: () => {
            // EventSource may error when the stream ends; ignore if we already
            // closed after a terminal event.
          },
        });

        return created;
      } catch (error) {
        const message =
          error instanceof RunApiError
            ? error.message
            : "Failed to start run.";
        setState({
          ...initialState,
          status: "failed",
          errorMessage: message,
          isLive: false,
        });
        throw error;
      }
    },
    [],
  );

  const cancel = useCallback(async () => {
    const runId = state.runId;
    if (!runId) return;
    try {
      await cancelRun(runId);
    } catch (error) {
      const message =
        error instanceof RunApiError
          ? error.message
          : "Failed to cancel run.";
      setState((prev) => ({ ...prev, errorMessage: message }));
    }
  }, [state.runId]);

  return {
    ...state,
    start,
    cancel,
    reset,
  };
}
