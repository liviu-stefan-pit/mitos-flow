/**
 * Explicit mapping from React Flow UI shapes → shared domain Workflow (Phase 10).
 */

import type { Edge, Node } from "@xyflow/react";
import {
  defaultPortsForKind,
  defaultSettingsForKind,
  type ArtifactOutputMode,
  type EdgeKind,
  type NodeKind,
  type NodeSettings,
  type Workflow,
  type WorkflowEdge,
  type WorkflowNode,
  WORKFLOW_SCHEMA_VERSION,
} from "../../domain/workflow";
import {
  isArtifactOutputMode,
  type ArtifactOutputNodeData,
  type InputNodeData,
  type KnowledgeBaseNodeData,
  type RulesNodeData,
  type SkillNodeData,
} from "./nodeData";
import { nodeKindFromFlowType } from "./nodeKinds";

export type UiToDomainResult =
  | { ok: true; workflow: Workflow }
  | { ok: false; reason: string };

const EDGE_KINDS: ReadonlySet<string> = new Set(["dataFlow", "resourceAttachment"]);

/**
 * Map the live canvas (React Flow nodes/edges) into the shared domain model.
 * Unknown node/edge types fail the mapping instead of silently dropping settings.
 */
export function uiGraphToDomainWorkflow(
  nodes: Node[],
  edges: Edge[],
  options?: { name?: string },
): UiToDomainResult {
  const domainNodes: WorkflowNode[] = [];

  for (const node of nodes) {
    const kind = nodeKindFromFlowType(node.type);
    if (!kind) {
      return {
        ok: false,
        reason: `Unknown node type '${node.type ?? ""}' on node '${node.id}'.`,
      };
    }

    const label =
      typeof (node.data as { label?: unknown }).label === "string" &&
      (node.data as { label: string }).label.trim().length > 0
        ? (node.data as { label: string }).label
        : kind;

    domainNodes.push({
      id: node.id,
      kind,
      label,
      position: { x: node.position.x, y: node.position.y },
      ports: defaultPortsForKind(kind),
      settings: settingsFromUiData(kind, node.data),
    });
  }

  const domainEdges: WorkflowEdge[] = [];
  for (const edge of edges) {
    if (!edge.type || !EDGE_KINDS.has(edge.type)) {
      return {
        ok: false,
        reason: `Unknown or missing edge kind on edge '${edge.id}'.`,
      };
    }
    if (!edge.sourceHandle || !edge.targetHandle) {
      return {
        ok: false,
        reason: `Edge '${edge.id}' is missing source or target port handles.`,
      };
    }

    domainEdges.push({
      id: edge.id,
      kind: edge.type as EdgeKind,
      sourceNodeId: edge.source,
      targetNodeId: edge.target,
      sourcePortId: edge.sourceHandle,
      targetPortId: edge.targetHandle,
    });
  }

  return {
    ok: true,
    workflow: {
      metadata: {
        name: options?.name ?? "Untitled Workflow",
        schemaVersion: WORKFLOW_SCHEMA_VERSION,
      },
      nodes: domainNodes,
      edges: domainEdges,
    },
  };
}

function settingsFromUiData(kind: NodeKind, data: unknown): NodeSettings {
  const defaults = defaultSettingsForKind(kind);
  const record =
    typeof data === "object" && data !== null
      ? (data as Record<string, unknown>)
      : {};

  switch (kind) {
    case "input": {
      const input = record as Partial<InputNodeData>;
      return {
        mediaType:
          typeof input.mediaType === "string" && input.mediaType.length > 0
            ? input.mediaType
            : (defaults as { mediaType: string }).mediaType,
        content: typeof input.content === "string" ? input.content : "",
      };
    }
    case "skill": {
      const skill = record as Partial<SkillNodeData>;
      return {
        description:
          typeof skill.description === "string" ? skill.description : "",
        joinPolicy: "wait_for_all",
      };
    }
    case "knowledgeBase": {
      const kb = record as Partial<KnowledgeBaseNodeData>;
      return {
        description: typeof kb.description === "string" ? kb.description : "",
      };
    }
    case "rules": {
      const rules = record as Partial<RulesNodeData>;
      return {
        description:
          typeof rules.description === "string" ? rules.description : "",
        content: typeof rules.content === "string" ? rules.content : "",
        libraryAssetId:
          typeof rules.libraryAssetId === "string"
            ? rules.libraryAssetId
            : null,
      };
    }
    case "artifactOutput": {
      const output = record as Partial<ArtifactOutputNodeData>;
      const mode: ArtifactOutputMode = isArtifactOutputMode(output.mode)
        ? output.mode
        : "pass-through";
      return { mode };
    }
  }
}
