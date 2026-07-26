import type { NodeKind } from "./nodeKinds";
import { handleKindFromId, type HandleKind } from "./handles";

/** Visual / semantic edge kinds from docs/architecture.md. */
export type EdgeKind = "dataFlow" | "resourceAttachment";

export type ConnectionValidation =
  | { ok: true; edgeKind: EdgeKind }
  | { ok: false; reason: string };

/** Allowed data-flow pairs: source → target. */
const DATA_FLOW_PAIRS: ReadonlyArray<readonly [NodeKind, NodeKind]> = [
  ["input", "skill"],
  ["skill", "skill"],
  ["skill", "artifactOutput"],
];

/** Allowed resource-attachment pairs: source → target. */
const RESOURCE_PAIRS: ReadonlyArray<readonly [NodeKind, NodeKind]> = [
  ["knowledgeBase", "skill"],
  ["rules", "skill"],
];

function pairAllowed(
  pairs: ReadonlyArray<readonly [NodeKind, NodeKind]>,
  source: NodeKind,
  target: NodeKind,
): boolean {
  return pairs.some(([s, t]) => s === source && t === target);
}

export type ValidateConnectionArgs = {
  sourceNodeId: string;
  targetNodeId: string;
  sourceKind: NodeKind | null;
  targetKind: NodeKind | null;
  sourceHandleId?: string | null;
  targetHandleId?: string | null;
};

/**
 * Pure connection validator for Phase 6.
 * Rejects self-links, unknown kinds, handle mismatches, and disallowed
 * source→target pairs. Returns the edge kind when the connection is allowed.
 */
export function validateConnection(
  args: ValidateConnectionArgs,
): ConnectionValidation {
  const {
    sourceNodeId,
    targetNodeId,
    sourceKind,
    targetKind,
    sourceHandleId,
    targetHandleId,
  } = args;

  if (sourceNodeId === targetNodeId) {
    return { ok: false, reason: "Cannot connect a node to itself." };
  }

  if (!sourceKind || !targetKind) {
    return { ok: false, reason: "Unknown node kind." };
  }

  const sourceHandle = handleKindFromId(sourceHandleId);
  const targetHandle = handleKindFromId(targetHandleId);

  // Handles are required once nodes expose typed ports; missing = invalid.
  if (!sourceHandle || !targetHandle) {
    return {
      ok: false,
      reason: "Connect a data handle to a data handle, or a resource handle to a resource handle.",
    };
  }

  if (sourceHandle !== targetHandle) {
    return {
      ok: false,
      reason: "Data ports and resource ports cannot be connected to each other.",
    };
  }

  if (sourceHandle === "data") {
    if (!pairAllowed(DATA_FLOW_PAIRS, sourceKind, targetKind)) {
      return {
        ok: false,
        reason: dataFlowRejectionReason(sourceKind, targetKind),
      };
    }
    return { ok: true, edgeKind: "dataFlow" };
  }

  // sourceHandle === "resource"
  if (!pairAllowed(RESOURCE_PAIRS, sourceKind, targetKind)) {
    return {
      ok: false,
      reason: resourceRejectionReason(sourceKind, targetKind),
    };
  }
  return { ok: true, edgeKind: "resourceAttachment" };
}

function dataFlowRejectionReason(source: NodeKind, target: NodeKind): string {
  return `Data-flow edges are only allowed from Input→Skill, Skill→Skill, or Skill→Artifact Output (got ${display(source)}→${display(target)}).`;
}

function resourceRejectionReason(source: NodeKind, target: NodeKind): string {
  return `Resource edges are only allowed from Knowledge Base→Skill or Rules→Skill (got ${display(source)}→${display(target)}).`;
}

function display(kind: NodeKind): string {
  switch (kind) {
    case "input":
      return "Input";
    case "skill":
      return "Skill";
    case "knowledgeBase":
      return "Knowledge Base";
    case "rules":
      return "Rules";
    case "artifactOutput":
      return "Artifact Output";
  }
}

/** Every source×target NodeKind pair — used by exhaustive unit tests. */
export const ALL_NODE_KINDS: readonly NodeKind[] = [
  "input",
  "skill",
  "knowledgeBase",
  "rules",
  "artifactOutput",
];

export function isAllowedDataFlowPair(
  source: NodeKind,
  target: NodeKind,
): boolean {
  return pairAllowed(DATA_FLOW_PAIRS, source, target);
}

export function isAllowedResourcePair(
  source: NodeKind,
  target: NodeKind,
): boolean {
  return pairAllowed(RESOURCE_PAIRS, source, target);
}

export type { HandleKind };
