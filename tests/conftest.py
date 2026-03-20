"""Shared fixtures for VHP tests."""

import sys
from pathlib import Path

import pytest

# Ensure vhp and data modules are importable
backend_src = Path(__file__).resolve().parent.parent / "src"
backend_data = Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(backend_src))
sys.path.insert(0, str(backend_data))

from vhp.hypergraph import Entity, HyperEdge, Hypergraph, PairwiseEdge

_DRUGBANK_XML = backend_data / "drugbank.xml"


@pytest.fixture(scope="session")
def sample_hypergraph() -> Hypergraph:
    """Load a small slice of real DrugBank data (50 drugs) for tests."""
    if not _DRUGBANK_XML.exists():
        pytest.skip("DrugBank XML not available — skipping real-data tests")
    from drugbank_loader import load_drugbank
    return load_drugbank(str(_DRUGBANK_XML), max_drugs=50)
