import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { NodeInspector } from "./NodeInspector";

describe("NodeInspector — KB retrieval controls (Phase 20)", () => {
  it("edits top-K and threshold on the selected Skill/KB attachment only", () => {
    const nodes: Node[] = [
      {
        id: "skill-1",
        type: "skill",
        selected: true,
        position: { x: 0, y: 0 },
        data: { label: "Draft", description: "" },
      },
      {
        id: "kb-a",
        type: "knowledgeBase",
        position: { x: 0, y: 100 },
        data: { label: "Pricing", description: "", content: "" },
      },
      {
        id: "kb-b",
        type: "knowledgeBase",
        position: { x: 100, y: 100 },
        data: { label: "Shipping", description: "", content: "" },
      },
    ];
    const edges: Edge[] = [
      {
        id: "e-kb-a",
        type: "resourceAttachment",
        source: "kb-a",
        target: "skill-1",
        sourceHandle: "resource-out",
        targetHandle: "resource-in",
        data: { topK: 5, threshold: 0 },
      },
      {
        id: "e-kb-b",
        type: "resourceAttachment",
        source: "kb-b",
        target: "skill-1",
        sourceHandle: "resource-out",
        targetHandle: "resource-in",
        data: { topK: 3, threshold: 1 },
      },
    ];

    const onUpdateEdgeData = vi.fn();

    render(
      <NodeInspector
        node={nodes[0]}
        nodes={nodes}
        edges={edges}
        onUpdateData={vi.fn()}
        onUpdateEdgeData={onUpdateEdgeData}
      />,
    );

    const attachments = screen.getAllByTestId("inspector-kb-attachment");
    expect(attachments).toHaveLength(2);
    expect(attachments[0]).toHaveAttribute("data-kb-node-id", "kb-a");
    expect(attachments[1]).toHaveAttribute("data-kb-node-id", "kb-b");

    const topKInputs = screen.getAllByTestId("inspector-kb-topk");
    const thresholdInputs = screen.getAllByTestId("inspector-kb-threshold");
    expect(topKInputs[0]).toHaveValue(5);
    expect(topKInputs[1]).toHaveValue(3);
    expect(thresholdInputs[0]).toHaveValue(0);
    expect(thresholdInputs[1]).toHaveValue(1);

    fireEvent.change(topKInputs[0], { target: { value: "1" } });
    expect(onUpdateEdgeData).toHaveBeenCalledWith("e-kb-a", { topK: 1 });
    expect(onUpdateEdgeData).not.toHaveBeenCalledWith(
      "e-kb-b",
      expect.anything(),
    );

    fireEvent.change(thresholdInputs[1], { target: { value: "2.5" } });
    expect(onUpdateEdgeData).toHaveBeenCalledWith("e-kb-b", {
      threshold: 2.5,
    });
  });
});
