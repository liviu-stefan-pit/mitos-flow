import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RunEvent } from "../../domain/run";
import type { Workflow } from "../../domain/workflow";
import { useWorkflowRun } from "./useWorkflowRun";

const sampleWorkflow: Workflow = {
  metadata: { name: "Test", schemaVersion: 1 },
  nodes: [],
  edges: [],
};

type Handler = (event: RunEvent) => void;

const mocks = vi.hoisted(() => {
  let onEvent: Handler | null = null;
  const unsubscribe = vi.fn();
  return {
    getOnEvent: () => onEvent,
    setOnEvent: (handler: Handler | null) => {
      onEvent = handler;
    },
    unsubscribe,
    createRun: vi.fn(),
    cancelRun: vi.fn(),
  };
});

vi.mock("./runsApi", () => ({
  createRun: mocks.createRun,
  cancelRun: mocks.cancelRun,
  RunApiError: class extends Error {},
  subscribeToRunEvents: (
    _id: string,
    handlers: { onEvent: Handler },
  ) => {
    mocks.setOnEvent(handlers.onEvent);
    return mocks.unsubscribe;
  },
}));

beforeEach(() => {
  mocks.setOnEvent(null);
  mocks.unsubscribe.mockClear();
  mocks.createRun.mockReset();
  mocks.cancelRun.mockReset();
  mocks.createRun.mockResolvedValue({
    id: "run-1",
    status: "queued",
    nodeResults: [],
    errors: [],
  });
});

describe("useWorkflowRun", () => {
  it("applies live events without duplicating ids and closes on terminal", async () => {
    const { result } = renderHook(() => useWorkflowRun());

    await act(async () => {
      await result.current.start(sampleWorkflow, { delayMs: 10 });
    });

    expect(result.current.runId).toBe("run-1");
    expect(mocks.getOnEvent()).toBeTruthy();

    const event: RunEvent = {
      id: "run-1:1",
      seq: 1,
      type: "running",
      scope: "node",
      runId: "run-1",
      nodeId: "skill-1",
      timestamp: new Date().toISOString(),
    };

    act(() => {
      mocks.getOnEvent()?.(event);
      mocks.getOnEvent()?.(event);
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.nodeStates["skill-1"]).toBe("running");
    expect(result.current.activeEdgeNodeIds.has("skill-1")).toBe(true);

    act(() => {
      mocks.getOnEvent()?.({
        id: "run-1:2",
        seq: 2,
        type: "completed",
        scope: "run",
        runId: "run-1",
        timestamp: new Date().toISOString(),
        output: "done",
      });
    });

    await waitFor(() => {
      expect(result.current.status).toBe("completed");
      expect(result.current.isLive).toBe(false);
      expect(result.current.output).toBe("done");
      expect(mocks.unsubscribe).toHaveBeenCalled();
    });
  });

  it("surfaces rejected runs without subscribing", async () => {
    mocks.createRun.mockResolvedValueOnce({
      id: "run-2",
      status: "rejected",
      nodeResults: [],
      errors: [{ code: "unsupported_graph", message: "bad graph" }],
    });

    const { result } = renderHook(() => useWorkflowRun());
    await act(async () => {
      await result.current.start(sampleWorkflow);
    });

    expect(result.current.status).toBe("rejected");
    expect(result.current.isLive).toBe(false);
    expect(result.current.errorMessage).toBe("bad graph");
    expect(mocks.getOnEvent()).toBeNull();
  });
});
