/**
 * Run / SSE domain types — mirrors backend (Phases 15–16).
 */

import type { ValidationIssue, Workflow } from "./workflow";

export type NodeRunState =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "blocked"
  | "cancelled"
  | "timeout";

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "rejected"
  | "cancelled";

export type RunEventType =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "blocked"
  | "cancelled"
  | "timeout";

export type RunEventScope = "run" | "node";

export type RunOptions = {
  delayMs?: number;
  nodeTimeoutMs?: number | null;
};

export type RunRequest = {
  workflow: Workflow;
  options?: RunOptions;
};

export type NodeRunResult = {
  nodeId: string;
  state: NodeRunState;
  output?: string | null;
  mediaType?: string | null;
  error?: string | null;
};

export type RunEvent = {
  id: string;
  seq: number;
  type: RunEventType;
  scope: RunEventScope;
  runId: string;
  nodeId?: string | null;
  message?: string | null;
  output?: string | null;
  mediaType?: string | null;
  error?: string | null;
  timestamp: string;
};

export type RunResponse = {
  id: string;
  status: RunStatus;
  nodeResults: NodeRunResult[];
  errors: ValidationIssue[];
  output?: string | null;
  mediaType?: string | null;
  events?: RunEvent[];
};

export type CancelRunResponse = {
  id: string;
  status: RunStatus;
  cancelRequested: boolean;
};

export const DEFAULT_LIVE_DELAY_MS = 400;
