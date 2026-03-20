"""DrugBank 6.0 XML loader.

Parses the DrugBank XML file and constructs a VHP Hypergraph with:
  - Drug entities from <drug> elements
  - Pairwise DDI edges from <drug-interactions>
  - Hyperedges built from CYP450 metabolic conflicts, category stacking,
    and severity escalation patterns

Requires: DrugBank XML (CC BY-NC 4.0 academic license)
Download: https://go.drugbank.com/releases/latest
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

from vhp.hypergraph import Entity, HyperEdge, Hypergraph, PairwiseEdge

logger = logging.getLogger(__name__)

# DrugBank XML namespace
NS = "{http://www.drugbank.ca}"


def _iter_drugs(xml_path: str | Path) -> Iterator[ET.Element]:
    """Stream-parse DrugBank XML to avoid loading 700MB into memory."""
    for event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == f"{NS}drug" and elem.get("type") in ("biotech", "small molecule"):
            yield elem
            elem.clear()


def load_drugbank(
    xml_path: str | Path,
    max_drugs: int | None = None,
) -> Hypergraph:
    """Load DrugBank XML into a VHP Hypergraph.

    Args:
        xml_path: Path to the DrugBank XML file.
        max_drugs: Optional limit for testing (e.g., 500 for quick loads).

    Returns:
        Populated Hypergraph with drugs, interactions, and hyperedges.
    """
    hg = Hypergraph("drugbank")
    drug_categories: Dict[str, Set[str]] = defaultdict(set)  # drug_id -> {categories}
    drug_enzymes: Dict[str, Set[str]] = defaultdict(set)     # drug_id -> {enzyme_ids}
    interactions: list[Tuple[str, str, str]] = []

    count = 0
    for drug_elem in _iter_drugs(xml_path):
        # --- Extract drug info ---
        db_id_elem = drug_elem.find(f"{NS}drugbank-id[@primary='true']")
        name_elem = drug_elem.find(f"{NS}name")
        if db_id_elem is None or name_elem is None:
            continue

        drug_id = db_id_elem.text or ""
        drug_name = name_elem.text or ""

        # Categories
        for cat_elem in drug_elem.findall(f".//{NS}category/{NS}category"):
            if cat_elem.text:
                drug_categories[drug_id].add(cat_elem.text)  # type: ignore[arg-type]

        # Determine primary class from categories
        cats = drug_categories.get(drug_id, set())
        drug_class = next(iter(sorted(cats)), "unknown")

        hg.add_entity(Entity(
            drug_id, "drug", drug_name,
            tuple(sorted([("class", drug_class)] + [("category", c) for c in sorted(cats)[:5]])),
        ))

        # Enzymes (for CYP450 hyperedge construction)
        for enzyme_elem in drug_elem.findall(f".//{NS}enzymes/{NS}enzyme"):
            enz_id_elem = enzyme_elem.find(f"{NS}id")
            if enz_id_elem is not None and enz_id_elem.text:
                drug_enzymes[drug_id].add(enz_id_elem.text)  # type: ignore[arg-type]

        # Drug-drug interactions
        for ddi_elem in drug_elem.findall(f".//{NS}drug-interactions/{NS}drug-interaction"):
            target_id_elem = ddi_elem.find(f"{NS}drugbank-id")
            desc_elem = ddi_elem.find(f"{NS}description")
            if target_id_elem is not None and target_id_elem.text:
                desc = desc_elem.text if desc_elem is not None else ""
                interactions.append((drug_id, target_id_elem.text, desc or ""))

        count += 1
        if max_drugs and count >= max_drugs:
            break

    logger.info("Loaded %d drugs from DrugBank", count)

    # --- Build pairwise DDI edges ---
    seen_pairs: set[Tuple[str, str]] = set()
    for src, tgt, desc in interactions:
        if src not in hg.entities or tgt not in hg.entities:
            continue
        pair: Tuple[str, str] = (min(src, tgt), max(src, tgt))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        severity = _infer_severity(desc)
        hg.add_pairwise_edge(PairwiseEdge(
            src, "interacts_with", tgt,
            (("severity", severity), ("description", desc[:200])),
        ))

    logger.info("Built %d pairwise DDI edges", len(hg.pairwise_edges))

    # --- Build hyperedges ---
    _build_cyp_hyperedges(hg, drug_enzymes)
    _build_category_hyperedges(hg, drug_categories)

    logger.info("Built %d hyperedges", len(hg.hyperedges))
    return hg


def _infer_severity(description: str) -> str:
    """Infer DDI severity from DrugBank description text."""
    lower = description.lower()
    if any(w in lower for w in ("contraindicated", "fatal", "serious", "severe")):
        return "severe"
    elif any(w in lower for w in ("major", "significant", "increased risk")):
        return "high"
    elif any(w in lower for w in ("moderate", "monitor", "caution")):
        return "moderate"
    return "low"


def _build_cyp_hyperedges(
    hg: Hypergraph, drug_enzymes: Dict[str, Set[str]]
) -> None:
    """Build hyperedges from shared CYP450 enzyme pathways."""
    enzyme_drugs: Dict[str, Set[str]] = defaultdict(set)
    for drug_id, enzymes in drug_enzymes.items():
        for enz in enzymes:
            enzyme_drugs[enz].add(drug_id)

    he_count = 0
    for enz_id, drugs in enzyme_drugs.items():
        drugs_in_hg = [d for d in drugs if d in hg.entities]
        if len(drugs_in_hg) >= 3:
            # Take groups of 3 that share this enzyme
            sorted_drugs = sorted(drugs_in_hg)[:5]  # cap to avoid combinatorial explosion
            hg.add_hyperedge(HyperEdge(
                f"HE_CYP_{he_count:04d}",
                frozenset(sorted_drugs[:3]),
                "metabolic_conflict",
                severity=0.7,
                evidence=f"Shared enzyme pathway: {enz_id}",
            ))
            he_count += 1


def _build_category_hyperedges(
    hg: Hypergraph, drug_categories: Dict[str, Set[str]]
) -> None:
    """Build polypharmacy hyperedges from therapeutic category stacking."""
    cat_drugs: Dict[str, Set[str]] = defaultdict(set)
    for drug_id, cats in drug_categories.items():
        if drug_id in hg.entities:
            for cat in cats:
                cat_drugs[cat].add(drug_id)

    he_count = 0
    for cat, drugs in cat_drugs.items():
        if len(drugs) >= 3:
            sorted_drugs = sorted(drugs)[:4]
            hg.add_hyperedge(HyperEdge(
                f"HE_CAT_{he_count:04d}",
                frozenset(sorted_drugs[:3]),
                "polypharmacy_risk",
                severity=0.6,
                evidence=f"Category stacking: {cat}",
                properties={"category": cat},
            ))
            he_count += 1
