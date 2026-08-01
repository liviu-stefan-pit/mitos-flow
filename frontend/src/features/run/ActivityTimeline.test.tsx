import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { RunEvent } from "../../domain/run";
import { ActivityTimeline } from "./ActivityTimeline";

describe("ActivityTimeline — attached rules (Phase 18)", () => {
  it("renders attached rules from a Skill completed event", () => {
    const events: RunEvent[] = [
      {
        id: "run-1:1",
        seq: 1,
        type: "completed",
        scope: "node",
        runId: "run-1",
        nodeId: "skill-1",
        message: "Attached 2 rule(s): Types, Tone",
        attachedRules: [
          {
            rulesNodeId: "rules-a",
            label: "Types",
            content: "Annotate public APIs.",
            order: 0,
          },
          {
            rulesNodeId: "rules-b",
            label: "Tone",
            content: "Keep replies concise.",
            order: 1,
          },
        ],
        timestamp: "2026-08-01T00:00:00Z",
      },
    ];

    render(
      <ActivityTimeline
        events={events}
        selectedNodeId={null}
        runStatus="completed"
      />,
    );

    expect(screen.getByTestId("activity-event-rules")).toBeInTheDocument();
    const rules = screen.getAllByTestId("activity-attached-rule");
    expect(rules).toHaveLength(2);
    expect(rules[0]).toHaveAttribute("data-rules-node-id", "rules-a");
    expect(rules[1]).toHaveAttribute("data-rules-node-id", "rules-b");
    expect(screen.getByText("Attached 2 rule(s): Types, Tone")).toBeInTheDocument();
  });
});

describe("ActivityTimeline — cited KB chunks (Phase 19–20)", () => {
  it("renders query, chunk ids, and citations from a Skill completed event", () => {
    const events: RunEvent[] = [
      {
        id: "run-2:1",
        seq: 1,
        type: "completed",
        scope: "node",
        runId: "run-2",
        nodeId: "skill-1",
        message:
          "Query: What is Mitos Flow?; Retrieved 1 KB chunk(s) [kb-product:c0]: Product docs#0",
        knowledgeQuery: "What is Mitos Flow?",
        knowledgeChunks: [
          {
            chunkId: "kb-product:c0",
            kbNodeId: "kb-product",
            kbLabel: "Product docs",
            text: "Mitos Flow is a visual AI workflow builder.",
            score: 3,
            citation: "Product docs#0",
            order: 0,
          },
        ],
        timestamp: "2026-08-01T00:00:00Z",
      },
    ];

    render(
      <ActivityTimeline
        events={events}
        selectedNodeId={null}
        runStatus="completed"
      />,
    );

    expect(screen.getByTestId("activity-knowledge-query")).toHaveTextContent(
      "Query: What is Mitos Flow?",
    );
    expect(screen.getByTestId("activity-event-kb")).toBeInTheDocument();
    const chunks = screen.getAllByTestId("activity-cited-chunk");
    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toHaveAttribute("data-chunk-id", "kb-product:c0");
    expect(chunks[0]).toHaveAttribute("data-kb-node-id", "kb-product");
    expect(screen.getByText("Product docs#0")).toBeInTheDocument();
    expect(screen.getByText("kb-product:c0")).toBeInTheDocument();
  });
});

describe("ActivityTimeline — run summary (Phase 28)", () => {
  it("shows token counts and estimated cost with disclaimer", () => {
    render(
      <ActivityTimeline
        events={[]}
        selectedNodeId={null}
        runStatus="completed"
        summary={{
          inputTokens: 100,
          outputTokens: 50,
          totalTokens: 150,
          estimatedCostUsd: 0.00125,
          costIsEstimate: true,
          rateTableVersion: 1,
          disclaimer:
            "Estimated cost from a local rate table — not an exact charge.",
          usageAvailable: true,
          pricingAvailable: true,
          callCount: 1,
        }}
      />,
    );

    expect(screen.getByTestId("activity-run-summary")).toBeInTheDocument();
    expect(screen.getByTestId("summary-input-tokens")).toHaveTextContent("100");
    expect(screen.getByTestId("summary-output-tokens")).toHaveTextContent("50");
    expect(screen.getByTestId("summary-total-tokens")).toHaveTextContent("150");
    const cost = screen.getByTestId("summary-estimated-cost");
    expect(cost).toHaveTextContent(/est\./i);
    expect(cost).not.toHaveTextContent(/exact/i);
    expect(screen.getByTestId("summary-disclaimer")).toHaveTextContent(
      /not an exact charge/i,
    );
  });

  it("shows unknown when usage and pricing are unavailable", () => {
    render(
      <ActivityTimeline
        events={[]}
        selectedNodeId={null}
        runStatus="completed"
        summary={{
          inputTokens: null,
          outputTokens: null,
          totalTokens: null,
          estimatedCostUsd: null,
          costIsEstimate: true,
          disclaimer:
            "Estimated cost from a local rate table — not an exact charge.",
          usageAvailable: false,
          pricingAvailable: false,
          callCount: 0,
        }}
      />,
    );

    expect(screen.getByTestId("summary-input-tokens")).toHaveTextContent(
      "unknown",
    );
    expect(screen.getByTestId("summary-output-tokens")).toHaveTextContent(
      "unknown",
    );
    expect(screen.getByTestId("summary-total-tokens")).toHaveTextContent(
      "unknown",
    );
    expect(screen.getByTestId("summary-estimated-cost")).toHaveTextContent(
      "unknown",
    );
  });

  it("never presents estimates as exact charges", () => {
    render(
      <ActivityTimeline
        events={[]}
        selectedNodeId={null}
        runStatus="completed"
        summary={{
          inputTokens: 10,
          outputTokens: 5,
          totalTokens: 15,
          estimatedCostUsd: 0,
          costIsEstimate: true,
          disclaimer:
            "Estimated cost from a local rate table — not an exact charge.",
          usageAvailable: true,
          pricingAvailable: true,
        }}
      />,
    );

    const cost = screen.getByTestId("summary-estimated-cost");
    expect(cost.textContent?.toLowerCase()).toMatch(/est\./);
    expect(cost.textContent?.toLowerCase()).not.toMatch(/exact charge/);
    expect(screen.getByTestId("summary-disclaimer").textContent).toMatch(
      /not an exact charge/i,
    );
  });
});
