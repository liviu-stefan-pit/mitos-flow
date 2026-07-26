import { Handle, Position, type NodeProps } from "@xyflow/react";
import { RESOURCE_OUT_HANDLE } from "../handles";

export type RulesNodeData = {
  label: string;
};

export function RulesNode({ data }: NodeProps) {
  const label = (data as RulesNodeData).label;

  return (
    <div className="graph-node graph-node-rules" data-testid="node-rules">
      <div className="graph-node-kind">Rules</div>
      <div className="graph-node-label">{label}</div>
      <Handle
        type="source"
        position={Position.Right}
        id={RESOURCE_OUT_HANDLE}
        className="handle-resource"
        title="Resource out"
      />
    </div>
  );
}
