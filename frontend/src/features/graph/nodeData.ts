import type { NodeKind } from "./nodeKinds";

/** Artifact Output projection mode (execution comes in later phases). */
export type ArtifactOutputMode = "pass-through" | "selector" | "prompted";

/** Per-Skill runner (Phase 24). */
export type SkillRunnerKind = "fake" | "cursor";

export const ARTIFACT_OUTPUT_MODES: ArtifactOutputMode[] = [
  "pass-through",
  "selector",
  "prompted",
];

export type InputNodeData = {
  label: string;
  mediaType: string;
  content: string;
};

export type SkillNodeData = {
  label: string;
  description: string;
  /** Phase 24: Fake or Cursor for this Skill only. */
  runner?: SkillRunnerKind;
};

export type KnowledgeBaseNodeData = {
  label: string;
  description: string;
  content: string;
  libraryAssetId?: string | null;
};

export type RulesNodeData = {
  label: string;
  description: string;
  content: string;
  libraryAssetId?: string | null;
};

export type ArtifactOutputNodeData = {
  label: string;
  mode: ArtifactOutputMode;
};

export type MitosNodeData =
  | InputNodeData
  | SkillNodeData
  | KnowledgeBaseNodeData
  | RulesNodeData
  | ArtifactOutputNodeData;

export function defaultNodeData(kind: NodeKind, label: string): MitosNodeData {
  switch (kind) {
    case "input":
      return { label, mediaType: "text/plain", content: "" };
    case "skill":
      return { label, description: "", runner: "fake" };
    case "knowledgeBase":
      return { label, description: "", content: "", libraryAssetId: null };
    case "rules":
      return { label, description: "", content: "", libraryAssetId: null };
    case "artifactOutput":
      return { label, mode: "pass-through" };
  }
}

export function isArtifactOutputMode(value: unknown): value is ArtifactOutputMode {
  return (
    value === "pass-through" || value === "selector" || value === "prompted"
  );
}
