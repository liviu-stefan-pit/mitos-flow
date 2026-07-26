/** All five node kinds available in the palette (Phase 5). */
export type NodeKind =
  | "input"
  | "skill"
  | "knowledgeBase"
  | "rules"
  | "artifactOutput";

export type NodeKindConfig = {
  kind: NodeKind;
  /** React Flow node `type` used to look up the renderer in nodeTypes. */
  flowType: string;
  /** Domain ID prefix, per docs/architecture.md. */
  idPrefix: string;
  /** Human-readable label shown in the palette and as the default node label. */
  displayName: string;
};

export const NODE_KIND_CONFIGS: NodeKindConfig[] = [
  { kind: "input", flowType: "mitosInput", idPrefix: "input", displayName: "Input" },
  { kind: "skill", flowType: "skill", idPrefix: "skill", displayName: "Skill" },
  {
    kind: "knowledgeBase",
    flowType: "knowledgeBase",
    idPrefix: "kb",
    displayName: "Knowledge Base",
  },
  { kind: "rules", flowType: "rules", idPrefix: "rules", displayName: "Rules" },
  {
    kind: "artifactOutput",
    flowType: "artifactOutput",
    idPrefix: "output",
    displayName: "Artifact Output",
  },
];

const FLOW_TYPE_TO_KIND: Record<string, NodeKind> = Object.fromEntries(
  NODE_KIND_CONFIGS.map((c) => [c.flowType, c.kind]),
) as Record<string, NodeKind>;

/** Resolve a React Flow node `type` string back to a domain NodeKind. */
export function nodeKindFromFlowType(
  flowType: string | undefined,
): NodeKind | null {
  if (!flowType) return null;
  return FLOW_TYPE_TO_KIND[flowType] ?? null;
}
