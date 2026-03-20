"""Hypergraph router — CRUD + query endpoints for Layer 1."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_state

router = APIRouter()


# -- Stats / overview -------------------------------------------------------

@router.get("/stats")
def get_stats():
    return get_state().hypergraph.stats


@router.get("/entities")
def get_entities(
    limit: int = Query(200, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    types: Optional[str] = Query(None, description="Comma-separated entity types to include"),
):
    hg = get_state().hypergraph
    if types:
        type_set = {t.strip() for t in types.split(",")}
        filtered = [e for e in hg.entities.values() if e.type in type_set]
        total = len(filtered)
        entities = filtered[offset:offset + limit]
    else:
        total = len(hg.entities)
        entities = list(hg.entities.values())[offset:offset + limit]
    return {
        "items": [
            {"id": e.id, "type": e.type, "name": e.name, "properties": e.props_dict()}
            for e in entities
        ],
        "total": total,
    }


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str):
    e = get_state().hypergraph.get_entity(entity_id)
    if not e:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return {"id": e.id, "type": e.type, "name": e.name, "properties": e.props_dict()}


@router.get("/edges")
def get_edges(
    limit: int = Query(500, ge=1, le=50000),
    offset: int = Query(0, ge=0),
    entity_ids: Optional[str] = Query(None, description="Comma-separated entity IDs to get edges for"),
):
    hg = get_state().hypergraph
    if entity_ids:
        id_set = {eid.strip() for eid in entity_ids.split(",")}
        # Collect ALL cross-type edges first, then DDI edges up to limit
        cross_type = []
        ddi = []
        for e in hg.pairwise_edges:
            if e.source_id in id_set or e.target_id in id_set:
                if e.relation != "interacts_with":
                    cross_type.append(e)
                else:
                    ddi.append(e)
        # Prioritise cross-type (targets, enzymes, …) then fill with DDIs
        if len(cross_type) >= limit:
            matching = cross_type[:limit]
        else:
            remaining = limit - len(cross_type)
            matching = cross_type + ddi[:remaining]
        return [
            {
                "source_id": e.source_id,
                "relation": e.relation,
                "target_id": e.target_id,
                "properties": e.props_dict(),
            }
            for e in matching
        ]
    return [
        {
            "source_id": e.source_id,
            "relation": e.relation,
            "target_id": e.target_id,
            "properties": e.props_dict(),
        }
        for e in hg.pairwise_edges[offset:offset + limit]
    ]


@router.get("/hyperedges")
def get_hyperedges():
    hg = get_state().hypergraph
    return [
        {
            "id": h.id,
            "entity_ids": sorted(h.entity_ids),
            "label": h.label,
            "severity": h.severity,
            "evidence": h.evidence,
            "properties": h.properties,
        }
        for h in hg.hyperedges
    ]


@router.get("/neighbors/{entity_id}")
def get_neighbors(entity_id: str, relation: str | None = None):
    hg = get_state().hypergraph
    if entity_id not in hg.entities:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return [
        {"neighbor_id": nid, "relation": edge.relation, "properties": edge.props_dict()}
        for nid, edge in hg.get_neighbors(entity_id, relation)
    ]


@router.get("/partitions")
def get_partitions():
    parts = get_state().hypergraph.partition_by_type()
    return {
        name: {
            "entity_count": len(p.entity_ids),
            "pairwise_count": len(p.pairwise_edges),
            "hyperedge_count": len(p.hyperedges),
        }
        for name, p in parts.items()
    }


class SubgraphRequest(BaseModel):
    entity_ids: list[str]
    max_hops: int = 2


@router.post("/subgraph")
def extract_subgraph(req: SubgraphRequest):
    sub = get_state().hypergraph.extract_subgraph(set(req.entity_ids), req.max_hops)
    return sub.to_dict()
