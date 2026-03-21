"""Application state and dependency injection for the VHP API."""

from __future__ import annotations

import logging
import os
import sys
import time as _time
from pathlib import Path
from typing import Optional

from vhp.audit import AuditRecord, AuditVerifier
from vhp.graphrag import DrugEmbeddingIndex, GraphRAGRetriever
from vhp.hypergraph import Hypergraph
from vhp.pipeline import VHPPipeline
from vhp.reasoning import ReasoningEngine, get_engine
from vhp.serialization import serialize_partition
from vhp.verkle import TemporalRootChain, VerkleTree

# Add backend/data to path so drugbank_loader is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "data"))

logger = logging.getLogger(__name__)


class AppState:
    """Singleton holding all VHP runtime state."""

    def __init__(self):
        self._hypergraph: Optional[Hypergraph] = None
        self._verkle: Optional[VerkleTree] = None
        self._root_chain: Optional[TemporalRootChain] = None
        self._pipeline: Optional[VHPPipeline] = None
        self._engine_type: str = "ollama"
        self._embedding_index: Optional[DrugEmbeddingIndex] = None
        self._graphrag: Optional[GraphRAGRetriever] = None

    def initialise(self, engine_type: str | None = None, **engine_kwargs) -> None:
        """Build the hypergraph, Verkle tree, and pipeline."""
        from drugbank_loader import load_drugbank

        xml_path = Path(__file__).resolve().parent.parent.parent / "data" / "drugbank.xml"
        max_drugs_env = os.environ.get("VHP_MAX_DRUGS")
        max_drugs = int(max_drugs_env) if max_drugs_env else None

        logger.info("Loading DrugBank from %s (max_drugs=%s) …", xml_path, max_drugs)
        t0 = _time.perf_counter()
        self._hypergraph = load_drugbank(str(xml_path), max_drugs=max_drugs)
        elapsed = _time.perf_counter() - t0
        hg = self._hypergraph
        logger.info(
            "DrugBank loaded: %d entities, %d edges, %d hyperedges in %.1fs",
            len(hg.entities), len(hg.pairwise_edges), len(hg.hyperedges), elapsed,
        )
        self._verkle = VerkleTree()
        self._root_chain = TemporalRootChain()

        # Build Verkle tree from hypergraph partitions
        partitions = self._hypergraph.partition_by_type()
        leaf_data = [
            (name, serialize_partition(p)) for name, p in sorted(partitions.items())
        ]
        self._verkle.build(leaf_data)
        self._root_chain.append_root(self._verkle.root_commitment)

        # Engine selection: env var > explicit arg > auto-detect Ollama > simulated
        if engine_type is None:
            engine_type = os.environ.get("VHP_ENGINE", "auto")
        if engine_type == "auto":
            engine_type = self._detect_engine(**engine_kwargs)
        self._engine_type = engine_type
        logger.info("Reasoning engine: %s", engine_type)
        engine = get_engine(engine_type, self._hypergraph, **engine_kwargs)
        self._pipeline = VHPPipeline(
            self._hypergraph, self._verkle, engine, self._root_chain
        )

        # Build embedding index for GraphRAG (async-friendly — cached to disk)
        try:
            self._embedding_index = DrugEmbeddingIndex()
            self._embedding_index.build(self._hypergraph)
            self._graphrag = GraphRAGRetriever(self._embedding_index, self._hypergraph)
            logger.info("GraphRAG embedding index ready (%d drugs)", len(self._embedding_index.drug_ids))
        except Exception as exc:
            logger.warning("GraphRAG embedding index failed (Ollama embedding model unavailable?): %s", exc)
            self._embedding_index = None
            self._graphrag = None

    def _detect_engine(self, **kwargs) -> str:
        """Verify Ollama is running and the model is available."""
        import httpx

        base_url = kwargs.get("base_url", "http://localhost:11434")
        model = kwargs.get("model", os.environ.get("VHP_MODEL", "phi4"))
        try:
            resp = httpx.get(f"{base_url}/api/tags", timeout=3.0)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Accept both exact match and prefix match (e.g. "llama3" matches "llama3:latest")
            if any(m == model or m.startswith(f"{model}:") for m in models):
                logger.info("Ollama detected with model '%s' — using LLM engine", model)
                return "ollama"
            logger.warning(
                "Ollama running but model '%s' not found (available: %s). "
                "Pull it with: ollama pull %s",
                model, models, model,
            )
        except Exception:
            logger.error(
                "Ollama not reachable at %s — VHP requires Ollama for real LLM inference. "
                "Start Ollama first: https://ollama.ai",
                base_url,
            )
        # Still return 'ollama' — it will error on first query, giving a clear message
        return "ollama"

    @property
    def hypergraph(self) -> Hypergraph:
        if self._hypergraph is None:
            self.initialise()
        return self._hypergraph  # type: ignore[return-value]

    @property
    def verkle(self) -> VerkleTree:
        if self._verkle is None:
            self.initialise()
        return self._verkle  # type: ignore[return-value]

    @property
    def root_chain(self) -> TemporalRootChain:
        if self._root_chain is None:
            self.initialise()
        return self._root_chain  # type: ignore[return-value]

    @property
    def pipeline(self) -> VHPPipeline:
        if self._pipeline is None:
            self.initialise()
        return self._pipeline  # type: ignore[return-value]

    @property
    def engine_type(self) -> str:
        return self._engine_type

    @property
    def graphrag(self) -> Optional[GraphRAGRetriever]:
        return self._graphrag

    @property
    def embedding_index(self) -> Optional[DrugEmbeddingIndex]:
        return self._embedding_index


# Module-level singleton
_state: Optional[AppState] = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
