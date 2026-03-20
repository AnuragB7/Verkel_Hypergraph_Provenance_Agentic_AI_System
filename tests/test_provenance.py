"""Tests for Layer 3: Provenance DAG."""

from vhp.provenance import NodeType, ProvenanceDAG, ProvenanceNode


def test_add_nodes():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Check interactions")
    a1 = dag.add_action("check_pairwise", depends_on=[t1])
    o1 = dag.add_observation("Found 2 interactions", depends_on=[a1])
    c1 = dag.add_conclusion("Safe with monitoring", depends_on=[o1])

    assert dag.node_count == 4
    assert dag.nodes[t1].node_type == NodeType.THOUGHT
    assert dag.nodes[c1].node_type == NodeType.CONCLUSION


def test_dependency_tracking():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Step 1")
    a1 = dag.add_action("Do something", depends_on=[t1])
    assert dag.nodes[a1].depends_on == [t1]
    assert (t1, a1) in dag.edges


def test_hash_computation():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Content A")
    t2 = dag.add_thought("Content B")
    assert dag.nodes[t1].node_hash != dag.nodes[t2].node_hash


def test_hash_changes_with_content():
    dag1 = ProvenanceDAG()
    dag2 = ProvenanceDAG()
    id1 = dag1.add_thought("Same content")
    id2 = dag2.add_thought("Different content")
    assert dag1.nodes[id1].node_hash != dag2.nodes[id2].node_hash


def test_verify_all_hashes():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Think")
    a1 = dag.add_action("Act", depends_on=[t1])
    o1 = dag.add_observation("Observe", depends_on=[a1])
    c1 = dag.add_conclusion("Conclude", depends_on=[o1])

    results = dag.verify_all_hashes()
    assert all(results.values())


def test_tampered_node_detected():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Original")
    a1 = dag.add_action("Act", depends_on=[t1])

    # Tamper with content
    dag.nodes[t1].content = "TAMPERED"

    results = dag.verify_all_hashes()
    assert not results[t1]


def test_acyclicity_valid():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("A")
    t2 = dag.add_thought("B", depends_on=[t1])
    dag.add_thought("C", depends_on=[t2])
    assert dag.verify_acyclicity()


def test_acyclicity_cycle_detected():
    dag = ProvenanceDAG()
    n1 = dag.add_thought("A")
    n2 = dag.add_thought("B", depends_on=[n1])
    # Inject a cycle
    dag.edges.append((n2, n1))
    assert not dag.verify_acyclicity()


def test_depth():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("L1")
    t2 = dag.add_thought("L2", depends_on=[t1])
    t3 = dag.add_thought("L3", depends_on=[t2])
    assert dag.depth == 3


def test_reasoning_chain():
    dag = ProvenanceDAG()
    t1 = dag.add_thought("Start")
    a1 = dag.add_action("Mid", depends_on=[t1])
    c1 = dag.add_conclusion("End", depends_on=[a1])

    chain = dag.get_reasoning_chain(c1)
    assert len(chain) == 3
    assert chain[0].id == t1
    assert chain[-1].id == c1


def test_to_dict():
    dag = ProvenanceDAG()
    dag.add_thought("Test")
    d = dag.to_dict()
    assert d["node_count"] == 1
    assert len(d["nodes"]) == 1
    assert d["nodes"][0]["type"] == "thought"
