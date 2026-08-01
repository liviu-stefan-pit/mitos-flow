import type { Page } from "@playwright/test";

/** Matches frontend `DRAFT_STORAGE_KEY`. */
export const DRAFT_STORAGE_KEY = "mitos-flow.workflow-draft";

export type SeedDraft = {
  version: 1;
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    sourceHandle?: string | null;
    targetHandle?: string | null;
    type?: string;
    data?: { topK?: number; threshold?: number };
  }>;
};

/**
 * Seed a workflow draft into localStorage before the app boots, then navigate.
 * Avoids flaky React Flow drag/connect under corner UI panels (fitView + overlays).
 */
export async function gotoWithDraft(
  page: Page,
  draft: SeedDraft,
  path = "/",
): Promise<void> {
  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
    },
    { key: DRAFT_STORAGE_KEY, value: JSON.stringify(draft) },
  );
  await page.goto(path);
}

/** Import a real file (by absolute path) through the Asset library drop UI. */
export async function importLibraryFile(
  page: Page,
  filePath: string,
): Promise<void> {
  await page.getByTestId("asset-library-file-input").setInputFiles(filePath);
  await page.getByTestId("asset-preview-dialog").waitFor({ state: "visible" });
  await page.getByTestId("asset-preview-confirm").click();
  await page
    .getByTestId("asset-preview-dialog")
    .waitFor({ state: "hidden", timeout: 10_000 });
}

type GoldenContent = {
  inputContent: string;
  rulesFactsContent: string;
  rulesStructureContent: string;
  kbContent: string;
};

/** Golden Input→Skill→Output with two Rules + one KB resource attachments. */
export function goldenStoryDraft(content: GoldenContent): SeedDraft {
  return {
    version: 1,
    nodes: [
      {
        id: "input-1",
        type: "mitosInput",
        position: { x: 900, y: 0 },
        data: {
          label: "Brief",
          mediaType: "text/plain",
          content: content.inputContent,
        },
      },
      {
        id: "rules-facts",
        type: "rules",
        position: { x: 900, y: 300 },
        data: {
          label: "no-invented-facts",
          description: "",
          content: content.rulesFactsContent,
          libraryAssetId: null,
        },
      },
      {
        id: "rules-structure",
        type: "rules",
        position: { x: 900, y: 600 },
        data: {
          label: "prefer-explicit-structure",
          description: "",
          content: content.rulesStructureContent,
          libraryAssetId: null,
        },
      },
      {
        id: "kb-overview",
        type: "knowledgeBase",
        position: { x: 900, y: 900 },
        data: {
          label: "product-overview",
          description: "",
          content: content.kbContent,
          libraryAssetId: null,
        },
      },
      {
        id: "skill-1",
        type: "skill",
        position: { x: 1300, y: 450 },
        data: { label: "Draft", description: "" },
      },
      {
        id: "output-1",
        type: "artifactOutput",
        position: { x: 1800, y: 450 },
        data: { label: "Out", mode: "pass-through" },
      },
    ],
    edges: [
      {
        id: "e-data-1",
        source: "input-1",
        target: "skill-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
        type: "dataFlow",
      },
      {
        id: "e-data-2",
        source: "skill-1",
        target: "output-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
        type: "dataFlow",
      },
      {
        id: "e-res-facts",
        source: "rules-facts",
        target: "skill-1",
        sourceHandle: "resource-out",
        targetHandle: "resource-in",
        type: "resourceAttachment",
      },
      {
        id: "e-res-structure",
        source: "rules-structure",
        target: "skill-1",
        sourceHandle: "resource-out",
        targetHandle: "resource-in",
        type: "resourceAttachment",
      },
      {
        id: "e-res-kb",
        source: "kb-overview",
        target: "skill-1",
        sourceHandle: "resource-out",
        targetHandle: "resource-in",
        type: "resourceAttachment",
        data: { topK: 5, threshold: 0 },
      },
    ],
  };
}

/** Linear Input→Skill→Skill→Output for cancel mid-run. */
export function cancelChainDraft(
  inputContent = "Hello from cancel test",
): SeedDraft {
  return {
    version: 1,
    nodes: [
      {
        id: "input-1",
        type: "mitosInput",
        position: { x: 900, y: 450 },
        data: {
          label: "Brief",
          mediaType: "text/plain",
          content: inputContent,
        },
      },
      {
        id: "skill-1",
        type: "skill",
        position: { x: 1300, y: 450 },
        data: { label: "Draft", description: "" },
      },
      {
        id: "skill-2",
        type: "skill",
        position: { x: 1700, y: 450 },
        data: { label: "Polish", description: "" },
      },
      {
        id: "output-1",
        type: "artifactOutput",
        position: { x: 2100, y: 450 },
        data: { label: "Out", mode: "pass-through" },
      },
    ],
    edges: [
      {
        id: "e1",
        source: "input-1",
        target: "skill-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
        type: "dataFlow",
      },
      {
        id: "e2",
        source: "skill-1",
        target: "skill-2",
        sourceHandle: "data-out",
        targetHandle: "data-in",
        type: "dataFlow",
      },
      {
        id: "e3",
        source: "skill-2",
        target: "output-1",
        sourceHandle: "data-out",
        targetHandle: "data-in",
        type: "dataFlow",
      },
    ],
  };
}
