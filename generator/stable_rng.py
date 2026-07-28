from __future__ import annotations

import hashlib
import random
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


def seed_for(master_seed: int, *parts: object) -> int:
    raw = "|".join([str(master_seed), *(str(p) for p in parts)]).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big")


def rng_for(master_seed: int, *parts: object) -> random.Random:
    return random.Random(seed_for(master_seed, *parts))


def stable_float(master_seed: int, *parts: object) -> float:
    return rng_for(master_seed, *parts).random()


def stable_choice(values: Sequence[T], master_seed: int, *parts: object) -> T:
    if not values:
        raise ValueError("Cannot choose from an empty sequence")
    return values[rng_for(master_seed, *parts).randrange(len(values))]


def stable_sample(values: Sequence[T], k: int, master_seed: int, *parts: object) -> list[T]:
    if k < 0 or k > len(values):
        raise ValueError(f"Invalid sample size {k} for population {len(values)}")
    return rng_for(master_seed, *parts).sample(list(values), k)
