import { Handle, Position, type NodeProps } from "@xyflow/react";
import { RESOURCE_OUT_HANDLE } from "../handles";
import type { KnowledgeBaseNodeData } from "../nodeData";

export type { KnowledgeBaseNodeData };

export function KnowledgeBaseNode({ data }: NodeProps) {
  const { label } = data as KnowledgeBaseNodeData;

  return (
    <div className="graph-node graph-node-kb" data-testid="node-kb">
      <div className="graph-node-kind">Knowledge Base</div>
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
