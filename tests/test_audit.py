"""Tests for the audit protocol."""

import time

from vhp.audit import AuditRecord, AuditResult, AuditVerifier
from vhp.provenance import ProvenanceDAG


def _make_record() -> AuditRecord:
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Check interaction")
    o1 = dag.add_observation("Found risk", depends_on=[t1])
    dag.add_conclusion("Caution needed", depends_on=[o1])

    record = AuditRecord(
        query="Is warfarin safe?",
        timestamp=time.time(),
        verkle_root=b"\xab" * 32,
        provenance_dag=dag,
        verkle_proofs_count=2,
        final_response="Caution needed",
    )
    record.compute_hash()
    return record


def test_create_audit_record():
    r = _make_record()
    assert r.record_hash != b""
    assert len(r.record_hash) == 32


def test_verify_valid_record():
    r = _make_record()
    v = AuditVerifier()
    result = v.verify(r, trusted_root=r.verkle_root)
    assert result.overall_valid


def test_verify_with_wrong_root():
    r = _make_record()
    v = AuditVerifier()
    result = v.verify(r, trusted_root=b"\x00" * 32)
    assert not result.verkle_root_matches
    assert not result.overall_valid


def test_tampered_record_detected():
    r = _make_record()
    # Tamper with response
    r.final_response = "TAMPERED"
    v = AuditVerifier()
    result = v.verify(r)
    assert not result.record_hash_valid
    assert not result.overall_valid


def test_tampered_dag_detected():
    r = _make_record()
    # Tamper with a DAG node
    first_node = list(r.provenance_dag.nodes.values())[0]
    first_node.content = "TAMPERED"
    v = AuditVerifier()
    result = v.verify(r)
    assert not result.all_dag_hashes_valid


def test_audit_result_to_dict():
    result = AuditResult(
        record_hash_valid=True,
        verkle_root_matches=True,
        all_dag_hashes_valid=True,
        dag_is_acyclic=True,
        overall_valid=True,
    )
    d = result.to_dict()
    assert all(d.values())


def test_record_to_dict():
    r = _make_record()
    d = r.to_dict()
    assert d["query"] == "Is warfarin safe?"
    assert "provenance_dag" in d
    assert d["verkle_proofs_count"] == 2
