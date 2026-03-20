"""Tests for Layer 1: Hypergraph knowledge representation."""

from vhp.hypergraph import Entity, HyperEdge, Hypergraph, PairwiseEdge
from vhp.serialization import serialize_hyperedge, serialize_partition


def test_entities_loaded(sample_hypergraph):
    assert len(sample_hypergraph.entities) > 0


def test_pairwise_edges_loaded(sample_hypergraph):
    assert len(sample_hypergraph.pairwise_edges) > 0


def test_hyperedges_loaded(sample_hypergraph):
    assert len(sample_hypergraph.hyperedges) > 0


def test_entity_type_is_drug(sample_hypergraph):
    for eid, e in sample_hypergraph.entities.items():
        assert e.type == "drug"
        break  # at minimum the first entity is a drug


def test_get_entity_missing(sample_hypergraph):
    assert sample_hypergraph.get_entity("NONEXISTENT") is None


def test_get_neighbors(sample_hypergraph):
    """At least one drug should have interacts_with neighbours."""
    found = False
    for eid in sample_hypergraph.entities:
        neighbors = sample_hypergraph.get_neighbors(eid, "interacts_with")
        if neighbors:
            found = True
            break
    assert found, "No interacting drugs found"


def test_get_hyperedges_for_entities(sample_hypergraph):
    """Pick two drugs from a hyperedge and verify lookup returns it."""
    if not sample_hypergraph.hyperedges:
        return
    he = sample_hypergraph.hyperedges[0]
    pair = set(list(he.entity_ids)[:2])
    found = sample_hypergraph.get_hyperedges_for_entities(pair)
    assert len(found) >= 1


def test_partition_by_type(sample_hypergraph):
    parts = sample_hypergraph.partition_by_type()
    assert len(parts) > 0
    assert any(k.startswith("pairwise_") for k in parts)


def test_canonical_serialization_determinism():
    he = HyperEdge("X", frozenset({"b", "a", "c"}), "test", 0.5, properties={"z": 1, "a": 2})
    b1 = serialize_hyperedge(he)
    b2 = serialize_hyperedge(he)
    assert b1 == b2


def test_partition_serialization_determinism(sample_hypergraph):
    parts = sample_hypergraph.partition_by_type()
    for name, p in parts.items():
        b1 = serialize_partition(p)
        b2 = serialize_partition(p)
        assert b1 == b2, f"Non-deterministic serialization for {name}"


def test_extract_subgraph(sample_hypergraph):
    eid = next(iter(sample_hypergraph.entities))
    sub = sample_hypergraph.extract_subgraph({eid}, max_hops=1)
    assert eid in sub.entities


def test_stats(sample_hypergraph):
    s = sample_hypergraph.stats
    assert s["entities"] > 0
    assert s["pairwise_edges"] >= 0
    assert s["hyperedges"] >= 0


def test_to_dict(sample_hypergraph):
    d = sample_hypergraph.to_dict()
    assert d["name"] == "drugbank"
    assert len(d["entities"]) > 0
