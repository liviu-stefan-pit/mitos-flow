import { describe, it, expect } from "vitest";
import {
  DRAFT_SCHEMA_VERSION,
  clearDraft,
  draftToReactFlow,
  loadDraft,
  parseWorkflowDraft,
  saveDraft,
  toWorkflowDraft,
} from "./draftStorage";

function memoryStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  return {
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    setItem(key: string, value: string) {
      store[key] = value;
    },
    removeItem(key: string) {
      delete store[key];
    },
    _store: store,
  };
}

describe("parseWorkflowDraft", () => {
  it("accepts a valid v1 draft", () => {
    const result = parseWorkflowDraft({
      version: DRAFT_SCHEMA_VERSION,
      nodes: [
        {
          id: "input-1",
          type: "mitosInput",
          position: { x: 10, y: 20 },
          data: {
            label: "Brief",
            mediaType: "text/plain",
            content: "hello",
          },
        },
        {
          id: "skill-1",
          type: "skill",
          position: { x: 200, y: 20 },
          data: { label: "Draft", description: "summarize" },
        },
      ],
      edges: [
        {
          id: "e1",
          source: "input-1",
          target: "skill-1",
          sourceHandle: "data-out",
          targetHandle: "data-in",
          type: "dataFlow",
        },
      ],
    });

    expect(result.status).toBe("ok");
    if (result.status !== "ok") return;
    expect(result.draft.nodes).toHaveLength(2);
    expect(result.draft.edges).toHaveLength(1);
    expect(result.draft.nodes[0].data).toMatchObject({
      label: "Brief",
      content: "hello",
    });
  });

  it("rejects unsupported versions", () => {
    const result = parseWorkflowDraft({
      version: 99,
      nodes: [],
      edges: [],
    });
    expect(result.status).toBe("corrupt");
  });

  it("rejects invalid JSON shapes", () => {
    expect(parseWorkflowDraft("nope").status).toBe("corrupt");
    expect(parseWorkflowDraft({ version: 1 }).status).toBe("corrupt");
  });

  it("rejects dangling edges", () => {
    const result = parseWorkflowDraft({
      version: 1,
      nodes: [
        {
          id: "input-1",
          type: "mitosInput",
          position: { x: 0, y: 0 },
          data: { label: "Input" },
        },
      ],
      edges: [
        {
          id: "e1",
          source: "input-1",
          target: "missing",
          type: "dataFlow",
        },
      ],
    });
    expect(result.status).toBe("corrupt");
  });
});

describe("draft storage round-trip", () => {
  it("saves and loads positions and settings", () => {
    const storage = memoryStorage();
    const nodes = [
      {
        id: "output-1",
        type: "artifactOutput",
        position: { x: 40, y: 80 },
        data: { label: "Result", mode: "selector" as const },
      },
    ];
    const edges: never[] = [];

    saveDraft(nodes, edges, storage);
    const loaded = loadDraft(storage);
    expect(loaded.status).toBe("ok");
    if (loaded.status !== "ok") return;

    const restored = draftToReactFlow(loaded.draft);
    expect(restored.nodes[0].position).toEqual({ x: 40, y: 80 });
    expect(restored.nodes[0].data).toMatchObject({
      label: "Result",
      mode: "selector",
    });
  });

  it("falls back with a warning for corrupt storage", () => {
    const storage = memoryStorage({
      "mitos-flow.workflow-draft": "{not-json",
    });
    const loaded = loadDraft(storage);
    expect(loaded.status).toBe("corrupt");
    if (loaded.status !== "corrupt") return;
    expect(loaded.warning.length).toBeGreaterThan(0);
  });

  it("clearDraft removes the saved entry", () => {
    const storage = memoryStorage();
    saveDraft([], [], storage);
    clearDraft(storage);
    expect(loadDraft(storage).status).toBe("empty");
  });

  it("toWorkflowDraft strips selection-only state", () => {
    const draft = toWorkflowDraft(
      [
        {
          id: "skill-1",
          type: "skill",
          position: { x: 1, y: 2 },
          selected: true,
          data: { label: "Skill", description: "x" },
        },
      ],
      [],
    );
    expect(draft.nodes[0]).toEqual({
      id: "skill-1",
      type: "skill",
      position: { x: 1, y: 2 },
      data: { label: "Skill", description: "x", runner: "fake" },
    });
  });
});
