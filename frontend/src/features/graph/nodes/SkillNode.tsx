import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  DATA_IN_HANDLE,
  DATA_OUT_HANDLE,
  RESOURCE_IN_HANDLE,
} from "../handles";
import type { SkillNodeData } from "../nodeData";

export type { SkillNodeData };

export function SkillNode({ data }: NodeProps) {
  const { label } = data as SkillNodeData;

  return (
    <div className="graph-node graph-node-skill" data-testid="node-skill">
      <Handle
        type="target"
        position={Position.Left}
        id={DATA_IN_HANDLE}
        className="handle-data"
        title="Data in"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id={RESOURCE_IN_HANDLE}
        className="handle-resource"
        title="Resource in"
      />
      <div className="graph-node-kind">Skill</div>
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
