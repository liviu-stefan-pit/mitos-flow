/** Cursor CLI capability probe types (Phase 21). */

export type CursorCapabilityStatus =
  | "absent"
  | "available"
  | "unsupported_version"
  | "error";

export interface CursorFeatureFlags {
  printMode: boolean;
  outputFormat: boolean;
  workspace: boolean;
  force: boolean;
  model: boolean;
  listModels: boolean;
  trust: boolean;
  apiKey: boolean;
  streamPartialOutput: boolean;
}

export interface CursorCapabilityReport {
  status: CursorCapabilityStatus;
  message: string;
  executable: string | null;
  version: string | null;
  versionRaw: string | null;
  minimumVersion: string;
  helpExcerpt: string | null;
  features: CursorFeatureFlags;
}

export const FEATURE_LABELS: Record<keyof CursorFeatureFlags, string> = {
  printMode: "Print / headless mode (--print)",
  outputFormat: "Output format (--output-format)",
  workspace: "Workspace path (--workspace)",
  force: "Force / yolo (--force)",
  model: "Model selection (--model)",
  listModels: "List models (--list-models)",
  trust: "Trust workspace (--trust)",
  apiKey: "API key (--api-key)",
  streamPartialOutput: "Stream partial output",
};
