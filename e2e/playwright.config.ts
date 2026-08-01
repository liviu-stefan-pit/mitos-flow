import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

import { E2E_LIBRARY_ROOT } from "./env";

const REPO_ROOT = path.resolve(__dirname, "..");

/**
 * Phase 20.5 — slim Playwright regression suite (Chromium only for v1).
 *
 * Boots the real dev stack (`npm run dev`) against an isolated managed
 * library root so import → attach → run → trace can be exercised through the
 * actual browser UI, not mocked services.
 */
export default defineConfig({
  testDir: __dirname,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  globalSetup: path.resolve(__dirname, "global-setup.ts"),
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // `dev:e2e` runs the backend without --reload: on Windows, uvicorn's
    // --reload subprocess does not reliably forward the MITOS_LIBRARY_ROOT
    // override below, which defeats library isolation for this suite.
    command: "npm run dev:e2e",
    cwd: REPO_ROOT,
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      MITOS_LIBRARY_ROOT: E2E_LIBRARY_ROOT,
    },
  },
});
