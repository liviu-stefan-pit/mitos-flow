import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from "vitest";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { DRAFT_STORAGE_KEY, DRAFT_SCHEMA_VERSION } from "./draftStorage";

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverMock;

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

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("WorkflowCanvas", () => {
  it("starts with an empty canvas when no draft is saved", () => {
    render(<WorkflowCanvas />);

    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();
    expect(screen.queryByTestId("node-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-skill")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-kb")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-rules")).not.toBeInTheDocument();
    expect(screen.queryByTestId("node-output")).not.toBeInTheDocument();
    expect(screen.getByTestId("node-inspector-empty")).toBeInTheDocument();
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

  it("opens the inspector for a selected node and edits its label", () => {
    render(<WorkflowCanvas />);

    fireEvent.click(screen.getByTestId("palette-add-skill"));
    fireEvent.click(screen.getByTestId("node-skill"));

    const inspector = screen.getByTestId("node-inspector");
    expect(within(inspector).getByTestId("inspector-kind")).toHaveTextContent(
      "Skill",
    );

    const labelInput = screen.getByTestId("inspector-label");
    fireEvent.change(labelInput, { target: { value: "Summarizer" } });

    expect(screen.getByTestId("node-skill")).toHaveTextContent("Summarizer");
    expect(labelInput).toHaveValue("Summarizer");
  });

  it("does not cross-mutate node settings when switching selection", () => {
    render(<WorkflowCanvas />);

    fireEvent.click(screen.getByTestId("palette-add-input"));
    fireEvent.click(screen.getByTestId("palette-add-skill"));

    fireEvent.click(screen.getByTestId("node-input"));
    fireEvent.change(screen.getByTestId("inspector-label"), {
      target: { value: "Brief A" },
    });
    fireEvent.change(screen.getByTestId("inspector-content"), {
      target: { value: "alpha payload" },
    });

    fireEvent.click(screen.getByTestId("node-skill"));
    fireEvent.change(screen.getByTestId("inspector-label"), {
      target: { value: "Skill B" },
    });
    fireEvent.change(screen.getByTestId("inspector-description"), {
      target: { value: "beta desc" },
    });

    expect(screen.getByTestId("node-input")).toHaveTextContent("Brief A");
    expect(screen.getByTestId("node-skill")).toHaveTextContent("Skill B");

    fireEvent.click(screen.getByTestId("node-input"));
    expect(screen.getByTestId("inspector-label")).toHaveValue("Brief A");
    expect(screen.getByTestId("inspector-content")).toHaveValue(
      "alpha payload",
    );

    fireEvent.click(screen.getByTestId("node-skill"));
    expect(screen.getByTestId("inspector-label")).toHaveValue("Skill B");
    expect(screen.getByTestId("inspector-description")).toHaveValue(
      "beta desc",
    );
  });

  it("restores a saved draft on mount", () => {
    localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({
        version: DRAFT_SCHEMA_VERSION,
        nodes: [
          {
            id: "input-restored",
            type: "mitosInput",
            position: { x: 120, y: 40 },
            data: {
              label: "Restored Input",
              mediaType: "application/json",
              content: '{"ok":true}',
            },
          },
          {
            id: "output-restored",
            type: "artifactOutput",
            position: { x: 360, y: 40 },
            data: { label: "Restored Output", mode: "prompted" },
          },
        ],
        edges: [],
      }),
    );

    render(<WorkflowCanvas />);

    expect(screen.getByTestId("node-input")).toHaveTextContent(
      "Restored Input",
    );
    expect(screen.getByTestId("node-output")).toHaveTextContent(
      "Restored Output",
    );

    fireEvent.click(screen.getByTestId("node-input"));
    expect(screen.getByTestId("inspector-media-type")).toHaveValue(
      "application/json",
    );
    expect(screen.getByTestId("inspector-content")).toHaveValue('{"ok":true}');

    fireEvent.click(screen.getByTestId("node-output"));
    expect(screen.getByTestId("inspector-output-mode")).toHaveValue("prompted");
  });

  it("shows a warning and starts empty when the draft is corrupt", () => {
    localStorage.setItem(DRAFT_STORAGE_KEY, "{not-json");

    render(<WorkflowCanvas />);

    expect(screen.getByTestId("draft-warning")).toBeInTheDocument();
    expect(screen.queryByTestId("node-input")).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "null")).toEqual(
      { version: 1, nodes: [], edges: [] },
    );
  });

  it("clears the canvas and draft after New Workflow confirmation", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<WorkflowCanvas />);
    fireEvent.click(screen.getByTestId("palette-add-skill"));
    expect(screen.getByTestId("node-skill")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("palette-new-workflow"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.queryByTestId("node-skill")).not.toBeInTheDocument();
    expect(localStorage.getItem(DRAFT_STORAGE_KEY)).toBe(
      JSON.stringify({ version: 1, nodes: [], edges: [] }),
    );
  });

  it("does not clear when New Workflow is cancelled", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<WorkflowCanvas />);
    fireEvent.click(screen.getByTestId("palette-add-input"));
    fireEvent.click(screen.getByTestId("palette-new-workflow"));

    expect(screen.getByTestId("node-input")).toBeInTheDocument();
  });

  it("clears the canvas and draft after Reset Draft confirmation", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<WorkflowCanvas />);
    fireEvent.click(screen.getByTestId("palette-add-rules"));
    fireEvent.click(screen.getByTestId("palette-reset-draft"));

    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.queryByTestId("node-rules")).not.toBeInTheDocument();
  });
});
