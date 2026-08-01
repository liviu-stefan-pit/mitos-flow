import type { NodeKind } from "./nodeKinds";

/** Artifact Output projection mode (execution comes in later phases). */
export type ArtifactOutputMode = "pass-through" | "selector" | "prompted";

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
};

export type KnowledgeBaseNodeData = {
  label: string;
  description: string;
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
      return { label, description: "" };
    case "knowledgeBase":
      return { label, description: "" };
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
