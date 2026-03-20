"""Audit router — record listing and verification."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.dependencies import get_state
from vhp.audit import AuditVerifier

router = APIRouter()


@router.get("/records")
def list_records():
    records = get_state().pipeline.audit_records
    return [
        {
            "index": i,
            "query": r.query,
            "response": r.final_response,
            "timestamp": r.timestamp,
            "record_hash": r.record_hash.hex(),
            "dag_nodes": r.provenance_dag.node_count,
            "verkle_proofs_count": r.verkle_proofs_count,
        }
        for i, r in enumerate(records)
    ]


@router.get("/records/{index}")
def get_record(index: int):
    records = get_state().pipeline.audit_records
    if index < 0 or index >= len(records):
        raise HTTPException(404, f"Record index {index} out of range")
    return records[index].to_dict()


@router.get("/records/{index}/verify")
def verify_record(index: int):
    state = get_state()
    records = state.pipeline.audit_records
    if index < 0 or index >= len(records):
        raise HTTPException(404, f"Record index {index} out of range")
    verifier = AuditVerifier()
    result = verifier.verify(records[index], trusted_root=state.verkle.root_commitment)
    return result.to_dict()
