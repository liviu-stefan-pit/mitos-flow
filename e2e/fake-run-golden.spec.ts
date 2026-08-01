import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  goldenStoryDraft,
  gotoWithDraft,
  importLibraryFile,
} from "./support";

const REPO_ROOT = path.resolve(__dirname, "..");
const PLAYGROUND = path.join(REPO_ROOT, "playground");

test.use({ viewport: { width: 1440, height: 900 } });

/**
 * Golden fake-run story through the browser:
 * import playground assets → run a seeded wired graph → assert Activity shows
 * query, cited chunk, and attached rules.
 *
 * Topology + node bodies are seeded via localStorage draft (stable IDs/edges)
 * so the suite does not depend on React Flow drag/connect under UI overlays.
 * Asset library import is still exercised through the real UI.
 */
test("import, attach, run, and trace a workflow end to end", async ({
  page,
}) => {
  test.setTimeout(60_000);

  const queryText =
    "What is Mitos Flow and how does it handle named inputs and joins?";
  const rulesFactsPath = path.join(
    PLAYGROUND,
    "rules",
    "no-invented-facts.mdc",
  );
  const rulesStructurePath = path.join(
    PLAYGROUND,
    "rules",
    "prefer-explicit-structure.mdc",
  );
  const kbPath = path.join(PLAYGROUND, "kb", "product-overview.md");

  // Bodies after frontmatter — same content the library apply path would set.
  const rulesFactsBody = readFileSync(rulesFactsPath, "utf8")
    .replace(/^---[\s\S]*?---\s*/, "")
    .trim();
  const rulesStructureBody = readFileSync(rulesStructurePath, "utf8")
    .replace(/^---[\s\S]*?---\s*/, "")
    .trim();
  const kbBody = readFileSync(kbPath, "utf8").trim();

  await gotoWithDraft(
    page,
    goldenStoryDraft({
      inputContent: queryText,
      rulesFactsContent: rulesFactsBody,
      rulesStructureContent: rulesStructureBody,
      kbContent: kbBody,
    }),
  );
  await expect(page.getByTestId("connection-status")).toHaveClass(
    /status-connected/,
    { timeout: 15_000 },
  );
  await expect(
    page.locator('.react-flow__node[data-id="skill-1"]'),
  ).toBeVisible();

  // --- Import playground assets via the Asset library UI -----------------
  await importLibraryFile(page, rulesFactsPath);
  await importLibraryFile(page, rulesStructurePath);
  await importLibraryFile(page, kbPath);

  const assetList = page.getByTestId("asset-library-list");
  await expect(assetList.getByTestId("asset-library-item-rules")).toHaveCount(
    2,
  );
  await expect(
    assetList.getByTestId("asset-library-item-knowledgeBase"),
  ).toHaveCount(1);

  // --- Run and wait for completion ---------------------------------------
  await page.getByTestId("palette-run-workflow").click();
  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "completed",
    { timeout: 20_000 },
  );
  await expect(page.getByTestId("run-stopped-banner")).toHaveCount(0);

  // Unfiltered timeline shows all events (no node selected).
  await expect(page.getByTestId("activity-knowledge-query")).toContainText(
    queryText,
  );
  await expect(page.getByTestId("activity-cited-chunk").first()).toBeVisible();
  await expect(page.getByTestId("activity-attached-rule")).toHaveCount(2);
});
