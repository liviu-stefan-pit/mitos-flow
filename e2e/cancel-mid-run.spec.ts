import { expect, test } from "@playwright/test";

import { cancelChainDraft, gotoWithDraft } from "./support";

test.use({ viewport: { width: 1440, height: 900 } });

/**
 * Cancel mid-run on a seeded Input→Skill→Skill→Output chain: cancel as soon
 * as Cancel is enabled (during the live delay window) and assert the
 * downstream Skill never completes.
 */
test("cancel mid-run stops before the downstream skill completes", async ({
  page,
}) => {
  await gotoWithDraft(page, cancelChainDraft());
  await expect(page.getByTestId("connection-status")).toHaveClass(
    /status-connected/,
    { timeout: 15_000 },
  );
  await expect(
    page.locator('.react-flow__node[data-id="skill-1"]'),
  ).toBeVisible();
  await expect(
    page.locator('.react-flow__node[data-id="skill-2"]'),
  ).toBeVisible();

  await page.getByTestId("palette-run-workflow").click();
  // Cancel immediately once the run is live — default delayMs (400) on Input
  // then Skill-1 gives a window before Skill-2 can complete.
  await expect(page.getByTestId("palette-cancel-run")).toBeEnabled({
    timeout: 5_000,
  });
  await page.getByTestId("palette-cancel-run").click();

  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "cancelled",
    { timeout: 10_000 },
  );
  await expect(page.getByTestId("run-stopped-banner")).toBeVisible();

  await expect(
    page.locator('.react-flow__node[data-id="skill-2"]'),
  ).not.toHaveClass(/run-state-completed/);
  await expect(
    page.locator('.react-flow__node[data-id="output-1"]'),
  ).not.toHaveClass(/run-state-completed/);
});
