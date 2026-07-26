import { useEffect, useState } from "react";
import {
  checkBackendHealth,
  type ConnectionStatus,
} from "./healthApi";

export function useBackendConnection() {
  const [status, setStatus] = useState<ConnectionStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const healthy = await checkBackendHealth();
      if (!cancelled) {
        setStatus(healthy ? "connected" : "disconnected");
      }
    }

    check();
    const interval = setInterval(check, 10_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return status;
}
