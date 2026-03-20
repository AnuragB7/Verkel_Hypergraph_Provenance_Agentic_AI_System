"""Canonical deterministic serialization for VHP data structures.

Every serialization function MUST produce identical bytes for
semantically identical data.  This is critical because the Verkle
tree commits to the serialized form — non-deterministic serialization
would break proof verification.

Rules:
  - dict keys sorted alphabetically
  - set/frozenset elements sorted
  - JSON with sort_keys=True, separators=(',', ':')
  - encode to UTF-8
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vhp.hypergraph import Entity, HyperEdge, HypergraphPartition, PairwiseEdge


def serialize_entity(entity: Entity) -> bytes:
    data = {
        "id": entity.id,
        "name": entity.name,
        "properties": dict(sorted(dict(entity.properties).items())),
        "type": entity.type,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def serialize_pairwise_edge(edge: PairwiseEdge) -> bytes:
    data = {
        "p": dict(sorted(dict(edge.properties).items())),
        "r": edge.relation,
        "s": edge.source_id,
        "t": edge.target_id,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def serialize_hyperedge(hedge: HyperEdge) -> bytes:
    data = {
        "e": sorted(hedge.entity_ids),
        "id": hedge.id,
        "l": hedge.label,
        "p": dict(sorted(hedge.properties.items())),
        "sv": hedge.severity,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def serialize_partition(partition: HypergraphPartition) -> bytes:
    edges = sorted(
        json.dumps(
            {
                "p": dict(sorted(dict(e.properties).items())),
                "r": e.relation,
                "s": e.source_id,
                "t": e.target_id,
            },
            sort_keys=True,
        )
        for e in partition.pairwise_edges
    )
    hedges = sorted(
        json.dumps(
            {
                "e": sorted(h.entity_ids),
                "id": h.id,
                "l": h.label,
                "sv": h.severity,
            },
            sort_keys=True,
        )
        for h in partition.hyperedges
    )
    entities = sorted(partition.entity_ids)
    combined = json.dumps(
        {"edges": edges, "entities": entities, "hedges": hedges},
        sort_keys=True,
        separators=(",", ":"),
    )
    return combined.encode("utf-8")
