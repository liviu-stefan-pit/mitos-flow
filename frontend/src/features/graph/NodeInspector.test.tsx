import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { NodeInspector } from "./NodeInspector";
import * as libraryApi from "../library/libraryApi";

vi.mock("../library/libraryApi", async () => {
  const actual = await vi.importActual<typeof libraryApi>("../library/libraryApi");
  return {
    ...actual,
    listLibraryAssets: vi.fn(),
    getLibraryAsset: vi.fn(),
  };
});

const mockedList = vi.mocked(libraryApi.listLibraryAssets);
const mockedGet = vi.mocked(libraryApi.getLibraryAsset);

beforeEach(() => {
  mockedList.mockResolvedValue({ assets: [] });
  mockedGet.mockReset();
});

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

describe("NodeInspector — Skill runner (Phase 24)", () => {
  it("selects Fake or Cursor runner for the Skill only", () => {
    const onUpdateData = vi.fn();
    const node: Node = {
      id: "skill-1",
      type: "skill",
      selected: true,
      position: { x: 0, y: 0 },
      data: { label: "Draft", description: "", runner: "fake" },
    };

    render(
      <NodeInspector
        node={node}
        nodes={[node]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(screen.getByTestId("inspector-runner-fake")).toBeChecked();
    expect(screen.queryByTestId("inspector-cursor-model")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inspector-runner-cursor"));
    expect(onUpdateData).toHaveBeenCalledWith("skill-1", {
      runner: "cursor",
      model: "composer-2.5",
    });
  });
});

describe("NodeInspector — Cursor model (Phase 24.5)", () => {
  it("shows model picker when Cursor is selected and hides it for Fake", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "available",
          models: [
            { id: "composer-2.5", label: "composer-2.5" },
            { id: "gpt-5.2", label: "GPT-5.2" },
          ],
          defaultModel: "composer-2.5",
          message: "ok",
        }),
      }),
    );

    const onUpdateData = vi.fn();
    const { rerender } = render(
      <NodeInspector
        node={{
          id: "skill-1",
          type: "skill",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Draft",
            description: "",
            runner: "cursor",
            model: "composer-2.5",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    const select = await screen.findByTestId("inspector-cursor-model");
    expect(select).toHaveValue("composer-2.5");

    fireEvent.change(select, { target: { value: "gpt-5.2" } });
    expect(onUpdateData).toHaveBeenCalledWith("skill-1", { model: "gpt-5.2" });

    rerender(
      <NodeInspector
        node={{
          id: "skill-1",
          type: "skill",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Draft",
            description: "",
            runner: "fake",
            model: "composer-2.5",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("inspector-cursor-model")).not.toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});

describe("NodeInspector — Artifact destinations (Phase 25)", () => {
  it("shows file path and write mode only for managed-file destination", () => {
    const onUpdateData = vi.fn();
    const { rerender } = render(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Save",
            mode: "pass-through",
            destination: "preview",
            filePath: null,
            writeMode: "timestamped",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(screen.getByTestId("inspector-output-destination")).toHaveValue(
      "preview",
    );
    expect(
      screen.queryByTestId("inspector-output-filepath"),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("inspector-output-destination"), {
      target: { value: "managedFile" },
    });
    expect(onUpdateData).toHaveBeenCalledWith("output-1", {
      destination: "managedFile",
    });

    rerender(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Save",
            mode: "pass-through",
            destination: "managedFile",
            filePath: "out.txt",
            writeMode: "overwrite",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(screen.getByTestId("inspector-output-filepath")).toHaveValue(
      "out.txt",
    );
    expect(screen.getByTestId("inspector-output-writemode")).toHaveValue(
      "overwrite",
    );
  });
});

describe("NodeInspector — Deterministic selectors (Phase 26)", () => {
  it("shows selector fields when mode is selector", () => {
    const onUpdateData = vi.fn();
    render(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Extract",
            mode: "selector",
            destination: "preview",
            selectorKind: "jsonPath",
            selectorExpression: "$.output.headline",
            missingDataPolicy: "fail",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(screen.getByTestId("inspector-selector-kind")).toHaveValue(
      "jsonPath",
    );
    expect(screen.getByTestId("inspector-selector-expression")).toHaveValue(
      "$.output.headline",
    );
    expect(screen.getByTestId("inspector-missing-data-policy")).toHaveValue(
      "fail",
    );

    fireEvent.change(screen.getByTestId("inspector-selector-expression"), {
      target: { value: "$.output.title" },
    });
    expect(onUpdateData).toHaveBeenCalledWith("output-1", {
      selectorExpression: "$.output.title",
    });
  });

  it("hides selector fields for pass-through mode", () => {
    render(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Out",
            mode: "pass-through",
            destination: "preview",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={vi.fn()}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(
      screen.queryByTestId("inspector-selector-kind"),
    ).not.toBeInTheDocument();
  });
});

describe("NodeInspector — Prompted projections (Phase 27)", () => {
  it("shows prompt template and runner fields when mode is prompted", () => {
    const onUpdateData = vi.fn();
    render(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Rewrite",
            mode: "prompted",
            destination: "preview",
            promptTemplate: "Rewrite as a headline",
            runner: "fake",
            model: "composer-2.5",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(screen.getByTestId("inspector-prompt-template")).toHaveValue(
      "Rewrite as a headline",
    );
    expect(screen.getByTestId("inspector-output-runner-fake")).toBeChecked();
    expect(
      screen.queryByTestId("inspector-selector-kind"),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("inspector-prompt-template"), {
      target: { value: "Make it shorter" },
    });
    expect(onUpdateData).toHaveBeenCalledWith("output-1", {
      promptTemplate: "Make it shorter",
    });
  });

  it("hides prompt fields for pass-through mode", () => {
    render(
      <NodeInspector
        node={{
          id: "output-1",
          type: "artifactOutput",
          selected: true,
          position: { x: 0, y: 0 },
          data: {
            label: "Out",
            mode: "pass-through",
            destination: "preview",
          },
        }}
        nodes={[]}
        edges={[]}
        onUpdateData={vi.fn()}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    expect(
      screen.queryByTestId("inspector-prompt-template"),
    ).not.toBeInTheDocument();
  });
});

describe("NodeInspector — Skill Apply from library (Phase 28.5)", () => {
  it("applies skill asset into label, description, and content", async () => {
    mockedList.mockResolvedValue({
      assets: [
        {
          id: "skill-asset-1",
          kind: "skill",
          name: "extract-structured",
          description: "Turn notes into JSON",
          originalFilename: "SKILL.md",
          importedAt: "2026-08-01T00:00:00Z",
        },
      ],
    });
    mockedGet.mockResolvedValue({
      originalContent: "---\nname: extract-structured\n---\n# Body",
      manifest: {
        id: "skill-asset-1",
        kind: "skill",
        name: "extract-structured",
        description: "Turn notes into JSON",
        frontmatter: { name: "extract-structured" },
        body: "# Extract structured\n\nEmit JSON only.",
        originalFilename: "SKILL.md",
        importedAt: "2026-08-01T00:00:00Z",
      },
    });

    const onUpdateData = vi.fn();
    const node: Node = {
      id: "skill-1",
      type: "skill",
      selected: true,
      position: { x: 0, y: 0 },
      data: {
        label: "Draft",
        description: "",
        content: "",
        libraryAssetId: null,
        runner: "fake",
      },
    };

    render(
      <NodeInspector
        node={node}
        nodes={[node]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    const select = await screen.findByTestId("inspector-skill-library");
    fireEvent.change(select, { target: { value: "skill-asset-1" } });

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith("skill-asset-1");
    });
    await waitFor(() => {
      expect(onUpdateData).toHaveBeenCalledWith(
        "skill-1",
        expect.objectContaining({
          label: "extract-structured",
          description: "Turn notes into JSON",
          content: "# Extract structured\n\nEmit JSON only.",
          libraryAssetId: "skill-asset-1",
        }),
      );
    });
  });

  it("clears libraryAssetId when skill content is edited manually", () => {
    const onUpdateData = vi.fn();
    const node: Node = {
      id: "skill-1",
      type: "skill",
      selected: true,
      position: { x: 0, y: 0 },
      data: {
        label: "extract-structured",
        description: "desc",
        content: "body",
        libraryAssetId: "skill-asset-1",
        runner: "fake",
      },
    };

    render(
      <NodeInspector
        node={node}
        nodes={[node]}
        edges={[]}
        onUpdateData={onUpdateData}
        onUpdateEdgeData={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByTestId("inspector-skill-content"), {
      target: { value: "edited body" },
    });
    expect(onUpdateData).toHaveBeenCalledWith("skill-1", {
      content: "edited body",
      libraryAssetId: null,
    });
  });
});
