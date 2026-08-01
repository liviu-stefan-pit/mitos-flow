import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

import {
  E2E_CURSOR_STUB,
  E2E_CURSOR_WORKSPACE,
  E2E_LIBRARY_ROOT,
  E2E_OUTPUT_ROOT,
} from "./env";

const REPO_ROOT = path.resolve(__dirname, "..");

/**
 * Phase 31 — Playwright regression suite (extends Phase 20.5).
 *
 * Chromium only. Cursor is stubbed via ``MITOS_CURSOR_CLI`` so CI never spends
 * real tokens. Boots ``npm run dev:e2e`` against isolated library/output roots.
 */
export default defineConfig({
  testDir: __dirname,
  timeout: 45_000,
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
    // --reload subprocess does not reliably forward env overrides below.
    command: "npm run dev:e2e",
    cwd: REPO_ROOT,
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      MITOS_LIBRARY_ROOT: E2E_LIBRARY_ROOT,
      MITOS_OUTPUT_ROOT: E2E_OUTPUT_ROOT,
      MITOS_CURSOR_CLI: E2E_CURSOR_STUB,
      MITOS_CURSOR_WORKSPACE_ROOT: E2E_CURSOR_WORKSPACE,
    },
  },
});
