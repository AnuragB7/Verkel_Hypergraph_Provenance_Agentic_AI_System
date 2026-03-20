"""GraphRAG retriever — semantic search + graph expansion for symptom→drug matching.

Flow:
  1. Embed symptoms via Ollama nomic-embed-text
  2. Cosine-similarity against cached drug-indication embeddings → seed drugs
  3. Graph expansion: 1-hop traversal from seeds to targets/pathways/enzymes/carriers
  4. Discover related drugs that share those biological entities
  5. Build rich subgraph context for LLM reasoning
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logger = logging.getLogger(__name__)

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
BATCH_SIZE = 200
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / ".cache"


# ── Vector utilities (no numpy dependency) ─────────────────────

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: List[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _cosine_sim(a: List[float], b: List[float]) -> float:
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


# ── Ollama embedding helper ───────────────────────────────────

def _embed_batch(texts: List[str], model: str = EMBED_MODEL) -> List[List[float]]:
    """Call Ollama /api/embed for a batch of texts."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": model, "input": texts},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _embed_single(text: str, model: str = EMBED_MODEL) -> List[float]:
    return _embed_batch([text], model)[0]


# ── Drug Embedding Index ──────────────────────────────────────
class DrugEmbeddingIndex:
    """Pre-computed embeddings for all drug indications, cached to disk."""

    def __init__(self):
        self.drug_ids: List[str] = []
        self.drug_names: List[str] = []
        self.indications: List[str] = []
        self.embeddings: List[List[float]] = []
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def build(self, hypergraph: Any) -> None:
        """Build embedding index from hypergraph drug entities."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Collect drugs with non-empty indications
        drugs: List[Tuple[str, str, str]] = []
        for entity in hypergraph.entities.values():
            if entity.type != "drug":
                continue
            indication = entity.props_dict().get("indication", "")
            if indication and len(indication.strip()) > 10:
                drugs.append((entity.id, entity.name, indication[:500]))

        drugs.sort(key=lambda d: d[0])
        logger.info("Found %d drugs with indications for embedding", len(drugs))

        # Check cache validity (hash of drug IDs + indication lengths)
        cache_key = hashlib.sha256(
            json.dumps([(d[0], len(d[2])) for d in drugs]).encode()
        ).hexdigest()[:16]
        cache_file = CACHE_DIR / f"drug_embeddings_{cache_key}.json"

        if cache_file.exists():
            logger.info("Loading cached embeddings from %s", cache_file.name)
            with open(cache_file) as f:
                cached = json.load(f)
            self.drug_ids = cached["drug_ids"]
            self.drug_names = cached["drug_names"]
            self.indications = cached["indications"]
            self.embeddings = cached["embeddings"]
            self._ready = True
            logger.info("Loaded %d cached drug embeddings", len(self.drug_ids))
            return

        # Compute embeddings in batches
        self.drug_ids = [d[0] for d in drugs]
        self.drug_names = [d[1] for d in drugs]
        self.indications = [d[2] for d in drugs]
        self.embeddings = []

        t0 = time.perf_counter()
        for i in range(0, len(drugs), BATCH_SIZE):
            batch = self.indications[i : i + BATCH_SIZE]
            # Prefix for nomic-embed-text search/document distinction
            prefixed = [f"search_document: {text}" for text in batch]
            embs = _embed_batch(prefixed)
            self.embeddings.extend(embs)
            if (i // BATCH_SIZE) % 10 == 0:
                logger.info(
                    "Embedded %d/%d drugs (%.0f%%)",
                    min(i + BATCH_SIZE, len(drugs)),
                    len(drugs),
                    min(100, (i + BATCH_SIZE) / len(drugs) * 100),
                )

        elapsed = time.perf_counter() - t0
        logger.info("Embedded %d drugs in %.1fs", len(self.drug_ids), elapsed)

        # Cache to disk
        with open(cache_file, "w") as f:
            json.dump(
                {
                    "drug_ids": self.drug_ids,
                    "drug_names": self.drug_names,
                    "indications": self.indications,
                    "embeddings": self.embeddings,
                },
                f,
            )
        logger.info("Cached embeddings to %s", cache_file.name)
        self._ready = True

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """Semantic search: embed query, return top-K drugs by cosine similarity."""
        if not self._ready:
            return []

        query_emb = _embed_single(f"search_query: {query}")
        scores = [
            (i, _cosine_sim(query_emb, emb)) for i, emb in enumerate(self.embeddings)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, sim in scores[:top_k]:
            results.append(
                {
                    "id": self.drug_ids[idx],
                    "name": self.drug_names[idx],
                    "indication": self.indications[idx],
                    "similarity": round(sim, 4),
                }
            )
        return results


# ── GraphRAG Retriever ────────────────────────────────────────
class GraphRAGRetriever:
    """Combines semantic search with graph traversal for drug retrieval."""

    def __init__(self, embedding_index: DrugEmbeddingIndex, hypergraph: Any):
        self.index = embedding_index
        self.hg = hypergraph

    def retrieve(
        self,
        symptoms: str,
        seed_k: int = 10,
        expand_hops: int = 1,
        max_related: int = 20,
    ) -> Dict[str, Any]:
        """
        Full GraphRAG retrieval pipeline.

        Returns dict with:
          - seed_drugs:   top-K from embedding search
          - graph_context: biological entities connected to seeds
          - related_drugs: drugs discovered via shared targets/pathways
          - subgraph_summary: text summary for LLM
        """
        # Step 1: Semantic seed retrieval
        seed_drugs = self.index.search(symptoms, top_k=seed_k)
        seed_ids = {d["id"] for d in seed_drugs}

        # Step 2: 1-hop graph expansion from seed drugs
        connected_targets: Dict[str, Set[str]] = {}   # target_id → set of drug_ids
        connected_pathways: Dict[str, Set[str]] = {}   # pathway_id → set of drug_ids
        connected_enzymes: Dict[str, Set[str]] = {}
        connected_transporters: Dict[str, Set[str]] = {}
        drug_bio_links: Dict[str, List[Dict]] = {}    # drug_id → list of bio links

        for drug_id in seed_ids:
            if drug_id not in self.hg.entities:
                continue
            neighbors = self.hg.get_neighbors(drug_id)
            bio_links = []
            for neighbor_id, edge in neighbors:
                neighbor = self.hg.entities.get(neighbor_id)
                if not neighbor:
                    continue
                link = {
                    "entity_id": neighbor_id,
                    "entity_name": neighbor.name,
                    "entity_type": neighbor.type,
                    "relation": edge.relation,
                }
                bio_links.append(link)

                if edge.relation == "targets":
                    connected_targets.setdefault(neighbor_id, set()).add(drug_id)
                elif edge.relation == "participates_in":
                    connected_pathways.setdefault(neighbor_id, set()).add(drug_id)
                elif edge.relation == "metabolized_by":
                    connected_enzymes.setdefault(neighbor_id, set()).add(drug_id)
                elif edge.relation == "transported_by":
                    connected_transporters.setdefault(neighbor_id, set()).add(drug_id)

            drug_bio_links[drug_id] = bio_links

        # Step 3: Find related drugs via shared targets/pathways (reverse traversal)
        related_drug_scores: Dict[str, float] = {}
        related_drug_reasons: Dict[str, List[str]] = {}

        for target_id, src_drugs in connected_targets.items():
            target = self.hg.entities.get(target_id)
            target_name = target.name if target else target_id
            # Find other drugs targeting the same protein
            for neighbor_id, edge in self.hg.get_neighbors(target_id):
                if neighbor_id in seed_ids or neighbor_id in related_drug_scores:
                    continue
                neighbor = self.hg.entities.get(neighbor_id)
                if not neighbor or neighbor.type != "drug":
                    continue
                related_drug_scores[neighbor_id] = related_drug_scores.get(neighbor_id, 0) + 2.0
                related_drug_reasons.setdefault(neighbor_id, []).append(
                    f"shares target {target_name} with {', '.join(src_drugs)}"
                )

        for pathway_id, src_drugs in connected_pathways.items():
            pathway = self.hg.entities.get(pathway_id)
            pw_name = pathway.name if pathway else pathway_id
            for neighbor_id, edge in self.hg.get_neighbors(pathway_id):
                if neighbor_id in seed_ids:
                    continue
                neighbor = self.hg.entities.get(neighbor_id)
                if not neighbor or neighbor.type != "drug":
                    continue
                related_drug_scores[neighbor_id] = related_drug_scores.get(neighbor_id, 0) + 1.0
                related_drug_reasons.setdefault(neighbor_id, []).append(
                    f"shares pathway {pw_name} with {', '.join(src_drugs)}"
                )

        # Sort related drugs by graph score
        related_sorted = sorted(
            related_drug_scores.items(), key=lambda x: x[1], reverse=True
        )[:max_related]

        related_drugs = []
        for drug_id, score in related_sorted:
            entity = self.hg.entities.get(drug_id)
            if not entity:
                continue
            indication = entity.props_dict().get("indication", "")
            related_drugs.append(
                {
                    "id": drug_id,
                    "name": entity.name,
                    "indication": indication[:300],
                    "graph_score": score,
                    "reasons": related_drug_reasons.get(drug_id, []),
                }
            )

        # Step 4: Check DDI interactions among all candidate drugs
        all_candidate_ids = list(seed_ids) + [d["id"] for d in related_drugs]

        # Step 5: Build graph context summary
        graph_context = {
            "targets": {
                tid: {
                    "name": self.hg.entities[tid].name if tid in self.hg.entities else tid,
                    "connected_seeds": sorted(drugs),
                }
                for tid, drugs in connected_targets.items()
            },
            "pathways": {
                pid: {
                    "name": self.hg.entities[pid].name if pid in self.hg.entities else pid,
                    "connected_seeds": sorted(drugs),
                }
                for pid, drugs in connected_pathways.items()
            },
            "enzymes": {
                eid: {
                    "name": self.hg.entities[eid].name if eid in self.hg.entities else eid,
                    "connected_seeds": sorted(drugs),
                }
                for eid, drugs in connected_enzymes.items()
            },
        }

        # Step 6: Build text summary for LLM
        summary_parts = []
        summary_parts.append(f"=== GraphRAG Retrieval for: {symptoms} ===\n")

        summary_parts.append("SEED DRUGS (by indication similarity):")
        for d in seed_drugs[:8]:
            summary_parts.append(
                f"  • {d['name']} ({d['id']}) [sim={d['similarity']}]: {d['indication'][:150]}"
            )

        if connected_targets:
            summary_parts.append(f"\nSHARED TARGETS ({len(connected_targets)} proteins):")
            for tid, drugs in list(connected_targets.items())[:10]:
                tname = self.hg.entities[tid].name if tid in self.hg.entities else tid
                summary_parts.append(f"  • {tname}: targeted by {', '.join(sorted(drugs))}")

        if connected_pathways:
            summary_parts.append(f"\nSHARED PATHWAYS ({len(connected_pathways)}):")
            for pid, drugs in list(connected_pathways.items())[:10]:
                pname = self.hg.entities[pid].name if pid in self.hg.entities else pid
                summary_parts.append(f"  • {pname}: involves {', '.join(sorted(drugs))}")

        if related_drugs:
            summary_parts.append(f"\nGRAPH-DISCOVERED DRUGS ({len(related_drugs)}):")
            for d in related_drugs[:8]:
                summary_parts.append(
                    f"  • {d['name']} ({d['id']}) [graph_score={d['graph_score']}]"
                )
                for r in d["reasons"][:2]:
                    summary_parts.append(f"      → {r}")

        subgraph_summary = "\n".join(summary_parts)

        return {
            "seed_drugs": seed_drugs,
            "graph_context": graph_context,
            "related_drugs": related_drugs,
            "drug_bio_links": drug_bio_links,
            "all_candidate_ids": all_candidate_ids,
            "subgraph_summary": subgraph_summary,
        }
