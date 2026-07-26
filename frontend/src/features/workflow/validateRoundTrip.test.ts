import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { uiGraphToDomainWorkflow } from "../graph/toDomainWorkflow";
import { validateWorkflow } from "./validateApi";
import type { WorkflowValidationResult } from "../../domain/workflow";

function representativeUiGraph(): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: [
      {
        id: "input-1",
        type: "mitosInput",
        position: { x: 0, y: 0 },
        data: {
          label: "Brief",
          mediaType: "text/markdown",
          content: "# Launch brief",
        },
      },
      {
        id: "skill-1",
        type: "skill",
        position: { x: 200, y: 0 },
        data: { label: "Summarize", description: "Condense the brief" },
      },
      {
        id: "output-1",
        type: "artifactOutput",
        position: { x: 400, y: 0 },
        data: { label: "Out", mode: "prompted" },
      },
    ],
    edges: [
      {
        id: "e1",
        type: "dataFlow",
        source: "input-1",
        target: "skill-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
      },
      {
        id: "e2",
        type: "dataFlow",
        source: "skill-1",
        target: "output-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
      },
    ],
  };
}

describe("schema round-trip via validate API", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("validates a representative workflow without losing settings", async () => {
    const { nodes, edges } = representativeUiGraph();
    const mapped = uiGraphToDomainWorkflow(nodes, edges, {
      name: "Representative",
    });
    expect(mapped.ok).toBe(true);
    if (!mapped.ok) return;

    const apiResponse: WorkflowValidationResult = {
      valid: true,
      errors: [],
      workflow: structuredClone(mapped.workflow),
    };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(apiResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await validateWorkflow(mapped.workflow);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/workflows/validate"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mapped.workflow),
      }),
    );

    expect(result.valid).toBe(true);
    expect(result.workflow).not.toBeNull();

    const returned = Object.fromEntries(
      result.workflow!.nodes.map((node) => [node.id, node]),
    );
    expect(returned["input-1"].settings).toEqual({
      mediaType: "text/markdown",
      content: "# Launch brief",
    });
    expect(returned["skill-1"].settings).toEqual({
      description: "Condense the brief",
      joinPolicy: "wait_for_all",
    });
    expect(returned["output-1"].settings).toEqual({ mode: "prompted" });
  });
});
