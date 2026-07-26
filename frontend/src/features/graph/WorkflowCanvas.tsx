import {
  Background,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { nodeTypes } from "./nodes";
import { sampleEdges, sampleNodes } from "./sampleGraph";
import "./WorkflowCanvas.css";

function WorkflowCanvasInner() {
  return (
    <div className="workflow-canvas" data-testid="workflow-canvas">
      <ReactFlow
        nodes={sampleNodes}
        edges={sampleEdges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
      </ReactFlow>
    </div>
  );
}

export function WorkflowCanvas() {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner />
    </ReactFlowProvider>
  );
}
