import { describe, it, expect } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { uiGraphToDomainWorkflow } from "./toDomainWorkflow";

function sampleUiGraph(): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [
    {
      id: "input-1",
      type: "mitosInput",
      position: { x: 10, y: 20 },
      data: {
        label: "Brief",
        mediaType: "application/json",
        content: '{"topic":"launch"}',
      },
    },
    {
      id: "skill-1",
      type: "skill",
      position: { x: 220, y: 20 },
      data: { label: "Writer", description: "Draft launch notes" },
    },
    {
      id: "kb-1",
      type: "knowledgeBase",
      position: { x: 220, y: 160 },
      data: { label: "Docs", description: "Product handbook" },
    },
    {
      id: "rules-1",
      type: "rules",
      position: { x: 40, y: 160 },
      data: {
        label: "Tone",
        description: "Stay concise",
        content: "Prefer short sentences.",
      },
    },
    {
      id: "output-1",
      type: "artifactOutput",
      position: { x: 440, y: 20 },
      data: { label: "Result", mode: "selector" },
    },
  ];

  const edges: Edge[] = [
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
    {
      id: "e3",
      type: "resourceAttachment",
      source: "kb-1",
      target: "skill-1",
      sourceHandle: "resource-out",
      targetHandle: "resource-in",
    },
    {
      id: "e4",
      type: "resourceAttachment",
      source: "rules-1",
      target: "skill-1",
      sourceHandle: "resource-out",
      targetHandle: "resource-in",
    },
  ];

  return { nodes, edges };
}

describe("uiGraphToDomainWorkflow", () => {
  it("maps UI graph settings into the shared domain model without loss", () => {
    const { nodes, edges } = sampleUiGraph();
    const result = uiGraphToDomainWorkflow(nodes, edges, {
      name: "Round-trip sample",
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.workflow.metadata).toEqual({
      name: "Round-trip sample",
      schemaVersion: 1,
    });

    const byId = Object.fromEntries(
      result.workflow.nodes.map((node) => [node.id, node]),
    );

    expect(byId["input-1"].settings).toEqual({
      mediaType: "application/json",
      content: '{"topic":"launch"}',
    });
    expect(byId["skill-1"].settings).toEqual({
      description: "Draft launch notes",
      joinPolicy: "wait_for_all",
      runner: "fake",
    });
    expect(byId["kb-1"].settings).toEqual({
      description: "Product handbook",
      content: "",
      libraryAssetId: null,
    });
    expect(byId["rules-1"].settings).toEqual({
      description: "Stay concise",
      content: "Prefer short sentences.",
      libraryAssetId: null,
    });
    expect(byId["output-1"].settings).toEqual({ mode: "selector" });

    expect(result.workflow.edges).toHaveLength(4);
    expect(result.workflow.edges[0]).toMatchObject({
      kind: "dataFlow",
      sourceNodeId: "input-1",
      targetNodeId: "skill-1",
      sourcePortId: "data-out",
      targetPortId: "data-in",
    });
    expect(result.workflow.edges[0].settings).toBeNull();
    // Resource edges get default retrieval controls when edge data is absent.
    const kbEdge = result.workflow.edges.find(
      (edge) => edge.sourceNodeId === "kb-1",
    );
    expect(kbEdge?.settings).toEqual({ topK: 5, threshold: 0 });
  });

  it("maps per-attachment topK and threshold from KB resource edge data", () => {
    const { nodes, edges } = sampleUiGraph();
    const withControls = edges.map((edge) =>
      edge.id === "e3"
        ? { ...edge, data: { topK: 2, threshold: 1.5 } }
        : edge,
    );
    const result = uiGraphToDomainWorkflow(nodes, withControls);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const kbEdge = result.workflow.edges.find(
      (edge) => edge.sourceNodeId === "kb-1",
    );
    expect(kbEdge?.settings).toEqual({ topK: 2, threshold: 1.5 });
  });

  it("rejects unknown node types instead of dropping settings", () => {
    const result = uiGraphToDomainWorkflow(
      [
        {
          id: "x-1",
          type: "unknownType",
          position: { x: 0, y: 0 },
          data: { label: "X" },
        },
      ],
      [],
    );

    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toContain("Unknown node type");
  });
});
