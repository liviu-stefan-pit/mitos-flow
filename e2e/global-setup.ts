import { rmSync } from "node:fs";

import { E2E_LIBRARY_ROOT } from "./env";

/**
 * Runs once before the whole Playwright suite. Best-effort: if a dev server
 * is already running (reuseExistingServer) the backend process env cannot be
 * changed retroactively, so this only guarantees isolation when Playwright
 * starts its own webServer.
 */
export default function globalSetup(): void {
  rmSync(E2E_LIBRARY_ROOT, { recursive: true, force: true });
}
