import { ConnectionStatusIndicator } from "./features/health/ConnectionStatusIndicator";
import { useBackendConnection } from "./features/health/useBackendConnection";
import { WorkflowCanvas } from "./features/graph/WorkflowCanvas";
import "./App.css";

export function App() {
  const connectionStatus = useBackendConnection();

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Mitos Flow</h1>
        <ConnectionStatusIndicator status={connectionStatus} />
      </header>
      <main className="workspace">
        <WorkflowCanvas />
      </main>
    </div>
  );
}
