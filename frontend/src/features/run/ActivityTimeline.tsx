import type { RunEvent, RunSummary } from "../../domain/run";
import "./ActivityTimeline.css";

type ActivityTimelineProps = {
  events: RunEvent[];
  selectedNodeId: string | null;
  runStatus: string;
  summary?: RunSummary | null;
};

function formatTokens(value: number | null | undefined): string {
  return value == null ? "unknown" : String(value);
}

function formatEstimatedCost(summary: RunSummary): string {
  if (summary.estimatedCostUsd == null) {
    return "unknown";
  }
  // Always label as estimate — never present as an exact charge.
  const amount = summary.estimatedCostUsd.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
  return `est. ${amount}`;
}

export function ActivityTimeline({
  events,
  selectedNodeId,
  runStatus,
  summary = null,
}: ActivityTimelineProps) {
  const filtered = selectedNodeId
    ? events.filter(
        (event) =>
          (event.scope === "node" && event.nodeId === selectedNodeId) ||
          (event.scope === "run" &&
            (event.type === "queued" ||
              event.type === "running" ||
              event.type === "completed" ||
              event.type === "failed" ||
              event.type === "cancelled")),
      )
    : events;

  const showSummary =
    summary != null &&
    (runStatus === "completed" ||
      runStatus === "failed" ||
      runStatus === "cancelled");

  return (
    <aside
      className="activity-timeline"
      data-testid="activity-timeline"
      aria-label="Run activity timeline"
    >
      <div className="activity-timeline-header">
        <span>Activity</span>
        <span
          className={`activity-timeline-status status-${runStatus}`}
          data-testid="activity-run-status"
        >
          {runStatus}
        </span>
      </div>
      {showSummary ? (
        <div
          className="activity-run-summary"
          data-testid="activity-run-summary"
          role="region"
          aria-label="Run summary"
        >
          <div className="activity-run-summary-title">Run summary</div>
          <dl className="activity-run-summary-stats">
            <div>
              <dt>Input tokens</dt>
              <dd data-testid="summary-input-tokens">
                {formatTokens(summary.inputTokens)}
              </dd>
            </div>
            <div>
              <dt>Output tokens</dt>
              <dd data-testid="summary-output-tokens">
                {formatTokens(summary.outputTokens)}
              </dd>
            </div>
            <div>
              <dt>Total tokens</dt>
              <dd data-testid="summary-total-tokens">
                {formatTokens(summary.totalTokens)}
              </dd>
            </div>
            <div>
              <dt>Estimated cost</dt>
              <dd data-testid="summary-estimated-cost">
                {formatEstimatedCost(summary)}
              </dd>
            </div>
          </dl>
          <p
            className="activity-run-summary-disclaimer"
            data-testid="summary-disclaimer"
          >
            {summary.disclaimer ??
              "Estimated cost from a local rate table — not an exact charge."}
          </p>
        </div>
      ) : null}
      {selectedNodeId ? (
        <p className="activity-timeline-filter" data-testid="activity-filter">
          Showing events for selected node + run lifecycle
        </p>
      ) : (
        <p className="activity-timeline-filter">All run events</p>
      )}
      {filtered.length === 0 ? (
        <p className="activity-timeline-empty" data-testid="activity-empty">
          Start a run to see live progress.
        </p>
      ) : (
        <ol className="activity-timeline-list" data-testid="activity-event-list">
          {filtered.map((event) => (
            <li
              key={event.id}
              className={`activity-event scope-${event.scope} type-${event.type}`}
              data-testid="activity-event"
              data-event-id={event.id}
              data-event-type={event.type}
              data-event-scope={event.scope}
              data-node-id={event.nodeId ?? undefined}
            >
              <span className="activity-event-type">
                {event.scope}:{event.type}
              </span>
              {event.nodeId ? (
                <span className="activity-event-node">{event.nodeId}</span>
              ) : null}
              {event.message ? (
                <span className="activity-event-message">{event.message}</span>
              ) : null}
              {event.attachedRules && event.attachedRules.length > 0 ? (
                <ul
                  className="activity-event-rules"
                  data-testid="activity-event-rules"
                >
                  {event.attachedRules.map((rule) => (
                    <li
                      key={`${event.id}-${rule.rulesNodeId}`}
                      data-testid="activity-attached-rule"
                      data-rules-node-id={rule.rulesNodeId}
                    >
                      <strong>{rule.label}</strong>
                      {rule.content ? (
                        <span title={rule.content}>
                          {rule.content.length > 60
                            ? `${rule.content.slice(0, 60)}…`
                            : rule.content}
                        </span>
                      ) : (
                        <span>(empty)</span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : null}
              {event.knowledgeQuery ? (
                <span
                  className="activity-event-query"
                  data-testid="activity-knowledge-query"
                >
                  Query: {event.knowledgeQuery}
                </span>
              ) : null}
              {event.knowledgeChunks && event.knowledgeChunks.length > 0 ? (
                <ul
                  className="activity-event-kb"
                  data-testid="activity-event-kb"
                >
                  {event.knowledgeChunks.map((chunk) => (
                    <li
                      key={`${event.id}-${chunk.chunkId}`}
                      data-testid="activity-cited-chunk"
                      data-chunk-id={chunk.chunkId}
                      data-kb-node-id={chunk.kbNodeId}
                    >
                      <strong>{chunk.citation}</strong>
                      <span className="activity-chunk-id">{chunk.chunkId}</span>
                      <span title={chunk.text}>
                        {chunk.text.length > 60
                          ? `${chunk.text.slice(0, 60)}…`
                          : chunk.text}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {event.elapsedMs != null || event.exitCode != null || event.model ? (
                <span
                  className="activity-event-capture"
                  data-testid="activity-cursor-capture"
                >
                  {event.model ? (
                    <span data-testid="activity-cursor-model">
                      model {event.model}
                    </span>
                  ) : null}
                  {event.model &&
                  (event.elapsedMs != null || event.exitCode != null)
                    ? " · "
                    : null}
                  {event.elapsedMs != null ? `${event.elapsedMs}ms` : null}
                  {event.elapsedMs != null && event.exitCode != null
                    ? " · "
                    : null}
                  {event.exitCode != null ? `exit ${event.exitCode}` : null}
                  {event.usage?.totalTokens != null
                    ? ` · tokens ${event.usage.totalTokens}`
                    : event.usage?.inputTokens != null ||
                        event.usage?.outputTokens != null
                      ? ` · tokens in=${event.usage.inputTokens ?? "?"} out=${event.usage.outputTokens ?? "?"}`
                      : null}
                </span>
              ) : null}
              {event.artifactPath ? (
                <span
                  className="activity-event-artifact"
                  data-testid="activity-artifact-path"
                  title={event.artifactAbsolutePath ?? event.artifactPath}
                >
                  Saved {event.bytesWritten != null ? `${event.bytesWritten} bytes → ` : ""}
                  {event.artifactPath}
                </span>
              ) : null}
              {event.promptTemplate ? (
                <span
                  className="activity-event-prompt"
                  data-testid="activity-prompt-template"
                  title={event.promptTemplate}
                >
                  Prompt:{" "}
                  {event.promptTemplate.length > 60
                    ? `${event.promptTemplate.slice(0, 60)}…`
                    : event.promptTemplate}
                </span>
              ) : null}
              {event.error ? (
                <span className="activity-event-error">{event.error}</span>
              ) : null}
              {event.output ? (
                <span className="activity-event-output" title={event.output}>
                  {event.output.length > 80
                    ? `${event.output.slice(0, 80)}…`
                    : event.output}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
