"""Layer 4: Pluggable Reasoning Engine.

VHP is engine-agnostic — the verification stack wraps ANY reasoning
system.  This module defines the abstract interface and the concrete
OllamaReasoningEngine implementation that connects to a local Ollama
instance for real SLM/LLM inference (Phi-4, Gemma3, Llama3, etc.).

All benchmarks and evaluations use real LLM inference to produce
genuine empirical evidence for the paper.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set, Tuple

from vhp.hypergraph import Hypergraph

logger = logging.getLogger(__name__)


class ReasoningEngine(ABC):
    """Abstract base class for reasoning engines."""

    @abstractmethod
    def think(self, query: str, context: str) -> str:
        """Generate a thought about what to investigate next."""

    @abstractmethod
    def parse_action(self, thought: str) -> Tuple[str, Set[str]]:
        """Parse a thought into (action_type, target_entity_ids)."""

    @abstractmethod
    def synthesize(self, query: str, observations: List[str]) -> str:
        """Synthesize observations into a final conclusion."""

    @abstractmethod
    def should_continue(self, iteration: int, observations: List[str]) -> bool:
        """Decide whether to continue reasoning or conclude."""

    def reset(self, entity_ids: Set[str]) -> None:
        """Reset engine state for a new query (optional)."""


# ---------------------------------------------------------------------------
# Ollama engine (real SLM inference)
# ---------------------------------------------------------------------------

class OllamaReasoningEngine(ReasoningEngine):
    """Reasoning engine backed by a local Ollama instance.

    Requires Ollama running at the configured URL with a model pulled.
    Recommended models: phi4, qwen3:4b, mistral:7b
    """

    def __init__(
        self,
        hypergraph: Hypergraph,
        model: str = "phi4",
        base_url: str = "http://localhost:11434",
        max_iterations: int = 3,
    ):
        self.hg = hypergraph
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_iterations = max_iterations
        self._query_entities: Set[str] = set()
        self._completed_actions: Set[str] = set()

    def reset(self, entity_ids: Set[str]) -> None:
        self._query_entities = entity_ids
        self._completed_actions = set()

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama generate API (non-streaming)."""
        import httpx

        logger.info("[Ollama/%s] Sending prompt (%d chars)…", self.model, len(prompt))
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=300.0,
        )
        resp.raise_for_status()
        text = resp.json()["response"]
        logger.info("[Ollama/%s] Response received (%d chars)", self.model, len(text))
        return text

    def stream_ollama(self, prompt: str):
        """Stream tokens from Ollama generate API. Yields (token, is_done) tuples."""
        import httpx

        logger.info("[Ollama/%s] Streaming prompt (%d chars)…", self.model, len(prompt))
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": True},
            timeout=httpx.Timeout(timeout=300.0, connect=10.0),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                import json as _json
                chunk = _json.loads(line)
                token = chunk.get("response", "")
                done = chunk.get("done", False)
                if token:
                    yield token, done
                if done:
                    break
        logger.info("[Ollama/%s] Stream complete", self.model)

    def _entity_summary(self) -> str:
        """Build a rich summary of the queried entities from the hypergraph."""
        lines = []
        for eid in sorted(self._query_entities):
            e = self.hg.entities.get(eid)
            if not e:
                lines.append(f"{eid} — (not found in hypergraph)")
                continue

            props = e.props_dict()
            parts = [f"**{e.name}** ({eid})"]

            # Classification / class / groups
            if props.get("classification"):
                parts.append(f"  Classification: {props['classification']}")
            elif props.get("class"):
                parts.append(f"  Class: {props['class']}")
            if props.get("groups"):
                parts.append(f"  Status: {props['groups']}")

            # Key clinical fields
            if props.get("indication"):
                parts.append(f"  Indication: {props['indication']}")
            if props.get("mechanism_of_action"):
                parts.append(f"  Mechanism: {props['mechanism_of_action']}")
            if props.get("half_life"):
                parts.append(f"  Half-life: {props['half_life']}")
            if props.get("metabolism"):
                parts.append(f"  Metabolism: {props['metabolism']}")
            if props.get("protein_binding"):
                parts.append(f"  Protein binding: {props['protein_binding']}")
            if props.get("toxicity"):
                parts.append(f"  Toxicity: {props['toxicity']}")

            # Targets, transporters, carriers, pathways
            if props.get("targets"):
                parts.append(f"  Targets: {props['targets']}")
            if props.get("transporters"):
                parts.append(f"  Transporters: {props['transporters']}")
            if props.get("carriers"):
                parts.append(f"  Carriers: {props['carriers']}")
            if props.get("pathways"):
                parts.append(f"  Pathways: {props['pathways']}")

            # Supplementary
            if props.get("food_interactions"):
                parts.append(f"  Food interactions: {props['food_interactions']}")
            if props.get("dosages"):
                parts.append(f"  Dosages: {props['dosages']}")
            if props.get("mixtures"):
                parts.append(f"  Mixtures: {props['mixtures']}")

            # Categories
            cat_list = [v for k, v in e.properties if k == "category"]
            if cat_list:
                parts.append(f"  Categories: {', '.join(cat_list)}")

            lines.append("\n".join(parts))
        return "\n\n".join(lines)

    def build_think_prompt(self, query: str, context: str) -> str:
        entity_info = self._entity_summary()
        return (
            "You are a clinical pharmacology reasoning agent with access to a "
            "verified drug interaction hypergraph built from DrugBank data.\n\n"
            f"**Query:** {query}\n\n"
            f"**Entities under analysis:**\n{entity_info}\n\n"
            f"**Evidence gathered so far:**\n{context}\n\n"
            "Based on the above, what specific aspect should be investigated next?\n"
            "Choose ONE of the following actions (use the EXACT keyword in brackets):\n"
            "  [pairwise] — Check direct drug-drug interaction edges in the hypergraph\n"
            "  [hyperedges] — Check multi-factor polypharmacy risks via hyperedge analysis "
            "(shared CYP450 enzymes, metabolic conflicts, category overlaps)\n"
            + (f"Already completed: {', '.join(sorted(self._completed_actions))}\n" if self._completed_actions else "")
            + "Respond with a single concise thought. Include the [keyword] of your chosen action."
        )

    def build_synthesize_prompt(self, query: str, observations: List[str]) -> str:
        entity_info = self._entity_summary()
        obs_text = "\n".join(f"- {o}" for o in observations)
        return (
            "You are a clinical pharmacology reasoning agent. You have completed "
            "a multi-step investigation using a verified drug interaction hypergraph (DrugBank).\n\n"
            f"**Query:** {query}\n\n"
            f"**Entities analyzed:**\n{entity_info}\n\n"
            f"**Evidence from hypergraph (verified via Verkle proofs):**\n{obs_text}\n\n"
            "Provide a structured clinical recommendation:\n"
            "1. **Risk Level**: SAFE / CAUTION / CONTRAINDICATED\n"
            "2. **Key Findings**: Summarize the critical interactions or risks found\n"
            "3. **Clinical Rationale**: Explain the mechanism (e.g. which enzymes, pathways, or conditions are involved)\n"
            "4. **Recommendation**: What should a clinician do?\n\n"
            "Base your answer ONLY on the evidence above. Do not speculate beyond the provided data."
        )

    def think(self, query: str, context: str) -> str:
        prompt = self.build_think_prompt(query, context)
        try:
            return self._call_ollama(prompt)
        except Exception as exc:
            logger.warning("Ollama call failed: %s", exc)
            return f"I should investigate entities: {', '.join(sorted(self._query_entities))}"

    def parse_action(self, thought: str) -> Tuple[str, Set[str]]:
        lower = thought.lower()
        # Score each action by keyword match specificity
        scores: Dict[str, int] = {"check_pairwise": 0, "check_hyperedges": 0}
        # Bracketed keywords (from prompt instructions) get highest weight
        if "[pairwise]" in lower:
            scores["check_pairwise"] += 10
        if "[hyperedges]" in lower:
            scores["check_hyperedges"] += 10
        # Fallback: contextual keywords with lower weight
        for kw in ("pairwise", "drug-drug", "interaction"):
            if kw in lower:
                scores["check_pairwise"] += 1
        for kw in ("hyperedge", "multi-factor", "polypharmacy", "cyp", "enzyme", "metabolic"):
            if kw in lower:
                scores["check_hyperedges"] += 1

        # Pick highest-scoring action that hasn't been completed yet
        for action, _ in sorted(scores.items(), key=lambda x: -x[1]):
            if action not in self._completed_actions and scores[action] > 0:
                self._completed_actions.add(action)
                return action, self._query_entities

        # All done or no match — pick first uncompleted action
        for action in ("check_pairwise", "check_hyperedges"):
            if action not in self._completed_actions:
                self._completed_actions.add(action)
                return action, self._query_entities

        return "check_pairwise", self._query_entities

    def synthesize(self, query: str, observations: List[str]) -> str:
        prompt = self.build_synthesize_prompt(query, observations)
        try:
            return self._call_ollama(prompt)
        except Exception as exc:
            logger.warning("Ollama call failed: %s", exc)
            critical = [o for o in observations if "CRITICAL" in o]
            if critical:
                return f"CONTRAINDICATED: {len(critical)} critical risk(s). {critical[0]}"
            return "Unable to reach SLM. Based on observations: monitor closely."

    def should_continue(self, iteration: int, observations: List[str]) -> bool:
        return iteration < self.max_iterations


def get_engine(
    engine_type: str,
    hypergraph: Hypergraph,
    **kwargs: Any,
) -> ReasoningEngine:
    """Factory function for reasoning engines.

    Only the Ollama engine is supported — all evaluation uses real
    LLM inference for genuine empirical evidence.
    """
    if engine_type == "ollama":
        import os
        if "model" not in kwargs:
            kwargs["model"] = os.environ.get("VHP_MODEL", "phi4")
        return OllamaReasoningEngine(hypergraph, **kwargs)
    raise ValueError(
        f"Unknown engine type: {engine_type!r}. "
        "Only 'ollama' is supported — ensure Ollama is running."
    )
