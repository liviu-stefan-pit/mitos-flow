import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { validateConnection } from "./connectionValidator";
import { edgeTypes } from "./edges";
import { NodePalette } from "./NodePalette";
import { createNode } from "./nodeFactory";
import { nodeTypes } from "./nodes";
import { nodeKindFromFlowType, type NodeKind } from "./nodeKinds";
import "./WorkflowCanvas.css";

const FEEDBACK_MS = 4000;

/**
 * Phase 6: typed edges (solid data-flow, dashed resource) with connection
 * rules. Canvas still starts empty each load (persistence is Phase 8).
 */
function WorkflowCanvasInner() {
  const { screenToFlowPosition } = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showFeedback = useCallback((message: string) => {
    setFeedback(message);
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setFeedback(null), FEEDBACK_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    };
  }, []);

  const hasSelection = useMemo(
    () =>
      nodes.some((node) => node.selected) ||
      edges.some((edge) => edge.selected),
    [nodes, edges],
  );

  const handleAddNode = useCallback(
    (kind: NodeKind) => {
      const bounds = canvasRef.current?.getBoundingClientRect();
      const center = bounds
        ? screenToFlowPosition({
            x: bounds.left + bounds.width / 2,
            y: bounds.top + bounds.height / 2,
          })
        : { x: 0, y: 0 };

      setNodes((current) => [
        ...current,
        createNode(kind, center, current.length),
      ]);
    },
    [screenToFlowPosition, setNodes],
  );

  const handleDeleteSelected = useCallback(() => {
    const selectedNodeIds = new Set(
      nodes.filter((n) => n.selected).map((n) => n.id),
    );
    setNodes((current) => current.filter((node) => !node.selected));
    setEdges((current) =>
      current.filter(
        (edge) =>
          !edge.selected &&
          !selectedNodeIds.has(edge.source) &&
          !selectedNodeIds.has(edge.target),
      ),
    );
  }, [nodes, setNodes, setEdges]);

  const resolveConnection = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) {
        return {
          ok: false as const,
          reason: "Incomplete connection.",
        };
      }
      const sourceNode = nodes.find((n) => n.id === connection.source);
      const targetNode = nodes.find((n) => n.id === connection.target);
      return validateConnection({
        sourceNodeId: connection.source,
        targetNodeId: connection.target,
        sourceKind: nodeKindFromFlowType(sourceNode?.type),
        targetKind: nodeKindFromFlowType(targetNode?.type),
        sourceHandleId: connection.sourceHandle,
        targetHandleId: connection.targetHandle,
      });
    },
    [nodes],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      const result = resolveConnection(connection as Connection);
      return result.ok;
    },
    [resolveConnection],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const result = resolveConnection(connection);
      if (!result.ok) {
        showFeedback(result.reason);
        return;
      }
      setEdges((current) =>
        addEdge(
          {
            ...connection,
            type: result.edgeKind,
            id: `${result.edgeKind}-${connection.source}-${connection.sourceHandle}-${connection.target}-${connection.targetHandle}-${Date.now()}`,
          },
          current,
        ),
      );
    },
    [resolveConnection, setEdges, showFeedback],
  );

  const onConnectEnd = useCallback(
    (
      _event: MouseEvent | TouchEvent,
      connectionState: {
        isValid: boolean | null;
        fromNode: Node | null;
        toNode: Node | null;
        fromHandle: { id?: string | null } | null;
        toHandle: { id?: string | null } | null;
      },
    ) => {
      // User aimed at a node but the connection was rejected — show why.
      if (
        connectionState.fromNode &&
        connectionState.toNode &&
        connectionState.isValid === false
      ) {
        const result = validateConnection({
          sourceNodeId: connectionState.fromNode.id,
          targetNodeId: connectionState.toNode.id,
          sourceKind: nodeKindFromFlowType(connectionState.fromNode.type),
          targetKind: nodeKindFromFlowType(connectionState.toNode.type),
          sourceHandleId: connectionState.fromHandle?.id,
          targetHandleId: connectionState.toHandle?.id,
        });
        showFeedback(
          result.ok ? "That connection is not allowed." : result.reason,
        );
      }
    },
    [showFeedback],
  );

  return (
    <div
      className="workflow-canvas"
      data-testid="workflow-canvas"
      ref={canvasRef}
    >
      <NodePalette
        onAddNode={handleAddNode}
        onDeleteSelected={handleDeleteSelected}
        hasSelection={hasSelection}
      />
      {feedback ? (
        <div
          className="connection-feedback"
          data-testid="connection-feedback"
          role="status"
        >
          {feedback}
        </div>
      ) : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onConnectEnd={onConnectEnd}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        nodesFocusable
        edgesFocusable
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
