"""Deterministic DAG scheduler with named-input joins (Phase 14)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from mitos_api.domain.workflow import (
    ArtifactOutputMode,
    ArtifactOutputNodeSettings,
    AttachedKnowledgeBase,
    AttachedRule,
    EdgeKind,
    InputEnvelope,
    JoinPolicy,
    KnowledgeBaseNodeSettings,
    NodeKind,
    Port,
    PortDirection,
    PortKind,
    ResourceAttachmentSettings,
    RulesNodeSettings,
    SkillNodeSettings,
    ValidationIssue,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
)


@dataclass(frozen=True)
class LinearChainPlan:
    """
    Execution plan for Inputs → Skills → Artifact Outputs.

    Phase 14 allows multiple Input nodes and wait_for_all joins into a Skill
    via distinct named data-in ports. Passive output fan-out remains supported.
    Phase 26 allows pass-through and deterministic selector outputs.
    Phase 27 allows prompted projections (explicit second runner call).
    """

    input_nodes: list[WorkflowNode]
    skill_nodes: list[WorkflowNode]
    output_nodes: list[WorkflowNode]

    @property
    def input_node(self) -> WorkflowNode:
        """Convenience for single-input plans (Phase 11–13 callers)."""
        if len(self.input_nodes) != 1:
            raise ValueError(
                f"Expected exactly one input node, found {len(self.input_nodes)}"
            )
        return self.input_nodes[0]

    @property
    def output_node(self) -> WorkflowNode:
        """Convenience for single-output plans (Phase 11–12 callers)."""
        if len(self.output_nodes) != 1:
            raise ValueError(
                f"Expected exactly one output node, found {len(self.output_nodes)}"
            )
        return self.output_nodes[0]


def plan_linear_chain(
    workflow: Workflow,
) -> tuple[LinearChainPlan | None, list[ValidationIssue]]:
    """
    Validate Phase-14 graph shape and return a topo-ordered plan.

    Supported:
    - One or more Input nodes
    - One or more Skills (linear Skill→Skill path; joins into a Skill via
      distinct named data-in ports with wait_for_all)
    - One or more Artifact Outputs (pass-through, selector, or prompted) fed
      by a single terminal Skill

    Rejects: Input branching, Skill→Skill branching, same-port multi-edge,
    join policies other than wait_for_all.
    Resource nodes are ignored for scheduling.
    """
    by_kind: dict[NodeKind, list[WorkflowNode]] = {
        NodeKind.INPUT: [],
        NodeKind.SKILL: [],
        NodeKind.ARTIFACT_OUTPUT: [],
        NodeKind.KNOWLEDGE_BASE: [],
        NodeKind.RULES: [],
    }
    for node in workflow.nodes:
        by_kind[node.kind].append(node)

    errors: list[ValidationIssue] = []

    if len(by_kind[NodeKind.INPUT]) < 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 requires at least one Input node "
                    f"(found {len(by_kind[NodeKind.INPUT])})."
                ),
            )
        )
    if len(by_kind[NodeKind.SKILL]) < 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 requires at least one Skill node "
                    f"(found {len(by_kind[NodeKind.SKILL])})."
                ),
            )
        )
    if len(by_kind[NodeKind.ARTIFACT_OUTPUT]) < 1:
        errors.append(
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 requires at least one Artifact Output node "
                    f"(found {len(by_kind[NodeKind.ARTIFACT_OUTPUT])})."
                ),
            )
        )

    if errors:
        return None, errors

    input_nodes = by_kind[NodeKind.INPUT]
    output_nodes = by_kind[NodeKind.ARTIFACT_OUTPUT]
    skill_nodes = by_kind[NodeKind.SKILL]

    for skill in skill_nodes:
        if not isinstance(skill.settings, SkillNodeSettings):
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Skill settings are invalid.",
                    nodeId=skill.id,
                )
            ]
        if skill.settings.joinPolicy is not JoinPolicy.WAIT_FOR_ALL:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Phase 14 only supports join policy wait_for_all "
                        f"(got '{skill.settings.joinPolicy.value}')."
                    ),
                    nodeId=skill.id,
                )
            ]

    for output_node in output_nodes:
        if not isinstance(output_node.settings, ArtifactOutputNodeSettings):
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Artifact Output settings are invalid.",
                    nodeId=output_node.id,
                )
            ]
        mode = output_node.settings.mode
        # Phase 27: pass-through, selector, and prompted projections.
        if mode not in (
            ArtifactOutputMode.PASS_THROUGH,
            ArtifactOutputMode.SELECTOR,
            ArtifactOutputMode.PROMPTED,
        ):
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Unsupported Artifact Output mode "
                        f"'{mode.value}'."
                    ),
                    nodeId=output_node.id,
                )
            ]
        if mode is ArtifactOutputMode.SELECTOR:
            if output_node.settings.selectorKind is None or not (
                output_node.settings.selectorExpression or ""
            ).strip():
                return None, [
                    ValidationIssue(
                        code="unsupported_graph",
                        message=(
                            "Selector Artifact Outputs require selectorKind "
                            "and selectorExpression."
                        ),
                        nodeId=output_node.id,
                    )
                ]
        if mode is ArtifactOutputMode.PROMPTED:
            if not (output_node.settings.promptTemplate or "").strip():
                return None, [
                    ValidationIssue(
                        code="unsupported_graph",
                        message=(
                            "Prompted Artifact Outputs require a non-empty "
                            "promptTemplate."
                        ),
                        nodeId=output_node.id,
                    )
                ]

    chain_ids = {
        *(n.id for n in input_nodes),
        *(n.id for n in skill_nodes),
        *(n.id for n in output_nodes),
    }
    nodes_by_id = {n.id: n for n in workflow.nodes if n.id in chain_ids}
    output_ids = {n.id for n in output_nodes}
    skill_ids = {n.id for n in skill_nodes}
    input_ids = {n.id for n in input_nodes}

    data_edges = [
        e
        for e in workflow.edges
        if e.kind is EdgeKind.DATA_FLOW
        and e.sourceNodeId in chain_ids
        and e.targetNodeId in chain_ids
    ]

    successors: dict[str, list[str]] = defaultdict(list)
    predecessors: dict[str, list[str]] = defaultdict(list)
    inbound_edges: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in data_edges:
        successors[edge.sourceNodeId].append(edge.targetNodeId)
        predecessors[edge.targetNodeId].append(edge.sourceNodeId)
        inbound_edges[edge.targetNodeId].append(edge)

    # Each Skill data-in port accepts at most one data-flow edge.
    for skill in skill_nodes:
        seen_ports: dict[str, str] = {}
        for edge in inbound_edges[skill.id]:
            port_id = edge.targetPortId
            if port_id in seen_ports:
                return None, [
                    ValidationIssue(
                        code="unsupported_graph",
                        message=(
                            "Each Skill input port accepts at most one data-flow "
                            f"edge (port '{port_id}' on '{skill.id}' has multiple)."
                        ),
                        nodeId=skill.id,
                        edgeId=edge.id,
                    )
                ]
            port = _find_data_in_port(skill, port_id)
            if port is None:
                return None, [
                    ValidationIssue(
                        code="unsupported_graph",
                        message=(
                            f"Data-flow edge must target a data-in port on Skill "
                            f"'{skill.id}' (got '{port_id}')."
                        ),
                        nodeId=skill.id,
                        edgeId=edge.id,
                    )
                ]
            seen_ports[port_id] = edge.id

    # Inputs: exactly one data-flow out, to a Skill; no inbound data-flow.
    for input_node in input_nodes:
        if predecessors[input_node.id]:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Input nodes cannot have data-flow inputs.",
                    nodeId=input_node.id,
                )
            ]
        input_outs = successors[input_node.id]
        if len(input_outs) != 1:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Phase 14 does not support Input branching "
                        f"(Input has {len(input_outs)} data-flow outs)."
                    ),
                    nodeId=input_node.id,
                )
            ]
        if input_outs[0] not in skill_ids:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Input must connect to a Skill via data-flow.",
                    nodeId=input_node.id,
                )
            ]

    # Outputs: in-degree 1, out-degree 0; predecessor must be a Skill.
    for output_node in output_nodes:
        outs = successors[output_node.id]
        ins = predecessors[output_node.id]
        if outs:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Artifact Output nodes are sinks and cannot have "
                        "data-flow outs."
                    ),
                    nodeId=output_node.id,
                )
            ]
        if len(ins) != 1:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Each Artifact Output must have exactly one data-flow "
                        f"in (found {len(ins)})."
                    ),
                    nodeId=output_node.id,
                )
            ]
        if ins[0] not in skill_ids:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Artifact Output must be fed by a Skill.",
                    nodeId=output_node.id,
                )
            ]

    # Skills: at least one inbound; outs are either one Skill or only Outputs.
    terminal_skill_id: str | None = None
    for skill in skill_nodes:
        outs = successors[skill.id]
        ins = predecessors[skill.id]
        if not ins:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Each Skill must have at least one data-flow in.",
                    nodeId=skill.id,
                )
            ]
        if not outs:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message="Each Skill must have at least one data-flow out.",
                    nodeId=skill.id,
                )
            ]

        targets_are_all_outputs = all(t in output_ids for t in outs)
        targets_are_all_skills = all(t in skill_ids for t in outs)

        if targets_are_all_outputs:
            if terminal_skill_id is not None and terminal_skill_id != skill.id:
                return None, [
                    ValidationIssue(
                        code="unsupported_graph",
                        message=(
                            "Phase 14 allows only one terminal Skill to fan "
                            "out to Artifact Outputs."
                        ),
                        nodeId=skill.id,
                    )
                ]
            terminal_skill_id = skill.id
            continue

        if targets_are_all_skills and len(outs) == 1:
            continue

        return None, [
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 does not support Skill→Skill branching; only "
                    "the terminal Skill may fan out to Artifact Outputs "
                    f"(node '{skill.id}' has {len(outs)} data-flow outs)."
                ),
                nodeId=skill.id,
            )
        ]

    if terminal_skill_id is None:
        return None, [
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 requires the Skill chain to end by feeding "
                    "Artifact Output node(s)."
                ),
            )
        ]

    # Topo-order executable nodes (Inputs + Skills).
    executable_ids = {*input_ids, *skill_ids}
    order_ids = _topological_order(executable_ids, successors, predecessors)
    if order_ids is None:
        return None, [
            ValidationIssue(
                code="unsupported_graph",
                message="Phase 14 could not topologically order the execution graph.",
            )
        ]

    ordered_inputs = [nodes_by_id[nid] for nid in order_ids if nid in input_ids]
    ordered_skills = [nodes_by_id[nid] for nid in order_ids if nid in skill_ids]

    if len(ordered_inputs) != len(input_nodes) or len(ordered_skills) != len(skill_nodes):
        return None, [
            ValidationIssue(
                code="unsupported_graph",
                message=(
                    "Phase 14 requires every Input and Skill to participate "
                    "in the DAG that feeds Artifact Outputs."
                ),
            )
        ]

    if order_ids[-1] != terminal_skill_id:
        # Terminal skill must be last among executable nodes only if nothing
        # else is concurrent; with joins, other inputs may interleave earlier
        # but the terminal skill must still be the last skill. Verify that.
        if ordered_skills[-1].id != terminal_skill_id:
            return None, [
                ValidationIssue(
                    code="unsupported_graph",
                    message=(
                        "Skill chain must end at the terminal Skill that feeds outputs."
                    ),
                    nodeId=terminal_skill_id,
                )
            ]

    ordered_outputs = sorted(output_nodes, key=lambda n: n.id)
    # Stable input list by id for determinism in the plan surface.
    plan_inputs = sorted(ordered_inputs, key=lambda n: n.id)

    return (
        LinearChainPlan(
            input_nodes=plan_inputs,
            skill_nodes=ordered_skills,
            output_nodes=ordered_outputs,
        ),
        [],
    )


def collect_input_envelopes(
    skill: WorkflowNode,
    workflow: Workflow,
    completed_outputs: dict[str, tuple[str, str]],
    arrival_order: dict[str, int],
) -> tuple[list[InputEnvelope] | None, ValidationIssue | None]:
    """
    Apply wait_for_all: every data-in port on the Skill must have an envelope.

    Envelopes are returned sorted by port name so arrival order cannot change
    the runner-facing join result. The ``order`` field still records arrival.
    """
    data_in_ports = [
        port
        for port in skill.ports
        if port.kind is PortKind.DATA and port.direction is PortDirection.IN
    ]
    if not data_in_ports:
        return None, ValidationIssue(
            code="blocked",
            message=f"Skill '{skill.id}' has no data-in ports.",
            nodeId=skill.id,
        )

    ports_by_id = {port.id: port for port in data_in_ports}
    inbound = [
        edge
        for edge in workflow.edges
        if edge.kind is EdgeKind.DATA_FLOW and edge.targetNodeId == skill.id
    ]

    envelopes_by_port_id: dict[str, InputEnvelope] = {}
    for edge in inbound:
        port = ports_by_id.get(edge.targetPortId)
        if port is None:
            return None, ValidationIssue(
                code="blocked",
                message=(
                    f"Skill '{skill.id}' blocked: edge targets unknown data-in "
                    f"port '{edge.targetPortId}'."
                ),
                nodeId=skill.id,
                edgeId=edge.id,
            )
        upstream = completed_outputs.get(edge.sourceNodeId)
        if upstream is None:
            return None, ValidationIssue(
                code="blocked",
                message=(
                    f"Skill '{skill.id}' blocked waiting for upstream "
                    f"'{edge.sourceNodeId}' on port "
                    f"'{port.name or port.id}' (wait_for_all)."
                ),
                nodeId=skill.id,
            )
        payload, media_type = upstream
        envelopes_by_port_id[port.id] = InputEnvelope(
            port=port.name or port.id,
            payload=payload,
            mediaType=media_type,
            sourceNodeId=edge.sourceNodeId,
            order=arrival_order.get(edge.sourceNodeId, 0),
        )

    missing = [
        port.name or port.id
        for port in data_in_ports
        if port.id not in envelopes_by_port_id
    ]
    if missing:
        missing_list = ", ".join(sorted(missing))
        return None, ValidationIssue(
            code="blocked",
            message=(
                f"Skill '{skill.id}' blocked: missing inputs for port(s) "
                f"{missing_list} (wait_for_all)."
            ),
            nodeId=skill.id,
        )

    envelopes = sorted(envelopes_by_port_id.values(), key=lambda item: item.port)
    return envelopes, None


def collect_attached_rules(
    skill: WorkflowNode,
    workflow: Workflow,
) -> list[AttachedRule]:
    """
    Resolve Rules → Skill resource attachments before Skill execution (Phase 18).

    Many-to-many: one Rules node may attach to many Skills; many Rules may
    attach to one Skill. Duplicate edges to the same Rules node are collapsed
    so rule content is never duplicated in the runner request. Order is by
    Rules node id for deterministic FakeRunner / Cursor prompt assembly.
    Knowledge Base attachments are handled separately (Phase 19).
    """
    nodes_by_id = {node.id: node for node in workflow.nodes}
    seen: dict[str, WorkflowNode] = {}

    for edge in workflow.edges:
        if edge.kind is not EdgeKind.RESOURCE_ATTACHMENT:
            continue
        if edge.targetNodeId != skill.id:
            continue
        source = nodes_by_id.get(edge.sourceNodeId)
        if source is None or source.kind is not NodeKind.RULES:
            continue
        # First edge wins; later duplicates are ignored (no content duplication).
        if source.id not in seen:
            seen[source.id] = source

    ordered = sorted(seen.values(), key=lambda node: node.id)
    attached: list[AttachedRule] = []
    for index, node in enumerate(ordered):
        content = ""
        if isinstance(node.settings, RulesNodeSettings):
            content = node.settings.content
        attached.append(
            AttachedRule(
                rulesNodeId=node.id,
                label=node.label,
                content=content,
                order=index,
            )
        )
    return attached


def collect_attached_knowledge_bases(
    skill: WorkflowNode,
    workflow: Workflow,
) -> list[AttachedKnowledgeBase]:
    """
    Resolve Knowledge Base → Skill resource attachments (Phases 19–20).

    Many-to-many with dedupe by KB node id; order is by KB node id.
    Rules attachments are ignored here (Phase 18).
    Per-attachment ``topK`` / ``threshold`` come from the first resource edge
    for that KB→Skill link (duplicate edges collapse; first edge wins).
    """
    nodes_by_id = {node.id: node for node in workflow.nodes}
    # First edge wins for both content source and retrieval controls.
    seen: dict[str, tuple[WorkflowNode, ResourceAttachmentSettings | None]] = {}

    for edge in workflow.edges:
        if edge.kind is not EdgeKind.RESOURCE_ATTACHMENT:
            continue
        if edge.targetNodeId != skill.id:
            continue
        source = nodes_by_id.get(edge.sourceNodeId)
        if source is None or source.kind is not NodeKind.KNOWLEDGE_BASE:
            continue
        if source.id not in seen:
            seen[source.id] = (source, edge.settings)

    ordered = sorted(seen.items(), key=lambda item: item[0])
    attached: list[AttachedKnowledgeBase] = []
    defaults = ResourceAttachmentSettings()
    for index, (_kb_id, (node, edge_settings)) in enumerate(ordered):
        content = ""
        if isinstance(node.settings, KnowledgeBaseNodeSettings):
            content = node.settings.content
        top_k = edge_settings.topK if edge_settings is not None else defaults.topK
        threshold = (
            edge_settings.threshold
            if edge_settings is not None
            else defaults.threshold
        )
        attached.append(
            AttachedKnowledgeBase(
                kbNodeId=node.id,
                label=node.label,
                content=content,
                order=index,
                topK=top_k,
                threshold=threshold,
            )
        )
    return attached


def _find_data_in_port(skill: WorkflowNode, port_id: str) -> Port | None:
    for port in skill.ports:
        if (
            port.id == port_id
            and port.kind is PortKind.DATA
            and port.direction is PortDirection.IN
        ):
            return port
    return None


def _topological_order(
    node_ids: set[str],
    successors: dict[str, list[str]],
    predecessors: dict[str, list[str]],
) -> list[str] | None:
    """Kahn's algorithm; returns None if the graph is not a DAG covering all nodes."""
    in_degree = {
        nid: sum(1 for p in predecessors[nid] if p in node_ids) for nid in node_ids
    }
    queue: deque[str] = deque(
        sorted(nid for nid, deg in in_degree.items() if deg == 0)
    )
    order: list[str] = []

    while queue:
        if len(queue) > 1:
            items = sorted(queue)
            queue.clear()
            queue.extend(items)
        current = queue.popleft()
        order.append(current)
        for nxt in sorted(successors[current]):
            if nxt not in node_ids:
                continue
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(node_ids):
        return None
    return order
