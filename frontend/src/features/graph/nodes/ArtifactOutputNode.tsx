import { Handle, Position, type NodeProps } from "@xyflow/react";
import { DATA_IN_HANDLE } from "../handles";
import {
  isArtifactDestinationKind,
  isArtifactOutputMode,
  type ArtifactOutputNodeData,
} from "../nodeData";

export type { ArtifactOutputNodeData };

export function ArtifactOutputNode({ data }: NodeProps) {
  const nodeData = data as ArtifactOutputNodeData;
  const { label } = nodeData;
  const destination = isArtifactDestinationKind(nodeData.destination)
    ? nodeData.destination
    : "preview";
  const mode = isArtifactOutputMode(nodeData.mode)
    ? nodeData.mode
    : "pass-through";
  const runnerKind = nodeData.runner === "cursor" ? "cursor" : "fake";

  return (
    <div className="graph-node graph-node-output" data-testid="node-output">
      <Handle
        type="target"
        position={Position.Left}
        id={DATA_IN_HANDLE}
        className="handle-data"
        title="Data in"
      />
      <div className="graph-node-kind">Artifact Output</div>
      <div className="graph-node-label">{label}</div>
      <div
        className={`graph-node-runner mode-${mode}`}
        data-testid="output-mode-badge"
      >
        {mode === "selector"
          ? "Selector"
          : mode === "prompted"
            ? "Prompted"
            : "Pass-through"}
      </div>
      {mode === "prompted" ? (
        <div
          className={`graph-node-runner runner-${runnerKind}`}
          data-testid="output-runner-badge"
        >
          {runnerKind === "cursor" ? "Cursor" : "Fake"}
        </div>
      ) : null}
      <div
        className={`graph-node-runner destination-${destination}`}
        data-testid="output-destination-badge"
      >
        {destination === "managedFile" ? "File" : "Preview"}
      </div>
    </div>
  );
}
