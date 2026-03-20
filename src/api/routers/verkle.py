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
    depth = len(vt._levels)

    # Build bottom-up: first assign leaf labels, then propagate up
    # vt._levels[0] = leaves, vt._levels[-1] = root
    # We reverse so levels[0] = root, levels[-1] = leaves

    # Leaf labels (bottom of _levels = index 0)
    leaf_labels: list[str] = []
    for i in range(len(vt._levels[0])):
        if i < len(vt._leaf_commitments):
            leaf_labels.append(vt._leaf_commitments[i][0])
        else:
            leaf_labels.append(f"pad_{i}")

    # Build label tree bottom-up: each internal node's label = summary of children
    label_tree: list[list[str]] = [leaf_labels]
    current = leaf_labels
    while len(current) > 1:
        parent_labels: list[str] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else left
            # Summarize: if both children are short, combine them
            parent_labels.append(f"{left} + {right}")
        label_tree.append(parent_labels)
        current = parent_labels

    # Now build the response: levels[0] = root (top), levels[-1] = leaves (bottom)
    levels = []
    for lvl_idx, level in enumerate(reversed(vt._levels)):
        # Map from reversed index to label_tree index
        label_lvl_idx = depth - 1 - lvl_idx
        nodes = []
        for node_idx, commitment in enumerate(level):
            label = None
            if label_lvl_idx < len(label_tree) and node_idx < len(label_tree[label_lvl_idx]):
                label = label_tree[label_lvl_idx][node_idx]
            nodes.append({
                "hash": commitment.hex()[:16],
                "label": label,
            })
        levels.append(nodes)
    return {
        "depth": depth,
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

    # Collect partition stats for context
    partitions = state.hypergraph.partition_by_type()
    from vhp.serialization import serialize_partition
    original_partition = None
    for name, p in sorted(partitions.items()):
        if name == req.partition_name:
            original_partition = p
            break

    original_data = serialize_partition(original_partition) if original_partition else b""
    original_data_size = len(original_data)
    edge_count = len(original_partition.pairwise_edges) if original_partition else 0
    hyperedge_count = len(original_partition.hyperedges) if original_partition else 0

    # Record original state
    original_root = vt.root_commitment
    original_leaf_hash = proof_before.leaf_commitment.hex()[:32]

    # Verify before tampering
    valid_before = vt.verify_proof(proof_before, original_root)

    # Tamper: replace real partition data with garbage bytes
    tamper_payload = b"TAMPERED"
    from vhp.crypto import commit as vhp_commit
    tampered_leaf_hash = vhp_commit(tamper_payload).hex()[:32]

    new_root = vt.update_leaf(req.partition_name, tamper_payload)
    root_changed = original_root != new_root

    # Old proof should fail against new root
    valid_after = vt.verify_proof(proof_before, new_root)

    # Restore original data
    for name, p in sorted(partitions.items()):
        if name == req.partition_name:
            vt.update_leaf(name, serialize_partition(p))
            break

    return {
        "partition": req.partition_name,
        "valid_before_tamper": valid_before,
        "root_changed": root_changed,
        "valid_after_tamper": valid_after,
        "tamper_detected": valid_before and not valid_after,
        "original_root": original_root.hex()[:32] + "...",
        "tampered_root": new_root.hex()[:32] + "...",
        "original_leaf_hash": original_leaf_hash + "...",
        "tampered_leaf_hash": tampered_leaf_hash + "...",
        "original_data_size": original_data_size,
        "tamper_payload": "0x" + tamper_payload.hex(),
        "tamper_payload_size": len(tamper_payload),
        "edge_count": edge_count,
        "hyperedge_count": hyperedge_count,
        "proof_size_bytes": proof_before.size_bytes,
    }
