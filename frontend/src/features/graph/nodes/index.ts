import type { NodeTypes } from "@xyflow/react";
import { ArtifactOutputNode } from "./ArtifactOutputNode";
import { InputNode } from "./InputNode";
import { KnowledgeBaseNode } from "./KnowledgeBaseNode";
import { RulesNode } from "./RulesNode";
import { SkillNode } from "./SkillNode";

export { ArtifactOutputNode, InputNode, KnowledgeBaseNode, RulesNode, SkillNode };

export const nodeTypes: NodeTypes = {
  mitosInput: InputNode,
  skill: SkillNode,
  knowledgeBase: KnowledgeBaseNode,
  rules: RulesNode,
  artifactOutput: ArtifactOutputNode,
};
