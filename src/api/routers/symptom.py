"""Symptom Checker router — GraphRAG-powered symptom→drug matching + safety check.

Pipeline:
  1. Semantic search: embed symptoms → cosine similarity against drug indications
  2. Graph expansion: traverse hypergraph from seed drugs to targets/pathways/enzymes
  3. Discover related drugs via shared biological entities
  4. LLM selection: reason over graph context to pick best drugs
  5. Safety check: DDI interactions + polypharmacy hyperedge alerts
  6. LLM safety conclusion with full graph context
"""

from __future__ import annotations

import json
import logging
import re
from itertools import combinations
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_state

router = APIRouter()
logger = logging.getLogger(__name__)


class SymptomRequest(BaseModel):
    symptoms: str
    age: int | None = None
    gender: str | None = None
    weight: float | None = None


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _keyword_fallback(symptoms: str, limit: int = 20) -> list[dict[str, Any]]:
    """Keyword-based fallback when embedding index is unavailable."""
    state = get_state()
    hg = state.hypergraph
    keywords = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", symptoms)]
    if not keywords:
        return []
    matches: list[tuple[int, dict]] = []
    for entity in hg.entities.values():
        if entity.type != "drug":
            continue
        indication = entity.props_dict().get("indication", "")
        if not indication:
            continue
        text = indication.lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            matches.append((score, {
                "id": entity.id,
                "name": entity.name,
                "indication": indication[:300],
                "similarity": score / len(keywords),
            }))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matches[:limit]]


def _check_interactions(drug_ids: list[str]) -> list[dict]:
    """Check pairwise DDI interactions between selected drugs."""
    state = get_state()
    hg = state.hypergraph
    id_set = set(drug_ids)
    interactions = []
    seen: set[tuple[str, str]] = set()

    for edge in hg.pairwise_edges:
        if edge.relation != "interacts_with":
            continue
        a, b = edge.source_id, edge.target_id
        if a in id_set and b in id_set:
            pair = (min(a, b), max(a, b))
            if pair in seen:
                continue
            seen.add(pair)
            props = edge.props_dict()
            name_a = hg.entities[a].name if a in hg.entities else a
            name_b = hg.entities[b].name if b in hg.entities else b
            interactions.append({
                "drug_a": a, "drug_b": b,
                "name_a": name_a, "name_b": name_b,
                "severity": props.get("severity", "unknown"),
                "description": props.get("description", ""),
            })

    return interactions


def _check_hyperedges(drug_ids: list[str]) -> list[dict]:
    """Check if any hyperedge covers 2+ of the selected drugs."""
    state = get_state()
    hg = state.hypergraph
    id_set = set(drug_ids)
    alerts = []
    for he in hg.hyperedges:
        overlap = id_set & set(he.entity_ids)
        if len(overlap) >= 2:
            alerts.append({
                "id": he.id,
                "label": he.label,
                "severity": he.severity,
                "overlap": sorted(overlap),
            })
    return alerts


@router.post("/analyze/stream")
def stream_symptom_analysis(req: SymptomRequest):
    """Stream GraphRAG symptom analysis."""

    def generate():
        state = get_state()
        from vhp.reasoning import OllamaReasoningEngine
        engine = state.pipeline.engine
        is_ollama = isinstance(engine, OllamaReasoningEngine)
        graphrag = state.graphrag

        # ── Phase 1: GraphRAG Retrieval ─────────────────────────────
        if graphrag and graphrag.index.ready:
            yield _sse({"type": "phase", "phase": "searching",
                        "message": "Semantic search + graph expansion (GraphRAG)..."})
            retrieval = graphrag.retrieve(req.symptoms, seed_k=10, max_related=15)
            seed_drugs = retrieval["seed_drugs"]
            related_drugs = retrieval["related_drugs"]
            graph_context = retrieval["graph_context"]
            subgraph_summary = retrieval["subgraph_summary"]

            yield _sse({"type": "candidates", "drugs": seed_drugs, "count": len(seed_drugs)})
            yield _sse({"type": "graph_expansion", "related_drugs": related_drugs,
                        "targets": len(graph_context.get("targets", {})),
                        "pathways": len(graph_context.get("pathways", {})),
                        "enzymes": len(graph_context.get("enzymes", {}))})

            if not seed_drugs:
                yield _sse({"type": "phase", "phase": "done",
                            "message": "No semantically matching drugs found."})
                yield _sse({"type": "done", "selected": [], "interactions": [],
                            "hyperedge_alerts": []})
                return

            # Build combined candidate list for LLM
            all_candidates = seed_drugs + related_drugs
        else:
            # Keyword fallback
            yield _sse({"type": "phase", "phase": "searching",
                        "message": "Keyword search (embedding index unavailable)..."})
            seed_drugs = _keyword_fallback(req.symptoms, limit=20)
            related_drugs = []
            graph_context = {}
            subgraph_summary = ""
            yield _sse({"type": "candidates", "drugs": seed_drugs, "count": len(seed_drugs)})

            if not seed_drugs:
                yield _sse({"type": "phase", "phase": "done",
                            "message": "No matching drugs found."})
                yield _sse({"type": "done", "selected": [], "interactions": [],
                            "hyperedge_alerts": []})
                return
            all_candidates = seed_drugs

        # ── Phase 2: LLM Drug Selection (with graph context) ──────
        yield _sse({"type": "phase", "phase": "llm_matching",
                    "message": "LLM reasoning over graph context..."})

        seed_list = "\n".join(
            f"  - {d['id']} ({d['name']}) [similarity={d.get('similarity', '?')}]: "
            f"{d['indication'][:200]}"
            for d in seed_drugs[:10]
        )

        graph_discovered = ""
        if related_drugs:
            graph_discovered = "\nGRAPH-DISCOVERED DRUGS (found via shared biological targets/pathways):\n"
            graph_discovered += "\n".join(
                f"  - {d['id']} ({d['name']}) [graph_score={d.get('graph_score', '?')}]: "
                + "; ".join(d.get("reasons", [])[:2])
                for d in related_drugs[:10]
            )

        patient_info = f"Patient symptoms: {req.symptoms}\n"
        if req.age is not None:
            patient_info += f"Age: {req.age} years\n"
        if req.gender:
            patient_info += f"Gender: {req.gender}\n"
        if req.weight is not None:
            patient_info += f"Weight: {req.weight} kg\n"

        prompt = (
            f"You are a clinical pharmacology assistant using GraphRAG retrieval.\n\n"
            f"{patient_info}\n"
            f"SEED DRUGS (matched by semantic similarity of indication text):\n"
            f"{seed_list}\n"
            f"{graph_discovered}\n\n"
        )
        if subgraph_summary:
            prompt += (
                f"HYPERGRAPH CONTEXT (biological relationships):\n"
                f"{subgraph_summary}\n\n"
            )
        demographics_note = ""
        if req.age is not None or req.gender or req.weight is not None:
            demographics_note = (
                "- Patient demographics (age, gender, weight) — adjust dosing "
                "and drug choice accordingly\n"
            )
        prompt += (
            f"Based on the symptoms, the semantic matches, AND the graph relationships, "
            f"select the 3-5 most appropriate drugs for this patient.\n"
            f"Consider:\n"
            f"- Direct indication match (seed drugs)\n"
            f"- Shared biological targets (graph-discovered drugs may act through "
            f"the same mechanism)\n"
            f"- Pathway relationships\n"
            f"{demographics_note}\n"
            f"For each drug, explain WHY it was selected and how the graph context "
            f"supports the choice.\n\n"
            f"IMPORTANT: Output EXACTLY this format at the end:\n"
            f"SELECTED: DB00001, DB00002, DB00003\n"
            f"(use actual DrugBank IDs from the lists above)"
        )

        yield _sse({"type": "prompt", "text": prompt})

        if is_ollama:
            llm_parts: list[str] = []
            try:
                for token, _done in engine.stream_ollama(prompt):
                    llm_parts.append(token)
                    yield _sse({"type": "token", "text": token})
                llm_response = "".join(llm_parts)
            except Exception as exc:
                logger.warning("LLM stream failed: %s", exc)
                llm_response = f"Could not reach LLM: {exc}"
                yield _sse({"type": "token", "text": llm_response})
        else:
            # Simulated: pick top 4 from seeds
            llm_response = "Simulated selection from GraphRAG candidates.\n"
            top = seed_drugs[:4]
            for d in top:
                llm_response += (
                    f"- {d['name']} ({d['id']}): "
                    f"indication similarity {d.get('similarity', '?')}\n"
                )
            llm_response += f"\nSELECTED: {', '.join(d['id'] for d in top)}"
            yield _sse({"type": "token", "text": llm_response})

        yield _sse({"type": "step_end", "step_type": "llm_matching"})

        # Parse selected drug IDs
        selected_ids: list[str] = []
        sel_match = re.search(r"SELECTED:\s*(.+)", llm_response, re.IGNORECASE)
        if sel_match:
            raw_ids = re.findall(r"DB\d{5}", sel_match.group(1))
            all_candidate_ids = {d["id"] for d in all_candidates}
            selected_ids = [did for did in raw_ids if did in all_candidate_ids]

        if not selected_ids:
            selected_ids = [d["id"] for d in seed_drugs[:4]]

        selected_drugs = []
        for did in selected_ids:
            for d in all_candidates:
                if d["id"] == did:
                    selected_drugs.append(d)
                    break
        yield _sse({"type": "selected", "drugs": selected_drugs})

        # ── Phase 3: Safety Check ──────────────────────────────────
        yield _sse({"type": "phase", "phase": "safety_check",
                    "message": "Checking drug-drug interactions..."})
        interactions = _check_interactions(selected_ids)
        yield _sse({"type": "interactions", "interactions": interactions,
                    "count": len(interactions)})

        # Hyperedge alerts
        hyperedge_alerts = _check_hyperedges(selected_ids)
        yield _sse({"type": "hyperedge_alerts", "alerts": hyperedge_alerts,
                    "count": len(hyperedge_alerts)})

        # ── Phase 4: LLM Safety Conclusion ─────────────────────────
        yield _sse({"type": "phase", "phase": "safety_conclusion",
                    "message": "LLM generating safety assessment..."})

        drug_names = ", ".join(f"{d['name']} ({d['id']})" for d in selected_drugs)
        interaction_summary = ""
        if interactions:
            interaction_summary = "Known drug-drug interactions:\n" + "\n".join(
                f"- {i['name_a']} + {i['name_b']}: {i['severity']} — {i['description'][:150]}"
                for i in interactions
            )
        else:
            interaction_summary = "No direct drug-drug interactions found in the hypergraph."

        hyperedge_summary = ""
        if hyperedge_alerts:
            hyperedge_summary = "Polypharmacy / category alerts:\n" + "\n".join(
                f"- {a['label']} (severity {a['severity']}): involves {', '.join(a['overlap'])}"
                for a in hyperedge_alerts
            )

        safety_patient = f"Patient symptoms: {req.symptoms}\n"
        if req.age is not None:
            safety_patient += f"Age: {req.age} years\n"
        if req.gender:
            safety_patient += f"Gender: {req.gender}\n"
        if req.weight is not None:
            safety_patient += f"Weight: {req.weight} kg\n"

        safety_prompt = (
            f"You are a clinical safety officer.\n\n"
            f"{safety_patient}"
            f"Suggested drugs: {drug_names}\n\n"
            f"{interaction_summary}\n\n"
            f"{hyperedge_summary}\n\n"
        )
        if subgraph_summary:
            safety_prompt += (
                f"BIOLOGICAL CONTEXT (from hypergraph):\n"
                f"Shared targets: {len(graph_context.get('targets', {}))}\n"
                f"Shared pathways: {len(graph_context.get('pathways', {}))}\n"
                f"Shared enzymes: {len(graph_context.get('enzymes', {}))}\n\n"
            )
        safety_prompt += (
            f"Provide a concise safety assessment:\n"
            f"1. Can these drugs be given together?\n"
            f"2. What are the key risks (considering DDI + shared biological targets)?\n"
            f"3. Any recommended alternatives or precautions?\n"
        )
        if req.age is not None or req.gender or req.weight is not None:
            safety_prompt += (
                f"4. Any age-, gender-, or weight-specific warnings for this patient?\n"
            )

        yield _sse({"type": "prompt", "text": safety_prompt})

        if is_ollama:
            conc_parts: list[str] = []
            try:
                for token, _done in engine.stream_ollama(safety_prompt):
                    conc_parts.append(token)
                    yield _sse({"type": "token", "text": token})
            except Exception as exc:
                logger.warning("Safety LLM failed: %s", exc)
                yield _sse({"type": "token", "text": f"LLM unavailable: {exc}"})
        else:
            if interactions:
                sev_counts: dict[str, int] = {}
                for i in interactions:
                    s = i["severity"]
                    sev_counts[s] = sev_counts.get(s, 0) + 1
                summary = ", ".join(f"{c} {s}" for s, c in sev_counts.items())
                msg = (
                    f"Safety check complete. Found {len(interactions)} "
                    f"interactions ({summary}). "
                    f"Review {', '.join(i['name_a'] + ' + ' + i['name_b'] for i in interactions[:3])} "
                    f"before prescribing."
                )
            else:
                msg = "No direct interactions found. These drugs appear safe to combine based on available data."
            if hyperedge_alerts:
                msg += f" Warning: {len(hyperedge_alerts)} polypharmacy alert(s) detected."
            yield _sse({"type": "token", "text": msg})

        yield _sse({"type": "step_end", "step_type": "safety_conclusion"})

        yield _sse({
            "type": "done",
            "selected": selected_drugs,
            "interactions": interactions,
            "hyperedge_alerts": hyperedge_alerts,
        })

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/analyze")
def analyze_symptoms(req: SymptomRequest):
    """Non-streaming version: GraphRAG search + safety check."""
    state = get_state()
    graphrag = state.graphrag

    if graphrag and graphrag.index.ready:
        retrieval = graphrag.retrieve(req.symptoms, seed_k=10, max_related=10)
        candidates = retrieval["seed_drugs"]
        related = retrieval["related_drugs"]
        selected_ids = [d["id"] for d in candidates[:4]]
    else:
        candidates = _keyword_fallback(req.symptoms, limit=10)
        related = []
        selected_ids = [d["id"] for d in candidates[:4]]

    interactions = _check_interactions(selected_ids)
    hyperedge_alerts = _check_hyperedges(selected_ids)
    return {
        "symptoms": req.symptoms,
        "candidates": candidates,
        "related_drugs": related,
        "selected": candidates[:4],
        "interactions": interactions,
        "hyperedge_alerts": hyperedge_alerts,
    }
