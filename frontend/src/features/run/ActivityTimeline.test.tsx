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
