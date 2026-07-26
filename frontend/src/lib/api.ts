const DEFAULT_API_URL = "http://localhost:8000";

export function getApiUrl(): string {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  // In dev, use the Vite proxy (same-origin /api requests).
  if (import.meta.env.DEV) {
    return "";
  }
  return DEFAULT_API_URL;
}
