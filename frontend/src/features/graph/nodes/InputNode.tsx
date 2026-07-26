import { Handle, Position, type NodeProps } from "@xyflow/react";
import { DATA_OUT_HANDLE } from "../handles";
import type { InputNodeData } from "../nodeData";

export type { InputNodeData };

export function InputNode({ data }: NodeProps) {
  const { label } = data as InputNodeData;

  return (
    <div className="graph-node graph-node-input" data-testid="node-input">
      <div className="graph-node-kind">Input</div>
      <div className="graph-node-label">{label}</div>
      <Handle
        type="source"
        position={Position.Right}
        id={DATA_OUT_HANDLE}
        className="handle-data"
        title="Data out"
      />
    </div>
  );
}
