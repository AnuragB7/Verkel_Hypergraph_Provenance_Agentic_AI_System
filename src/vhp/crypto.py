"""Cryptographic primitives for VHP.

Uses SHA-256 for hashing and simulated polynomial commitments.
In production, replace commit/combine_commitments with Pedersen
commitments over the Bandersnatch curve (py_ecc).
"""

import hashlib


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def commit(data: bytes) -> bytes:
    """Simulated polynomial commitment.

    In production, this would be a Pedersen commitment:
        C = g^{p(s)} where p is a polynomial encoding `data`.
    For the prototype, we simulate with a domain-separated SHA-256.
    """
    return sha256(b"commit:" + data)


def combine_commitments(commitments: list[bytes]) -> bytes:
    """Simulated vector commitment combination.

    In production, this aggregates Pedersen commitments via
    multi-scalar multiplication.  For the prototype, we sort
    inputs for determinism and hash them together.
    """
    combined = b"".join(sorted(commitments))
    return sha256(b"combine:" + combined)
