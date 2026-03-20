"""Verkle router — proof generation, verification, tree info for Layer 2."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import get_state

router = APIRouter()


@router.get("/root")
def get_root():
    vt = get_state().verkle
    return {
        "root": vt.root_hex,
        "leaf_count": vt.leaf_count,
        "leaf_labels": vt.leaf_labels,
        "depth": len(vt._levels),
    }


@router.get("/tree")
def get_tree():
    """Return full tree structure for visualization."""
    vt = get_state().verkle
    levels = []
    for lvl_idx, level in enumerate(reversed(vt._levels)):
        nodes = []
        for node_idx, commitment in enumerate(level):
            label = None
            # Bottom level (leaves) — attach partition labels
            if lvl_idx == len(vt._levels) - 1:
                if node_idx < len(vt._leaf_commitments):
                    label = vt._leaf_commitments[node_idx][0]
            nodes.append({
                "hash": commitment.hex()[:16],
                "label": label,
            })
        levels.append(nodes)
    return {
        "depth": len(vt._levels),
        "leaf_count": vt.leaf_count,
        "root": vt.root_hex,
        "levels": levels,
    }


@router.get("/proof/{partition_name}")
def get_proof(partition_name: str):
    vt = get_state().verkle
    try:
        proof = vt.generate_proof(partition_name)
    except KeyError:
        raise HTTPException(404, f"Partition '{partition_name}' not found")
    return proof.to_dict()


class VerifyRequest(BaseModel):
    partition_name: str


@router.post("/verify")
def verify_partition(req: VerifyRequest):
    state = get_state()
    vt = state.verkle
    try:
        proof = vt.generate_proof(req.partition_name)
    except KeyError:
        raise HTTPException(404, f"Partition '{req.partition_name}' not found")
    is_valid = vt.verify_proof(proof, vt.root_commitment)
    return {
        "partition": req.partition_name,
        "valid": is_valid,
        "proof_size_bytes": proof.size_bytes,
    }


@router.get("/root-chain")
def get_root_chain():
    return get_state().root_chain.to_dict()


@router.get("/root-chain/verify")
def verify_root_chain():
    rc = get_state().root_chain
    return {"valid": rc.verify_chain_integrity(), "length": len(rc)}


class TamperRequest(BaseModel):
    partition_name: str


@router.post("/tamper-detect")
def detect_tampering(req: TamperRequest):
    """Simulate tamper detection: generate proof, tamper data, re-verify."""
    state = get_state()
    vt = state.verkle

    try:
        proof_before = vt.generate_proof(req.partition_name)
    except KeyError:
        raise HTTPException(404, f"Partition '{req.partition_name}' not found")

    # Record original root
    original_root = vt.root_commitment

    # Verify before tampering
    valid_before = vt.verify_proof(proof_before, original_root)

    # Tamper: update with garbage data
    new_root = vt.update_leaf(req.partition_name, b"TAMPERED")
    root_changed = original_root != new_root

    # Old proof should fail against new root
    valid_after = vt.verify_proof(proof_before, new_root)

    # Restore original data
    partitions = state.hypergraph.partition_by_type()
    from vhp.serialization import serialize_partition
    for name, p in sorted(partitions.items()):
        if name == req.partition_name:
            vt.update_leaf(name, serialize_partition(p))
            break

    return {
        "valid_before_tamper": valid_before,
        "root_changed": root_changed,
        "valid_after_tamper": valid_after,
        "tamper_detected": valid_before and not valid_after,
    }
