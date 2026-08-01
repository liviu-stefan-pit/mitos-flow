/**
 * Run / SSE domain types — mirrors backend (Phases 15–16, 23).
 */

import type { CursorFeatureFlags } from "./cursor";
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

export type RunnerKind = "fake" | "cursor";

export type RunnerUsage = {
  inputTokens?: number | null;
  outputTokens?: number | null;
  totalTokens?: number | null;
  source?: string | null;
};

export type CursorRunOptions = {
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
};

export type RunOptions = {
  delayMs?: number;
  nodeTimeoutMs?: number | null;
  runner?: RunnerKind;
  cursor?: CursorRunOptions | null;
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
  attachedRules?: AttachedRule[];
  knowledgeChunks?: CitedChunk[];
  knowledgeQuery?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  exitCode?: number | null;
  elapsedMs?: number | null;
  usage?: RunnerUsage | null;
};

export type AttachedRule = {
  rulesNodeId: string;
  label: string;
  content: string;
  order: number;
};

export type CitedChunk = {
  chunkId: string;
  kbNodeId: string;
  kbLabel: string;
  text: string;
  score: number;
  citation: string;
  order: number;
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
  attachedRules?: AttachedRule[];
  knowledgeChunks?: CitedChunk[];
  knowledgeQuery?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  exitCode?: number | null;
  elapsedMs?: number | null;
  usage?: RunnerUsage | null;
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
