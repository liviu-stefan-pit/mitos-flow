import type { Node } from "@xyflow/react";
import { NODE_KIND_CONFIGS, type NodeKind } from "./nodeKinds";

/**
 * Creates a new node of the given kind with a unique ID and a staggered
 * position so newly added nodes don't all land on top of each other.
 * `existingCount` should be the current total number of nodes on the canvas.
 */
export function createNode(kind: NodeKind, existingCount: number): Node {
  const config = NODE_KIND_CONFIGS.find((c) => c.kind === kind);
  if (!config) {
    throw new Error(`Unknown node kind: ${kind}`);
  }

  const id = `${config.idPrefix}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
  const column = existingCount % 5;
  const row = Math.floor(existingCount / 5);

  return {
    id,
    type: config.flowType,
    position: { x: 80 + column * 220, y: 120 + row * 140 },
    data: { label: config.displayName },
  };
}
