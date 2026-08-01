# Architecture glossary (playground KB)

Short definitions for Mitos Flow domain terms. Useful for multi-chunk KB retrieval demos.

## InputEnvelope

An envelope carries `port`, `payload`, `mediaType`, `sourceNodeId`, and `order`. Skills with multiple named inputs wait for every required port (`wait_for_all`) before running. Envelope order is sorted by port name so arrival timing cannot change FakeRunner output.

## Data-flow edge

A solid edge that moves payloads between nodes. Allowed pairs in v1: Input→Skill, Skill→Skill, Skill→Artifact Output. Cycles are rejected.

## Resource attachment edge

A dashed edge that attaches Knowledge Base or Rules nodes to Skills (and later prompt resources to Outputs). Resource edges do not carry run payloads; they contribute context before execution.

## Artifact Output

A sink node that receives upstream Skill results. Modes planned for later phases:

- **Pass-through** — emit the full upstream result (no model call)
- **Selector** — extract a field/section via JSONPath or heading (no model call)
- **Prompted** — second explicit model call with its own prompt template

## Capability probe

A read-only check that locates the Cursor CLI, reads `--version` / `--help`, and reports help-advertised features. It never runs user prompts.
