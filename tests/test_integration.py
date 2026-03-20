"""Integration tests: full VHP pipeline end-to-end."""

from vhp.audit import AuditVerifier
from vhp.pipeline import VHPPipeline
from vhp.reasoning import SimulatedReasoningEngine
from vhp.serialization import serialize_partition
from vhp.verkle import TemporalRootChain, VerkleTree


def _build_pipeline(hg):
    parts = hg.partition_by_type()
    leaf_data = [(n, serialize_partition(p)) for n, p in sorted(parts.items())]
    vt = VerkleTree()
    vt.build(leaf_data)
    rc = TemporalRootChain()
    rc.append_root(vt.root_commitment)
    engine = SimulatedReasoningEngine(hg)
    return VHPPipeline(hg, vt, engine, rc)


def _pick_drug_pair(hg):
    """Return two drug IDs that have a pairwise interaction."""
    for edge in hg.pairwise_edges:
        if edge.source_id in hg.entities and edge.target_id in hg.entities:
            return {edge.source_id, edge.target_id}
    # Fall back: just pick first two drugs
    drugs = [eid for eid, e in hg.entities.items() if e.type == "drug"]
    return set(drugs[:2])


def _pick_severe_pair(hg):
    """Return a drug pair with a severe interaction (or any pair as fallback)."""
    for edge in hg.pairwise_edges:
        sev = edge.props_dict().get("severity", "low")
        if sev == "severe":
            return {edge.source_id, edge.target_id}
    return _pick_drug_pair(hg)


def test_full_pipeline_query(sample_hypergraph):
    pipeline = _build_pipeline(sample_hypergraph)
    entity_ids = _pick_drug_pair(sample_hypergraph)
    record = pipeline.process_query(
        "Integration test query",
        entity_ids,
    )
    assert record.final_response is not None
    assert record.provenance_dag.node_count > 0
    assert record.record_hash != b""

    result = AuditVerifier().verify(record, trusted_root=pipeline.vt.root_commitment)
    assert result.overall_valid


def test_full_pipeline_severe_interaction(sample_hypergraph):
    pipeline = _build_pipeline(sample_hypergraph)
    entity_ids = _pick_severe_pair(sample_hypergraph)
    record = pipeline.process_query(
        "Severe interaction test",
        entity_ids,
    )
    assert record.final_response is not None
    result = AuditVerifier().verify(record, trusted_root=pipeline.vt.root_commitment)
    assert result.overall_valid


def test_pipeline_audit_records_accumulate(sample_hypergraph):
    pipeline = _build_pipeline(sample_hypergraph)
    pair = _pick_drug_pair(sample_hypergraph)
    pipeline.process_query("Q1", pair)
    assert len(pipeline.audit_records) == 1


def test_tamper_detection_after_pipeline(sample_hypergraph):
    pipeline = _build_pipeline(sample_hypergraph)
    pair = _pick_drug_pair(sample_hypergraph)
    record = pipeline.process_query("Test", pair)

    # Tamper
    record.final_response = "MALICIOUS OUTPUT"
    result = AuditVerifier().verify(record)
    assert not result.record_hash_valid
    assert not result.overall_valid


def test_proof_sizes_at_scale():
    """Verify proof size remains constant as tree grows."""
    import hashlib
    from vhp.verkle import VerkleTree, MerkleTree

    for n in [8, 64, 256, 1024]:
        ld = [(f"l{i}", hashlib.sha256(f"d{i}".encode()).digest()) for i in range(n)]
        vt = VerkleTree()
        vt.build(ld)
        vp = vt.generate_proof("l0")
        assert vp.size_bytes == 96, f"Verkle proof not constant at n={n}"

        mt = MerkleTree()
        mt.build(ld)
        mp = mt.generate_proof("l0")
        assert mp.size_bytes > 0
        assert vp.size_bytes <= mp.size_bytes
