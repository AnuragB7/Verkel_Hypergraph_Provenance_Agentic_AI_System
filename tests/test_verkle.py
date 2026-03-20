"""Tests for Layer 2: Verkle verification."""

import hashlib

import pytest

from vhp.serialization import serialize_partition
from vhp.verkle import MerkleTree, TemporalRootChain, VerkleTree


@pytest.fixture
def leaf_data(sample_hypergraph):
    parts = sample_hypergraph.partition_by_type()
    return [(name, serialize_partition(p)) for name, p in sorted(parts.items())]


def test_build_tree(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)
    assert root is not None
    assert len(root) == 32  # SHA-256


def test_root_commitment(leaf_data):
    vt = VerkleTree()
    vt.build(leaf_data)
    assert vt.root_hex != "None"


def test_proof_constant_size(leaf_data):
    vt = VerkleTree()
    vt.build(leaf_data)
    for label, _ in leaf_data:
        proof = vt.generate_proof(label)
        assert proof.size_bytes == 96


def test_verify_valid_proof(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)
    for label, _ in leaf_data:
        proof = vt.generate_proof(label)
        assert vt.verify_proof(proof, root) is True


def test_verify_fails_with_wrong_root(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)
    proof = vt.generate_proof(leaf_data[0][0])
    fake_root = b"\x00" * 32
    assert vt.verify_proof(proof, fake_root) is False


def test_update_leaf_changes_root(leaf_data):
    vt = VerkleTree()
    old_root = vt.build(leaf_data)
    new_root = vt.update_leaf(leaf_data[0][0], b"MODIFIED")
    assert old_root != new_root


def test_old_proof_fails_after_update(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)
    proof = vt.generate_proof(leaf_data[0][0])
    assert vt.verify_proof(proof, root)
    vt.update_leaf(leaf_data[0][0], b"TAMPERED")
    assert not vt.verify_proof(proof, vt.root_commitment)


def test_proof_not_found():
    vt = VerkleTree()
    vt.build([("a", b"data")])
    with pytest.raises(KeyError):
        vt.generate_proof("nonexistent")


def test_proof_size_vs_merkle():
    """Verkle proofs should be smaller than Merkle proofs at non-trivial scales.

    At very small tree sizes (n=4), Merkle proofs (64 bytes) are smaller
    than Verkle's constant 96 bytes.  The advantage kicks in once Merkle
    proofs exceed 96 bytes (n > 8, i.e., depth > 3).
    """
    for n in [16, 32, 64, 128, 256]:
        leaf_data = [(f"leaf_{i}", hashlib.sha256(f"d{i}".encode()).digest()) for i in range(n)]

        vt = VerkleTree()
        vt.build(leaf_data)
        vp = vt.generate_proof("leaf_0")

        mt = MerkleTree()
        mt.build(leaf_data)
        mp = mt.generate_proof("leaf_0")

        assert vp.size_bytes <= mp.size_bytes, f"Verkle > Merkle at n={n}"


def test_temporal_root_chain(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)

    rc = TemporalRootChain()
    rc.append_root(root)
    assert len(rc) == 1

    # Update and append
    new_root = vt.update_leaf(leaf_data[0][0], b"V2")
    rc.append_root(new_root)
    assert len(rc) == 2
    assert rc.verify_chain_integrity()


def test_temporal_root_chain_tamper_detection(leaf_data):
    vt = VerkleTree()
    root = vt.build(leaf_data)

    rc = TemporalRootChain()
    rc.append_root(root)
    rc.append_root(root)
    assert rc.verify_chain_integrity()

    # Tamper with chain entry
    rc.chain[0] = (rc.chain[0][0], rc.chain[0][1], b"\xff" * 32)
    assert not rc.verify_chain_integrity()
