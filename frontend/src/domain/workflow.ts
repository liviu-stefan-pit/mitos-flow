/**
 * Shared workflow domain types — mirrors backend Pydantic models (Phase 10).
 * JSON field names are camelCase to match the API contract.
 */

export type NodeKind =
  | "input"
  | "skill"
  | "knowledgeBase"
  | "rules"
  | "artifactOutput";

export type EdgeKind = "dataFlow" | "resourceAttachment";

export type PortKind = "data" | "resource";

export type PortDirection = "in" | "out";

export type JoinPolicy = "wait_for_all";

export type ArtifactOutputMode = "pass-through" | "selector" | "prompted";

export type Position = {
  x: number;
  y: number;
};

export type Port = {
  id: string;
  kind: PortKind;
  direction: PortDirection;
  name?: string | null;
};

export type InputNodeSettings = {
  mediaType: string;
  content: string;
};

export type SkillNodeSettings = {
  description: string;
  joinPolicy: JoinPolicy;
};

export type KnowledgeBaseNodeSettings = {
  description: string;
};

export type RulesNodeSettings = {
  description: string;
};

export type ArtifactOutputNodeSettings = {
  mode: ArtifactOutputMode;
};

export type NodeSettings =
  | InputNodeSettings
  | SkillNodeSettings
  | KnowledgeBaseNodeSettings
  | RulesNodeSettings
  | ArtifactOutputNodeSettings;

export type WorkflowNode = {
  id: string;
  kind: NodeKind;
  label: string;
  position: Position;
  ports: Port[];
  settings: NodeSettings;
};

export type WorkflowEdge = {
  id: string;
  kind: EdgeKind;
  sourceNodeId: string;
  targetNodeId: string;
  sourcePortId: string;
  targetPortId: string;
};

export type WorkflowMetadata = {
  name: string;
  schemaVersion: 1;
};

export type Workflow = {
  metadata: WorkflowMetadata;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

export type ValidationIssue = {
  code: string;
  message: string;
  nodeId?: string | null;
  edgeId?: string | null;
};

export type WorkflowValidationResult = {
  valid: boolean;
  errors: ValidationIssue[];
  workflow: Workflow | null;
};

export const WORKFLOW_SCHEMA_VERSION = 1 as const;

export function defaultPortsForKind(kind: NodeKind): Port[] {
  switch (kind) {
    case "input":
      return [{ id: "data-out", kind: "data", direction: "out" }];
    case "skill":
      return [
        { id: "data-in", kind: "data", direction: "in", name: "default" },
        { id: "data-out", kind: "data", direction: "out" },
        { id: "resource-in", kind: "resource", direction: "in" },
      ];
    case "knowledgeBase":
      return [{ id: "resource-out", kind: "resource", direction: "out" }];
    case "rules":
      return [{ id: "resource-out", kind: "resource", direction: "out" }];
    case "artifactOutput":
      return [{ id: "data-in", kind: "data", direction: "in" }];
  }
}

export function defaultSettingsForKind(kind: NodeKind): NodeSettings {
  switch (kind) {
    case "input":
      return { mediaType: "text/plain", content: "" };
    case "skill":
      return { description: "", joinPolicy: "wait_for_all" };
    case "knowledgeBase":
    case "rules":
      return { description: "" };
    case "artifactOutput":
      return { mode: "pass-through" };
  }
}
