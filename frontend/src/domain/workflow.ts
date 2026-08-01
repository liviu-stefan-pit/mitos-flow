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

/** Phase 25 — where pass-through output is delivered. */
export type ArtifactDestinationKind = "preview" | "managedFile";

/** Phase 25 — managed-file write policy under MITOS_OUTPUT_ROOT. */
export type ArtifactFileWriteMode = "overwrite" | "timestamped";

/** Phase 26 — non-LLM selector kinds. */
export type SelectorKind = "jsonPath" | "namedSection";

/** Phase 26 — behavior when a selector matches nothing. */
export type MissingDataPolicy = "skip" | "empty" | "warning" | "fail";

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
  /** Phase 28.5: SKILL.md body from managed library (optional). */
  content?: string;
  libraryAssetId?: string | null;
  joinPolicy: JoinPolicy;
  /** Phase 24: per-Skill Fake or Cursor runner. */
  runner?: "fake" | "cursor";
  /** Phase 24.5: preferred Cursor model (default composer-2.5). */
  model?: string | null;
};

/** Phase 24.5: cheapest Composer — never fall through to CLI ``auto``. */
export const DEFAULT_CURSOR_SKILL_MODEL = "composer-2.5";

export type KnowledgeBaseNodeSettings = {
  description: string;
  content: string;
  libraryAssetId?: string | null;
};

export type RulesNodeSettings = {
  description: string;
  content: string;
  libraryAssetId?: string | null;
};

export type ArtifactOutputNodeSettings = {
  mode: ArtifactOutputMode;
  destination?: ArtifactDestinationKind;
  filePath?: string | null;
  writeMode?: ArtifactFileWriteMode;
  /** Phase 26 — required when mode is selector. */
  selectorKind?: SelectorKind | null;
  selectorExpression?: string | null;
  missingDataPolicy?: MissingDataPolicy;
  /** Phase 27 — required when mode is prompted. */
  promptTemplate?: string | null;
  /** Phase 27 — Fake or Cursor for the prompted projection call. */
  runner?: "fake" | "cursor";
  /** Phase 27 — Cursor model for prompted projection (default composer-2.5). */
  model?: string | null;
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
  /** Phase 20: per KB→Skill attachment retrieval controls. */
  settings?: ResourceAttachmentSettings | null;
};

export type ResourceAttachmentSettings = {
  topK: number;
  threshold: number;
};

export const DEFAULT_KB_TOP_K = 5;
export const DEFAULT_KB_THRESHOLD = 0;

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
        { id: "resource-in-top", kind: "resource", direction: "in" },
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
      return {
        description: "",
        content: "",
        libraryAssetId: null,
        joinPolicy: "wait_for_all",
        runner: "fake",
        model: DEFAULT_CURSOR_SKILL_MODEL,
      };
    case "knowledgeBase":
      return { description: "", content: "", libraryAssetId: null };
    case "rules":
      return { description: "", content: "", libraryAssetId: null };
    case "artifactOutput":
      return {
        mode: "pass-through",
        destination: "preview",
        filePath: null,
        writeMode: "timestamped",
        selectorKind: null,
        selectorExpression: null,
        missingDataPolicy: "fail",
        promptTemplate: null,
        runner: "fake",
        model: DEFAULT_CURSOR_SKILL_MODEL,
      };
  }
}
