import os from "node:os";
import path from "node:path";

/**
 * Isolated managed-library root for the Playwright suite so E2E imports never
 * pollute (or get polluted by) a developer's local `.mitos-flow-library`.
 *
 * Shared between playwright.config.ts (webServer env) and global-setup.ts
 * (pre-run cleanup).
 */
export const E2E_LIBRARY_ROOT = path.join(
  os.tmpdir(),
  "mitos-flow-e2e-library",
);

/** Isolated Artifact Output root for managed-file destinations. */
export const E2E_OUTPUT_ROOT = path.join(
  os.tmpdir(),
  "mitos-flow-e2e-artifacts",
);

/** Isolated Cursor workspace root for stubbed Cursor runs. */
export const E2E_CURSOR_WORKSPACE = path.join(
  os.tmpdir(),
  "mitos-flow-e2e-cursor-workspace",
);

/**
 * Path to the Phase 31 Cursor CLI stub used by Playwright / CI.
 * Real Cursor is never required for automated E2E.
 */
export const E2E_CURSOR_STUB = path.resolve(
  __dirname,
  "stubs",
  process.platform === "win32" ? "cursor-agent.cmd" : "cursor-agent.sh",
);
