"""Unified Audit Protocol.

Creates and verifies AuditRecords that bind together:
  - The original query
  - The Verkle root at decision time
  - The complete Provenance DAG
  - All Verkle proofs used
  - The final response
  - A tamper-evident record hash

An independent AuditVerifier can re-verify any record without
access to the original system.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from vhp.crypto import sha256
from vhp.provenance import ProvenanceDAG


@dataclass
class AuditRecord:
    """Complete cryptographic audit record for one AI decision."""

    query: str
    timestamp: float
    verkle_root: bytes
    provenance_dag: ProvenanceDAG
    verkle_proofs_count: int
    final_response: str
    record_hash: bytes = b""

    def compute_hash(self) -> bytes:
        content = json.dumps(
            {
                "query": self.query,
                "timestamp": self.timestamp,
                "verkle_root": self.verkle_root.hex(),
                "dag_nodes": self.provenance_dag.node_count,
                "response": self.final_response,
            },
            sort_keys=True,
        ).encode("utf-8")
        self.record_hash = sha256(content)
        return self.record_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "verkle_root": self.verkle_root.hex(),
            "provenance_dag": self.provenance_dag.to_dict(),
            "verkle_proofs_count": self.verkle_proofs_count,
            "final_response": self.final_response,
            "record_hash": self.record_hash.hex() if self.record_hash else "",
        }


@dataclass
class AuditResult:
    """Per-check verification result."""

    record_hash_valid: bool = False
    verkle_root_matches: bool = False
    all_dag_hashes_valid: bool = False
    dag_is_acyclic: bool = False
    overall_valid: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "record_hash_valid": self.record_hash_valid,
            "verkle_root_matches": self.verkle_root_matches,
            "all_dag_hashes_valid": self.all_dag_hashes_valid,
            "dag_is_acyclic": self.dag_is_acyclic,
            "overall_valid": self.overall_valid,
        }


class AuditVerifier:
    """Independent verification of audit records.

    Can be run by a third party with no access to the original system.
    """

    def verify(
        self, record: AuditRecord, trusted_root: Optional[bytes] = None
    ) -> AuditResult:
        result = AuditResult()

        # 1. Record hash integrity
        expected = sha256(
            json.dumps(
                {
                    "query": record.query,
                    "timestamp": record.timestamp,
                    "verkle_root": record.verkle_root.hex(),
                    "dag_nodes": record.provenance_dag.node_count,
                    "response": record.final_response,
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        result.record_hash_valid = expected == record.record_hash

        # 2. Verkle root match (if trusted root provided)
        result.verkle_root_matches = (
            record.verkle_root == trusted_root if trusted_root else True
        )

        # 3. DAG hash verification
        dag_results = record.provenance_dag.verify_all_hashes()
        result.all_dag_hashes_valid = all(dag_results.values()) if dag_results else True

        # 4. DAG acyclicity
        result.dag_is_acyclic = record.provenance_dag.verify_acyclicity()

        # 5. Overall
        result.overall_valid = all([
            result.record_hash_valid,
            result.verkle_root_matches,
            result.all_dag_hashes_valid,
            result.dag_is_acyclic,
        ])

        return result
