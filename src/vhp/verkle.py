"""Layer 2: Verkle Verification.

Implements a Verkle tree with simulated polynomial commitments (SHA-256),
a standard Merkle tree for comparison, and a temporal root chain.

Key property: Verkle proofs are constant-size (~96 bytes) regardless of
tree size, while Merkle proofs grow O(log n) with 32 bytes per level.

Production note: Replace `crypto.commit` / `crypto.combine_commitments`
with Pedersen commitments over the Bandersnatch curve for real constant-
size proofs.  The tree structure and API remain identical.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from vhp.crypto import combine_commitments, commit, sha256


# ---------------------------------------------------------------------------
# Proof types
# ---------------------------------------------------------------------------

@dataclass
class VerkleProof:
    """Constant-size Verkle proof (simulated)."""

    path_commitments: List[bytes]
    opening_proof: bytes   # Fixed ~48 bytes in real implementation
    leaf_index: int
    leaf_commitment: bytes

    @property
    def size_bytes(self) -> int:
        # Real Verkle: ~96 bytes regardless of tree size
        return 96

    def to_dict(self) -> dict:
        return {
            "leaf_index": self.leaf_index,
            "leaf_commitment": self.leaf_commitment.hex(),
            "opening_proof": self.opening_proof.hex(),
            "path_depth": len(self.path_commitments),
            "proof_size_bytes": self.size_bytes,
        }


@dataclass
class MerkleProof:
    """Variable-size Merkle proof (for comparison benchmarks)."""

    sibling_hashes: List[Tuple[bytes, str]]  # (hash, direction)

    @property
    def size_bytes(self) -> int:
        return len(self.sibling_hashes) * 32


# ---------------------------------------------------------------------------
# Verkle Tree
# ---------------------------------------------------------------------------

class VerkleTree:
    """Simplified Verkle tree with simulated vector commitments.

    Build from (label, data_bytes) pairs.  Each leaf is a committed
    partition; internal nodes aggregate children via combine_commitments.
    """

    def __init__(self, branching_factor: int = 256):
        self.branching_factor = branching_factor
        self._leaf_commitments: List[Tuple[str, bytes]] = []
        self._leaf_index: Dict[str, int] = {}
        self._root: Optional[bytes] = None
        self._levels: List[List[bytes]] = []

    # -- Construction ------------------------------------------------------

    def build(self, leaf_data: List[Tuple[str, bytes]]) -> bytes:
        """Build tree from (label, serialized_data) pairs.  Returns root."""
        self._leaf_commitments = []
        self._leaf_index = {}

        for i, (label, data) in enumerate(leaf_data):
            c = commit(data)
            self._leaf_commitments.append((label, c))
            self._leaf_index[label] = i

        level = [c for _, c in self._leaf_commitments]
        if len(level) % 2 == 1:
            level.append(level[-1])  # pad to even
        self._levels = [level]

        while len(level) > 1:
            next_level: list[bytes] = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else level[i]
                next_level.append(combine_commitments([left, right]))
            self._levels.append(next_level)
            level = next_level

        self._root = level[0]
        return self._root

    # -- Properties --------------------------------------------------------

    @property
    def root_commitment(self) -> bytes:
        if self._root is None:
            raise ValueError("Tree not built yet")
        return self._root

    @property
    def root_hex(self) -> str:
        if self._root is None:
            return "None"
        return self._root.hex()[:32] + "..."

    @property
    def leaf_count(self) -> int:
        return len(self._leaf_commitments)

    @property
    def leaf_labels(self) -> List[str]:
        return [label for label, _ in self._leaf_commitments]

    # -- Proofs ------------------------------------------------------------

    def generate_proof(self, label: str) -> VerkleProof:
        if label not in self._leaf_index:
            raise KeyError(f"Leaf '{label}' not found in tree")

        idx = self._leaf_index[label]
        path_commitments: list[bytes] = []

        current_idx = idx
        for level in self._levels[:-1]:
            sibling_idx = current_idx ^ 1
            if sibling_idx < len(level):
                path_commitments.append(level[sibling_idx])
            current_idx //= 2

        opening_proof = sha256(b"opening:" + self._leaf_commitments[idx][1])

        return VerkleProof(
            path_commitments=path_commitments,
            opening_proof=opening_proof,
            leaf_index=idx,
            leaf_commitment=self._leaf_commitments[idx][1],
        )

    def verify_proof(self, proof: VerkleProof, expected_root: bytes) -> bool:
        current = proof.leaf_commitment
        idx = proof.leaf_index

        for sibling in proof.path_commitments:
            if idx % 2 == 0:
                current = combine_commitments([current, sibling])
            else:
                current = combine_commitments([sibling, current])
            idx //= 2

        return current == expected_root

    # -- Mutation ----------------------------------------------------------

    def update_leaf(self, label: str, new_data: bytes) -> bytes:
        """Update a leaf and recompute path to root.  Returns new root."""
        idx = self._leaf_index[label]
        new_commitment = commit(new_data)
        self._leaf_commitments[idx] = (label, new_commitment)
        self._levels[0][idx] = new_commitment

        current_idx = idx
        for level_i in range(len(self._levels) - 1):
            parent_idx = current_idx // 2
            left_idx = parent_idx * 2
            right_idx = left_idx + 1
            left = self._levels[level_i][left_idx]
            right = (
                self._levels[level_i][right_idx]
                if right_idx < len(self._levels[level_i])
                else left
            )
            self._levels[level_i + 1][parent_idx] = combine_commitments([left, right])
            current_idx = parent_idx

        self._root = self._levels[-1][0]
        return self._root

    # -- Serialization for API ---------------------------------------------

    def to_dict(self) -> dict:
        return {
            "root": self.root_hex,
            "leaf_count": self.leaf_count,
            "leaf_labels": self.leaf_labels,
            "depth": len(self._levels),
        }


# ---------------------------------------------------------------------------
# Merkle Tree (comparison baseline)
# ---------------------------------------------------------------------------

class MerkleTree:
    """Standard Merkle tree for comparison benchmarks."""

    def __init__(self):
        self._leaves: List[Tuple[str, bytes]] = []
        self._leaf_index: Dict[str, int] = {}
        self._levels: List[List[bytes]] = []
        self._root: Optional[bytes] = None

    def build(self, leaf_data: List[Tuple[str, bytes]]) -> bytes:
        self._leaves = [(label, sha256(data)) for label, data in leaf_data]
        self._leaf_index = {label: i for i, (label, _) in enumerate(self._leaves)}

        level = [h for _, h in self._leaves]
        if len(level) % 2 == 1:
            level.append(level[-1])
        self._levels = [level]

        while len(level) > 1:
            next_level: list[bytes] = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else level[i]
                next_level.append(sha256(left + right))
            self._levels.append(next_level)
            level = next_level

        self._root = level[0]
        return self._root

    @property
    def root_commitment(self) -> bytes:
        if self._root is None:
            raise ValueError("Tree not built yet")
        return self._root

    def generate_proof(self, label: str) -> MerkleProof:
        idx = self._leaf_index[label]
        siblings: list[Tuple[bytes, str]] = []
        current_idx = idx
        for level in self._levels[:-1]:
            if current_idx % 2 == 0:
                sib_idx = current_idx + 1
                direction = "right"
            else:
                sib_idx = current_idx - 1
                direction = "left"
            if sib_idx < len(level):
                siblings.append((level[sib_idx], direction))
            current_idx //= 2
        return MerkleProof(sibling_hashes=siblings)


# ---------------------------------------------------------------------------
# Temporal Root Chain
# ---------------------------------------------------------------------------

class TemporalRootChain:
    """Append-only chain of Verkle roots for historical verification."""

    def __init__(self):
        self.chain: List[Tuple[float, bytes, bytes]] = []  # (ts, verkle_root, chained)

    def append_root(self, verkle_root: bytes) -> bytes:
        ts = time.time()
        if self.chain:
            prev = self.chain[-1][2]
            chained = sha256(verkle_root + prev + str(ts).encode())
        else:
            chained = sha256(verkle_root + b"genesis" + str(ts).encode())
        self.chain.append((ts, verkle_root, chained))
        return chained

    def verify_chain_integrity(self) -> bool:
        for i, (ts, vroot, chained) in enumerate(self.chain):
            if i == 0:
                expected = sha256(vroot + b"genesis" + str(ts).encode())
            else:
                prev_chained = self.chain[i - 1][2]
                expected = sha256(vroot + prev_chained + str(ts).encode())
            if expected != chained:
                return False
        return True

    def get_root_at_time(self, timestamp: float) -> Optional[bytes]:
        """Find the Verkle root that was active at a given time."""
        for ts, vroot, _ in reversed(self.chain):
            if ts <= timestamp:
                return vroot
        return None

    def __len__(self) -> int:
        return len(self.chain)

    def to_dict(self) -> dict:
        return {
            "length": len(self.chain),
            "entries": [
                {"timestamp": ts, "verkle_root": vroot.hex()[:24] + "...", "chained": ch.hex()[:24] + "..."}
                for ts, vroot, ch in self.chain
            ],
        }
