/** Managed local Skill/Rules library types (Phase 17). */

export type AssetKind = "skill" | "rules";

export type LibraryValidationIssue = {
  code: string;
  message: string;
  nodeId?: string | null;
  edgeId?: string | null;
};

export type LibraryAssetManifest = {
  id: string;
  kind: AssetKind;
  name: string;
  description: string;
  originalFilename: string;
  importedAt: string;
  frontmatter: Record<string, unknown>;
  body: string;
};

export type LibraryAsset = {
  manifest: LibraryAssetManifest;
  originalContent: string;
};

export type LibraryAssetSummary = {
  id: string;
  kind: AssetKind;
  name: string;
  description: string;
  originalFilename: string;
  importedAt: string;
};

export type LibraryPreviewRequest = {
  filename: string;
  content: string;
  kind?: AssetKind | null;
};

export type LibraryPreviewResponse = {
  ok: boolean;
  kind?: AssetKind | null;
  name?: string | null;
  description?: string | null;
  frontmatter?: Record<string, unknown> | null;
  body?: string | null;
  originalContent?: string | null;
  originalFilename?: string | null;
  errors: LibraryValidationIssue[];
};

export type LibraryImportRequest = {
  filename: string;
  content: string;
  kind?: AssetKind | null;
};

export type LibraryImportResponse = {
  ok: boolean;
  asset?: LibraryAsset | null;
  errors: LibraryValidationIssue[];
};

export type LibraryListResponse = {
  assets: LibraryAssetSummary[];
};

export type LibraryBatchImportResponse = {
  results: LibraryImportResponse[];
  importedCount: number;
  failedCount: number;
};

/** Pending file awaiting preview/confirm in the UI. */
export type PendingLibraryFile = {
  filename: string;
  content: string;
  kindHint?: AssetKind | null;
};
