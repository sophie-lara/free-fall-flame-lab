"""Portable float-vector encoding and cosine similarity."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence


def encode_vector(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def decode_vector(payload: bytes, dimensions: int) -> tuple[float, ...]:
    expected = dimensions * 4
    if len(payload) != expected:
        raise ValueError(f"Expected {expected} vector bytes, received {len(payload)}")
    return struct.unpack(f"<{dimensions}f", payload)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Vectors must have the same non-zero dimensions")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("Zero vectors do not have cosine similarity")
    return dot / (left_norm * right_norm)
