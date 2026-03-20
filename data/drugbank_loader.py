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

    # Collect biological entities (targets, enzymes, transporters, carriers)
    # to create as graph nodes with relationship edges
    bio_entities: Dict[str, Tuple[str, str, str]] = {}  # id -> (name, type, action)
    drug_targets: list[Tuple[str, str, str]] = []    # (drug_id, bio_id, action)
    drug_transporters: list[Tuple[str, str]] = []     # (drug_id, bio_id)
    drug_carriers: list[Tuple[str, str]] = []          # (drug_id, bio_id)
    pathway_entities: Dict[str, str] = {}              # pathway_id -> name
    drug_pathways: list[Tuple[str, str]] = []          # (drug_id, pathway_id)

    # Text fields to extract (tag name -> property key), truncated to 200 chars
    _TEXT_FIELDS = {
        "indication": "indication",
        "mechanism-of-action": "mechanism_of_action",
        "pharmacodynamics": "pharmacodynamics",
        "toxicity": "toxicity",
        "metabolism": "metabolism",
        "half-life": "half_life",
        "protein-binding": "protein_binding",
    }

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

        # Classification hierarchy (kingdom → superclass → class → subclass → direct-parent)
        classification_parts: list[str] = []
        cls_elem = drug_elem.find(f"{NS}classification")
        if cls_elem is not None:
            for tag in ("kingdom", "superclass", "class", "subclass", "direct-parent"):
                val = cls_elem.findtext(f"{NS}{tag}", "")
                if val:
                    classification_parts.append(val)
        classification = " > ".join(classification_parts) if classification_parts else ""

        # Groups (approved / withdrawn / experimental / investigational)
        groups: list[str] = []
        for g in drug_elem.findall(f".//{NS}groups/{NS}group"):
            if g.text:
                groups.append(g.text)

        # Targets (protein targets) — create as graph entities
        targets: list[str] = []
        for tgt in drug_elem.findall(f".//{NS}targets/{NS}target"):
            tgt_id = tgt.findtext(f"{NS}id", "")
            tgt_name = tgt.findtext(f"{NS}name", "")
            if tgt_id and tgt_name:
                targets.append(tgt_name)
                actions = [a.text for a in tgt.findall(f".//{NS}actions/{NS}action") if a.text]
                action = actions[0] if actions else "unknown"
                bio_entities[tgt_id] = (tgt_name, "target", action)
                drug_targets.append((drug_id, tgt_id, action))

        # Carriers & Transporters — create as graph entities
        carriers: list[str] = []
        for c in drug_elem.findall(f".//{NS}carriers/{NS}carrier"):
            c_id = c.findtext(f"{NS}id", "")
            c_name = c.findtext(f"{NS}name", "")
            if c_id and c_name:
                carriers.append(c_name)
                bio_entities[c_id] = (c_name, "carrier", "")
                drug_carriers.append((drug_id, c_id))
        transporters: list[str] = []
        for tr in drug_elem.findall(f".//{NS}transporters/{NS}transporter"):
            tr_id = tr.findtext(f"{NS}id", "")
            tr_name = tr.findtext(f"{NS}name", "")
            if tr_id and tr_name:
                transporters.append(tr_name)
                bio_entities[tr_id] = (tr_name, "transporter", "")
                drug_transporters.append((drug_id, tr_id))

        # Pathways — create as graph entities
        pathways: list[str] = []
        for pw in drug_elem.findall(f".//{NS}pathways/{NS}pathway"):
            pw_smpdb = pw.findtext(f"{NS}smpdb-id", "")
            pw_name = pw.findtext(f"{NS}name", "")
            if pw_name:
                pathways.append(pw_name)
                if pw_smpdb:
                    pw_id = pw_smpdb
                else:
                    pw_id = f"PW_{pw_name.replace(' ', '_')[:40]}"
                pathway_entities[pw_id] = pw_name
                drug_pathways.append((drug_id, pw_id))

        # Food interactions
        food_interactions: list[str] = []
        for fi in drug_elem.findall(f".//{NS}food-interactions/{NS}food-interaction"):
            if fi.text:
                food_interactions.append(fi.text.strip()[:150])

        # Dosages
        dosages: list[str] = []
        for dos in drug_elem.findall(f".//{NS}dosages/{NS}dosage"):
            form = dos.findtext(f"{NS}form", "")
            route = dos.findtext(f"{NS}route", "")
            strength = dos.findtext(f"{NS}strength", "")
            parts = [p for p in (form, route, strength) if p]
            if parts:
                dosages.append(", ".join(parts))

        # Mixtures (brand-name combinations)
        mixtures: list[str] = []
        for mix in drug_elem.findall(f".//{NS}mixtures/{NS}mixture"):
            mix_name = mix.findtext(f"{NS}name", "")
            mix_ingr = mix.findtext(f"{NS}ingredients", "")
            if mix_name:
                entry = mix_name
                if mix_ingr:
                    entry += f" ({mix_ingr[:100]})"
                mixtures.append(entry)

        # Build properties tuple
        props: list[Tuple[str, str]] = [("class", drug_class)]
        props.extend(("category", c) for c in sorted(cats)[:5])
        if classification:
            props.append(("classification", classification))
        if groups:
            props.append(("groups", ", ".join(groups)))

        # Text fields (truncated)
        for xml_tag, prop_key in _TEXT_FIELDS.items():
            el = drug_elem.find(f"{NS}{xml_tag}")
            if el is not None and el.text and el.text.strip():
                props.append((prop_key, el.text.strip()[:200]))

        if targets:
            props.append(("targets", ", ".join(targets[:10])))
        if carriers:
            props.append(("carriers", ", ".join(carriers[:5])))
        if transporters:
            props.append(("transporters", ", ".join(transporters[:5])))
        if pathways:
            props.append(("pathways", ", ".join(pathways[:5])))
        if food_interactions:
            props.append(("food_interactions", " | ".join(food_interactions[:3])))
        if dosages:
            props.append(("dosages", " | ".join(dosages[:5])))
        if mixtures:
            props.append(("mixtures", " | ".join(mixtures[:5])))

        hg.add_entity(Entity(drug_id, "drug", drug_name, tuple(sorted(props))))

        # Enzymes (for CYP450 hyperedge construction + graph entities)
        for enzyme_elem in drug_elem.findall(f".//{NS}enzymes/{NS}enzyme"):
            enz_id_elem = enzyme_elem.find(f"{NS}id")
            enz_name_elem = enzyme_elem.find(f"{NS}name")
            if enz_id_elem is not None and enz_id_elem.text:
                enz_id = enz_id_elem.text
                enz_name = enz_name_elem.text if enz_name_elem is not None and enz_name_elem.text else enz_id
                drug_enzymes[drug_id].add(enz_id)  # type: ignore[arg-type]
                actions = [a.text for a in enzyme_elem.findall(f".//{NS}actions/{NS}action") if a.text]
                action = actions[0] if actions else "substrate"
                bio_entities[enz_id] = (enz_name, "enzyme", action)

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

    # --- Create biological entities (targets, enzymes, transporters, carriers, pathways) ---
    for bio_id, (bio_name, bio_type, action) in bio_entities.items():
        if bio_id not in hg.entities:
            bio_props: list[Tuple[str, str]] = []
            if action:
                bio_props.append(("action", action))
            hg.add_entity(Entity(bio_id, bio_type, bio_name, tuple(sorted(bio_props))))
    for pw_id, pw_name in pathway_entities.items():
        if pw_id not in hg.entities:
            hg.add_entity(Entity(pw_id, "pathway", pw_name, ()))

    bio_count = len(bio_entities) + len(pathway_entities)
    logger.info("Created %d biological entities (targets, enzymes, transporters, carriers, pathways)", bio_count)

    # --- Build relationship edges (drug → target/enzyme/transporter/carrier/pathway) ---
    rel_count = 0
    for drug_id, tgt_id, action in drug_targets:
        if drug_id in hg.entities and tgt_id in hg.entities:
            hg.add_pairwise_edge(PairwiseEdge(
                drug_id, "targets", tgt_id,
                (("action", action),),
            ))
            rel_count += 1
    for drug_id, enz_id in ((d, e) for d, enzs in drug_enzymes.items() for e in enzs):
        if drug_id in hg.entities and enz_id in hg.entities:
            hg.add_pairwise_edge(PairwiseEdge(
                drug_id, "metabolized_by", enz_id,
                (),
            ))
            rel_count += 1
    for drug_id, tr_id in drug_transporters:
        if drug_id in hg.entities and tr_id in hg.entities:
            hg.add_pairwise_edge(PairwiseEdge(
                drug_id, "transported_by", tr_id,
                (),
            ))
            rel_count += 1
    for drug_id, ca_id in drug_carriers:
        if drug_id in hg.entities and ca_id in hg.entities:
            hg.add_pairwise_edge(PairwiseEdge(
                drug_id, "carried_by", ca_id,
                (),
            ))
            rel_count += 1
    for drug_id, pw_id in drug_pathways:
        if drug_id in hg.entities and pw_id in hg.entities:
            hg.add_pairwise_edge(PairwiseEdge(
                drug_id, "participates_in", pw_id,
                (),
            ))
            rel_count += 1
    logger.info("Built %d biological relationship edges", rel_count)

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
