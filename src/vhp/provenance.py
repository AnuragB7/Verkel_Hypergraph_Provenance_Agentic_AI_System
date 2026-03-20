"""Layer 3: Provenance DAG.

Tracks the causal reasoning chain as a Directed Acyclic Graph (DAG).
Each node represents a reasoning step and contains:
  - Content (the thought / action / observation / conclusion)
  - Verkle proofs for knowledge accessed
  - Cryptographic hash linking to parent nodes

Tampering with any step invalidates all descendant hashes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from vhp.crypto import sha256
from vhp.verkle import VerkleProof


class NodeType(Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    CONCLUSION = "conclusion"


@dataclass
class ProvenanceNode:
    """A single step in the reasoning provenance DAG."""

    id: str
    node_type: NodeType
    content: str
    timestamp: float

    # Knowledge provenance
    kg_queries: List[str] = field(default_factory=list)
    verkle_proofs: List[VerkleProof] = field(default_factory=list)
    hyperedges_accessed: List[str] = field(default_factory=list)

    # Causal dependencies (parent node IDs)
    depends_on: List[str] = field(default_factory=list)

    # Cryptographic hash: H(content || proofs || dependency_hashes)
    node_hash: bytes = b""

    def compute_hash(self, dep_hashes: Dict[str, bytes]) -> bytes:
        content_bytes = self.content.encode("utf-8")
        proof_bytes = b"|".join(p.opening_proof for p in self.verkle_proofs)
        dep_bytes = b"|".join(
            dep_hashes[d] for d in sorted(self.depends_on) if d in dep_hashes
        )
        self.node_hash = sha256(content_bytes + b"|" + proof_bytes + b"|" + dep_bytes)
        return self.node_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.node_type.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "kg_queries": self.kg_queries,
            "hyperedges_accessed": self.hyperedges_accessed,
            "depends_on": self.depends_on,
            "node_hash": self.node_hash.hex() if self.node_hash else "",
            "verkle_proof_count": len(self.verkle_proofs),
        }


class ProvenanceDAG:
    """Directed Acyclic Graph tracking reasoning provenance."""

    def __init__(self):
        self.nodes: Dict[str, ProvenanceNode] = {}
        self.edges: List[tuple[str, str]] = []  # (from, to)

    # -- Node creation ----------------------------------------------------

    def _add_node(
        self,
        node_type: NodeType,
        content: str,
        depends_on: List[str] | None = None,
        verkle_proofs: List[VerkleProof] | None = None,
        hyperedges: List[str] | None = None,
        kg_queries: List[str] | None = None,
    ) -> str:
        node_id = str(uuid.uuid4())[:8]
        node = ProvenanceNode(
            id=node_id,
            node_type=node_type,
            content=content,
            timestamp=time.time(),
            kg_queries=kg_queries or [],
            verkle_proofs=verkle_proofs or [],
            hyperedges_accessed=hyperedges or [],
            depends_on=depends_on or [],
        )
        dep_hashes = {
            nid: self.nodes[nid].node_hash
            for nid in (depends_on or [])
            if nid in self.nodes
        }
        node.compute_hash(dep_hashes)

        self.nodes[node_id] = node
        for dep_id in depends_on or []:
            self.edges.append((dep_id, node_id))
        return node_id

    def add_thought(self, content: str, depends_on: List[str] | None = None) -> str:
        return self._add_node(NodeType.THOUGHT, content, depends_on)

    def add_action(
        self,
        content: str,
        depends_on: List[str] | None = None,
        kg_queries: List[str] | None = None,
    ) -> str:
        return self._add_node(NodeType.ACTION, content, depends_on, kg_queries=kg_queries)

    def add_observation(
        self,
        content: str,
        depends_on: List[str] | None = None,
        verkle_proofs: List[VerkleProof] | None = None,
        hyperedges: List[str] | None = None,
    ) -> str:
        return self._add_node(
            NodeType.OBSERVATION, content, depends_on,
            verkle_proofs=verkle_proofs, hyperedges=hyperedges,
        )

    def add_conclusion(self, content: str, depends_on: List[str]) -> str:
        return self._add_node(NodeType.CONCLUSION, content, depends_on)

    # -- Verification ------------------------------------------------------

    def verify_all_hashes(self) -> Dict[str, bool]:
        """Independently recompute and check every node hash (topological order)."""
        results: dict[str, bool] = {}
        processed: set[str] = set()
        remaining = set(self.nodes.keys())

        while remaining:
            ready = [
                nid for nid in remaining
                if all(d in processed for d in self.nodes[nid].depends_on)
            ]
            if not ready:
                break  # cycle detected
            for nid in ready:
                node = self.nodes[nid]
                dep_hashes = {
                    d: self.nodes[d].node_hash
                    for d in node.depends_on
                    if d in self.nodes
                }
                expected = sha256(
                    node.content.encode("utf-8")
                    + b"|"
                    + b"|".join(p.opening_proof for p in node.verkle_proofs)
                    + b"|"
                    + b"|".join(dep_hashes[d] for d in sorted(node.depends_on) if d in dep_hashes)
                )
                results[nid] = expected == node.node_hash
                processed.add(nid)
                remaining.discard(nid)

        return results

    def verify_acyclicity(self) -> bool:
        """DFS-based cycle detection."""
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            in_stack.add(node_id)
            for src, tgt in self.edges:
                if src == node_id:
                    if tgt in in_stack:
                        return False
                    if tgt not in visited and not dfs(tgt):
                        return False
            in_stack.discard(node_id)
            return True

        for nid in self.nodes:
            if nid not in visited:
                if not dfs(nid):
                    return False
        return True

    def get_reasoning_chain(self, node_id: str) -> List[ProvenanceNode]:
        """Get all ancestor nodes for a given node (BFS backwards)."""
        chain: list[ProvenanceNode] = []
        queue = [node_id]
        seen: set[str] = set()
        while queue:
            nid = queue.pop(0)
            if nid in seen or nid not in self.nodes:
                continue
            seen.add(nid)
            node = self.nodes[nid]
            chain.append(node)
            queue.extend(node.depends_on)
        return list(reversed(chain))

    # -- Properties --------------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def depth(self) -> int:
        if not self.nodes:
            return 0
        depths: dict[str, int] = {}
        for nid in self.nodes:
            self._compute_depth(nid, depths)
        return max(depths.values()) if depths else 0

    def _compute_depth(self, nid: str, depths: dict[str, int]) -> int:
        if nid in depths:
            return depths[nid]
        node = self.nodes[nid]
        if not node.depends_on:
            depths[nid] = 1
        else:
            depths[nid] = 1 + max(
                self._compute_depth(d, depths)
                for d in node.depends_on
                if d in self.nodes
            )
        return depths[nid]

    # -- Serialization ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "depth": self.depth,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"from": src, "to": tgt} for src, tgt in self.edges],
        }
