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
