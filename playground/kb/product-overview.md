# Mitos Flow — product overview (playground KB)

Mitos Flow is a visual AI workflow builder. Users drag skills and rules onto a canvas, wire data-flow and resource attachments, and run the graph with a deterministic fake runner first, then Cursor CLI.

## v1 focus areas

- Named inputs with wait-for-all joins
- Managed local skill/rules/KB libraries
- Live run events and cancellation
- Artifact outputs (pass-through, selector, prompted — later phases)

## Runner strategy

The fake runner returns deterministic strings so UI, scheduler, and attachment wiring can be tested without spending tokens. The Cursor CLI adapter comes after the scheduler is stable. Skills may later choose Fake or Cursor per node.

## Knowledge bases

Knowledge bases are plain `.txt` / `.md` files imported into a managed library. Retrieval is keyword-based in v1 (no embeddings). Attachments are many-to-many: one KB can feed many Skills, and one Skill can attach many KBs. Per-attachment top-K and score threshold control how many chunks land in the run trace.

## Rules attachments

Rules are `.mdc` files with optional frontmatter. Attached rules are ordered by Rules node id before a Skill runs, and appear in the Activity timeline. Duplicate edges to the same Rules node are collapsed.

## What this file is for

This file is sample KB content for demos and regression stories. It should stay free of secrets and small enough to skim.
