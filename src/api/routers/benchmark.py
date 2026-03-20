"""Benchmark router — performance and adversarial testing."""

from __future__ import annotations

import hashlib
import random
import time
from typing import Set

from fastapi import APIRouter

from api.dependencies import get_state
from vhp.hypergraph import Hypergraph
from vhp.serialization import serialize_partition
from vhp.verkle import MerkleTree, VerkleTree

router = APIRouter()


def _pick_drug_ids(hg: Hypergraph, n: int = 3) -> Set[str]:
    """Pick *n* drug entity IDs from the loaded hypergraph."""
    drugs = [eid for eid, e in hg.entities.items() if e.type == "drug"]
    return set(random.sample(drugs, min(n, len(drugs))))


def _pick_interacting_pair(hg: Hypergraph) -> Set[str]:
    """Return a pair of drugs that have a pairwise interaction."""
    if hg.pairwise_edges:
        edge = random.choice(hg.pairwise_edges)
        return {edge.source_id, edge.target_id}
    return _pick_drug_ids(hg, 2)


@router.post("/performance")
def run_performance_benchmark():
    """Time key VHP operations."""
    state = get_state()
    hg = state.hypergraph
    results: list[dict] = []

    # 1. Hypergraph partition
    t0 = time.perf_counter()
    parts = hg.partition_by_type()
    results.append({"operation": "partition_hypergraph", "ms": (time.perf_counter() - t0) * 1000})

    leaf_data = [(n, serialize_partition(p)) for n, p in sorted(parts.items())]

    # 2. Verkle build
    vt = VerkleTree()
    t0 = time.perf_counter()
    vt.build(leaf_data)
    results.append({"operation": "build_verkle", "ms": (time.perf_counter() - t0) * 1000})

    # 3. Merkle build (comparison)
    mt = MerkleTree()
    t0 = time.perf_counter()
    mt.build(leaf_data)
    results.append({"operation": "build_merkle", "ms": (time.perf_counter() - t0) * 1000})

    # 4. Verkle proof generation
    label = leaf_data[0][0]
    t0 = time.perf_counter()
    for _ in range(100):
        vt.generate_proof(label)
    results.append({"operation": "verkle_proof_gen_100x", "ms": (time.perf_counter() - t0) * 1000})

    # 5. Verkle proof verification
    proof = vt.generate_proof(label)
    t0 = time.perf_counter()
    for _ in range(100):
        vt.verify_proof(proof, vt.root_commitment)
    results.append({"operation": "verkle_verify_100x", "ms": (time.perf_counter() - t0) * 1000})

    # 6. Pipeline query
    from vhp.reasoning import SimulatedReasoningEngine
    from vhp.pipeline import VHPPipeline
    from vhp.verkle import TemporalRootChain

    engine = SimulatedReasoningEngine(hg)
    rc = TemporalRootChain()
    rc.append_root(vt.root_commitment)
    pipeline = VHPPipeline(hg, vt, engine, rc)

    query_ids = _pick_drug_ids(hg, 3)
    t0 = time.perf_counter()
    pipeline.process_query("Benchmark query", query_ids)
    results.append({"operation": "full_pipeline_query", "ms": (time.perf_counter() - t0) * 1000})

    return {"results": results}


@router.post("/proof-sizes")
def proof_size_comparison():
    """Compare Verkle vs Merkle proof sizes at different scales."""
    import hashlib
    comparisons: list[dict] = []

    for n_leaves in [4, 8, 16, 32, 64, 128, 256, 512, 1024]:
        leaf_data = [(f"leaf_{i}", hashlib.sha256(f"data_{i}".encode()).digest()) for i in range(n_leaves)]

        vt = VerkleTree()
        vt.build(leaf_data)
        vp = vt.generate_proof("leaf_0")

        mt = MerkleTree()
        mt.build(leaf_data)
        mp = mt.generate_proof("leaf_0")

        comparisons.append({
            "leaves": n_leaves,
            "verkle_bytes": vp.size_bytes,
            "merkle_bytes": mp.size_bytes,
        })

    return {"comparisons": comparisons}


@router.post("/adversarial")
def adversarial_test():
    """Run adversarial integrity tests."""
    state = get_state()
    tests: list[dict] = []

    # Test 1: Tamper with a partition
    vt = state.verkle
    labels = vt.leaf_labels
    if labels:
        proof = vt.generate_proof(labels[0])
        valid_before = vt.verify_proof(proof, vt.root_commitment)
        old_root = vt.root_commitment

        vt.update_leaf(labels[0], b"ADVERSARIAL_TAMPER")
        valid_after = vt.verify_proof(proof, vt.root_commitment)

        # Restore
        parts = state.hypergraph.partition_by_type()
        for name, p in sorted(parts.items()):
            if name == labels[0]:
                vt.update_leaf(name, serialize_partition(p))
                break

        tests.append({
            "test": "verkle_tamper_detection",
            "passed": valid_before and not valid_after,
            "details": {
                "valid_before": valid_before,
                "valid_after_tamper": valid_after,
                "root_changed": old_root != vt.root_commitment,
            },
        })

    # Test 2: Root chain integrity
    rc = state.root_chain
    tests.append({
        "test": "root_chain_integrity",
        "passed": rc.verify_chain_integrity(),
        "details": {"chain_length": len(rc)},
    })

    # Test 3: Process query and verify audit
    adv_ids = _pick_drug_ids(state.hypergraph, 3)
    record = state.pipeline.process_query(
        "Adversarial test query",
        adv_ids,
    )
    verification = state.pipeline.verify_record(record)
    tests.append({
        "test": "full_audit_verification",
        "passed": verification.get("overall_valid", False),
        "details": verification,
    })

    return {
        "tests": tests,
        "all_passed": all(t["passed"] for t in tests),
    }


# -----------------------------------------------------------------------
# NEW: Scalability — overhead vs entity count
# -----------------------------------------------------------------------
@router.post("/scalability")
def scalability_benchmark():
    """Measure VHP overhead as the number of Verkle leaves grows."""
    results: list[dict] = []

    for n_leaves in [4, 8, 16, 32, 64, 128, 256, 512, 1024]:
        leaf_data = [
            (f"part_{i}", hashlib.sha256(f"payload_{i}".encode()).digest())
            for i in range(n_leaves)
        ]

        # Build
        vt = VerkleTree()
        t0 = time.perf_counter()
        vt.build(leaf_data)
        build_ms = (time.perf_counter() - t0) * 1000

        # Proof generation (avg over all leaves)
        t0 = time.perf_counter()
        for label, _ in leaf_data:
            vt.generate_proof(label)
        proof_ms = (time.perf_counter() - t0) / n_leaves * 1000

        # Verification (avg)
        proof = vt.generate_proof(leaf_data[0][0])
        t0 = time.perf_counter()
        for _ in range(n_leaves):
            vt.verify_proof(proof, vt.root_commitment)
        verify_ms = (time.perf_counter() - t0) / n_leaves * 1000

        results.append({
            "leaves": n_leaves,
            "build_ms": round(build_ms, 4),
            "proof_gen_ms": round(proof_ms, 4),
            "verify_ms": round(verify_ms, 4),
        })

    return {"results": results}


# -----------------------------------------------------------------------
# NEW: Layer-by-layer overhead breakdown for a single query
# -----------------------------------------------------------------------
@router.post("/layer-overhead")
def layer_overhead_benchmark():
    """Break down per-layer overhead of a single VHP pipeline query."""
    from vhp.pipeline import VHPPipeline
    from vhp.provenance import ProvenanceDAG
    from vhp.reasoning import SimulatedReasoningEngine
    from vhp.verkle import TemporalRootChain

    state = get_state()
    hg = state.hypergraph
    entity_ids = _pick_drug_ids(hg, 3)

    layers: list[dict] = []

    # Layer 1: hypergraph query
    t0 = time.perf_counter()
    subgraph = hg.extract_subgraph(entity_ids)
    layers.append({
        "layer": "L1 — Hypergraph Query",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    # Partition + serialize
    t0 = time.perf_counter()
    parts = hg.partition_by_type()
    leaf_data = [(n, serialize_partition(p)) for n, p in sorted(parts.items())]
    layers.append({
        "layer": "L1 — Serialize Partitions",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    # Layer 2: Verkle build + proof
    vt = VerkleTree()
    t0 = time.perf_counter()
    vt.build(leaf_data)
    layers.append({
        "layer": "L2 — Build Verkle Tree",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    t0 = time.perf_counter()
    for label, _ in leaf_data:
        vt.generate_proof(label)
    layers.append({
        "layer": "L2 — Generate All Proofs",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    t0 = time.perf_counter()
    for label, _ in leaf_data:
        proof = vt.generate_proof(label)
        vt.verify_proof(proof, vt.root_commitment)
    layers.append({
        "layer": "L2 — Verify All Proofs",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    # Layer 3: Provenance DAG reasoning
    engine = SimulatedReasoningEngine(hg)
    rc = TemporalRootChain()
    rc.append_root(vt.root_commitment)
    pipeline = VHPPipeline(hg, vt, engine, rc)

    t0 = time.perf_counter()
    record = pipeline.process_query("Layer overhead test", entity_ids)
    layers.append({
        "layer": "L3 — Provenance Reasoning",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    # Audit verification
    t0 = time.perf_counter()
    pipeline.verify_record(record)
    layers.append({
        "layer": "Audit Verification",
        "ms": round((time.perf_counter() - t0) * 1000, 4),
    })

    total = sum(l["ms"] for l in layers)
    return {"layers": layers, "total_ms": round(total, 4)}


# -----------------------------------------------------------------------
# NEW: Provenance DAG depth / node-count across varying query complexity
# -----------------------------------------------------------------------
@router.post("/dag-complexity")
def dag_complexity_benchmark():
    """Measure how DAG depth and node count vary with query breadth."""
    from vhp.pipeline import VHPPipeline
    from vhp.reasoning import SimulatedReasoningEngine
    from vhp.verkle import TemporalRootChain

    state = get_state()
    hg = state.hypergraph

    parts = hg.partition_by_type()
    leaf_data = [(n, serialize_partition(p)) for n, p in sorted(parts.items())]
    vt = VerkleTree()
    vt.build(leaf_data)

    # Dynamically build scenarios at increasing entity counts
    all_drug_ids = [eid for eid, e in hg.entities.items() if e.type == "drug"]
    random.shuffle(all_drug_ids)
    pool = all_drug_ids[:10]  # pick 10 drugs for varying-size queries
    scenarios = [
        (f"{k} entities", set(pool[:k]))
        for k in range(2, min(len(pool) + 1, 8))
    ]

    results: list[dict] = []
    for label, eids in scenarios:
        engine = SimulatedReasoningEngine(hg)
        rc = TemporalRootChain()
        rc.append_root(vt.root_commitment)
        pipeline = VHPPipeline(hg, vt, engine, rc)

        available = eids & set(hg.entities.keys())
        if len(available) < 2:
            continue

        t0 = time.perf_counter()
        record = pipeline.process_query(f"DAG complexity test ({label})", available)
        elapsed = (time.perf_counter() - t0) * 1000

        results.append({
            "label": label,
            "entities": len(available),
            "dag_nodes": record.provenance_dag.node_count,
            "dag_depth": record.provenance_dag.depth,
            "verkle_proofs": record.verkle_proofs_count,
            "query_ms": round(elapsed, 4),
        })

    return {"results": results}


# -----------------------------------------------------------------------
# NEW: Hypergraph vs Pairwise detection comparison
# -----------------------------------------------------------------------
@router.post("/hypergraph-vs-pairwise")
def hypergraph_vs_pairwise():
    """Compare multi-factor risk detection: hypergraph vs pairwise-only."""
    state = get_state()
    hg = state.hypergraph

    # Dynamically build test scenarios from loaded data
    all_drugs = [eid for eid, e in hg.entities.items() if e.type == "drug"]
    random.shuffle(all_drugs)
    pool = all_drugs[:8]

    def _name(eid: str) -> str:
        return hg.entities[eid].name if eid in hg.entities else eid

    test_scenarios = [
        {"label": " + ".join(_name(d) for d in pool[:k]), "ids": set(pool[:k])}
        for k in range(2, min(len(pool) + 1, 7))
    ]

    comparisons: list[dict] = []
    for scenario in test_scenarios:
        eids = scenario["ids"] & set(hg.entities.keys())
        if len(eids) < 2:
            continue

        # Pairwise-only: count pairwise edges involving these entities
        pairwise_hits = 0
        for edge in hg.pairwise_edges:
            if edge.source_id in eids and edge.target_id in eids:
                pairwise_hits += 1

        # Hyperedge: count hyperedges involving ≥2 of these entities
        hyperedge_hits = 0
        hyperedge_labels: list[str] = []
        for he in hg.hyperedges:
            overlap = set(he.entity_ids) & eids
            if len(overlap) >= 2:
                hyperedge_hits += 1
                hyperedge_labels.append(he.label)

        # In pairwise-only, multi-factor combos go undetected
        multi_factor_detected_pairwise = pairwise_hits > 0
        multi_factor_detected_hyper = hyperedge_hits > 0

        comparisons.append({
            "scenario": scenario["label"],
            "entity_count": len(eids),
            "pairwise_edges_found": pairwise_hits,
            "hyperedges_found": hyperedge_hits,
            "hyperedge_labels": hyperedge_labels[:3],
            "pairwise_detects_risk": multi_factor_detected_pairwise,
            "hypergraph_detects_risk": multi_factor_detected_hyper,
        })

    # Summary stats
    total = len(comparisons)
    pairwise_detected = sum(1 for c in comparisons if c["pairwise_detects_risk"])
    hyper_detected = sum(1 for c in comparisons if c["hypergraph_detects_risk"])

    return {
        "comparisons": comparisons,
        "summary": {
            "total_scenarios": total,
            "pairwise_detection_rate": round(pairwise_detected / total * 100, 1) if total else 0,
            "hypergraph_detection_rate": round(hyper_detected / total * 100, 1) if total else 0,
        },
    }


# -----------------------------------------------------------------------
# NEW: Verkle vs Merkle build-time comparison at scale
# -----------------------------------------------------------------------
@router.post("/build-time-comparison")
def build_time_comparison():
    """Compare Verkle vs Merkle tree build + proof times at varying scale."""
    results: list[dict] = []

    for n in [4, 16, 64, 256, 512, 1024]:
        leaf_data = [
            (f"leaf_{i}", hashlib.sha256(f"d_{i}".encode()).digest())
            for i in range(n)
        ]

        # Verkle
        vt = VerkleTree()
        t0 = time.perf_counter()
        vt.build(leaf_data)
        verkle_build = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        vp = vt.generate_proof("leaf_0")
        verkle_proof = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        vt.verify_proof(vp, vt.root_commitment)
        verkle_verify = (time.perf_counter() - t0) * 1000

        # Merkle
        mt = MerkleTree()
        t0 = time.perf_counter()
        mt.build(leaf_data)
        merkle_build = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        mp = mt.generate_proof("leaf_0")
        merkle_proof = (time.perf_counter() - t0) * 1000

        # Merkle verify: recompute root from proof siblings
        t0 = time.perf_counter()
        current = hashlib.sha256(b"d_0").digest()
        current = hashlib.sha256(current).digest()  # leaf hash
        for sib_hash, direction in mp.sibling_hashes:
            if direction == "left":
                current = hashlib.sha256(sib_hash + current).digest()
            else:
                current = hashlib.sha256(current + sib_hash).digest()
        merkle_verify = (time.perf_counter() - t0) * 1000

        results.append({
            "leaves": n,
            "verkle_build_ms": round(verkle_build, 4),
            "merkle_build_ms": round(merkle_build, 4),
            "verkle_proof_ms": round(verkle_proof, 4),
            "merkle_proof_ms": round(merkle_proof, 4),
            "verkle_verify_ms": round(verkle_verify, 4),
            "merkle_verify_ms": round(merkle_verify, 4),
        })

    return {"results": results}
