import { useCallback, useMemo } from "react";
import {
  Background,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { NodePalette } from "./NodePalette";
import { createNode } from "./nodeFactory";
import { nodeTypes } from "./nodes";
import type { NodeKind } from "./nodeKinds";
import "./WorkflowCanvas.css";

/**
 * Phase 5: canvas starts empty every load (no persistence yet). Nodes can be
 * added from the palette, selected, moved, and deleted. Edges and node
 * settings are out of scope until later phases.
 */
function WorkflowCanvasInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, , onEdgesChange] = useEdgesState<Edge>([]);

  const hasSelection = useMemo(() => nodes.some((node) => node.selected), [
    nodes,
  ]);

  const handleAddNode = useCallback(
    (kind: NodeKind) => {
      setNodes((current) => [...current, createNode(kind, current.length)]);
    },
    [setNodes],
  );

  const handleDeleteSelected = useCallback(() => {
    setNodes((current) => current.filter((node) => !node.selected));
  }, [setNodes]);

  return (
    <div className="workflow-canvas" data-testid="workflow-canvas">
      <NodePalette
        onAddNode={handleAddNode}
        onDeleteSelected={handleDeleteSelected}
        hasSelection={hasSelection}
      />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        nodesFocusable
        edgesFocusable={false}
        deleteKeyCode={["Backspace", "Delete"]}
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
