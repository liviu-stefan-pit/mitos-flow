import { useCallback, useEffect, useState } from "react";
import {
  FEATURE_LABELS,
  type CursorCapabilityReport,
  type CursorCapabilityStatus,
  type CursorFeatureFlags,
} from "../../domain/cursor";
import { CursorApiError, fetchCursorCapability } from "./cursorApi";
import "./SettingsPage.css";

const STATUS_LABEL: Record<CursorCapabilityStatus, string> = {
  absent: "Not found",
  available: "Available",
  unsupported_version: "Unsupported version",
  error: "Probe error",
};

function featureEntries(
  features: CursorFeatureFlags,
): Array<[keyof CursorFeatureFlags, boolean]> {
  return (Object.keys(FEATURE_LABELS) as Array<keyof CursorFeatureFlags>).map(
    (key) => [key, features[key]],
  );
}

export function SettingsPage() {
  const [report, setReport] = useState<CursorCapabilityReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchCursorCapability();
      setReport(next);
    } catch (err) {
      setReport(null);
      setError(
        err instanceof CursorApiError
          ? err.message
          : "Could not load Cursor CLI status.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="settings-page" data-testid="settings-page">
      <section
        className="settings-section"
        data-testid="cursor-cli-status"
        aria-labelledby="cursor-cli-heading"
      >
        <div className="settings-section-header">
          <div>
            <h2 id="cursor-cli-heading">Cursor CLI</h2>
            <p className="settings-section-blurb">
              Read-only probe: detects the local Cursor agent CLI, version, and
              features advertised by <code>--help</code>. Does not run prompts.
            </p>
          </div>
          <button
            type="button"
            className="settings-refresh"
            onClick={() => void refresh()}
            disabled={loading}
            data-testid="cursor-cli-refresh"
          >
            {loading ? "Probing…" : "Refresh"}
          </button>
        </div>

        {error ? (
          <p className="settings-error" data-testid="cursor-cli-error" role="alert">
            {error}
          </p>
        ) : null}

        {loading && !report ? (
          <p className="settings-muted" data-testid="cursor-cli-loading">
            Checking Cursor CLI…
          </p>
        ) : null}

        {report ? (
          <div className="cursor-status-body">
            <dl className="cursor-status-grid">
              <div>
                <dt>Status</dt>
                <dd>
                  <span
                    className={`cursor-status-badge status-${report.status}`}
                    data-testid="cursor-cli-status-value"
                  >
                    {STATUS_LABEL[report.status]}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd data-testid="cursor-cli-version">
                  {report.version ?? "—"}
                </dd>
              </div>
              <div>
                <dt>Minimum supported</dt>
                <dd data-testid="cursor-cli-minimum-version">
                  {report.minimumVersion}
                </dd>
              </div>
              <div className="cursor-status-wide">
                <dt>Executable</dt>
                <dd data-testid="cursor-cli-executable">
                  <code>{report.executable ?? "—"}</code>
                </dd>
              </div>
              <div className="cursor-status-wide">
                <dt>Message</dt>
                <dd data-testid="cursor-cli-message">{report.message}</dd>
              </div>
            </dl>

            <h3 className="settings-subheading">Features from help</h3>
            <ul
              className="cursor-feature-list"
              data-testid="cursor-cli-features"
            >
              {featureEntries(report.features).map(([key, enabled]) => (
                <li
                  key={key}
                  className={enabled ? "feature-on" : "feature-off"}
                  data-testid={`cursor-feature-${key}`}
                >
                  <span className="feature-mark" aria-hidden="true">
                    {enabled ? "✓" : "·"}
                  </span>
                  {FEATURE_LABELS[key]}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
