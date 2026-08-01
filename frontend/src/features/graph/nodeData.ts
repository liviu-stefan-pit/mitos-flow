import type { NodeKind } from "./nodeKinds";

/** Artifact Output projection mode (execution comes in later phases). */
export type ArtifactOutputMode = "pass-through" | "selector" | "prompted";

/** Per-Skill runner (Phase 24). */
export type SkillRunnerKind = "fake" | "cursor";

/** Phase 24.5: cheapest Composer default for Cursor Skills. */
export const DEFAULT_CURSOR_SKILL_MODEL = "composer-2.5";

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
  /** Phase 24.5: preferred Cursor model when runner is Cursor. */
  model?: string | null;
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
      return {
        label,
        description: "",
        runner: "fake",
        model: DEFAULT_CURSOR_SKILL_MODEL,
      };
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
