"""Layer 4: Pluggable Reasoning Engine.

VHP is engine-agnostic — the verification stack wraps ANY reasoning
system.  This module defines the abstract interface and two concrete
implementations:

  1. SimulatedReasoningEngine  — deterministic rule-based logic for
     reproducible evaluation independent of LLM stochasticity.
  2. OllamaReasoningEngine     — connects to a local Ollama instance
     for actual SLM/LLM inference (Phi-4, Qwen3, Mistral, etc.).
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
# Simulated (deterministic) engine
# ---------------------------------------------------------------------------

class SimulatedReasoningEngine(ReasoningEngine):
    """Rule-based reasoning for reproducible evaluation.

    Steps through a fixed check sequence:
      1. Check pairwise drug-drug interactions
      2. Check patient condition contraindications
      3. Check multi-factor hyperedge risks
    """

    def __init__(self, hypergraph: Hypergraph):
        self.hg = hypergraph
        self._query_entities: Set[str] = set()
        self._checked_pairwise = False
        self._checked_conditions = False
        self._checked_hyperedges = False

    def reset(self, entity_ids: Set[str]) -> None:
        self._query_entities = entity_ids
        self._checked_pairwise = False
        self._checked_conditions = False
        self._checked_hyperedges = False

    def think(self, query: str, context: str) -> str:
        if not self._checked_pairwise:
            drug_ids = [
                eid for eid in self._query_entities
                if eid in self.hg.entities and self.hg.entities[eid].type == "drug"
            ]
            return f"I should check pairwise interactions between: {', '.join(drug_ids)}"
        elif not self._checked_conditions:
            return "I should check if patient conditions create additional risk with these drugs"
        elif not self._checked_hyperedges:
            return "I should check for multi-factor polypharmacy risks via hyperedges"
        return "I have enough information to conclude"

    def parse_action(self, thought: str) -> Tuple[str, Set[str]]:
        if "pairwise" in thought:
            self._checked_pairwise = True
            return "check_pairwise", self._query_entities
        elif "conditions" in thought:
            self._checked_conditions = True
            return "check_conditions", self._query_entities
        elif "hyperedge" in thought or "multi-factor" in thought:
            self._checked_hyperedges = True
            return "check_hyperedges", self._query_entities
        return "conclude", self._query_entities

    def synthesize(self, query: str, observations: List[str]) -> str:
        critical = [o for o in observations if "CRITICAL" in o or "SEVERE" in o]
        warnings = [o for o in observations if "WARNING" in o or "MODERATE" in o]

        if critical:
            return f"CONTRAINDICATED: {len(critical)} critical risk(s) found. {' '.join(critical[:2])}"
        elif warnings:
            return f"CAUTION: {len(warnings)} moderate risk(s). Monitor closely. {' '.join(warnings[:2])}"
        return "No significant interactions detected. Safe to prescribe with standard monitoring."

    def should_continue(self, iteration: int, observations: List[str]) -> bool:
        return iteration < 3 and not (
            self._checked_pairwise and self._checked_conditions and self._checked_hyperedges
        )


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
        max_iterations: int = 5,
    ):
        self.hg = hypergraph
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_iterations = max_iterations
        self._query_entities: Set[str] = set()

    def reset(self, entity_ids: Set[str]) -> None:
        self._query_entities = entity_ids

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama generate API (non-streaming)."""
        import httpx

        logger.info("[Ollama/%s] Sending prompt (%d chars)…", self.model, len(prompt))
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=120.0,
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
            timeout=120.0,
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

    def build_think_prompt(self, query: str, context: str) -> str:
        return (
            "You are a clinical pharmacology reasoning agent.\n"
            f"Query: {query}\n"
            f"Context so far:\n{context}\n\n"
            "What should you investigate next? Respond with a single concise thought.\n"
            "Focus on: drug-drug interactions, contraindications, or multi-factor risks."
        )

    def build_synthesize_prompt(self, query: str, observations: List[str]) -> str:
        obs_text = "\n".join(f"- {o}" for o in observations)
        return (
            "You are a clinical pharmacology reasoning agent.\n"
            f"Query: {query}\n"
            f"Observations:\n{obs_text}\n\n"
            "Provide a concise clinical recommendation based on these observations.\n"
            "Include risk level (SAFE / CAUTION / CONTRAINDICATED) and key reasons."
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
        if any(kw in lower for kw in ("pairwise", "interaction", "drug-drug")):
            return "check_pairwise", self._query_entities
        elif any(kw in lower for kw in ("condition", "contraindic", "comorbid")):
            return "check_conditions", self._query_entities
        elif any(kw in lower for kw in ("hyperedge", "multi-factor", "polypharmacy", "combined")):
            return "check_hyperedges", self._query_entities
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
    """Factory function for reasoning engines."""
    if engine_type == "simulated":
        return SimulatedReasoningEngine(hypergraph)
    elif engine_type == "ollama":
        import os
        if "model" not in kwargs:
            kwargs["model"] = os.environ.get("VHP_MODEL", "phi4")
        return OllamaReasoningEngine(hypergraph, **kwargs)
    raise ValueError(f"Unknown engine type: {engine_type}")
