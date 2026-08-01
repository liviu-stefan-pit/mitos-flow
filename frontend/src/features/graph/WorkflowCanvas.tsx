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

import type { WorkflowValidationResult } from "../../domain/workflow";
import { AssetLibrary } from "../library/AssetLibrary";
import { ActivityTimeline } from "../run/ActivityTimeline";
import { useWorkflowRun } from "../run/useWorkflowRun";
import {
  validateWorkflow,
  WorkflowValidateError,
} from "../workflow/validateApi";
import { validateConnection } from "./connectionValidator";
import {
  clearDraft,
  draftToReactFlow,
  loadDraft,
  saveDraft,
} from "./draftStorage";
import { edgeTypes } from "./edges";
import { NodeInspector } from "./NodeInspector";
import { NodePalette } from "./NodePalette";
import { createNode } from "./nodeFactory";
import { nodeTypes } from "./nodes";
import { nodeKindFromFlowType, type NodeKind } from "./nodeKinds";
import { uiGraphToDomainWorkflow } from "./toDomainWorkflow";
import "./WorkflowCanvas.css";

const FEEDBACK_MS = 4000;
const WARNING_MS = 8000;

const NEW_WORKFLOW_CONFIRM =
  "Create a new workflow? The current canvas and saved draft will be cleared.";
const RESET_DRAFT_CONFIRM =
  "Reset the saved draft? The current canvas and browser draft will be cleared.";

/**
 * Phase 7–18: inspector, draft, validate, live runs, cancel, asset library,
 * Rules attachments in run trace.
 */
function WorkflowCanvasInner() {
  const { screenToFlowPosition } = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const [validating, setValidating] = useState(false);
  const [exportJson, setExportJson] = useState<string | null>(null);
  const [validationResult, setValidationResult] =
    useState<WorkflowValidationResult | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const workflowRun = useWorkflowRun();

  const showFeedback = useCallback((message: string) => {
    setFeedback(message);
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setFeedback(null), FEEDBACK_MS);
  }, []);

  const showWarning = useCallback((message: string) => {
    setWarning(message);
    if (warningTimer.current) clearTimeout(warningTimer.current);
    warningTimer.current = setTimeout(() => setWarning(null), WARNING_MS);
  }, []);

  useEffect(() => {
    const result = loadDraft();
    if (result.status === "ok") {
      const restored = draftToReactFlow(result.draft);
      setNodes(restored.nodes);
      setEdges(restored.edges);
    } else if (result.status === "corrupt") {
      clearDraft();
      showWarning(result.warning);
    }
    setDraftReady(true);
  }, [setNodes, setEdges, showWarning]);

  useEffect(() => {
    if (!draftReady) return;
    saveDraft(nodes, edges);
  }, [nodes, edges, draftReady]);

  useEffect(() => {
    return () => {
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
    };
  }, []);

  const selectedNode = useMemo(() => {
    const selected = nodes.filter((node) => node.selected);
    return selected.length === 1 ? selected[0] : null;
  }, [nodes]);

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

  const handleUpdateNodeData = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, ...patch } }
            : node,
        ),
      );
    },
    [setNodes],
  );

  const clearCanvasAndDraft = useCallback(() => {
    setNodes([]);
    setEdges([]);
    clearDraft();
  }, [setNodes, setEdges]);

  const handleNewWorkflow = useCallback(() => {
    if (!window.confirm(NEW_WORKFLOW_CONFIRM)) return;
    clearCanvasAndDraft();
  }, [clearCanvasAndDraft]);

  const handleResetDraft = useCallback(() => {
    if (!window.confirm(RESET_DRAFT_CONFIRM)) return;
    clearCanvasAndDraft();
  }, [clearCanvasAndDraft]);

  const handleExportWorkflow = useCallback(() => {
    const mapped = uiGraphToDomainWorkflow(nodes, edges);
    if (!mapped.ok) {
      showFeedback(mapped.reason);
      setExportJson(null);
      return;
    }
    setExportJson(JSON.stringify(mapped.workflow, null, 2));
    setValidationResult(null);
  }, [nodes, edges, showFeedback]);

  const handleValidateWorkflow = useCallback(async () => {
    const mapped = uiGraphToDomainWorkflow(nodes, edges);
    if (!mapped.ok) {
      showFeedback(mapped.reason);
      setValidationResult(null);
      return;
    }

    setExportJson(JSON.stringify(mapped.workflow, null, 2));
    setValidating(true);
    try {
      const result = await validateWorkflow(mapped.workflow);
      setValidationResult(result);
      if (result.valid) {
        showFeedback("Workflow is valid.");
      } else {
        showFeedback(
          result.errors[0]?.message ?? "Workflow validation failed.",
        );
      }
    } catch (error) {
      setValidationResult(null);
      const message =
        error instanceof WorkflowValidateError
          ? error.message
          : "Validation request failed.";
      showFeedback(message);
    } finally {
      setValidating(false);
    }
  }, [nodes, edges, showFeedback]);

  const handleRunWorkflow = useCallback(async () => {
    const mapped = uiGraphToDomainWorkflow(nodes, edges);
    if (!mapped.ok) {
      showFeedback(mapped.reason);
      return;
    }
    try {
      const created = await workflowRun.start(mapped.workflow);
      if (created.status === "rejected") {
        showFeedback(
          created.errors[0]?.message ?? "Workflow rejected for execution.",
        );
        return;
      }
      showFeedback("Run started — watch live progress on the canvas.");
    } catch {
      showFeedback("Failed to start run.");
    }
  }, [nodes, edges, showFeedback, workflowRun]);

  const handleCancelRun = useCallback(async () => {
    await workflowRun.cancel();
    showFeedback("Cancel requested — waiting for run to stop.");
  }, [showFeedback, workflowRun]);

  const displayNodes = useMemo(
    () =>
      nodes.map((node) => {
        const runState = workflowRun.nodeStates[node.id];
        const className = runState ? `run-state-${runState}` : undefined;
        return className ? { ...node, className } : { ...node, className: undefined };
      }),
    [nodes, workflowRun.nodeStates],
  );

  const displayEdges = useMemo(
    () =>
      edges.map((edge) => {
        if (edge.type !== "dataFlow") {
          return { ...edge, data: { ...(edge.data ?? {}), active: false } };
        }
        const active = workflowRun.activeEdgeNodeIds.has(edge.target);
        return {
          ...edge,
          data: { ...(edge.data ?? {}), active },
          className: active ? "data-flow-edge-active" : undefined,
        };
      }),
    [edges, workflowRun.activeEdgeNodeIds],
  );

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
        onNewWorkflow={handleNewWorkflow}
        onResetDraft={handleResetDraft}
        onExportWorkflow={handleExportWorkflow}
        onValidateWorkflow={() => {
          void handleValidateWorkflow();
        }}
        validating={validating}
        onRunWorkflow={() => {
          void handleRunWorkflow();
        }}
        onCancelRun={() => {
          void handleCancelRun();
        }}
        running={workflowRun.isLive}
        canRun={nodes.length > 0 && !workflowRun.isLive}
      />
      <NodeInspector node={selectedNode} onUpdateData={handleUpdateNodeData} />
      <AssetLibrary />
      <ActivityTimeline
        events={workflowRun.events}
        selectedNodeId={selectedNode?.id ?? null}
        runStatus={workflowRun.status}
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
      {warning ? (
        <div
          className="draft-warning"
          data-testid="draft-warning"
          role="alert"
        >
          {warning}
        </div>
      ) : null}
      {workflowRun.status === "cancelled" ? (
        <div
          className="run-stopped-banner"
          data-testid="run-stopped-banner"
          role="status"
        >
          Run stopped. Downstream nodes did not start.
          {workflowRun.errorMessage ? ` ${workflowRun.errorMessage}` : ""}
        </div>
      ) : null}
      {exportJson || validationResult ? (
        <div
          className="workflow-export-panel"
          data-testid="workflow-export-panel"
        >
          <div className="workflow-export-header">
            <span>Domain workflow</span>
            <button
              type="button"
              data-testid="workflow-export-close"
              onClick={() => {
                setExportJson(null);
                setValidationResult(null);
              }}
            >
              Close
            </button>
          </div>
          {validationResult ? (
            <div
              className={
                validationResult.valid
                  ? "workflow-validation-ok"
                  : "workflow-validation-error"
              }
              data-testid="workflow-validation-result"
              role="status"
            >
              {validationResult.valid ? (
                <p>Valid — settings returned intact from API.</p>
              ) : (
                <ul>
                  {validationResult.errors.map((error, index) => (
                    <li key={`${error.code}-${index}`}>{error.message}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
          {exportJson ? (
            <pre data-testid="workflow-export-json">{exportJson}</pre>
          ) : null}
        </div>
      ) : null}
      <ReactFlow
        nodes={displayNodes}
        edges={displayEdges}
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
