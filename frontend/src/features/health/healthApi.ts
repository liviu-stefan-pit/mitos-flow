import { getApiUrl } from "../../lib/api";

export type ConnectionStatus = "checking" | "connected" | "disconnected";

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiUrl()}/api/health`);
    if (!response.ok) return false;
    const data = await response.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}
