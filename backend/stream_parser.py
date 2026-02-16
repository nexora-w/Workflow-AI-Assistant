"""
Incremental JSON parser for streaming workflow detection.

As OpenAI streams tokens, this parser detects completed node and edge
objects within the workflow JSON, allowing the server to emit SSE events
the instant a node/edge is fully received — before the entire response
is finished.
"""

import json
from typing import List, Dict, Set, Tuple, Optional


class IncrementalWorkflowParser:
    """
    Feed tokens one-by-one (or in small chunks). After each feed,
    call `feed()` to get lists of newly-detected nodes and edges.

    Handles:
      - Nodes in any key order: {"id","label","type"} or {"type","id","label"} etc.
      - Edges in any key order: {"from","to"} or {"to","from"}
      - JSON inside markdown code blocks (```json ... ```)
      - Nodes/edges with extra keys (ignored gracefully)
    """

    def __init__(self):
        self.buffer: str = ""
        self._emitted_node_ids: Set[str] = set()
        self._emitted_edge_keys: Set[str] = set()

    def feed(self, chunk: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Feed a new chunk of streamed text.

        Returns
        -------
        (new_nodes, new_edges)
            new_nodes : list of {"id", "label", "type"} dicts
            new_edges : list of {"from", "to"} dicts
        """
        self.buffer += chunk
        new_nodes: List[Dict] = []
        new_edges: List[Dict] = []

        for obj in self._extract_leaf_objects():
            if self._is_node(obj):
                node_id = str(obj["id"])
                if node_id not in self._emitted_node_ids:
                    self._emitted_node_ids.add(node_id)
                    new_nodes.append({
                        "id": node_id,
                        "label": str(obj["label"]),
                        "type": str(obj["type"]),
                    })
            elif self._is_edge(obj):
                key = f"{obj['from']}->{obj['to']}"
                if key not in self._emitted_edge_keys:
                    self._emitted_edge_keys.add(key)
                    new_edges.append({
                        "from": str(obj["from"]),
                        "to": str(obj["to"]),
                    })

        return new_nodes, new_edges

    def get_all_nodes(self) -> List[Dict]:
        """Return all nodes detected so far, in emission order."""
        result = []
        seen = set()
        for obj in self._extract_leaf_objects():
            if self._is_node(obj):
                nid = str(obj["id"])
                if nid not in seen:
                    seen.add(nid)
                    result.append({
                        "id": nid,
                        "label": str(obj["label"]),
                        "type": str(obj["type"]),
                    })
        return result

    def get_all_edges(self) -> List[Dict]:
        """Return all edges detected so far."""
        result = []
        seen = set()
        for obj in self._extract_leaf_objects():
            if self._is_edge(obj):
                key = f"{obj['from']}->{obj['to']}"
                if key not in seen:
                    seen.add(key)
                    result.append({
                        "from": str(obj["from"]),
                        "to": str(obj["to"]),
                    })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_node(obj: Dict) -> bool:
        return (
            isinstance(obj, dict)
            and "id" in obj
            and "label" in obj
            and "type" in obj
        )

    @staticmethod
    def _is_edge(obj: Dict) -> bool:
        return (
            isinstance(obj, dict)
            and "from" in obj
            and "to" in obj
            and "id" not in obj  # avoid confusing a node with an edge
        )

    def _extract_leaf_objects(self) -> List[Dict]:
        """
        Scan the buffer for complete JSON objects that have no nested
        objects (leaf-level).  These are the node / edge candidates.
        """
        objects: List[Dict] = []
        text = self.buffer
        i = 0
        length = len(text)

        while i < length:
            if text[i] == "{":
                depth = 1
                j = i + 1
                while j < length and depth > 0:
                    ch = text[j]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                    elif ch == '"':
                        # Skip over string contents to avoid counting
                        # braces inside string values.
                        j += 1
                        while j < length and text[j] != '"':
                            if text[j] == "\\":
                                j += 1  # skip escaped char
                            j += 1
                    j += 1

                if depth == 0:
                    candidate = text[i:j]
                    inner = candidate[1:-1]
                    # Leaf object: no nested braces (after accounting for strings)
                    if self._has_no_nested_braces(inner):
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict):
                                objects.append(obj)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    i = j
                else:
                    # Incomplete object — stop scanning
                    break
            else:
                i += 1

        return objects

    @staticmethod
    def _has_no_nested_braces(inner: str) -> bool:
        """Check that `inner` (text between outer { }) has no nested { }."""
        in_string = False
        for i, ch in enumerate(inner):
            if ch == '"' and (i == 0 or inner[i - 1] != "\\"):
                in_string = not in_string
            elif not in_string and ch in "{}":
                return False
        return True
