"""VHP Pipeline — connects all three layers + reasoning engine.

The pipeline processes a query through:
  1. Reasoning engine iterates (think → act → observe)
  2. Each observation queries the Hypergraph (Layer 1)
  3. Each query generates Verkle proofs (Layer 2)
  4. Every step is recorded in a Provenance DAG (Layer 3)
  5. An AuditRecord is sealed with a cryptographic hash
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set, Tuple

from vhp.audit import AuditRecord, AuditVerifier
from vhp.hypergraph import Hypergraph, HypergraphPartition
from vhp.provenance import NodeType, ProvenanceDAG
from vhp.reasoning import ReasoningEngine, SimulatedReasoningEngine
from vhp.serialization import serialize_partition
from vhp.verkle import TemporalRootChain, VerkleProof, VerkleTree

logger = logging.getLogger(__name__)


class VHPPipeline:
    """Complete VHP pipeline connecting all layers."""

    def __init__(
        self,
        hypergraph: Hypergraph,
        verkle_tree: VerkleTree,
        engine: ReasoningEngine,
        root_chain: TemporalRootChain,
    ):
        self.hg = hypergraph
        self.vt = verkle_tree
        self.engine = engine
        self.root_chain = root_chain
        self.partitions = hypergraph.partition_by_type()
        self._audit_records: list[AuditRecord] = []

    def process_query(self, query: str, entity_ids: Set[str]) -> AuditRecord:
        """Process a query through the full VHP pipeline."""
        logger.info("Processing query: %s with entities: %s", query, entity_ids)

        # Reset engine state for new query
        if isinstance(self.engine, SimulatedReasoningEngine):
            self.engine.reset(entity_ids)
        elif hasattr(self.engine, "reset"):
            self.engine.reset(entity_ids)

        dag = ProvenanceDAG()
        observations: list[str] = []
        all_proofs: list[VerkleProof] = []
        iteration = 0
        prior_nodes: list[str] = []

        while self.engine.should_continue(iteration, observations):
            context = "\n".join(observations) if observations else "No observations yet."

            # THINK
            thought = self.engine.think(query, context)
            thought_id = dag.add_thought(
                thought, depends_on=prior_nodes if prior_nodes else None
            )

            # ACT
            action_type, targets = self.engine.parse_action(thought)
            action_id = dag.add_action(
                f"{action_type}: {targets}",
                depends_on=[thought_id],
                kg_queries=[action_type],
            )

            # OBSERVE (query verified hypergraph)
            obs_text, proofs, hedge_ids = self._execute_action(action_type, targets)
            obs_id = dag.add_observation(
                obs_text,
                depends_on=[action_id],
                verkle_proofs=proofs,
                hyperedges=hedge_ids,
            )
            observations.append(obs_text)
            all_proofs.extend(proofs)

            prior_nodes = [obs_id]
            iteration += 1

        # CONCLUDE
        conclusion = self.engine.synthesize(query, observations)
        all_obs_ids = [
            nid for nid, n in dag.nodes.items()
            if n.node_type == NodeType.OBSERVATION
        ]
        dag.add_conclusion(conclusion, depends_on=all_obs_ids)

        # Seal audit record
        record = AuditRecord(
            query=query,
            timestamp=time.time(),
            verkle_root=self.vt.root_commitment,
            provenance_dag=dag,
            verkle_proofs_count=len(all_proofs),
            final_response=conclusion,
        )
        record.compute_hash()
        self._audit_records.append(record)

        return record

    def _execute_action(
        self, action_type: str, targets: Set[str]
    ) -> Tuple[str, List[VerkleProof], List[str]]:
        """Execute an action against the hypergraph, returning (text, proofs, hedge_ids)."""
        proofs: list[VerkleProof] = []
        hedge_ids: list[str] = []

        if action_type == "check_pairwise":
            return self._check_pairwise(targets, proofs, hedge_ids)
        elif action_type == "check_conditions":
            return self._check_conditions(targets, proofs, hedge_ids)
        elif action_type == "check_hyperedges":
            return self._check_hyperedges(targets, proofs, hedge_ids)
        return "Unknown action", proofs, hedge_ids

    def _check_pairwise(
        self, targets: Set[str], proofs: list, hedge_ids: list
    ) -> Tuple[str, List[VerkleProof], List[str]]:
        interactions: list[str] = []
        target_list = list(targets)
        for i, eid_a in enumerate(target_list):
            for eid_b in target_list[i + 1:]:
                for neighbor_id, edge in self.hg.get_neighbors(eid_a, "interacts_with"):
                    if neighbor_id == eid_b:
                        sev = dict(edge.properties).get("severity", "unknown")
                        interactions.append(f"{eid_a}<->{eid_b} ({sev})")

        # Proof for the pairwise interactions partition
        for pname in self.partitions:
            if "interacts_with" in pname:
                try:
                    proofs.append(self.vt.generate_proof(pname))
                except KeyError:
                    pass

        if interactions:
            return (
                f"PAIRWISE: Found {len(interactions)} interactions: {'; '.join(interactions[:3])}",
                proofs,
                hedge_ids,
            )
        return "PAIRWISE: No direct interactions found", proofs, hedge_ids

    def _check_conditions(
        self, targets: Set[str], proofs: list, hedge_ids: list
    ) -> Tuple[str, List[VerkleProof], List[str]]:
        conditions: list[str] = []
        for eid in targets:
            if eid in self.hg.entities and self.hg.entities[eid].type == "condition":
                conditions.append(eid)
            for neighbor_id, edge in self.hg.get_neighbors(eid, "has_condition"):
                conditions.append(neighbor_id)

        contras: list[str] = []
        drug_ids = [
            e for e in targets
            if e in self.hg.entities and self.hg.entities[e].type == "drug"
        ]
        for drug in drug_ids:
            for neighbor_id, edge in self.hg.get_neighbors(drug, "contraindicated_for"):
                if neighbor_id in conditions or neighbor_id in targets:
                    contras.append(f"{drug} contraindicated for {neighbor_id}")

        for pname in self.partitions:
            if "contraindicated" in pname:
                try:
                    proofs.append(self.vt.generate_proof(pname))
                except KeyError:
                    pass

        if contras:
            return f"WARNING: {'; '.join(contras)}", proofs, hedge_ids
        return "CONDITIONS: No contraindications found with patient conditions", proofs, hedge_ids

    def _check_hyperedges(
        self, targets: Set[str], proofs: list, hedge_ids: list
    ) -> Tuple[str, List[VerkleProof], List[str]]:
        matching = self.hg.get_matching_hyperedges(targets)
        involved = self.hg.get_hyperedges_for_entities(targets)

        for pname in self.partitions:
            if "hyperedge" in pname:
                try:
                    proofs.append(self.vt.generate_proof(pname))
                except KeyError:
                    pass

        hedge_ids = [h.id for h in matching + involved]

        critical = [h for h in matching if h.severity >= 0.8]
        moderate = [h for h in involved if h not in matching and h.severity >= 0.5]

        if critical:
            details = "; ".join(
                f"{set(h.entity_ids)}→{h.label}(sev:{h.severity})"
                for h in critical[:2]
            )
            return (
                f"CRITICAL HYPEREDGE: {len(critical)} multi-factor risks: {details}",
                proofs,
                hedge_ids,
            )
        elif moderate:
            return (
                f"MODERATE: {len(moderate)} related hyperedges found",
                proofs,
                hedge_ids,
            )
        return "HYPEREDGES: No multi-factor risks detected", proofs, hedge_ids

    @property
    def audit_records(self) -> List[AuditRecord]:
        return list(self._audit_records)

    def verify_record(self, record: AuditRecord) -> dict:
        verifier = AuditVerifier()
        return verifier.verify(record, trusted_root=self.vt.root_commitment).to_dict()
