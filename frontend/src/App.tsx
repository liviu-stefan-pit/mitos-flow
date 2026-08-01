import { useState } from "react";
import { ConnectionStatusIndicator } from "./features/health/ConnectionStatusIndicator";
import { useBackendConnection } from "./features/health/useBackendConnection";
import { WorkflowCanvas } from "./features/graph/WorkflowCanvas";
import { SettingsPage } from "./features/settings/SettingsPage";
import "./App.css";

type AppView = "workspace" | "settings";

export function App() {
  const connectionStatus = useBackendConnection();
  const [view, setView] = useState<AppView>("workspace");

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Mitos Flow</h1>
        <div className="app-header-actions">
          <nav className="app-nav" aria-label="Primary">
            <button
              type="button"
              className={`app-nav-button${view === "workspace" ? " active" : ""}`}
              onClick={() => setView("workspace")}
              data-testid="nav-workspace"
              aria-current={view === "workspace" ? "page" : undefined}
            >
              Workspace
            </button>
            <button
              type="button"
              className={`app-nav-button${view === "settings" ? " active" : ""}`}
              onClick={() => setView("settings")}
              data-testid="nav-settings"
              aria-current={view === "settings" ? "page" : undefined}
            >
              Settings
            </button>
          </nav>
          <ConnectionStatusIndicator status={connectionStatus} />
        </div>
      </header>
      <main className="workspace">
        {view === "workspace" ? <WorkflowCanvas /> : <SettingsPage />}
      </main>
    </div>
  );
}
