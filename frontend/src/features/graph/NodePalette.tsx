import { NODE_KIND_CONFIGS, type NodeKind } from "./nodeKinds";
import "./NodePalette.css";

type NodePaletteProps = {
  onAddNode: (kind: NodeKind) => void;
  onDeleteSelected: () => void;
  hasSelection: boolean;
  onNewWorkflow: () => void;
  onResetDraft: () => void;
  onExportWorkflow: () => void;
  onValidateWorkflow: () => void;
  validating?: boolean;
  onRunWorkflow?: () => void;
  onCancelRun?: () => void;
  running?: boolean;
  canRun?: boolean;
  /** True when any Skill on the canvas uses the Cursor runner. */
  hasCursorSkill?: boolean;
};

export function NodePalette({
  onAddNode,
  onDeleteSelected,
  hasSelection,
  onNewWorkflow,
  onResetDraft,
  onExportWorkflow,
  onValidateWorkflow,
  validating = false,
  onRunWorkflow,
  onCancelRun,
  running = false,
  canRun = true,
  hasCursorSkill = false,
}: NodePaletteProps) {
  return (
    <div className="node-palette" data-testid="node-palette">
      <div className="node-palette-section">
        <span className="node-palette-label">Add node</span>
        <div className="node-palette-buttons">
          {NODE_KIND_CONFIGS.map((config) => (
            <button
              key={config.kind}
              type="button"
              data-testid={`palette-add-${config.kind}`}
              onClick={() => onAddNode(config.kind)}
            >
              {config.displayName}
            </button>
          ))}
        </div>
      </div>
      <div className="node-palette-section">
        <button
          type="button"
          data-testid="palette-delete-selected"
          disabled={!hasSelection}
          onClick={onDeleteSelected}
        >
          Delete selected
        </button>
      </div>
      <div className="node-palette-section node-palette-draft-actions">
        <button
          type="button"
          data-testid="palette-new-workflow"
          onClick={onNewWorkflow}
        >
          New Workflow
        </button>
        <button
          type="button"
          data-testid="palette-reset-draft"
          onClick={onResetDraft}
        >
          Reset Draft
        </button>
      </div>
      <div className="node-palette-section node-palette-api-actions">
        <span className="node-palette-label">Workflow API</span>
        <button
          type="button"
          data-testid="palette-export-workflow"
          onClick={onExportWorkflow}
        >
          Export JSON
        </button>
        <button
          type="button"
          data-testid="palette-validate-workflow"
          disabled={validating}
          onClick={onValidateWorkflow}
        >
          {validating ? "Validating…" : "Validate with API"}
        </button>
      </div>
      {onRunWorkflow ? (
        <div className="node-palette-section node-palette-run-actions">
          <span className="node-palette-label">Run</span>
          <p className="node-palette-hint" data-testid="palette-runner-hint">
            Per-Skill runner is set in the inspector (Fake or Cursor).
          </p>
          <button
            type="button"
            data-testid="palette-run-workflow"
            disabled={!canRun || running}
            onClick={onRunWorkflow}
          >
            {running
              ? "Running…"
              : hasCursorSkill
                ? "Run (includes Cursor)"
                : "Run workflow"}
          </button>
          <button
            type="button"
            data-testid="palette-cancel-run"
            disabled={!running}
            onClick={onCancelRun}
          >
            Cancel run
          </button>
        </div>
      ) : null}
    </div>
  );
}
