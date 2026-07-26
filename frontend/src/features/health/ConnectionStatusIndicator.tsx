import type { ConnectionStatus } from "./healthApi";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { label: string; className: string }
> = {
  checking: { label: "Checking…", className: "status-checking" },
  connected: { label: "Backend connected", className: "status-connected" },
  disconnected: {
    label: "Backend disconnected",
    className: "status-disconnected",
  },
};

interface ConnectionStatusProps {
  status: ConnectionStatus;
}

export function ConnectionStatusIndicator({ status }: ConnectionStatusProps) {
  const { label, className } = STATUS_CONFIG[status];

  return (
    <div className={`connection-status ${className}`} data-testid="connection-status">
      <span className="status-dot" />
      <span className="status-label">{label}</span>
    </div>
  );
}
