import { useEffect, useState } from "react";
import type { Edge, Node } from "@xyflow/react";
import type { LibraryAssetSummary } from "../../domain/library";
import type { CursorModelInfo } from "../../domain/cursor";
import {
  DEFAULT_CURSOR_SKILL_MODEL,
  DEFAULT_KB_THRESHOLD,
  DEFAULT_KB_TOP_K,
} from "../../domain/workflow";
import {
  getLibraryAsset,
  LibraryApiError,
  listLibraryAssets,
} from "../library/libraryApi";
import {
  CursorApiError,
  fetchCursorModels,
} from "../settings/cursorApi";
import {
  ARTIFACT_OUTPUT_MODES,
  isArtifactOutputMode,
  type ArtifactOutputMode,
  type ArtifactOutputNodeData,
  type InputNodeData,
  type KnowledgeBaseNodeData,
  type RulesNodeData,
  type SkillNodeData,
} from "./nodeData";
import { nodeKindFromFlowType, type NodeKind } from "./nodeKinds";
import "./NodeInspector.css";

type NodeInspectorProps = {
  node: Node | null;
  nodes: Node[];
  edges: Edge[];
  onUpdateData: (nodeId: string, patch: Record<string, unknown>) => void;
  onUpdateEdgeData: (edgeId: string, patch: Record<string, unknown>) => void;
};

function kindLabel(kind: NodeKind): string {
  switch (kind) {
    case "input":
      return "Input";
    case "skill":
      return "Skill";
    case "knowledgeBase":
      return "Knowledge Base";
    case "rules":
      return "Rules";
    case "artifactOutput":
      return "Artifact Output";
  }
}

export function NodeInspector({
  node,
  nodes,
  edges,
  onUpdateData,
  onUpdateEdgeData,
}: NodeInspectorProps) {
  if (!node) {
    return (
      <aside className="node-inspector" data-testid="node-inspector-empty">
        <div className="node-inspector-title">Inspector</div>
        <p className="node-inspector-hint">Select a node to edit its settings.</p>
      </aside>
    );
  }

  const kind = nodeKindFromFlowType(node.type);
  if (!kind) {
    return (
      <aside className="node-inspector" data-testid="node-inspector">
        <div className="node-inspector-title">Inspector</div>
        <p className="node-inspector-hint">Unknown node type.</p>
      </aside>
    );
  }

  const label =
    typeof (node.data as { label?: unknown }).label === "string"
      ? (node.data as { label: string }).label
      : "";

  return (
    <aside className="node-inspector" data-testid="node-inspector">
      <div className="node-inspector-title">Inspector</div>
      <div className="node-inspector-kind" data-testid="inspector-kind">
        {kindLabel(kind)}
      </div>

      <label className="node-inspector-field">
        <span>Name</span>
        <input
          type="text"
          data-testid="inspector-label"
          value={label}
          onChange={(event) =>
            onUpdateData(node.id, { label: event.target.value })
          }
        />
      </label>

      {kind === "input" ? (
        <InputFields
          data={node.data as InputNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}

      {kind === "skill" ? (
        <SkillFields
          skillNodeId={node.id}
          data={node.data as SkillNodeData}
          nodes={nodes}
          edges={edges}
          onPatch={(patch) => onUpdateData(node.id, patch)}
          onUpdateEdgeData={onUpdateEdgeData}
        />
      ) : null}

      {kind === "knowledgeBase" ? (
        <KnowledgeBaseFields
          nodeId={node.id}
          data={node.data as KnowledgeBaseNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}

      {kind === "rules" ? (
        <RulesFields
          nodeId={node.id}
          data={node.data as RulesNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}

      {kind === "artifactOutput" ? (
        <ArtifactOutputFields
          data={node.data as ArtifactOutputNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}
    </aside>
  );
}

function InputFields({
  data,
  onPatch,
}: {
  data: InputNodeData;
  onPatch: (patch: Partial<InputNodeData>) => void;
}) {
  return (
    <>
      <label className="node-inspector-field">
        <span>Media type</span>
        <input
          type="text"
          data-testid="inspector-media-type"
          value={data.mediaType ?? "text/plain"}
          onChange={(event) => onPatch({ mediaType: event.target.value })}
        />
      </label>
      <label className="node-inspector-field">
        <span>Content</span>
        <textarea
          data-testid="inspector-content"
          rows={4}
          value={data.content ?? ""}
          onChange={(event) => onPatch({ content: event.target.value })}
        />
      </label>
    </>
  );
}

function SkillFields({
  skillNodeId,
  data,
  nodes,
  edges,
  onPatch,
  onUpdateEdgeData,
}: {
  skillNodeId: string;
  data: SkillNodeData;
  nodes: Node[];
  edges: Edge[];
  onPatch: (patch: Partial<SkillNodeData>) => void;
  onUpdateEdgeData: (edgeId: string, patch: Record<string, unknown>) => void;
}) {
  const runnerKind = data.runner === "cursor" ? "cursor" : "fake";
  const [models, setModels] = useState<CursorModelInfo[]>([
    { id: DEFAULT_CURSOR_SKILL_MODEL, label: DEFAULT_CURSOR_SKILL_MODEL },
  ]);
  const [modelsMessage, setModelsMessage] = useState<string | null>(null);
  const [modelsStatus, setModelsStatus] = useState<string>("available");

  useEffect(() => {
    if (runnerKind !== "cursor") return;
    let cancelled = false;
    void (async () => {
      try {
        const report = await fetchCursorModels();
        if (cancelled) return;
        setModels(
          report.models.length > 0
            ? report.models
            : [
                {
                  id: report.defaultModel || DEFAULT_CURSOR_SKILL_MODEL,
                  label: report.defaultModel || DEFAULT_CURSOR_SKILL_MODEL,
                },
              ],
        );
        setModelsStatus(report.status);
        setModelsMessage(
          report.status === "available"
            ? null
            : report.message ||
                "Could not refresh Cursor models; using composer-2.5 default.",
        );
      } catch (err) {
        if (cancelled) return;
        setModels([
          {
            id: DEFAULT_CURSOR_SKILL_MODEL,
            label: DEFAULT_CURSOR_SKILL_MODEL,
          },
        ]);
        setModelsStatus("error");
        setModelsMessage(
          err instanceof CursorApiError
            ? err.message
            : "Could not load Cursor models; using composer-2.5 default.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runnerKind, skillNodeId]);

  const selectedModel =
    typeof data.model === "string" && data.model.trim().length > 0
      ? data.model.trim()
      : DEFAULT_CURSOR_SKILL_MODEL;

  const kbAttachments = edges
    .filter(
      (edge) =>
        edge.type === "resourceAttachment" && edge.target === skillNodeId,
    )
    .map((edge) => {
      const source = nodes.find((node) => node.id === edge.source);
      if (!source || nodeKindFromFlowType(source.type) !== "knowledgeBase") {
        return null;
      }
      const edgeData =
        typeof edge.data === "object" && edge.data !== null
          ? (edge.data as Record<string, unknown>)
          : {};
      const topK =
        typeof edgeData.topK === "number" &&
        Number.isFinite(edgeData.topK) &&
        edgeData.topK >= 1
          ? Math.floor(edgeData.topK)
          : DEFAULT_KB_TOP_K;
      const threshold =
        typeof edgeData.threshold === "number" &&
        Number.isFinite(edgeData.threshold) &&
        edgeData.threshold >= 0
          ? edgeData.threshold
          : DEFAULT_KB_THRESHOLD;
      const label =
        typeof (source.data as { label?: unknown }).label === "string"
          ? (source.data as { label: string }).label
          : source.id;
      return { edgeId: edge.id, kbNodeId: source.id, label, topK, threshold };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
    // Dedupe by KB node id (first edge wins), stable by edge id.
    .reduce<
      {
        edgeId: string;
        kbNodeId: string;
        label: string;
        topK: number;
        threshold: number;
      }[]
    >((acc, item) => {
      if (acc.some((existing) => existing.kbNodeId === item.kbNodeId)) {
        return acc;
      }
      acc.push(item);
      return acc;
    }, [])
    .sort((a, b) => a.kbNodeId.localeCompare(b.kbNodeId));

  return (
    <>
      <label className="node-inspector-field">
        <span>Description</span>
        <textarea
          data-testid="inspector-description"
          rows={3}
          value={data.description ?? ""}
          onChange={(event) => onPatch({ description: event.target.value })}
        />
      </label>
      <div className="node-inspector-field">
        <span>Runner</span>
        <div
          className="node-inspector-runner"
          role="radiogroup"
          aria-label="Skill runner"
          data-testid="inspector-runner-kind"
        >
          <label className="node-inspector-runner-option">
            <input
              type="radio"
              name={`runner-${skillNodeId}`}
              value="fake"
              checked={runnerKind === "fake"}
              onChange={() => onPatch({ runner: "fake" })}
              data-testid="inspector-runner-fake"
            />
            Fake
          </label>
          <label className="node-inspector-runner-option">
            <input
              type="radio"
              name={`runner-${skillNodeId}`}
              value="cursor"
              checked={runnerKind === "cursor"}
              onChange={() =>
                onPatch({
                  runner: "cursor",
                  model:
                    typeof data.model === "string" && data.model.trim()
                      ? data.model.trim()
                      : DEFAULT_CURSOR_SKILL_MODEL,
                })
              }
              data-testid="inspector-runner-cursor"
            />
            Cursor
          </label>
        </div>
      </div>
      {runnerKind === "cursor" ? (
        <label className="node-inspector-field">
          <span>Cursor model</span>
          <select
            data-testid="inspector-cursor-model"
            value={selectedModel}
            onChange={(event) => onPatch({ model: event.target.value })}
          >
            {!models.some((m) => m.id === selectedModel) ? (
              <option value={selectedModel}>{selectedModel}</option>
            ) : null}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label === model.id
                  ? model.id
                  : `${model.label} (${model.id})`}
              </option>
            ))}
          </select>
          {modelsMessage ? (
            <p
              className="node-inspector-hint"
              role="status"
              data-testid="inspector-cursor-model-warning"
              data-models-status={modelsStatus}
            >
              {modelsMessage}
            </p>
          ) : (
            <p className="node-inspector-hint">
              Default is {DEFAULT_CURSOR_SKILL_MODEL} (never silent auto).
            </p>
          )}
        </label>
      ) : null}
      <div className="node-inspector-field">
        <span>Join policy</span>
        <div
          className="node-inspector-readonly"
          data-testid="inspector-join-policy"
        >
          wait_for_all
        </div>
      </div>
      <div
        className="node-inspector-field"
        data-testid="inspector-kb-attachments"
      >
        <span>KB retrieval controls</span>
        {kbAttachments.length === 0 ? (
          <p className="node-inspector-hint">
            Attach a Knowledge Base with a dashed resource edge to set top-K
            and score threshold for this Skill/KB link.
          </p>
        ) : (
          <ul className="node-inspector-attachment-list">
            {kbAttachments.map((attachment) => (
              <li
                key={attachment.edgeId}
                className="node-inspector-attachment"
                data-testid="inspector-kb-attachment"
                data-kb-node-id={attachment.kbNodeId}
                data-edge-id={attachment.edgeId}
              >
                <div className="node-inspector-attachment-label">
                  {attachment.label}
                </div>
                <label className="node-inspector-field">
                  <span>Top-K</span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    data-testid="inspector-kb-topk"
                    value={attachment.topK}
                    onChange={(event) => {
                      const parsed = Number(event.target.value);
                      if (!Number.isFinite(parsed) || parsed < 1) return;
                      onUpdateEdgeData(attachment.edgeId, {
                        topK: Math.floor(parsed),
                      });
                    }}
                  />
                </label>
                <label className="node-inspector-field">
                  <span>Threshold</span>
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    data-testid="inspector-kb-threshold"
                    value={attachment.threshold}
                    onChange={(event) => {
                      const parsed = Number(event.target.value);
                      if (!Number.isFinite(parsed) || parsed < 0) return;
                      onUpdateEdgeData(attachment.edgeId, {
                        threshold: parsed,
                      });
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

function DescriptionField({
  testId,
  data,
  onPatch,
}: {
  testId: string;
  data: { description?: string };
  onPatch: (patch: { description: string }) => void;
}) {
  return (
    <label className="node-inspector-field">
      <span>Description</span>
      <textarea
        data-testid={testId}
        rows={3}
        value={data.description ?? ""}
        onChange={(event) => onPatch({ description: event.target.value })}
      />
    </label>
  );
}

function KnowledgeBaseFields({
  nodeId,
  data,
  onPatch,
}: {
  nodeId: string;
  data: KnowledgeBaseNodeData;
  onPatch: (patch: Partial<KnowledgeBaseNodeData> & { label?: string }) => void;
}) {
  const [assets, setAssets] = useState<LibraryAssetSummary[]>([]);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const selectedAssetId = data.libraryAssetId ?? "";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLibraryAssets();
        if (cancelled) return;
        setAssets(
          result.assets.filter((asset) => asset.kind === "knowledgeBase"),
        );
        setLibraryError(null);
      } catch (err) {
        if (cancelled) return;
        setLibraryError(
          err instanceof LibraryApiError
            ? err.message
            : "Could not load library knowledge bases.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  const applyFromLibrary = async (assetId: string) => {
    if (!assetId) {
      onPatch({ libraryAssetId: null });
      return;
    }
    setApplying(true);
    try {
      const asset = await getLibraryAsset(assetId);
      onPatch({
        label: asset.manifest.name,
        description: asset.manifest.description,
        content: asset.manifest.body,
        libraryAssetId: asset.manifest.id,
      });
      setLibraryError(null);
    } catch (err) {
      setLibraryError(
        err instanceof LibraryApiError
          ? err.message
          : "Could not load the selected knowledge base asset.",
      );
    } finally {
      setApplying(false);
    }
  };

  return (
    <>
      <DescriptionField
        testId="inspector-description"
        data={data}
        onPatch={(patch) => onPatch(patch)}
      />
      <label className="node-inspector-field">
        <span>KB content</span>
        <textarea
          data-testid="inspector-kb-content"
          rows={5}
          value={data.content ?? ""}
          onChange={(event) =>
            onPatch({ content: event.target.value, libraryAssetId: null })
          }
        />
      </label>
      <label className="node-inspector-field">
        <span>Apply from library</span>
        <select
          data-testid="inspector-kb-library"
          value={selectedAssetId}
          disabled={applying}
          onChange={(event) => {
            void applyFromLibrary(event.target.value);
          }}
        >
          <option value="">— Manual / none —</option>
          {assets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.name}
            </option>
          ))}
        </select>
      </label>
      {libraryError ? (
        <p
          className="node-inspector-hint"
          role="alert"
          data-testid="inspector-kb-library-error"
        >
          {libraryError}
        </p>
      ) : (
        <p className="node-inspector-hint">
          Attach this Knowledge Base to Skills with a dashed resource edge.
          Per-attachment top-K and threshold are edited on the Skill inspector.
          Keyword retrieval returns cited chunks (with query) into the Skill run
          request and activity trace.
        </p>
      )}
    </>
  );
}

function RulesFields({
  nodeId,
  data,
  onPatch,
}: {
  nodeId: string;
  data: RulesNodeData;
  onPatch: (patch: Partial<RulesNodeData> & { label?: string }) => void;
}) {
  const [assets, setAssets] = useState<LibraryAssetSummary[]>([]);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const selectedAssetId = data.libraryAssetId ?? "";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLibraryAssets();
        if (cancelled) return;
        setAssets(result.assets.filter((asset) => asset.kind === "rules"));
        setLibraryError(null);
      } catch (err) {
        if (cancelled) return;
        setLibraryError(
          err instanceof LibraryApiError
            ? err.message
            : "Could not load library rules.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  const applyFromLibrary = async (assetId: string) => {
    if (!assetId) {
      onPatch({ libraryAssetId: null });
      return;
    }
    setApplying(true);
    try {
      const asset = await getLibraryAsset(assetId);
      onPatch({
        label: asset.manifest.name,
        description: asset.manifest.description,
        content: asset.manifest.body,
        libraryAssetId: asset.manifest.id,
      });
      setLibraryError(null);
    } catch (err) {
      setLibraryError(
        err instanceof LibraryApiError
          ? err.message
          : "Could not load the selected rules asset.",
      );
    } finally {
      setApplying(false);
    }
  };

  return (
    <>
      <DescriptionField
        testId="inspector-description"
        data={data}
        onPatch={(patch) => onPatch(patch)}
      />
      <label className="node-inspector-field">
        <span>Rule content</span>
        <textarea
          data-testid="inspector-rules-content"
          rows={5}
          value={data.content ?? ""}
          onChange={(event) =>
            onPatch({ content: event.target.value, libraryAssetId: null })
          }
        />
      </label>
      <label className="node-inspector-field">
        <span>Apply from library</span>
        <select
          data-testid="inspector-rules-library"
          value={selectedAssetId}
          disabled={applying}
          onChange={(event) => {
            void applyFromLibrary(event.target.value);
          }}
        >
          <option value="">— Manual / none —</option>
          {assets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.name}
            </option>
          ))}
        </select>
      </label>
      {libraryError ? (
        <p className="node-inspector-hint" role="alert" data-testid="inspector-rules-library-error">
          {libraryError}
        </p>
      ) : (
        <p className="node-inspector-hint">
          Attach this Rules node to Skills with a dashed resource edge. Content
          is resolved into the Skill run request and activity trace.
        </p>
      )}
    </>
  );
}

function ArtifactOutputFields({
  data,
  onPatch,
}: {
  data: ArtifactOutputNodeData;
  onPatch: (patch: Partial<ArtifactOutputNodeData>) => void;
}) {
  const mode: ArtifactOutputMode = isArtifactOutputMode(data.mode)
    ? data.mode
    : "pass-through";

  return (
    <label className="node-inspector-field">
      <span>Output mode</span>
      <select
        data-testid="inspector-output-mode"
        value={mode}
        onChange={(event) =>
          onPatch({ mode: event.target.value as ArtifactOutputMode })
        }
      >
        {ARTIFACT_OUTPUT_MODES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}
