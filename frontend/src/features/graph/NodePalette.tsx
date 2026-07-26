import { NODE_KIND_CONFIGS, type NodeKind } from "./nodeKinds";
import "./NodePalette.css";

type NodePaletteProps = {
  onAddNode: (kind: NodeKind) => void;
  onDeleteSelected: () => void;
  hasSelection: boolean;
};

export function NodePalette({
  onAddNode,
  onDeleteSelected,
  hasSelection,
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
    </div>
  );
}
