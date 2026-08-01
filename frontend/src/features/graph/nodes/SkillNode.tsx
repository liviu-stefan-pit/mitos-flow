import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  DATA_IN_HANDLE,
  DATA_OUT_HANDLE,
  RESOURCE_IN_HANDLE,
  RESOURCE_IN_TOP_HANDLE,
} from "../handles";
import type { SkillNodeData } from "../nodeData";

export type { SkillNodeData };

export function SkillNode({ data }: NodeProps) {
  const { label, runner, model } = data as SkillNodeData;
  const runnerKind = runner === "cursor" ? "cursor" : "fake";
  const modelId =
    runnerKind === "cursor" &&
    typeof model === "string" &&
    model.trim().length > 0
      ? model.trim()
      : null;

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
        position={Position.Top}
        id={RESOURCE_IN_TOP_HANDLE}
        className="handle-resource"
        title="Resource in"
        data-testid="skill-resource-in-top"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id={RESOURCE_IN_HANDLE}
        className="handle-resource"
        title="Resource in"
        data-testid="skill-resource-in-bottom"
      />
      <div className="graph-node-kind">Skill</div>
      <div className="graph-node-label">{label}</div>
      <div
        className={`graph-node-runner runner-${runnerKind}`}
        data-testid="node-skill-runner"
      >
        {runnerKind === "cursor" ? "Cursor" : "Fake"}
      </div>
      {modelId ? (
        <div className="graph-node-model" data-testid="node-skill-model">
          {modelId}
        </div>
      ) : null}
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
