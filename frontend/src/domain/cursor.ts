/** Cursor CLI capability probe + dry-run types (Phases 21–22). */

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

export interface CursorSkillPayload {
  skillNodeId: string;
  skillLabel: string;
  description?: string;
  inputPayload?: string;
  inputMediaType?: string;
}

export interface CursorDryRunOptions {
  executable?: string | null;
  workspace?: string | null;
  features?: CursorFeatureFlags | null;
  model?: string | null;
  apiKey?: string | null;
  timeoutMs?: number;
  force?: boolean;
  trust?: boolean;
  outputFormat?: string;
  confirmed?: boolean;
}

export interface CursorDryRunRequest {
  request: CursorSkillPayload;
  options?: CursorDryRunOptions;
}

export interface CursorCommandPreview {
  argv: string[];
  commandDisplay: string;
  stdin: string;
  stdinPreview: string;
  timeoutMs: number;
  workspace: string;
  executable: string;
}

export interface CursorDryRunResponse {
  ok: boolean;
  errors: string[];
  preview: CursorCommandPreview | null;
  confirmationRequired: boolean;
  confirmed: boolean;
  message: string;
  spawned: boolean;
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

export const DEFAULT_DRY_RUN_SKILL: CursorSkillPayload = {
  skillNodeId: "skill-dry-run",
  skillLabel: "cursor-smoke",
  description:
    "Tiny read-only Cursor smoke skill. Summarize the input in three bullets.",
  inputPayload: "Preview the redacted Cursor command before a real spawn.",
  inputMediaType: "text/plain",
};
