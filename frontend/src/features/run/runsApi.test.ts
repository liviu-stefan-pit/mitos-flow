import { afterEach, describe, expect, it, vi } from "vitest";

import { createRun, cancelRun, getRun } from "./runsApi";
import type { Workflow } from "../../domain/workflow";

const sampleWorkflow: Workflow = {
  metadata: { name: "Test", schemaVersion: 1 },
  nodes: [],
  edges: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("runsApi", () => {
  it("createRun posts workflow and options", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "run-1",
        status: "queued",
        nodeResults: [],
        errors: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await createRun(sampleWorkflow, { delayMs: 400 });
    expect(result.id).toBe("run-1");
    expect(result.status).toBe("queued");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/runs");
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body.options.delayMs).toBe(400);
  });

  it("cancelRun posts to cancel endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "run-1",
        status: "running",
        cancelRequested: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await cancelRun("run-1");
    expect(result.cancelRequested).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/runs/run-1/cancel");
    expect(init.method).toBe("POST");
  });

  it("getRun fetches snapshot", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "run-1",
        status: "completed",
        nodeResults: [],
        errors: [],
        output: "ok",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await getRun("run-1");
    expect(result.status).toBe("completed");
    expect(result.output).toBe("ok");
  });
});
