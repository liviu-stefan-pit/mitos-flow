import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeAll } from "vitest";
import { WorkflowCanvas } from "./WorkflowCanvas";

beforeAll(() => {
  // @xyflow/react needs ResizeObserver in jsdom
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverMock;

  // fitView uses getBoundingClientRect
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width: 800,
        height: 600,
        top: 0,
        left: 0,
        bottom: 600,
        right: 800,
        x: 0,
        y: 0,
        toJSON() {},
      };
    },
  });
});

describe("WorkflowCanvas", () => {
  it("renders the sample Input → Skill → Artifact Output graph", () => {
    render(<WorkflowCanvas />);

    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("node-input")).toHaveTextContent("User Brief");
    expect(screen.getByTestId("node-skill")).toHaveTextContent("Draft Response");
    expect(screen.getByTestId("node-output")).toHaveTextContent(
      "Pass-through Output",
    );
  });

  it("is read-only: nodes are not draggable", () => {
    const { container } = render(<WorkflowCanvas />);
    const flow = container.querySelector(".react-flow");
    expect(flow).toBeInTheDocument();

    const draggableNodes = container.querySelectorAll(
      ".react-flow__node.draggable",
    );
    expect(draggableNodes.length).toBe(0);
  });
});
