import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_DRY_RUN_SKILL,
  FEATURE_LABELS,
  type CursorCapabilityReport,
  type CursorCapabilityStatus,
  type CursorDryRunResponse,
  type CursorFeatureFlags,
} from "../../domain/cursor";
import {
  CursorApiError,
  fetchCursorCapability,
  postCursorDryRun,
} from "./cursorApi";
import "./SettingsPage.css";

const STATUS_LABEL: Record<CursorCapabilityStatus, string> = {
  absent: "Not found",
  available: "Available",
  unsupported_version: "Unsupported version",
  error: "Probe error",
};

const DEFAULT_TIMEOUT_MS = 120_000;

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

  const [apiKey, setApiKey] = useState("");
  const [timeoutMs, setTimeoutMs] = useState(DEFAULT_TIMEOUT_MS);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunError, setDryRunError] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState<CursorDryRunResponse | null>(null);

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

  const runDryRun = useCallback(
    async (confirmed: boolean) => {
      if (!report?.executable) {
        setDryRunError(
          "Cursor CLI must be available before building a command preview.",
        );
        return;
      }
      setDryRunLoading(true);
      setDryRunError(null);
      try {
        const result = await postCursorDryRun({
          request: DEFAULT_DRY_RUN_SKILL,
          options: {
            executable: report.executable,
            features: report.features,
            apiKey: apiKey.trim() || null,
            timeoutMs,
            trust: true,
            force: false,
            outputFormat: "text",
            confirmed,
          },
        });
        setDryRun(result);
        if (!result.ok) {
          setDryRunError(result.errors.join(" ") || result.message);
        }
      } catch (err) {
        setDryRun(null);
        setDryRunError(
          err instanceof CursorApiError
            ? err.message
            : "Could not build Cursor dry-run preview.",
        );
      } finally {
        setDryRunLoading(false);
      }
    },
    [apiKey, report, timeoutMs],
  );

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

      <section
        className="settings-section settings-section-spaced"
        data-testid="cursor-dry-run"
        aria-labelledby="cursor-dry-run-heading"
      >
        <div className="settings-section-header">
          <div>
            <h2 id="cursor-dry-run-heading">Cursor command dry-run</h2>
            <p className="settings-section-blurb">
              Builds argv + stdin from a sample Skill request without spawning.
              Secrets are redacted in the preview. Confirm after reviewing, then
              use Fake/Cursor on the canvas to run Input → Skill → Output.
            </p>
          </div>
        </div>

        <div className="dry-run-form">
          <label className="dry-run-field">
            <span>Timeout (ms)</span>
            <input
              type="number"
              min={1}
              value={timeoutMs}
              onChange={(event) =>
                setTimeoutMs(Number(event.target.value) || DEFAULT_TIMEOUT_MS)
              }
              data-testid="cursor-dry-run-timeout"
            />
          </label>
          <label className="dry-run-field">
            <span>API key (optional — redacted in preview)</span>
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-…"
              data-testid="cursor-dry-run-api-key"
            />
          </label>
        </div>

        <div className="dry-run-actions">
          <button
            type="button"
            className="settings-refresh"
            disabled={dryRunLoading || !report?.executable}
            onClick={() => void runDryRun(false)}
            data-testid="cursor-dry-run-preview"
          >
            {dryRunLoading ? "Building…" : "Preview command"}
          </button>
          <button
            type="button"
            className="settings-confirm"
            disabled={
              dryRunLoading || !dryRun?.ok || !dryRun.preview || dryRun.confirmed
            }
            onClick={() => void runDryRun(true)}
            data-testid="cursor-dry-run-confirm"
          >
            Confirm preview
          </button>
        </div>

        {dryRunError ? (
          <p
            className="settings-error"
            data-testid="cursor-dry-run-error"
            role="alert"
          >
            {dryRunError}
          </p>
        ) : null}

        {dryRun?.preview ? (
          <div className="dry-run-preview" data-testid="cursor-dry-run-preview-panel">
            <p
              className={`dry-run-status ${dryRun.confirmed ? "confirmed" : "pending"}`}
              data-testid="cursor-dry-run-status"
            >
              {dryRun.message}
            </p>
            <dl className="cursor-status-grid">
              <div>
                <dt>Timeout</dt>
                <dd data-testid="cursor-dry-run-preview-timeout">
                  {dryRun.preview.timeoutMs} ms
                </dd>
              </div>
              <div>
                <dt>Spawned</dt>
                <dd data-testid="cursor-dry-run-spawned">
                  {dryRun.spawned ? "yes" : "no"}
                </dd>
              </div>
              <div className="cursor-status-wide">
                <dt>Workspace</dt>
                <dd data-testid="cursor-dry-run-workspace">
                  <code>{dryRun.preview.workspace}</code>
                </dd>
              </div>
              <div className="cursor-status-wide">
                <dt>Command (redacted)</dt>
                <dd>
                  <pre
                    className="dry-run-command"
                    data-testid="cursor-dry-run-command"
                  >
                    {dryRun.preview.commandDisplay}
                  </pre>
                </dd>
              </div>
              <div className="cursor-status-wide">
                <dt>Stdin preview</dt>
                <dd>
                  <pre
                    className="dry-run-stdin"
                    data-testid="cursor-dry-run-stdin"
                  >
                    {dryRun.preview.stdinPreview}
                  </pre>
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
      </section>
    </div>
  );
}
