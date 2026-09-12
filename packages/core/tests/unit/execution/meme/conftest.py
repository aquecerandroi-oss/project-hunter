"""Test keys are generated in memory from a seeded RNG and discarded. Never a real key."""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hunter_core.execution.meme.base58 import b58encode


@dataclass(frozen=True)
class TestKey:
    __test__ = False
    seed: bytes
    pubkey_raw: bytes

    @property
    def keypair_bytes(self) -> bytes:
        return self.seed + self.pubkey_raw

    @property
    def base58(self) -> str:
        return b58encode(self.keypair_bytes)

    @property
    def json_array(self) -> str:
        return "[" + ",".join(str(b) for b in self.keypair_bytes) + "]"

    @property
    def pubkey(self) -> str:
        return b58encode(self.pubkey_raw)


def make_test_key(seed_value: int) -> TestKey:
    seed = random.Random(seed_value).randbytes(32)
    pub = (
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return TestKey(seed=seed, pubkey_raw=pub)


@pytest.fixture
def test_key() -> TestKey:
    return make_test_key(20260912)
