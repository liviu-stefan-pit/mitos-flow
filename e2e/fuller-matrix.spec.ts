import { expect, test } from "@playwright/test";

import { chainCompositionDraft, gotoWithDraft } from "./support";

const API = "http://localhost:8000";

test.use({ viewport: { width: 1440, height: 900 } });

/**
 * Phase 31 fuller matrix (UI spine):
 * Draft → Polish chain completes, Activity shows run summary (tokens / estimate),
 * and the run snapshot still carries nested ``fake::`` composition.
 */
test("chain composition and run summary complete in the browser", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const inputContent = "Hello from chain matrix";
  await gotoWithDraft(page, chainCompositionDraft(inputContent));
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

  // Capture the run id from the create-run response.
  const createResponsePromise = page.waitForResponse(
    (res) =>
      res.url().includes("/api/runs") &&
      res.request().method() === "POST" &&
      !res.url().includes("/cancel") &&
      !res.url().includes("/events"),
  );
  await page.getByTestId("palette-run-workflow").click();
  const createResponse = await createResponsePromise;
  const created = await createResponse.json();
  expect(created.id).toBeTruthy();

  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "completed",
    { timeout: 20_000 },
  );
  await expect(page.getByTestId("activity-run-summary")).toBeVisible();
  await expect(page.getByTestId("summary-estimated-cost")).toBeVisible();
  await expect(page.getByTestId("summary-disclaimer")).toContainText(
    /not an exact charge/i,
  );

  const snap = await request.get(`${API}/api/runs/${created.id}`);
  expect(snap.ok()).toBeTruthy();
  const body = await snap.json();
  expect(body.status).toBe("completed");
  expect(body.output).toBe(
    `fake::Polish::fake::Draft::${inputContent}`,
  );
  expect(body.summary?.costIsEstimate).toBe(true);
});
