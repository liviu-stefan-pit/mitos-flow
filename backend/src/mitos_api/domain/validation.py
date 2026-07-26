"""Structural workflow validation (DAG, edges, IDs) — Phase 9."""

from __future__ import annotations

from collections import defaultdict, deque

from mitos_api.domain.workflow import (
    EdgeKind,
    NodeKind,
    PortDirection,
    PortKind,
    ValidationIssue,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowValidationResult,
)

# Allowed data-flow pairs: source kind → target kind (mirrors frontend validator).
_DATA_FLOW_PAIRS: frozenset[tuple[NodeKind, NodeKind]] = frozenset(
    {
        (NodeKind.INPUT, NodeKind.SKILL),
        (NodeKind.SKILL, NodeKind.SKILL),
        (NodeKind.SKILL, NodeKind.ARTIFACT_OUTPUT),
    }
)

_RESOURCE_PAIRS: frozenset[tuple[NodeKind, NodeKind]] = frozenset(
    {
        (NodeKind.KNOWLEDGE_BASE, NodeKind.SKILL),
        (NodeKind.RULES, NodeKind.SKILL),
    }
)


def validate_workflow(workflow: Workflow) -> WorkflowValidationResult:
    """Validate graph integrity. Does not execute the workflow."""
    errors: list[ValidationIssue] = []

    errors.extend(_check_duplicate_node_ids(workflow.nodes))
    errors.extend(_check_duplicate_edge_ids(workflow.edges))

    nodes_by_id = {node.id: node for node in workflow.nodes}

    for edge in workflow.edges:
        errors.extend(_validate_edge(edge, nodes_by_id))

    # Cycle check only when IDs are unique enough to build an adjacency map.
    if not any(e.code == "duplicate_node_id" for e in errors):
        errors.extend(_check_cycles(workflow.edges, set(nodes_by_id)))

    if errors:
        return WorkflowValidationResult(valid=False, errors=errors, workflow=None)

    return WorkflowValidationResult(valid=True, errors=[], workflow=workflow)


def _check_duplicate_node_ids(nodes: list[WorkflowNode]) -> list[ValidationIssue]:
    seen: set[str] = set()
    errors: list[ValidationIssue] = []
    for node in nodes:
        if node.id in seen:
            errors.append(
                ValidationIssue(
                    code="duplicate_node_id",
                    message=f"Duplicate node id '{node.id}'.",
                    nodeId=node.id,
                )
            )
        else:
            seen.add(node.id)
    return errors


def _check_duplicate_edge_ids(edges: list[WorkflowEdge]) -> list[ValidationIssue]:
    seen: set[str] = set()
    errors: list[ValidationIssue] = []
    for edge in edges:
        if edge.id in seen:
            errors.append(
                ValidationIssue(
                    code="duplicate_edge_id",
                    message=f"Duplicate edge id '{edge.id}'.",
                    edgeId=edge.id,
                )
            )
        else:
            seen.add(edge.id)
    return errors


def _validate_edge(
    edge: WorkflowEdge,
    nodes_by_id: dict[str, WorkflowNode],
) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []

    if edge.sourceNodeId == edge.targetNodeId:
        errors.append(
            ValidationIssue(
                code="self_link",
                message="Cannot connect a node to itself.",
                edgeId=edge.id,
                nodeId=edge.sourceNodeId,
            )
        )
        return errors

    source = nodes_by_id.get(edge.sourceNodeId)
    target = nodes_by_id.get(edge.targetNodeId)

    if source is None:
        errors.append(
            ValidationIssue(
                code="dangling_edge",
                message=f"Edge source node '{edge.sourceNodeId}' does not exist.",
                edgeId=edge.id,
            )
        )
    if target is None:
        errors.append(
            ValidationIssue(
                code="dangling_edge",
                message=f"Edge target node '{edge.targetNodeId}' does not exist.",
                edgeId=edge.id,
            )
        )
    if source is None or target is None:
        return errors

    source_port = _find_port(source, edge.sourcePortId)
    target_port = _find_port(target, edge.targetPortId)

    if source_port is None:
        errors.append(
            ValidationIssue(
                code="unknown_port",
                message=(
                    f"Source port '{edge.sourcePortId}' not found on "
                    f"node '{source.id}'."
                ),
                edgeId=edge.id,
                nodeId=source.id,
            )
        )
    if target_port is None:
        errors.append(
            ValidationIssue(
                code="unknown_port",
                message=(
                    f"Target port '{edge.targetPortId}' not found on "
                    f"node '{target.id}'."
                ),
                edgeId=edge.id,
                nodeId=target.id,
            )
        )
    if source_port is None or target_port is None:
        return errors

    if source_port.direction is not PortDirection.OUT:
        errors.append(
            ValidationIssue(
                code="invalid_port_direction",
                message=f"Source port '{source_port.id}' must be an output port.",
                edgeId=edge.id,
                nodeId=source.id,
            )
        )
    if target_port.direction is not PortDirection.IN:
        errors.append(
            ValidationIssue(
                code="invalid_port_direction",
                message=f"Target port '{target_port.id}' must be an input port.",
                edgeId=edge.id,
                nodeId=target.id,
            )
        )

    if source_port.kind != target_port.kind:
        errors.append(
            ValidationIssue(
                code="port_kind_mismatch",
                message="Data ports and resource ports cannot be connected.",
                edgeId=edge.id,
            )
        )
        return errors

    expected_edge_kind = (
        EdgeKind.DATA_FLOW
        if source_port.kind is PortKind.DATA
        else EdgeKind.RESOURCE_ATTACHMENT
    )
    if edge.kind is not expected_edge_kind:
        errors.append(
            ValidationIssue(
                code="invalid_edge_kind",
                message=(
                    f"Edge kind '{edge.kind.value}' does not match port kinds "
                    f"(expected '{expected_edge_kind.value}')."
                ),
                edgeId=edge.id,
            )
        )
        return errors

    if edge.kind is EdgeKind.DATA_FLOW:
        if (source.kind, target.kind) not in _DATA_FLOW_PAIRS:
            errors.append(
                ValidationIssue(
                    code="invalid_edge_kind",
                    message=(
                        "Data-flow edges are only allowed from Input→Skill, "
                        "Skill→Skill, or Skill→Artifact Output "
                        f"(got {source.kind.value}→{target.kind.value})."
                    ),
                    edgeId=edge.id,
                )
            )
    else:
        if (source.kind, target.kind) not in _RESOURCE_PAIRS:
            errors.append(
                ValidationIssue(
                    code="invalid_edge_kind",
                    message=(
                        "Resource edges are only allowed from Knowledge Base→Skill "
                        "or Rules→Skill "
                        f"(got {source.kind.value}→{target.kind.value})."
                    ),
                    edgeId=edge.id,
                )
            )

    return errors


def _find_port(node: WorkflowNode, port_id: str):
    for port in node.ports:
        if port.id == port_id:
            return port
    return None


def _check_cycles(
    edges: list[WorkflowEdge],
    node_ids: set[str],
) -> list[ValidationIssue]:
    """Reject directed cycles on data-flow edges (execution DAG)."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for edge in edges:
        if edge.kind is not EdgeKind.DATA_FLOW:
            continue
        if edge.sourceNodeId not in node_ids or edge.targetNodeId not in node_ids:
            continue
        if edge.sourceNodeId == edge.targetNodeId:
            continue
        adjacency[edge.sourceNodeId].append(edge.targetNodeId)
        indegree[edge.targetNodeId] = indegree.get(edge.targetNodeId, 0) + 1
        indegree.setdefault(edge.sourceNodeId, indegree.get(edge.sourceNodeId, 0))

    queue: deque[str] = deque(
        node_id for node_id, degree in indegree.items() if degree == 0
    )
    seen = 0
    while queue:
        node_id = queue.popleft()
        seen += 1
        for neighbor in adjacency.get(node_id, []):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    if seen < len(indegree):
        return [
            ValidationIssue(
                code="cycle",
                message="Workflow contains a cycle; v1 requires a DAG.",
            )
        ]
    return []
