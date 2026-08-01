import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
} from "react";
import type {
  AssetKind,
  LibraryAssetSummary,
  LibraryPreviewResponse,
  PendingLibraryFile,
} from "../../domain/library";
import {
  importLibraryFile,
  isLibraryMarkdownFilename,
  listLibraryAssets,
  LibraryApiError,
  previewLibraryFile,
} from "./libraryApi";
import "./AssetLibrary.css";

type PreviewState = {
  file: PendingLibraryFile;
  preview: LibraryPreviewResponse | null;
  loading: boolean;
  error: string | null;
};


async function readFileAsText(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () =>
      reject(reader.error ?? new Error(`Failed to read ${file.name}`));
    reader.readAsText(file);
  });
}

function inferKindHint(filename: string): AssetKind | null {
  const base = filename.replace(/\\/g, "/").split("/").pop()?.toLowerCase() ?? "";
  if (base === "skill.md") return "skill";
  if (base.endsWith(".mdc")) return "rules";
  return null;
}

export function AssetLibrary() {
  const [assets, setAssets] = useState<LibraryAssetSummary[]>([]);
  const [queue, setQueue] = useState<PendingLibraryFile[]>([]);
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const statusTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshList = useCallback(async () => {
    try {
      const result = await listLibraryAssets();
      setAssets(result.assets ?? []);
      setListError(null);
    } catch (err) {
      const message =
        err instanceof LibraryApiError
          ? err.message
          : "Could not load the asset library.";
      setListError(message);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLibraryAssets();
        if (!cancelled) {
          setAssets(result.assets ?? []);
          setListError(null);
        }
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof LibraryApiError
            ? err.message
            : "Could not load the asset library.";
        setListError(message);
      }
    })();
    return () => {
      cancelled = true;
      if (statusTimer.current) clearTimeout(statusTimer.current);
    };
  }, []);

  const showStatus = useCallback((message: string) => {
    setStatusMessage(message);
    if (statusTimer.current) clearTimeout(statusTimer.current);
    statusTimer.current = setTimeout(() => setStatusMessage(null), 5000);
  }, []);

  const startPreview = useCallback(async (file: PendingLibraryFile) => {
    setPreviewState({ file, preview: null, loading: true, error: null });
    try {
      const preview = await previewLibraryFile({
        filename: file.filename,
        content: file.content,
        kind: file.kindHint ?? undefined,
      });
      setPreviewState({ file, preview, loading: false, error: null });
    } catch (err) {
      const message =
        err instanceof LibraryApiError
          ? err.message
          : "Preview failed for this file.";
      setPreviewState({ file, preview: null, loading: false, error: message });
    }
  }, []);

  const enqueueFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      const accepted: PendingLibraryFile[] = [];
      const rejected: string[] = [];

      for (const file of files) {
        if (!isLibraryMarkdownFilename(file.name)) {
          rejected.push(file.name);
          continue;
        }
        const content = await readFileAsText(file);
        accepted.push({
          filename: file.name,
          content,
          kindHint: inferKindHint(file.name),
        });
      }

      if (rejected.length > 0) {
        showStatus(
          `Skipped non-Markdown file(s): ${rejected.join(", ")}. Use .md or .mdc.`,
        );
      }
      if (accepted.length === 0) return;

      setQueue((prev) => {
        const next = [...prev, ...accepted];
        return next;
      });
    },
    [showStatus],
  );

  // When queue has items and no active preview, start the next one.
  useEffect(() => {
    if (previewState !== null) return;
    if (queue.length === 0) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    void startPreview(next);
  }, [queue, previewState, startPreview]);

  const closePreview = useCallback(() => {
    setPreviewState(null);
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!previewState?.preview?.ok || !previewState.file) return;
    setConfirming(true);
    try {
      const result = await importLibraryFile({
        filename: previewState.file.filename,
        content: previewState.file.content,
        kind: previewState.file.kindHint ?? previewState.preview.kind ?? undefined,
      });
      if (!result.ok) {
        const msg =
          result.errors.map((e) => e.message).join(" ") ||
          "Import was rejected.";
        setPreviewState((prev) =>
          prev
            ? {
                ...prev,
                preview: {
                  ok: false,
                  errors: result.errors,
                  originalContent: prev.file.content,
                  originalFilename: prev.file.filename,
                },
                error: msg,
              }
            : prev,
        );
        return;
      }
      showStatus(
        `Imported ${result.asset?.manifest.kind ?? "asset"} “${result.asset?.manifest.name ?? ""}”.`,
      );
      setPreviewState(null);
      await refreshList();
    } catch (err) {
      const message =
        err instanceof LibraryApiError ? err.message : "Import failed.";
      setPreviewState((prev) =>
        prev ? { ...prev, error: message, loading: false } : prev,
      );
    } finally {
      setConfirming(false);
    }
  }, [previewState, refreshList, showStatus]);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setDragActive(false);
      if (event.dataTransfer.files?.length) {
        void enqueueFiles(event.dataTransfer.files);
      }
    },
    [enqueueFiles],
  );

  const canConfirm = Boolean(previewState?.preview?.ok) && !confirming;

  return (
    <>
      <div className="asset-library" data-testid="asset-library">
        <div className="asset-library-header">
          <span>Asset library</span>
          <button
            type="button"
            data-testid="asset-library-refresh"
            onClick={() => {
              void refreshList();
            }}
          >
            Refresh
          </button>
        </div>

        <div
          className={
            dragActive
              ? "asset-library-dropzone asset-library-dropzone-active"
              : "asset-library-dropzone"
          }
          data-testid="asset-library-dropzone"
          onDragEnter={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setDragActive(false);
          }}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
        >
          Drop Cursor skill / rules Markdown files here
          <div className="asset-library-dropzone-hint">
            .md / .mdc — preview, then confirm import
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".md,.mdc,.markdown,text/markdown"
            multiple
            hidden
            data-testid="asset-library-file-input"
            onChange={(e) => {
              if (e.target.files?.length) {
                void enqueueFiles(e.target.files);
                e.target.value = "";
              }
            }}
          />
        </div>

        {listError ? (
          <div className="asset-library-error" role="alert">
            {listError}
          </div>
        ) : null}
        {statusMessage ? (
          <div className="asset-library-status" data-testid="asset-library-status" role="status">
            {statusMessage}
          </div>
        ) : null}

        <div className="asset-library-list" data-testid="asset-library-list">
          {assets.length === 0 ? (
            <div className="asset-library-empty">No imported skills or rules yet.</div>
          ) : (
            assets.map((asset) => (
              <div
                key={asset.id}
                className="asset-library-item"
                data-testid={`asset-library-item-${asset.kind}`}
                data-asset-id={asset.id}
              >
                <span className="asset-library-item-kind">{asset.kind}</span>
                <span className="asset-library-item-name">{asset.name}</span>
                {asset.description ? (
                  <span className="asset-library-item-desc">{asset.description}</span>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>

      {previewState ? (
        <div
          className="asset-preview-overlay"
          data-testid="asset-preview-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Import preview"
        >
          <div className="asset-preview-dialog" data-testid="asset-preview-dialog">
            <div className="asset-preview-title">Import preview</div>
            {queue.length > 0 ? (
              <div className="asset-preview-queue">
                {queue.length} more file{queue.length === 1 ? "" : "s"} waiting
              </div>
            ) : null}

            {previewState.loading ? (
              <p data-testid="asset-preview-loading">Parsing frontmatter…</p>
            ) : null}

            {previewState.error && !previewState.preview ? (
              <div className="asset-preview-errors" role="alert">
                {previewState.error}
              </div>
            ) : null}

            {previewState.preview && !previewState.preview.ok ? (
              <div
                className="asset-preview-errors"
                data-testid="asset-preview-errors"
                role="alert"
              >
                <strong>Could not import this file</strong>
                <ul>
                  {previewState.preview.errors.map((err, index) => (
                    <li key={`${err.code}-${index}`}>{err.message}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {previewState.preview?.ok ? (
              <>
                <dl className="asset-preview-meta" data-testid="asset-preview-meta">
                  <dt>Kind</dt>
                  <dd>{previewState.preview.kind}</dd>
                  <dt>Name</dt>
                  <dd>{previewState.preview.name}</dd>
                  <dt>Description</dt>
                  <dd>{previewState.preview.description || "—"}</dd>
                  <dt>File</dt>
                  <dd>{previewState.preview.originalFilename}</dd>
                </dl>
                <pre className="asset-preview-body" data-testid="asset-preview-body">
                  {previewState.preview.body?.trim() || "(empty body)"}
                </pre>
              </>
            ) : null}

            <div className="asset-preview-actions">
              <button
                type="button"
                data-testid="asset-preview-cancel"
                onClick={closePreview}
                disabled={confirming}
              >
                {previewState.preview?.ok ? "Cancel" : "Close"}
              </button>
              <button
                type="button"
                data-testid="asset-preview-confirm"
                disabled={!canConfirm}
                onClick={() => {
                  void handleConfirm();
                }}
              >
                {confirming ? "Importing…" : "Confirm import"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
