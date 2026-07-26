import { Handle, Position, type NodeProps } from "@xyflow/react";
import { DATA_IN_HANDLE } from "../handles";

export type ArtifactOutputNodeData = {
  label: string;
};

export function ArtifactOutputNode({ data }: NodeProps) {
  const label = (data as ArtifactOutputNodeData).label;

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
    </div>
  );
}
