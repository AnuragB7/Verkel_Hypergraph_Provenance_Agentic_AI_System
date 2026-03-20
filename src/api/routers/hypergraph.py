"""Hypergraph router — CRUD + query endpoints for Layer 1."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_state

router = APIRouter()


# -- Stats / overview -------------------------------------------------------

@router.get("/stats")
def get_stats():
    return get_state().hypergraph.stats


@router.get("/entities")
def get_entities(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    hg = get_state().hypergraph
    entities = list(hg.entities.values())[offset:offset + limit]
    return [
        {"id": e.id, "type": e.type, "name": e.name, "properties": e.props_dict()}
        for e in entities
    ]


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str):
    e = get_state().hypergraph.get_entity(entity_id)
    if not e:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return {"id": e.id, "type": e.type, "name": e.name, "properties": e.props_dict()}


@router.get("/edges")
def get_edges(limit: int = Query(500, ge=1, le=50000), offset: int = Query(0, ge=0)):
    hg = get_state().hypergraph
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
