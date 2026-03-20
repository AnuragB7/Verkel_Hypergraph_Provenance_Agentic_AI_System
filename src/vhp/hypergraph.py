"""Layer 1: Hypergraph Knowledge Representation.

Implements the domain hypergraph H = (V, E₂, Eₕ) where:
  V  — entities (drugs, conditions, patients, enzymes, demographics)
  E₂ — pairwise edges (standard KG triples)
  Eₕ — hyperedges (multi-way interactions connecting 2+ entities)

Hyperedges are the key novelty: they capture emergent risks that arise
only when multiple factors co-occur (e.g., Drug A + Drug B + Condition C
creates a critical risk that the pairwise A↔B interaction alone rates moderate).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Entity:
    """A node in the hypergraph."""

    id: str          # e.g. "DB00001", "ICD10:E11"
    type: str        # "drug", "condition", "enzyme", "patient", "demographic"
    name: str
    properties: tuple = ()  # key-value pairs; tuple for hashability

    def props_dict(self) -> Dict[str, Any]:
        return dict(self.properties)


@dataclass(frozen=True)
class PairwiseEdge:
    """Standard KG triple: (source, relation, target)."""

    source_id: str
    relation: str   # "interacts_with", "contraindicated_for", "metabolized_by", …
    target_id: str
    properties: tuple = ()  # (severity, mechanism, evidence_level, …)

    def props_dict(self) -> Dict[str, Any]:
        return dict(self.properties)


@dataclass
class HyperEdge:
    """Multi-way interaction connecting 2+ entities.

    entity_ids is a frozenset for hashability / set operations.
    """

    id: str
    entity_ids: FrozenSet[str]
    label: str       # "polypharmacy_risk", "metabolic_conflict", …
    severity: float  # 0.0 – 1.0
    evidence: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HypergraphPartition:
    """A semantic sub-group of the hypergraph used as a Verkle leaf."""

    name: str
    entity_ids: Set[str]
    pairwise_edges: List[PairwiseEdge]
    hyperedges: List[HyperEdge]


# ---------------------------------------------------------------------------
# Hypergraph
# ---------------------------------------------------------------------------

class Hypergraph:
    """Domain hypergraph H = (V, E₂, Eₕ)."""

    def __init__(self, name: str = ""):
        self.name = name
        self.entities: Dict[str, Entity] = {}
        self.pairwise_edges: List[PairwiseEdge] = []
        self.hyperedges: List[HyperEdge] = []

        # Indices for efficient lookup
        self._adjacency: Dict[str, List[PairwiseEdge]] = defaultdict(list)
        self._entity_hyperedges: Dict[str, List[HyperEdge]] = defaultdict(list)

    # -- Mutation ----------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def add_pairwise_edge(self, edge: PairwiseEdge) -> None:
        self.pairwise_edges.append(edge)
        self._adjacency[edge.source_id].append(edge)
        self._adjacency[edge.target_id].append(edge)

    def add_hyperedge(self, hedge: HyperEdge) -> None:
        self.hyperedges.append(hedge)
        for eid in hedge.entity_ids:
            self._entity_hyperedges[eid].append(hedge)

    # -- Query -------------------------------------------------------------

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def get_neighbors(
        self, entity_id: str, relation: str | None = None
    ) -> List[Tuple[str, PairwiseEdge]]:
        results: list[Tuple[str, PairwiseEdge]] = []
        for edge in self._adjacency.get(entity_id, []):
            if relation and edge.relation != relation:
                continue
            other = edge.target_id if edge.source_id == entity_id else edge.source_id
            results.append((other, edge))
        return results

    def get_hyperedges_for_entity(self, entity_id: str) -> List[HyperEdge]:
        return list(self._entity_hyperedges.get(entity_id, []))

    def get_hyperedges_for_entities(self, entity_ids: Set[str]) -> List[HyperEdge]:
        """Find all hyperedges that involve ANY of the given entities."""
        seen: set[str] = set()
        result: list[HyperEdge] = []
        for eid in entity_ids:
            for hedge in self._entity_hyperedges.get(eid, []):
                if hedge.id not in seen:
                    seen.add(hedge.id)
                    result.append(hedge)
        return result

    def get_matching_hyperedges(self, entity_ids: Set[str]) -> List[HyperEdge]:
        """Find hyperedges where ALL member entities are in the given set."""
        return [h for h in self.hyperedges if h.entity_ids.issubset(entity_ids)]

    # -- Subgraph extraction -----------------------------------------------

    def extract_subgraph(self, entity_ids: Set[str], max_hops: int = 2) -> Hypergraph:
        """Extract a sub-hypergraph centered on the given entities."""
        visited: set[str] = set(entity_ids)
        frontier = set(entity_ids)

        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for eid in frontier:
                for neighbor_id, _ in self.get_neighbors(eid):
                    if neighbor_id not in visited:
                        next_frontier.add(neighbor_id)
                        visited.add(neighbor_id)
            frontier = next_frontier

        sub = Hypergraph(f"{self.name}_sub")
        for eid in visited:
            if eid in self.entities:
                sub.add_entity(self.entities[eid])
        for edge in self.pairwise_edges:
            if edge.source_id in visited and edge.target_id in visited:
                sub.add_pairwise_edge(edge)
        for hedge in self.hyperedges:
            if hedge.entity_ids.issubset(visited):
                sub.add_hyperedge(hedge)
        return sub

    # -- Partitioning for Verkle tree leaves --------------------------------

    def partition_by_type(self) -> Dict[str, HypergraphPartition]:
        """Partition into semantic subgroups for Verkle leaf construction."""
        partitions: dict[str, HypergraphPartition] = {}

        for edge in self.pairwise_edges:
            key = f"pairwise_{edge.relation}"
            if key not in partitions:
                partitions[key] = HypergraphPartition(key, set(), [], [])
            partitions[key].entity_ids.add(edge.source_id)
            partitions[key].entity_ids.add(edge.target_id)
            partitions[key].pairwise_edges.append(edge)

        for hedge in self.hyperedges:
            key = f"hyperedge_{hedge.label}"
            if key not in partitions:
                partitions[key] = HypergraphPartition(key, set(), [], [])
            partitions[key].entity_ids.update(hedge.entity_ids)
            partitions[key].hyperedges.append(hedge)

        return partitions

    # -- Stats -------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "entities": len(self.entities),
            "pairwise_edges": len(self.pairwise_edges),
            "hyperedges": len(self.hyperedges),
            "entity_types": len({e.type for e in self.entities.values()}),
        }

    # -- Serialization helpers for API -------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "stats": self.stats,
            "entities": [
                {"id": e.id, "type": e.type, "name": e.name, "properties": e.props_dict()}
                for e in self.entities.values()
            ],
            "pairwise_edges": [
                {
                    "source_id": e.source_id,
                    "relation": e.relation,
                    "target_id": e.target_id,
                    "properties": e.props_dict(),
                }
                for e in self.pairwise_edges
            ],
            "hyperedges": [
                {
                    "id": h.id,
                    "entity_ids": sorted(h.entity_ids),
                    "label": h.label,
                    "severity": h.severity,
                    "evidence": h.evidence,
                    "properties": h.properties,
                }
                for h in self.hyperedges
            ],
        }
