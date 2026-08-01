import type { NodeKind } from "./nodeKinds";

/** Artifact Output projection mode (execution comes in later phases). */
export type ArtifactOutputMode = "pass-through" | "selector" | "prompted";

/** Phase 25 — where pass-through output is delivered. */
export type ArtifactDestinationKind = "preview" | "managedFile";

/** Phase 25 — managed-file write policy under MITOS_OUTPUT_ROOT. */
export type ArtifactFileWriteMode = "overwrite" | "timestamped";

/** Phase 26 — non-LLM selector kinds. */
export type SelectorKind = "jsonPath" | "namedSection";

/** Phase 26 — behavior when a selector matches nothing. */
export type MissingDataPolicy = "skip" | "empty" | "warning" | "fail";

/** Per-Skill runner (Phase 24). */
export type SkillRunnerKind = "fake" | "cursor";

/** Phase 24.5: cheapest Composer default for Cursor Skills. */
export const DEFAULT_CURSOR_SKILL_MODEL = "composer-2.5";

export const ARTIFACT_OUTPUT_MODES: ArtifactOutputMode[] = [
  "pass-through",
  "selector",
  "prompted",
];

export const ARTIFACT_DESTINATIONS: ArtifactDestinationKind[] = [
  "preview",
  "managedFile",
];

export const ARTIFACT_FILE_WRITE_MODES: ArtifactFileWriteMode[] = [
  "overwrite",
  "timestamped",
];

export const SELECTOR_KINDS: SelectorKind[] = ["jsonPath", "namedSection"];

export const MISSING_DATA_POLICIES: MissingDataPolicy[] = [
  "skip",
  "empty",
  "warning",
  "fail",
];

export type InputNodeData = {
  label: string;
  mediaType: string;
  content: string;
};

export type SkillNodeData = {
  label: string;
  description: string;
  /** Phase 28.5: SKILL.md body applied from library. */
  content?: string;
  libraryAssetId?: string | null;
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
  /** Phase 25 — preview (default) or managed-file write. */
  destination?: ArtifactDestinationKind;
  /** Relative path under MITOS_OUTPUT_ROOT when destination is managedFile. */
  filePath?: string | null;
  writeMode?: ArtifactFileWriteMode;
  /** Phase 26 — selector kind when mode is selector. */
  selectorKind?: SelectorKind | null;
  /** Phase 26 — JSONPath or named section heading. */
  selectorExpression?: string | null;
  /** Phase 26 — missing-data policy (default fail). */
  missingDataPolicy?: MissingDataPolicy;
  /** Phase 27 — prompt template when mode is prompted. */
  promptTemplate?: string | null;
  /** Phase 27 — Fake or Cursor for the prompted projection call. */
  runner?: SkillRunnerKind;
  /** Phase 27 — Cursor model for prompted projection. */
  model?: string | null;
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
        content: "",
        libraryAssetId: null,
        runner: "fake",
        model: DEFAULT_CURSOR_SKILL_MODEL,
      };
    case "knowledgeBase":
      return { label, description: "", content: "", libraryAssetId: null };
    case "rules":
      return { label, description: "", content: "", libraryAssetId: null };
    case "artifactOutput":
      return {
        label,
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

export function isArtifactOutputMode(value: unknown): value is ArtifactOutputMode {
  return (
    value === "pass-through" || value === "selector" || value === "prompted"
  );
}

export function isArtifactDestinationKind(
  value: unknown,
): value is ArtifactDestinationKind {
  return value === "preview" || value === "managedFile";
}

export function isArtifactFileWriteMode(
  value: unknown,
): value is ArtifactFileWriteMode {
  return value === "overwrite" || value === "timestamped";
}

export function isSelectorKind(value: unknown): value is SelectorKind {
  return value === "jsonPath" || value === "namedSection";
}

export function isMissingDataPolicy(value: unknown): value is MissingDataPolicy {
  return (
    value === "skip" ||
    value === "empty" ||
    value === "warning" ||
    value === "fail"
  );
}
