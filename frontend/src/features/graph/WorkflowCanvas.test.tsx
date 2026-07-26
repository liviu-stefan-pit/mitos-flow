import { fireEvent, render, screen } from "@testing-library/react";
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
  it("starts with an empty canvas (no persistence yet)", () => {
    render(<WorkflowCanvas />);

    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();
    expect(screen.queryByTestId("node-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-skill")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-kb")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-rules")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-output")).not.toBeInTheDocument();
  });

  it("shows a palette with all five node kinds", () => {
    render(<WorkflowCanvas />);

    expect(screen.getByTestId("palette-add-input")).toBeInTheDocument();
    expect(screen.getByTestId("palette-add-skill")).toBeInTheDocument();
    expect(screen.getByTestId("palette-add-knowledgeBase")).toBeInTheDocument();
    expect(screen.getByTestId("palette-add-rules")).toBeInTheDocument();
    expect(screen.getByTestId("palette-add-artifactOutput")).toBeInTheDocument();
  });

  it("adds a node of each kind from the palette", () => {
    render(<WorkflowCanvas />);

    fireEvent.click(screen.getByTestId("palette-add-input"));
    expect(screen.getByTestId("node-input")).toHaveTextContent("Input");

    fireEvent.click(screen.getByTestId("palette-add-skill"));
    expect(screen.getByTestId("node-skill")).toHaveTextContent("Skill");

    fireEvent.click(screen.getByTestId("palette-add-knowledgeBase"));
    expect(screen.getByTestId("node-kb")).toHaveTextContent("Knowledge Base");

    fireEvent.click(screen.getByTestId("palette-add-rules"));
    expect(screen.getByTestId("node-rules")).toHaveTextContent("Rules");

    fireEvent.click(screen.getByTestId("palette-add-artifactOutput"));
    expect(screen.getByTestId("node-output")).toHaveTextContent(
      "Artifact Output",
    );
  });

  it("deletes the selected node when 'Delete selected' is clicked", () => {
    render(<WorkflowCanvas />);

    fireEvent.click(screen.getByTestId("palette-add-input"));
    const inputNode = screen.getByTestId("node-input");
    expect(inputNode).toBeInTheDocument();

    const deleteButton = screen.getByTestId("palette-delete-selected");
    expect(deleteButton).toBeDisabled();

    fireEvent.click(inputNode);
    expect(deleteButton).not.toBeDisabled();

    fireEvent.click(deleteButton);
    expect(screen.queryByTestId("node-input")).not.toBeInTheDocument();
  });

  it("nodes are draggable and selectable", () => {
    const { container } = render(<WorkflowCanvas />);
    fireEvent.click(screen.getByTestId("palette-add-skill"));

    const draggableNodes = container.querySelectorAll(
      ".react-flow__node.draggable",
    );
    expect(draggableNodes.length).toBeGreaterThan(0);

    const selectableNodes = container.querySelectorAll(
      ".react-flow__node.selectable",
    );
    expect(selectableNodes.length).toBeGreaterThan(0);
  });
});
