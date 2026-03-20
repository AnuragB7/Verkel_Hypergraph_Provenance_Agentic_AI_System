"""Reasoning router — query processing through VHP pipeline."""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_state

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    query: str
    entity_ids: list[str]


@router.post("/query")
def process_query(req: QueryRequest):
    state = get_state()
    record = state.pipeline.process_query(req.query, set(req.entity_ids))
    verification = state.pipeline.verify_record(record)
    return {
        "query": record.query,
        "response": record.final_response,
        "verkle_root": record.verkle_root.hex()[:32] + "...",
        "dag": record.provenance_dag.to_dict(),
        "verkle_proofs_count": record.verkle_proofs_count,
        "record_hash": record.record_hash.hex(),
        "verification": verification,
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@router.post("/query/stream")
def stream_query(req: QueryRequest):
    """Stream reasoning steps with token-level streaming for LLM outputs."""

    def generate():
        state = get_state()
        pipeline = state.pipeline
        engine = pipeline.engine

        from vhp.provenance import ProvenanceDAG, NodeType
        from vhp.reasoning import OllamaReasoningEngine

        is_ollama = isinstance(engine, OllamaReasoningEngine)
        entity_ids = set(req.entity_ids)

        logger.info("=== STREAM QUERY: %s | entities: %s | engine: %s ===",
                     req.query, req.entity_ids, type(engine).__name__)

        if hasattr(engine, "reset"):
            engine.reset(entity_ids)

        dag = ProvenanceDAG()
        observations: list[str] = []
        all_proofs = []
        iteration = 0
        prior_nodes: list[str] = []

        while engine.should_continue(iteration, observations):
            context = "\n".join(observations) if observations else "No observations yet."
            logger.info("--- Iteration %d ---", iteration)

            # THINK (token-stream if Ollama)
            logger.info("THINK: generating…")
            yield _sse({"type": "step_start", "step_type": "thought"})

            if is_ollama:
                prompt = engine.build_think_prompt(req.query, context)
                thought_parts = []
                for token, _done in engine.stream_ollama(prompt):
                    thought_parts.append(token)
                    yield _sse({"type": "token", "text": token})
                thought = "".join(thought_parts)
            else:
                thought = engine.think(req.query, context)
                yield _sse({"type": "token", "text": thought})

            thought_id = dag.add_thought(thought, depends_on=prior_nodes if prior_nodes else None)
            node = dag.nodes[thought_id]
            logger.info("THOUGHT [%s]: %.100s…", thought_id, thought)
            yield _sse({"type": "step_end", "step_type": "thought", "id": thought_id,
                         "hash": node.node_hash.hex()[:16]})

            # ACT (instant)
            action_type, targets = engine.parse_action(thought)
            action_content = f"{action_type}: {sorted(targets)}"
            action_id = dag.add_action(action_content, depends_on=[thought_id], kg_queries=[action_type])
            node = dag.nodes[action_id]
            logger.info("ACTION [%s]: %s", action_id, action_content)
            yield _sse({"type": "step_start", "step_type": "action"})
            yield _sse({"type": "token", "text": action_content})
            yield _sse({"type": "step_end", "step_type": "action", "id": action_id,
                         "hash": node.node_hash.hex()[:16], "depends_on": [thought_id]})

            # OBSERVE (instant — hypergraph lookup)
            logger.info("OBSERVE: querying hypergraph…")
            obs_text, proofs, hedge_ids = pipeline._execute_action(action_type, targets)
            obs_id = dag.add_observation(obs_text, depends_on=[action_id], verkle_proofs=proofs, hyperedges=hedge_ids)
            node = dag.nodes[obs_id]
            observations.append(obs_text)
            all_proofs.extend(proofs)
            logger.info("OBSERVATION [%s]: %s (proofs: %d)", obs_id, obs_text[:100], len(proofs))
            yield _sse({"type": "step_start", "step_type": "observation"})
            yield _sse({"type": "token", "text": obs_text})
            yield _sse({"type": "step_end", "step_type": "observation", "id": obs_id,
                         "hash": node.node_hash.hex()[:16], "depends_on": [action_id],
                         "verkle_proofs": len(proofs)})

            prior_nodes = [obs_id]
            iteration += 1

        # CONCLUDE (token-stream if Ollama)
        logger.info("CONCLUDE: synthesizing…")
        yield _sse({"type": "step_start", "step_type": "conclusion"})

        if is_ollama:
            prompt = engine.build_synthesize_prompt(req.query, observations)
            conc_parts = []
            for token, _done in engine.stream_ollama(prompt):
                conc_parts.append(token)
                yield _sse({"type": "token", "text": token})
            conclusion = "".join(conc_parts)
        else:
            conclusion = engine.synthesize(req.query, observations)
            yield _sse({"type": "token", "text": conclusion})

        all_obs_ids = [nid for nid, n in dag.nodes.items() if n.node_type == NodeType.OBSERVATION]
        conc_id = dag.add_conclusion(conclusion, depends_on=all_obs_ids)
        conc_node = dag.nodes[conc_id]
        logger.info("CONCLUSION [%s]: %.100s…", conc_id, conclusion)
        yield _sse({"type": "step_end", "step_type": "conclusion", "id": conc_id,
                     "hash": conc_node.node_hash.hex()[:16], "depends_on": all_obs_ids})

        # Seal audit record
        from vhp.audit import AuditRecord
        record = AuditRecord(
            query=req.query,
            timestamp=time.time(),
            verkle_root=pipeline.vt.root_commitment,
            provenance_dag=dag,
            verkle_proofs_count=len(all_proofs),
            final_response=conclusion,
        )
        record.compute_hash()
        pipeline._audit_records.append(record)
        verification = pipeline.verify_record(record)
        logger.info("=== QUERY COMPLETE: hash=%s, proofs=%d ===",
                     record.record_hash.hex()[:16], len(all_proofs))

        yield _sse({"type": "done", "verification": verification,
                     "verkle_root": record.verkle_root.hex()[:32] + "...",
                     "verkle_proofs_count": record.verkle_proofs_count,
                     "dag_nodes": dag.node_count, "dag_depth": dag.depth,
                     "record_hash": record.record_hash.hex()})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/engine")
def get_engine_info():
    state = get_state()
    from vhp.reasoning import OllamaReasoningEngine
    engine = state.pipeline.engine
    model = engine.model if isinstance(engine, OllamaReasoningEngine) else None
    return {"engine_type": state.engine_type, "model": model}


@router.get("/models")
def list_models():
    """List available Ollama models."""
    import httpx
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"models": models}
    except Exception:
        return {"models": []}


class SwitchRequest(BaseModel):
    model: str


@router.post("/engine/switch")
def switch_model(req: SwitchRequest):
    """Switch the Ollama model without reloading the hypergraph."""
    state = get_state()
    from vhp.reasoning import OllamaReasoningEngine, get_engine

    logger.info("Switching model to: %s", req.model)
    new_engine = get_engine("ollama", state.hypergraph, model=req.model)
    state.pipeline.engine = new_engine
    state._engine_type = "ollama"
    return {"engine_type": "ollama", "model": req.model}


@router.get("/scenarios")
def get_demo_scenarios():
    """Build demo scenarios dynamically from loaded DrugBank data."""
    state = get_state()
    hg = state.hypergraph
    scenarios: list[dict] = []

    def _name(eid: str) -> str:
        return hg.entities[eid].name if eid in hg.entities else eid

    # 1. Severe DDI pair
    for edge in hg.pairwise_edges:
        sev = edge.props_dict().get("severity", "low")
        if sev == "severe":
            scenarios.append({
                "name": f"Severe DDI: {_name(edge.source_id)} + {_name(edge.target_id)}",
                "query": f"Can {_name(edge.source_id)} and {_name(edge.target_id)} be prescribed together?",
                "entity_ids": [edge.source_id, edge.target_id],
                "expected_outcome": "contraindicated",
            })
            break

    # 2. CYP450 metabolic conflict hyperedge
    for he in hg.hyperedges:
        if he.label == "metabolic_conflict":
            names = [_name(eid) for eid in sorted(he.entity_ids)]
            scenarios.append({
                "name": f"CYP450 Conflict: {' + '.join(names[:3])}",
                "query": f"Metabolic conflict risk for {', '.join(names[:3])}?",
                "entity_ids": sorted(he.entity_ids)[:3],
                "expected_outcome": "caution",
            })
            break

    # 3. Low-risk pair
    for edge in hg.pairwise_edges:
        sev = edge.props_dict().get("severity", "low")
        if sev == "low":
            scenarios.append({
                "name": f"Low-Risk: {_name(edge.source_id)} + {_name(edge.target_id)}",
                "query": f"Is it safe to combine {_name(edge.source_id)} with {_name(edge.target_id)}?",
                "entity_ids": [edge.source_id, edge.target_id],
                "expected_outcome": "safe",
            })
            break

    # 4. Polypharmacy risk hyperedge
    for he in hg.hyperedges:
        if he.label == "polypharmacy_risk":
            names = [_name(eid) for eid in sorted(he.entity_ids)]
            scenarios.append({
                "name": f"Polypharmacy: {' + '.join(names[:3])}",
                "query": f"Polypharmacy risk assessment for {', '.join(names[:3])}",
                "entity_ids": sorted(he.entity_ids)[:3],
                "expected_outcome": "caution",
            })
            break

    return scenarios
