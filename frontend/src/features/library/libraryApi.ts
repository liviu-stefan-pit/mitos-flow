import { getApiUrl } from "../../lib/api";
import type {
  LibraryAsset,
  LibraryBatchImportResponse,
  LibraryImportRequest,
  LibraryImportResponse,
  LibraryListResponse,
  LibraryPreviewRequest,
  LibraryPreviewResponse,
} from "../../domain/library";

export class LibraryApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "LibraryApiError";
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

/** Preview a Markdown skill/rules file without writing to the library. */
export async function previewLibraryFile(
  request: LibraryPreviewRequest,
): Promise<LibraryPreviewResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/library/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new LibraryApiError("Could not reach the backend to preview the file.");
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new LibraryApiError(
      detail || `Preview failed (${response.status}).`,
      response.status,
    );
  }

  return parseJson<LibraryPreviewResponse>(response);
}

/** Confirm import into the managed local library. */
export async function importLibraryFile(
  request: LibraryImportRequest,
): Promise<LibraryImportResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/library/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new LibraryApiError("Could not reach the backend to import the file.");
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new LibraryApiError(
      detail || `Import failed (${response.status}).`,
      response.status,
    );
  }

  return parseJson<LibraryImportResponse>(response);
}

/** Import multiple files (one Skill + multiple Rules gate). */
export async function importLibraryBatch(
  files: LibraryImportRequest[],
): Promise<LibraryBatchImportResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/library/import/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
  } catch {
    throw new LibraryApiError("Could not reach the backend to import files.");
  }

  if (!response.ok) {
    throw new LibraryApiError(`Batch import failed (${response.status}).`, response.status);
  }

  return parseJson<LibraryBatchImportResponse>(response);
}

export async function listLibraryAssets(): Promise<LibraryListResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/library`);
  } catch {
    throw new LibraryApiError("Could not reach the backend to list library assets.");
  }

  if (!response.ok) {
    throw new LibraryApiError(`List library failed (${response.status}).`, response.status);
  }

  return parseJson<LibraryListResponse>(response);
}

export async function getLibraryAsset(assetId: string): Promise<LibraryAsset> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}/api/library/${encodeURIComponent(assetId)}`);
  } catch {
    throw new LibraryApiError("Could not reach the backend to load the asset.");
  }

  if (!response.ok) {
    throw new LibraryApiError(`Get library asset failed (${response.status}).`, response.status);
  }

  return parseJson<LibraryAsset>(response);
}

export function isLibraryMarkdownFilename(filename: string): boolean {
  const base = filename.replace(/\\/g, "/").split("/").pop() ?? filename;
  const lower = base.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".mdc") || lower.endsWith(".markdown");
}
