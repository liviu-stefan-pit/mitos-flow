import type { Node } from "@xyflow/react";
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
  onUpdateData: (nodeId: string, patch: Record<string, unknown>) => void;
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

export function NodeInspector({ node, onUpdateData }: NodeInspectorProps) {
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
          data={node.data as SkillNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}

      {kind === "knowledgeBase" ? (
        <DescriptionField
          testId="inspector-description"
          data={node.data as KnowledgeBaseNodeData}
          onPatch={(patch) => onUpdateData(node.id, patch)}
        />
      ) : null}

      {kind === "rules" ? (
        <DescriptionField
          testId="inspector-description"
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
  data,
  onPatch,
}: {
  data: SkillNodeData;
  onPatch: (patch: Partial<SkillNodeData>) => void;
}) {
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
        <span>Join policy</span>
        <div
          className="node-inspector-readonly"
          data-testid="inspector-join-policy"
        >
          wait_for_all
        </div>
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
