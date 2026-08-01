import { expect, test } from "@playwright/test";

import { cursorStubDraft, gotoWithDraft } from "./support";

test.use({ viewport: { width: 1440, height: 900 } });

/**
 * Phase 31 — Cursor stubbed in CI.
 *
 * ``MITOS_CURSOR_CLI`` points at ``e2e/stubs/cursor-agent(.cmd|.sh)`` so this
 * never spends real Cursor tokens. Manual real-CLI smoke stays in the README.
 */
test("stubbed Cursor Skill run completes without a real CLI", async ({
  page,
}) => {
  test.setTimeout(60_000);

  await gotoWithDraft(page, cursorStubDraft("Hello from input"));
  await expect(page.getByTestId("connection-status")).toHaveClass(
    /status-connected/,
    { timeout: 15_000 },
  );
  await expect(
    page.locator('.react-flow__node[data-id="skill-1"]'),
  ).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    await dialog.accept();
  });

  await page.getByTestId("palette-run-workflow").click();
  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "completed",
    { timeout: 25_000 },
  );
  await expect(page.getByTestId("run-stopped-banner")).toHaveCount(0);

  // Activity surfaces Cursor capture / model when the stub completes.
  await expect(page.getByTestId("activity-cursor-model")).toContainText(
    "composer-2.5",
  );
  await expect(page.getByTestId("activity-cursor-capture")).toBeVisible();
  await expect(
    page.locator('.react-flow__node[data-id="skill-1"]'),
  ).toHaveClass(/run-state-completed/);
  await expect(
    page.locator('.react-flow__node[data-id="output-1"]'),
  ).toHaveClass(/run-state-completed/);
});
