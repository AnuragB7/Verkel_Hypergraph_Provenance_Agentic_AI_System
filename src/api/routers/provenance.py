"""Provenance router — DAG inspection for Layer 3."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.dependencies import get_state

router = APIRouter()


@router.get("/records")
def list_provenance_records():
    """List all audit records' provenance DAGs (summary)."""
    records = get_state().pipeline.audit_records
    return [
        {
            "index": i,
            "query": r.query,
            "dag_nodes": r.provenance_dag.node_count,
            "dag_depth": r.provenance_dag.depth,
            "timestamp": r.timestamp,
        }
        for i, r in enumerate(records)
    ]


@router.get("/records/{index}/dag")
def get_dag(index: int):
    records = get_state().pipeline.audit_records
    if index < 0 or index >= len(records):
        raise HTTPException(404, f"Record index {index} out of range")
    return records[index].provenance_dag.to_dict()


@router.get("/records/{index}/chain/{node_id}")
def get_reasoning_chain(index: int, node_id: str):
    records = get_state().pipeline.audit_records
    if index < 0 or index >= len(records):
        raise HTTPException(404, f"Record index {index} out of range")
    dag = records[index].provenance_dag
    if node_id not in dag.nodes:
        raise HTTPException(404, f"Node '{node_id}' not found in DAG")
    chain = dag.get_reasoning_chain(node_id)
    return [n.to_dict() for n in chain]
