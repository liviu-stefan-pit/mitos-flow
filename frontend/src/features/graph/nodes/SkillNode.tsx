import { Handle, Position, type NodeProps } from "@xyflow/react";

export type SkillNodeData = {
  label: string;
};

export function SkillNode({ data }: NodeProps) {
  const label = (data as SkillNodeData).label;

  return (
    <div className="graph-node graph-node-skill" data-testid="node-skill">
      <Handle type="target" position={Position.Left} />
      <div className="graph-node-kind">Skill</div>
      <div className="graph-node-label">{label}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
