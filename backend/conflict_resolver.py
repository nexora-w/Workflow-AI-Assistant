"""
Conflict Resolution Engine for Collaborative Workflow Editing

Strategy: Version-based optimistic concurrency with operation-level merging.

How it works:
1. Each workflow has a monotonically increasing version number.
2. When a client submits an operation, it includes the base_version it was
   working from (the last version it saw).
3. If base_version == server version → apply directly (no conflict).
4. If base_version < server version → there were concurrent edits.
   The engine checks whether the concurrent operations conflict:
   - Non-conflicting (different targets) → auto-merge both, bump version.
   - Conflicting (same target) → reject, return latest state for client rebase.

Operation types:
  move_node   — change node position {node_id, position: {x, y}}
  add_node    — insert new node      {node: {id, label, type, position?}}
  delete_node — remove node + edges  {node_id}
  update_node — change label/type    {node_id, label?, type?}
  add_edge    — add edge             {edge: {from, to}}
  delete_edge — remove edge          {from, to}
"""

import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class Operation:
    op_type: str
    payload: dict
    
    @property
    def target_id(self) -> str:
        """Identify what this operation targets for conflict detection."""
        if self.op_type in ("move_node", "delete_node", "update_node"):
            return f"node:{self.payload.get('node_id', '')}"
        elif self.op_type == "add_node":
            return f"node:{self.payload.get('node', {}).get('id', '')}"
        elif self.op_type == "add_edge":
            edge = self.payload.get("edge", {})
            return f"edge:{edge.get('from', '')}-{edge.get('to', '')}"
        elif self.op_type == "delete_edge":
            return f"edge:{self.payload.get('from', '')}-{self.payload.get('to', '')}"
        return f"unknown:{id(self)}"

    @property
    def affected_node_ids(self) -> set:
        """All node IDs this operation reads or writes."""
        if self.op_type in ("move_node", "delete_node", "update_node"):
            return {self.payload.get("node_id", "")}
        elif self.op_type == "add_node":
            return {self.payload.get("node", {}).get("id", "")}
        elif self.op_type in ("add_edge", "delete_edge"):
            edge = self.payload if self.op_type == "delete_edge" else self.payload.get("edge", {})
            return {edge.get("from", ""), edge.get("to", "")}
        return set()


@dataclass
class ConflictResult:
    status: str  # "applied", "merged", "conflict"
    new_version: int
    new_data: str
    conflicts: List[str] = field(default_factory=list)


def detect_conflicts(incoming_ops: List[Operation], concurrent_ops: List[Operation]) -> List[str]:
    """
    Check whether incoming operations conflict with operations
    that were applied between the client's base_version and now.
    
    Conflict rules:
    - Two ops on the same target_id → conflict
    - delete_node + any op touching that node → conflict
    - move_node on same node → conflict (positions diverged)
    - move_node on different nodes → no conflict (merge)
    - add_node with same ID → conflict
    - Anything else on different targets → no conflict
    """
    conflicts = []
    
    concurrent_targets = {}
    concurrent_deleted_nodes = set()
    
    for op in concurrent_ops:
        concurrent_targets[op.target_id] = op
        if op.op_type == "delete_node":
            concurrent_deleted_nodes.add(op.payload.get("node_id", ""))
    
    for op in incoming_ops:
        if op.target_id in concurrent_targets:
            other = concurrent_targets[op.target_id]
            conflicts.append(
                f"Conflict on {op.target_id}: your '{op.op_type}' vs "
                f"concurrent '{other.op_type}'"
            )
            continue
        
        if op.op_type == "delete_node":
            node_id = op.payload.get("node_id", "")
            for c_op in concurrent_ops:
                if node_id in c_op.affected_node_ids:
                    conflicts.append(
                        f"Cannot delete node '{node_id}': it was modified by "
                        f"a concurrent '{c_op.op_type}' operation"
                    )
                    break
        
        affected = op.affected_node_ids
        for deleted_id in concurrent_deleted_nodes:
            if deleted_id in affected:
                conflicts.append(
                    f"Conflict: your '{op.op_type}' references node "
                    f"'{deleted_id}' which was deleted concurrently"
                )
    
    return conflicts


def apply_operation(workflow: dict, op: Operation) -> dict:
    """Apply a single operation to a workflow dict, returning the updated workflow."""
    nodes = list(workflow.get("nodes", []))
    edges = list(workflow.get("edges", []))
    
    if op.op_type == "move_node":
        node_id = op.payload["node_id"]
        position = op.payload["position"]
        for node in nodes:
            if node["id"] == node_id:
                node["position"] = position
                break
    
    elif op.op_type == "add_node":
        new_node = op.payload["node"]
        if not any(n["id"] == new_node["id"] for n in nodes):
            nodes.append(new_node)
    
    elif op.op_type == "delete_node":
        node_id = op.payload["node_id"]
        nodes = [n for n in nodes if n["id"] != node_id]
        edges = [e for e in edges if e["from"] != node_id and e["to"] != node_id]
    
    elif op.op_type == "update_node":
        node_id = op.payload["node_id"]
        for node in nodes:
            if node["id"] == node_id:
                if "label" in op.payload:
                    node["label"] = op.payload["label"]
                if "type" in op.payload:
                    node["type"] = op.payload["type"]
                break
    
    elif op.op_type == "add_edge":
        new_edge = op.payload["edge"]
        exists = any(
            e["from"] == new_edge["from"] and e["to"] == new_edge["to"]
            for e in edges
        )
        if not exists:
            edges.append(new_edge)
    
    elif op.op_type == "delete_edge":
        from_id = op.payload["from"]
        to_id = op.payload["to"]
        edges = [
            e for e in edges
            if not (e["from"] == from_id and e["to"] == to_id)
        ]
    
    return {"nodes": nodes, "edges": edges}


def apply_operations(workflow: dict, ops: List[Operation]) -> dict:
    """Apply a list of operations sequentially."""
    result = workflow
    for op in ops:
        result = apply_operation(result, op)
    return result


def resolve(
    current_data: str,
    current_version: int,
    base_version: int,
    incoming_ops: List[Operation],
    op_log: List[dict]
) -> ConflictResult:
    """
    Main conflict resolution entry point.
    
    Args:
        current_data: The current workflow JSON string on the server.
        current_version: The server's current version number.
        base_version: The version the client was working from.
        incoming_ops: The operations the client wants to apply.
        op_log: Operations applied between base_version and current_version
                (from WorkflowOperation records).
    
    Returns:
        ConflictResult with status, new data, and any conflict messages.
    """
    workflow = json.loads(current_data)
    
    if base_version == current_version:
        updated = apply_operations(workflow, incoming_ops)
        new_version = current_version + 1
        return ConflictResult(
            status="applied",
            new_version=new_version,
            new_data=json.dumps(updated)
        )
    
    concurrent_ops = []
    for entry in op_log:
        try:
            ops_data = json.loads(entry.get("op_data", "[]"))
            if isinstance(ops_data, list):
                for od in ops_data:
                    concurrent_ops.append(Operation(
                        op_type=od.get("op_type", ""),
                        payload=od.get("payload", {})
                    ))
            else:
                concurrent_ops.append(Operation(
                    op_type=ops_data.get("op_type", ""),
                    payload=ops_data.get("payload", {})
                ))
        except (json.JSONDecodeError, AttributeError):
            pass
    
    conflicts = detect_conflicts(incoming_ops, concurrent_ops)
    
    if conflicts:
        return ConflictResult(
            status="conflict",
            new_version=current_version,
            new_data=current_data,
            conflicts=conflicts
        )
    
    updated = apply_operations(workflow, incoming_ops)
    new_version = current_version + 1
    return ConflictResult(
        status="merged",
        new_version=new_version,
        new_data=json.dumps(updated)
    )
