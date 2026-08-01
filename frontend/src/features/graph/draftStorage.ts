import type { Edge, Node } from "@xyflow/react";
import {
  defaultNodeData,
  isArtifactOutputMode,
  DEFAULT_CURSOR_SKILL_MODEL,
  type MitosNodeData,
} from "./nodeData";
import {
  NODE_KIND_CONFIGS,
  nodeKindFromFlowType,
} from "./nodeKinds";

/** localStorage key for the browser-local workflow draft. */
export const DRAFT_STORAGE_KEY = "mitos-flow.workflow-draft";

/** Current draft schema version. Bump when the persisted shape changes. */
export const DRAFT_SCHEMA_VERSION = 1 as const;

export type DraftNodeV1 = {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: MitosNodeData;
};

export type DraftEdgeV1 = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  type?: string;
  /** Phase 20: KB attachment retrieval controls (topK / threshold). */
  data?: {
    topK?: number;
    threshold?: number;
  };
};

export type WorkflowDraftV1 = {
  version: typeof DRAFT_SCHEMA_VERSION;
  nodes: DraftNodeV1[];
  edges: DraftEdgeV1[];
};

export type LoadDraftResult =
  | { status: "empty" }
  | { status: "ok"; draft: WorkflowDraftV1 }
  | { status: "corrupt"; warning: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function normalizeNodeData(
  flowType: string,
  raw: unknown,
): MitosNodeData | null {
  const kind = nodeKindFromFlowType(flowType);
  if (!kind) return null;

  const record = isRecord(raw) ? raw : {};
  const displayName =
    NODE_KIND_CONFIGS.find((config) => config.kind === kind)?.displayName ??
    kind;
  const label =
    typeof record.label === "string" && record.label.trim().length > 0
      ? record.label
      : displayName;

  const defaults = defaultNodeData(kind, label);

  switch (kind) {
    case "input":
      return {
        label,
        mediaType:
          typeof record.mediaType === "string" && record.mediaType.length > 0
            ? record.mediaType
            : (defaults as { mediaType: string }).mediaType,
        content: typeof record.content === "string" ? record.content : "",
      };
    case "skill":
      return {
        label,
        description:
          typeof record.description === "string" ? record.description : "",
        runner:
          record.runner === "cursor" || record.runner === "fake"
            ? record.runner
            : "fake",
        model:
          typeof record.model === "string" && record.model.trim().length > 0
            ? record.model.trim()
            : DEFAULT_CURSOR_SKILL_MODEL,
      };
    case "knowledgeBase":
      return {
        label,
        description:
          typeof record.description === "string" ? record.description : "",
        content: typeof record.content === "string" ? record.content : "",
        libraryAssetId:
          typeof record.libraryAssetId === "string"
            ? record.libraryAssetId
            : null,
      };
    case "rules":
      return {
        label,
        description:
          typeof record.description === "string" ? record.description : "",
        content: typeof record.content === "string" ? record.content : "",
        libraryAssetId:
          typeof record.libraryAssetId === "string"
            ? record.libraryAssetId
            : null,
      };
    case "artifactOutput":
      return {
        label,
        mode: isArtifactOutputMode(record.mode) ? record.mode : "pass-through",
      };
  }
}

function parseDraftNode(value: unknown): DraftNodeV1 | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || value.id.length === 0) return null;
  if (typeof value.type !== "string" || value.type.length === 0) return null;
  if (!isRecord(value.position)) return null;
  if (!isFiniteNumber(value.position.x) || !isFiniteNumber(value.position.y)) {
    return null;
  }

  const data = normalizeNodeData(value.type, value.data);
  if (!data) return null;

  return {
    id: value.id,
    type: value.type,
    position: { x: value.position.x, y: value.position.y },
    data,
  };
}

function parseDraftEdge(value: unknown): DraftEdgeV1 | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || value.id.length === 0) return null;
  if (typeof value.source !== "string" || value.source.length === 0) return null;
  if (typeof value.target !== "string" || value.target.length === 0) return null;

  let data: DraftEdgeV1["data"];
  if (isRecord(value.data)) {
    const topK =
      typeof value.data.topK === "number" &&
      Number.isFinite(value.data.topK) &&
      value.data.topK >= 1
        ? Math.floor(value.data.topK)
        : undefined;
    const threshold =
      typeof value.data.threshold === "number" &&
      Number.isFinite(value.data.threshold) &&
      value.data.threshold >= 0
        ? value.data.threshold
        : undefined;
    if (topK !== undefined || threshold !== undefined) {
      data = { topK, threshold };
    }
  }

  return {
    id: value.id,
    source: value.source,
    target: value.target,
    sourceHandle:
      typeof value.sourceHandle === "string" || value.sourceHandle === null
        ? value.sourceHandle
        : undefined,
    targetHandle:
      typeof value.targetHandle === "string" || value.targetHandle === null
        ? value.targetHandle
        : undefined,
    type: typeof value.type === "string" ? value.type : undefined,
    data,
  };
}

/** Validate and normalize a parsed JSON value into a v1 draft. */
export function parseWorkflowDraft(raw: unknown): LoadDraftResult {
  if (raw === null || raw === undefined) {
    return { status: "empty" };
  }

  if (!isRecord(raw)) {
    return {
      status: "corrupt",
      warning: "Saved draft was invalid and was discarded.",
    };
  }

  if (raw.version !== DRAFT_SCHEMA_VERSION) {
    return {
      status: "corrupt",
      warning: "Saved draft used an unsupported version and was discarded.",
    };
  }

  if (!Array.isArray(raw.nodes) || !Array.isArray(raw.edges)) {
    return {
      status: "corrupt",
      warning: "Saved draft was missing nodes or edges and was discarded.",
    };
  }

  const nodes: DraftNodeV1[] = [];
  for (const entry of raw.nodes) {
    const node = parseDraftNode(entry);
    if (!node) {
      return {
        status: "corrupt",
        warning: "Saved draft contained an invalid node and was discarded.",
      };
    }
    nodes.push(node);
  }

  const nodeIds = new Set(nodes.map((node) => node.id));
  if (nodeIds.size !== nodes.length) {
    return {
      status: "corrupt",
      warning: "Saved draft had duplicate node IDs and was discarded.",
    };
  }

  const edges: DraftEdgeV1[] = [];
  for (const entry of raw.edges) {
    const edge = parseDraftEdge(entry);
    if (!edge) {
      return {
        status: "corrupt",
        warning: "Saved draft contained an invalid edge and was discarded.",
      };
    }
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      return {
        status: "corrupt",
        warning:
          "Saved draft had an edge pointing to a missing node and was discarded.",
      };
    }
    edges.push(edge);
  }

  return {
    status: "ok",
    draft: {
      version: DRAFT_SCHEMA_VERSION,
      nodes,
      edges,
    },
  };
}

/** Serialize React Flow state into the versioned draft schema. */
export function toWorkflowDraft(
  nodes: Node[],
  edges: Edge[],
): WorkflowDraftV1 {
  return {
    version: DRAFT_SCHEMA_VERSION,
    nodes: nodes.map((node) => {
      const kind = nodeKindFromFlowType(node.type);
      const fallbackLabel =
        NODE_KIND_CONFIGS.find((config) => config.kind === kind)
          ?.displayName ?? "Node";
      const data =
        normalizeNodeData(node.type ?? "", node.data) ??
        (kind
          ? defaultNodeData(kind, fallbackLabel)
          : ({ label: fallbackLabel } as MitosNodeData));
      return {
        id: node.id,
        type: node.type ?? "",
        position: { x: node.position.x, y: node.position.y },
        data,
      };
    }),
    edges: edges.map((edge) => {
      const record =
        typeof edge.data === "object" && edge.data !== null
          ? (edge.data as Record<string, unknown>)
          : {};
      const topK =
        typeof record.topK === "number" &&
        Number.isFinite(record.topK) &&
        record.topK >= 1
          ? Math.floor(record.topK)
          : undefined;
      const threshold =
        typeof record.threshold === "number" &&
        Number.isFinite(record.threshold) &&
        record.threshold >= 0
          ? record.threshold
          : undefined;
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? null,
        targetHandle: edge.targetHandle ?? null,
        type: edge.type,
        ...(topK !== undefined || threshold !== undefined
          ? { data: { topK, threshold } }
          : {}),
      };
    }),
  };
}

export function draftToReactFlow(draft: WorkflowDraftV1): {
  nodes: Node[];
  edges: Edge[];
} {
  return {
    nodes: draft.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: { ...node.position },
      data: { ...node.data },
    })),
    edges: draft.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
      targetHandle: edge.targetHandle ?? undefined,
      type: edge.type,
      ...(edge.data ? { data: { ...edge.data } } : {}),
    })),
  };
}

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function loadDraft(
  storage: StorageLike = localStorage,
): LoadDraftResult {
  let raw: string | null;
  try {
    raw = storage.getItem(DRAFT_STORAGE_KEY);
  } catch {
    return {
      status: "corrupt",
      warning: "Could not read the saved draft; starting empty.",
    };
  }

  if (raw === null || raw === "") {
    return { status: "empty" };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {
      status: "corrupt",
      warning: "Saved draft was not valid JSON and was discarded.",
    };
  }

  return parseWorkflowDraft(parsed);
}

export function saveDraft(
  nodes: Node[],
  edges: Edge[],
  storage: StorageLike = localStorage,
): void {
  const draft = toWorkflowDraft(nodes, edges);
  storage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
}

export function clearDraft(storage: StorageLike = localStorage): void {
  storage.removeItem(DRAFT_STORAGE_KEY);
}
