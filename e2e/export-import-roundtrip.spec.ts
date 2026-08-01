import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  domainWorkflowToDraft,
  goldenStoryDraft,
  gotoWithDraft,
  importLibraryFile,
} from "./support";

const REPO_ROOT = path.resolve(__dirname, "..");
const PLAYGROUND = path.join(REPO_ROOT, "playground");
const API = "http://localhost:8000";

test.use({ viewport: { width: 1440, height: 900 } });

type DomainWorkflow = {
  metadata?: { name?: string; schemaVersion?: number };
  nodes: Array<{
    id: string;
    kind: string;
    label: string;
    position: { x: number; y: number };
    settings?: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    kind: string;
    sourceNodeId: string;
    targetNodeId: string;
    sourcePortId: string;
    targetPortId: string;
    settings?: { topK?: number; threshold?: number } | null;
  }>;
};

async function exportFlow(
  request: APIRequestContext,
  workflow: DomainWorkflow,
  packagingMode: "reference" | "snapshot" | "embedded" = "embedded",
): Promise<Buffer> {
  const response = await request.post(`${API}/api/workflows/export`, {
    data: { workflow, packagingMode },
  });
  expect(response.ok()).toBeTruthy();
  return Buffer.from(await response.body());
}

async function importFlow(
  request: APIRequestContext,
  zipBytes: Buffer,
): Promise<{ ok: boolean; workflow: DomainWorkflow }> {
  const response = await request.post(`${API}/api/workflows/import`, {
    multipart: {
      file: {
        name: "portability.flow",
        mimeType: "application/zip",
        buffer: zipBytes,
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.ok).toBe(true);
  expect(body.workflow).toBeTruthy();
  return body;
}

/**
 * Phase 31 — Playwright portability story:
 * seed golden graph → fake run → export ``.flow`` → import → restore draft → re-run.
 *
 * Export/import go through the real HTTP APIs (Phases 29–30 have no canvas UI yet);
 * the browser still owns draft hydrate + Run + Activity assertions.
 */
test("export/import round-trip keeps the fake-run story green", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

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

  const rulesFactsBody = readFileSync(rulesFactsPath, "utf8")
    .replace(/^---[\s\S]*?---\s*/, "")
    .trim();
  const rulesStructureBody = readFileSync(rulesStructurePath, "utf8")
    .replace(/^---[\s\S]*?---\s*/, "")
    .trim();
  const kbBody = readFileSync(kbPath, "utf8").trim();

  const draft = goldenStoryDraft({
    inputContent: queryText,
    rulesFactsContent: rulesFactsBody,
    rulesStructureContent: rulesStructureBody,
    kbContent: kbBody,
  });

  await gotoWithDraft(page, draft);
  await expect(page.getByTestId("connection-status")).toHaveClass(
    /status-connected/,
    { timeout: 15_000 },
  );

  await importLibraryFile(page, rulesFactsPath);
  await importLibraryFile(page, rulesStructurePath);
  await importLibraryFile(page, kbPath);

  await page.getByTestId("palette-run-workflow").click();
  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "completed",
    { timeout: 20_000 },
  );
  await expect(page.getByTestId("activity-knowledge-query")).toContainText(
    queryText,
  );
  await expect(page.getByTestId("activity-attached-rule")).toHaveCount(2);

  // Resolve imported asset ids so embedded export includes manifests/originals.
  const libraryList = await request.get(`${API}/api/library`);
  expect(libraryList.ok()).toBeTruthy();
  const assets: Array<{ id: string; kind: string; name: string }> = (
    await libraryList.json()
  ).assets;
  const byName = Object.fromEntries(assets.map((a) => [a.name, a]));

  // Build domain workflow from the same draft shape the UI would export.
  const domainWorkflow: DomainWorkflow = {
    metadata: { name: "Phase 31 e2e portability", schemaVersion: 1 },
    nodes: draft.nodes.map((node) => {
      const kindByType: Record<string, string> = {
        mitosInput: "input",
        skill: "skill",
        knowledgeBase: "knowledgeBase",
        rules: "rules",
        artifactOutput: "artifactOutput",
      };
      const kind = kindByType[node.type];
      const { label, ...settings } = node.data;
      const name = String(label ?? "");
      const linked = byName[name];
      const nextSettings: Record<string, unknown> = { ...settings };
      if (linked && (kind === "rules" || kind === "knowledgeBase" || kind === "skill")) {
        nextSettings.libraryAssetId = linked.id;
      }
      return {
        id: node.id,
        kind,
        label: name || kind,
        position: node.position,
        settings: nextSettings,
      };
    }),
    edges: draft.edges.map((edge) => ({
      id: edge.id,
      kind: edge.type ?? "dataFlow",
      sourceNodeId: edge.source,
      targetNodeId: edge.target,
      sourcePortId: edge.sourceHandle ?? "data-out",
      targetPortId: edge.targetHandle ?? "data-in",
      settings: edge.data
        ? { topK: edge.data.topK, threshold: edge.data.threshold }
        : null,
    })),
  };

  const preview = await request.post(`${API}/api/workflows/export/preview`, {
    data: { workflow: domainWorkflow, packagingMode: "embedded" },
  });
  expect(preview.ok()).toBeTruthy();
  const previewBody = await preview.json();
  expect(previewBody.packagingMode).toBe("embedded");
  expect(previewBody.memberPaths).toEqual(
    expect.arrayContaining([
      "format.json",
      "workflow.json",
      "checksums.json",
    ]),
  );
  expect(previewBody.memberPaths.length).toBeGreaterThan(3);

  const zipBytes = await exportFlow(request, domainWorkflow, "embedded");
  const imported = await importFlow(request, zipBytes);
  expect(imported.workflow.nodes.map((n) => n.id).sort()).toEqual(
    domainWorkflow.nodes.map((n) => n.id).sort(),
  );

  // Fresh page context with the imported workflow as the draft.
  await gotoWithDraft(page, domainWorkflowToDraft(imported.workflow));
  await expect(page.getByTestId("connection-status")).toHaveClass(
    /status-connected/,
    { timeout: 15_000 },
  );
  await expect(
    page.locator('.react-flow__node[data-id="skill-1"]'),
  ).toBeVisible();

  await page.getByTestId("palette-run-workflow").click();
  await expect(page.getByTestId("activity-run-status")).toHaveText(
    "completed",
    { timeout: 20_000 },
  );
  await expect(page.getByTestId("activity-knowledge-query")).toContainText(
    queryText,
  );
  await expect(page.getByTestId("activity-cited-chunk").first()).toBeVisible();
  await expect(page.getByTestId("activity-attached-rule")).toHaveCount(2);
  await expect(page.getByTestId("activity-run-summary")).toBeVisible();
});
