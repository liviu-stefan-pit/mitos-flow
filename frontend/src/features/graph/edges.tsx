import {
  BaseEdge,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

/** Solid data-flow edge; animates when ``data.active`` is true. */
export function DataFlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const active = Boolean(
    data && typeof data === "object" && "active" in data && data.active,
  );

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      markerEnd={markerEnd}
      className={active ? "data-flow-edge-active" : undefined}
      style={{
        stroke: active ? "#2563eb" : "#64748b",
        strokeWidth: active ? 2.5 : 2,
        ...style,
      }}
    />
  );
}

/** Dashed resource-attachment edge. */
export function ResourceAttachmentEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      markerEnd={markerEnd}
      style={{
        stroke: "#f59e0b",
        strokeWidth: 2,
        strokeDasharray: "6 4",
        ...style,
      }}
    />
  );
}

export const edgeTypes = {
  dataFlow: DataFlowEdge,
  resourceAttachment: ResourceAttachmentEdge,
};
