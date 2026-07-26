import type { Edge, Node } from "@xyflow/react";

/** Fixed sample: Input → Skill → Artifact Output (Phase 4, read-only). */
export const sampleNodes: Node[] = [
  {
    id: "input-1",
    type: "mitosInput",
    position: { x: 80, y: 160 },
    data: { label: "User Brief" },
  },
  {
    id: "skill-1",
    type: "skill",
    position: { x: 360, y: 160 },
    data: { label: "Draft Response" },
  },
  {
    id: "output-1",
    type: "artifactOutput",
    position: { x: 660, y: 160 },
    data: { label: "Pass-through Output" },
  },
];

export const sampleEdges: Edge[] = [
  {
    id: "e-input-skill",
    source: "input-1",
    target: "skill-1",
    type: "smoothstep",
  },
  {
    id: "e-skill-output",
    source: "skill-1",
    target: "output-1",
    type: "smoothstep",
  },
];
