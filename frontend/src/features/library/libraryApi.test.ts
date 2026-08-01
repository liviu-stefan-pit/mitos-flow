import { describe, it, expect, vi, afterEach } from "vitest";
import {
  importLibraryBatch,
  importLibraryFile,
  isLibraryImportFilename,
  isLibraryMarkdownFilename,
  listLibraryAssets,
  previewLibraryFile,
} from "./libraryApi";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const skillContent = `---
name: draft-brief
description: Draft a concise project brief.
---

# Draft brief
`;

describe("libraryApi", () => {
  it("recognizes skill/rule/KB import filenames", () => {
    expect(isLibraryMarkdownFilename("SKILL.md")).toBe(true);
    expect(isLibraryMarkdownFilename("rules.mdc")).toBe(true);
    expect(isLibraryImportFilename("notes.txt")).toBe(true);
    expect(isLibraryImportFilename("notes.docx")).toBe(false);
  });

  it("previews a skill file via POST /api/library/preview", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        kind: "skill",
        name: "draft-brief",
        description: "Draft a concise project brief.",
        body: "# Draft brief\n",
        originalContent: skillContent,
        originalFilename: "SKILL.md",
        errors: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await previewLibraryFile({
      filename: "SKILL.md",
      content: skillContent,
    });

    expect(result.ok).toBe(true);
    expect(result.name).toBe("draft-brief");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/library/preview"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("confirms import via POST /api/library/import", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        asset: {
          originalContent: skillContent,
          manifest: {
            id: "abc",
            kind: "skill",
            name: "draft-brief",
            description: "Draft a concise project brief.",
            originalFilename: "SKILL.md",
            importedAt: "2026-07-29T00:00:00Z",
            frontmatter: { name: "draft-brief" },
            body: "# Draft brief\n",
          },
        },
        errors: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await importLibraryFile({
      filename: "SKILL.md",
      content: skillContent,
    });
    expect(result.ok).toBe(true);
    expect(result.asset?.manifest.name).toBe("draft-brief");
  });

  it("imports one skill and multiple rules via batch endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        importedCount: 3,
        failedCount: 0,
        results: [{ ok: true, errors: [] }, { ok: true, errors: [] }, { ok: true, errors: [] }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await importLibraryBatch([
      { filename: "SKILL.md", content: skillContent, kind: "skill" },
      { filename: "a.mdc", content: "---\ndescription: A\nalwaysApply: true\n---\nA", kind: "rules" },
      { filename: "b.mdc", content: "---\ndescription: B\nalwaysApply: true\n---\nB", kind: "rules" },
    ]);

    expect(result.importedCount).toBe(3);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/library/import/batch"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("lists library assets", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        assets: [
          {
            id: "1",
            kind: "skill",
            name: "draft-brief",
            description: "x",
            originalFilename: "SKILL.md",
            importedAt: "2026-07-29T00:00:00Z",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await listLibraryAssets();
    expect(result.assets).toHaveLength(1);
    expect(result.assets[0]?.kind).toBe("skill");
  });
});
