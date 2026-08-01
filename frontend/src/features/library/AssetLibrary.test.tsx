import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AssetLibrary } from "./AssetLibrary";
import * as libraryApi from "./libraryApi";

vi.mock("./libraryApi", async () => {
  const actual = await vi.importActual<typeof import("./libraryApi")>("./libraryApi");
  return {
    ...actual,
    listLibraryAssets: vi.fn(),
    previewLibraryFile: vi.fn(),
    importLibraryFile: vi.fn(),
  };
});

const mockedList = vi.mocked(libraryApi.listLibraryAssets);
const mockedPreview = vi.mocked(libraryApi.previewLibraryFile);
const mockedImport = vi.mocked(libraryApi.importLibraryFile);

const skillContent = `---
name: draft-brief
description: Draft a concise project brief from the supplied input.
---

# Draft brief

1. Read the input carefully.
`;

const ruleContent = `---
description: Prefer explicit types
globs: "**/*.ts"
alwaysApply: false
---

# TypeScript
`;

function mockFile(name: string, content: string): File {
  const file = new File([content], name, { type: "text/markdown" });
  if (typeof file.text !== "function") {
    Object.defineProperty(file, "text", {
      configurable: true,
      value: async () => content,
    });
  }
  return file;
}

function setInputFiles(input: HTMLElement, files: File[]) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: files,
  });
  fireEvent.change(input);
}

describe("AssetLibrary", () => {
  beforeEach(() => {
    mockedList.mockReset();
    mockedPreview.mockReset();
    mockedImport.mockReset();
    mockedList.mockResolvedValue({ assets: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders drop zone and empty library state", async () => {
    render(<AssetLibrary />);
    expect(screen.getByTestId("asset-library")).toBeInTheDocument();
    expect(screen.getByTestId("asset-library-dropzone")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/No imported skills, rules, or knowledge bases yet/i),
      ).toBeInTheDocument();
    });
  });

  it("previews a dropped skill file then confirms import", async () => {
    mockedPreview.mockResolvedValue({
      ok: true,
      kind: "skill",
      name: "draft-brief",
      description: "Draft a concise project brief from the supplied input.",
      body: "# Draft brief\n\n1. Read the input carefully.\n",
      originalContent: skillContent,
      originalFilename: "SKILL.md",
      errors: [],
    });
    mockedImport.mockResolvedValue({
      ok: true,
      asset: {
        originalContent: skillContent,
        manifest: {
          id: "skill-1",
          kind: "skill",
          name: "draft-brief",
          description: "Draft a concise project brief from the supplied input.",
          originalFilename: "SKILL.md",
          importedAt: "2026-07-29T00:00:00Z",
          frontmatter: { name: "draft-brief" },
          body: "# Draft brief\n",
        },
      },
      errors: [],
    });
    mockedList
      .mockResolvedValueOnce({ assets: [] })
      .mockResolvedValueOnce({
        assets: [
          {
            id: "skill-1",
            kind: "skill",
            name: "draft-brief",
            description: "Draft a concise project brief from the supplied input.",
            originalFilename: "SKILL.md",
            importedAt: "2026-07-29T00:00:00Z",
          },
        ],
      });

    render(<AssetLibrary />);

    const input = screen.getByTestId("asset-library-file-input");
    setInputFiles(input, [mockFile("SKILL.md", skillContent)]);

    expect(await screen.findByTestId("asset-preview-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("asset-preview-meta")).toHaveTextContent("draft-brief");
    expect(screen.getByTestId("asset-preview-confirm")).not.toBeDisabled();

    fireEvent.click(screen.getByTestId("asset-preview-confirm"));

    await waitFor(() => {
      expect(mockedImport).toHaveBeenCalledWith(
        expect.objectContaining({ filename: "SKILL.md" }),
      );
    });
    await waitFor(() => {
      expect(screen.queryByTestId("asset-preview-dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByTestId("asset-library-item-skill")).toHaveTextContent(
      "draft-brief",
    );
  });

  it("reports malformed frontmatter safely and blocks confirm", async () => {
    mockedPreview.mockResolvedValue({
      ok: false,
      errors: [
        {
          code: "malformed_frontmatter",
          message:
            "Malformed frontmatter: opening '---' found but closing '---' is missing or invalid.",
        },
      ],
    });

    render(<AssetLibrary />);
    setInputFiles(screen.getByTestId("asset-library-file-input"), [
      mockFile("SKILL.md", "---\nname: broken\n"),
    ]);

    expect(await screen.findByTestId("asset-preview-errors")).toHaveTextContent(
      /Malformed frontmatter/i,
    );
    expect(screen.getByTestId("asset-preview-confirm")).toBeDisabled();
  });

  it("imports one skill and multiple rules through sequential preview confirms", async () => {
    mockedPreview
      .mockResolvedValueOnce({
        ok: true,
        kind: "skill",
        name: "draft-brief",
        description: "Skill",
        body: "body",
        originalContent: skillContent,
        originalFilename: "SKILL.md",
        errors: [],
      })
      .mockResolvedValueOnce({
        ok: true,
        kind: "rules",
        name: "typescript-apis",
        description: "Prefer explicit types",
        body: "# TypeScript",
        originalContent: ruleContent,
        originalFilename: "typescript-apis.mdc",
        errors: [],
      })
      .mockResolvedValueOnce({
        ok: true,
        kind: "rules",
        name: "commits",
        description: "Keep commit messages concise",
        body: "# Commits",
        originalContent: ruleContent,
        originalFilename: "commits.mdc",
        errors: [],
      });

    mockedImport.mockImplementation(async (req) => ({
      ok: true,
      asset: {
        originalContent: req.content,
        manifest: {
          id: `id-${req.filename}`,
          kind: (req.kind ?? "skill") as "skill" | "rules",
          name: req.filename.replace(/\.(md|mdc)$/i, ""),
          description: "",
          originalFilename: req.filename,
          importedAt: "2026-07-29T00:00:00Z",
          frontmatter: {},
          body: "",
        },
      },
      errors: [],
    }));

    mockedList.mockResolvedValue({ assets: [] });

    render(<AssetLibrary />);

    setInputFiles(screen.getByTestId("asset-library-file-input"), [
      mockFile("SKILL.md", skillContent),
      mockFile("typescript-apis.mdc", ruleContent),
      mockFile("commits.mdc", ruleContent),
    ]);

    // Confirm skill
    expect(await screen.findByTestId("asset-preview-meta")).toHaveTextContent("draft-brief");
    fireEvent.click(screen.getByTestId("asset-preview-confirm"));

    // Confirm first rules
    await waitFor(() => {
      expect(screen.getByTestId("asset-preview-meta")).toHaveTextContent("typescript-apis");
    });
    fireEvent.click(screen.getByTestId("asset-preview-confirm"));

    // Confirm second rules
    await waitFor(() => {
      expect(screen.getByTestId("asset-preview-meta")).toHaveTextContent("commits");
    });
    fireEvent.click(screen.getByTestId("asset-preview-confirm"));

    await waitFor(() => {
      expect(mockedImport).toHaveBeenCalledTimes(3);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("asset-preview-dialog")).not.toBeInTheDocument();
    });
  });
});
