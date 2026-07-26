import type { NodeTypes } from "@xyflow/react";
import { ArtifactOutputNode } from "./ArtifactOutputNode";
import { InputNode } from "./InputNode";
import { SkillNode } from "./SkillNode";

export { ArtifactOutputNode, InputNode, SkillNode };

export const nodeTypes: NodeTypes = {
  mitosInput: InputNode,
  skill: SkillNode,
  artifactOutput: ArtifactOutputNode,
};
