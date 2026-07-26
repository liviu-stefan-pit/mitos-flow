import type { Node, XYPosition } from "@xyflow/react";
import { NODE_KIND_CONFIGS, type NodeKind } from "./nodeKinds";

/** Small offset so consecutive adds near the same center don't fully overlap. */
const STAGGER = 28;

/**
 * Creates a new node of the given kind at `center` (flow coordinates), with a
 * light stagger so rapid adds don't stack on the exact same point.
 */
export function createNode(
  kind: NodeKind,
  center: XYPosition,
  existingCount: number,
): Node {
  const config = NODE_KIND_CONFIGS.find((c) => c.kind === kind);
  if (!config) {
    throw new Error(`Unknown node kind: ${kind}`);
  }

  const id = `${config.idPrefix}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
  const staggerIndex = existingCount % 8;
  // Approximate node size so the visual center lands near the viewport center.
  const nodeWidth = 160;
  const nodeHeight = 64;

  return {
    id,
    type: config.flowType,
    position: {
      x: center.x - nodeWidth / 2 + staggerIndex * STAGGER,
      y: center.y - nodeHeight / 2 + staggerIndex * STAGGER,
    },
    data: { label: config.displayName },
  };
}
