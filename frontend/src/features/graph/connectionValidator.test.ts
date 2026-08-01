import { describe, it, expect } from "vitest";
import {
  ALL_NODE_KINDS,
  isAllowedDataFlowPair,
  isAllowedResourcePair,
  validateConnection,
  type EdgeKind,
} from "./connectionValidator";
import type { NodeKind } from "./nodeKinds";
import {
  DATA_IN_HANDLE,
  DATA_OUT_HANDLE,
  RESOURCE_IN_HANDLE,
  RESOURCE_IN_TOP_HANDLE,
  RESOURCE_OUT_HANDLE,
} from "./handles";

function check(
  source: NodeKind,
  target: NodeKind,
  sourceHandle: string,
  targetHandle: string,
) {
  return validateConnection({
    sourceNodeId: `${source}-a`,
    targetNodeId: `${target}-b`,
    sourceKind: source,
    targetKind: target,
    sourceHandleId: sourceHandle,
    targetHandleId: targetHandle,
  });
}

describe("validateConnection — self-links", () => {
  it("rejects connecting a node to itself", () => {
    const result = validateConnection({
      sourceNodeId: "skill-1",
      targetNodeId: "skill-1",
      sourceKind: "skill",
      targetKind: "skill",
      sourceHandleId: DATA_OUT_HANDLE,
      targetHandleId: DATA_IN_HANDLE,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toMatch(/itself/i);
    }
  });
});

describe("validateConnection — handle mismatches", () => {
  it("rejects data-out → resource-in", () => {
    const result = check("input", "skill", DATA_OUT_HANDLE, RESOURCE_IN_HANDLE);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toMatch(/data ports and resource ports/i);
    }
  });

  it("rejects resource-out → data-in", () => {
    const result = check(
      "knowledgeBase",
      "skill",
      RESOURCE_OUT_HANDLE,
      DATA_IN_HANDLE,
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toMatch(/data ports and resource ports/i);
    }
  });

  it("rejects missing handle ids", () => {
    const result = validateConnection({
      sourceNodeId: "input-1",
      targetNodeId: "skill-1",
      sourceKind: "input",
      targetKind: "skill",
      sourceHandleId: null,
      targetHandleId: DATA_IN_HANDLE,
    });
    expect(result.ok).toBe(false);
  });

  it("rejects unknown node kinds", () => {
    const result = validateConnection({
      sourceNodeId: "x",
      targetNodeId: "y",
      sourceKind: null,
      targetKind: "skill",
      sourceHandleId: DATA_OUT_HANDLE,
      targetHandleId: DATA_IN_HANDLE,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toMatch(/unknown/i);
    }
  });
});

describe("validateConnection — every data-flow source×target pair", () => {
  const expectedAllowed: Array<{
    source: NodeKind;
    target: NodeKind;
    edgeKind: EdgeKind;
  }> = [
    { source: "input", target: "skill", edgeKind: "dataFlow" },
    { source: "skill", target: "skill", edgeKind: "dataFlow" },
    { source: "skill", target: "artifactOutput", edgeKind: "dataFlow" },
  ];

  it.each(expectedAllowed)(
    "allows $source → $target as dataFlow",
    ({ source, target, edgeKind }) => {
      const result = check(source, target, DATA_OUT_HANDLE, DATA_IN_HANDLE);
      expect(result).toEqual({ ok: true, edgeKind });
    },
  );

  it("rejects every other data-handle pair", () => {
    const allowed = new Set(
      expectedAllowed.map(({ source, target }) => `${source}->${target}`),
    );

    for (const source of ALL_NODE_KINDS) {
      for (const target of ALL_NODE_KINDS) {
        if (source === target) {
          // Covered by self-link test when ids match; here ids differ so
          // same-kind pairs that are not in the allow-list must still fail
          // except skill→skill which is allowed.
        }
        const key = `${source}->${target}`;
        const result = check(source, target, DATA_OUT_HANDLE, DATA_IN_HANDLE);
        if (allowed.has(key)) {
          expect(result.ok).toBe(true);
        } else {
          expect(result.ok).toBe(false);
          if (!result.ok) {
            expect(result.reason).toMatch(/data-flow/i);
          }
        }
      }
    }
  });

  it("isAllowedDataFlowPair matches the allow-list", () => {
    for (const source of ALL_NODE_KINDS) {
      for (const target of ALL_NODE_KINDS) {
        const expected = expectedAllowed.some(
          (p) => p.source === source && p.target === target,
        );
        expect(isAllowedDataFlowPair(source, target)).toBe(expected);
      }
    }
  });
});

describe("validateConnection — every resource source×target pair", () => {
  const expectedAllowed: Array<{
    source: NodeKind;
    target: NodeKind;
    edgeKind: EdgeKind;
  }> = [
    { source: "knowledgeBase", target: "skill", edgeKind: "resourceAttachment" },
    { source: "rules", target: "skill", edgeKind: "resourceAttachment" },
  ];

  it.each(expectedAllowed)(
    "allows $source → $target as resourceAttachment",
    ({ source, target, edgeKind }) => {
      const result = check(
        source,
        target,
        RESOURCE_OUT_HANDLE,
        RESOURCE_IN_HANDLE,
      );
      expect(result).toEqual({ ok: true, edgeKind });
    },
  );

  it("rejects every other resource-handle pair", () => {
    const allowed = new Set(
      expectedAllowed.map(({ source, target }) => `${source}->${target}`),
    );

    for (const source of ALL_NODE_KINDS) {
      for (const target of ALL_NODE_KINDS) {
        const key = `${source}->${target}`;
        const result = check(
          source,
          target,
          RESOURCE_OUT_HANDLE,
          RESOURCE_IN_HANDLE,
        );
        if (allowed.has(key)) {
          expect(result.ok).toBe(true);
        } else {
          expect(result.ok).toBe(false);
          if (!result.ok) {
            expect(result.reason).toMatch(/resource/i);
          }
        }
      }
    }
  });

  it("isAllowedResourcePair matches the allow-list", () => {
    for (const source of ALL_NODE_KINDS) {
      for (const target of ALL_NODE_KINDS) {
        const expected = expectedAllowed.some(
          (p) => p.source === source && p.target === target,
        );
        expect(isAllowedResourcePair(source, target)).toBe(expected);
      }
    }
  });
});

describe("validateConnection — invalid direction examples", () => {
  it("rejects Skill → Input (data)", () => {
    const result = check("skill", "input", DATA_OUT_HANDLE, DATA_IN_HANDLE);
    expect(result.ok).toBe(false);
  });

  it("rejects Artifact Output → Skill (data)", () => {
    const result = check(
      "artifactOutput",
      "skill",
      DATA_OUT_HANDLE,
      DATA_IN_HANDLE,
    );
    expect(result.ok).toBe(false);
  });

  it("rejects Skill → Knowledge Base (resource)", () => {
    const result = check(
      "skill",
      "knowledgeBase",
      RESOURCE_OUT_HANDLE,
      RESOURCE_IN_HANDLE,
    );
    expect(result.ok).toBe(false);
  });

  it("rejects Input → Artifact Output (data, skipping Skill)", () => {
    const result = check(
      "input",
      "artifactOutput",
      DATA_OUT_HANDLE,
      DATA_IN_HANDLE,
    );
    expect(result.ok).toBe(false);
  });

  it("rejects Knowledge Base → Artifact Output", () => {
    const result = check(
      "knowledgeBase",
      "artifactOutput",
      RESOURCE_OUT_HANDLE,
      RESOURCE_IN_HANDLE,
    );
    expect(result.ok).toBe(false);
  });
});

describe("validateConnection — dual Skill resource-in handles (Phase 28.5)", () => {
  it("accepts resource-out → resource-in-top (KB → Skill)", () => {
    const result = check(
      "knowledgeBase",
      "skill",
      RESOURCE_OUT_HANDLE,
      RESOURCE_IN_TOP_HANDLE,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.edgeKind).toBe("resourceAttachment");
    }
  });

  it("accepts resource-out → resource-in-top (Rules → Skill)", () => {
    const result = check(
      "rules",
      "skill",
      RESOURCE_OUT_HANDLE,
      RESOURCE_IN_TOP_HANDLE,
    );
    expect(result.ok).toBe(true);
  });

  it("still accepts resource-out → resource-in (bottom)", () => {
    const result = check(
      "knowledgeBase",
      "skill",
      RESOURCE_OUT_HANDLE,
      RESOURCE_IN_HANDLE,
    );
    expect(result.ok).toBe(true);
  });
});
