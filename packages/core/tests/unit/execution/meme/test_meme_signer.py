"""The key is read once, never rendered, and the boot refuses before touching it (§3.3)."""

from __future__ import annotations

import copy
import gc
import json
import pickle
import traceback
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import structlog

from hunter_core.execution.meme.gates import ENV_GATES_FILE, ENV_LIVE_FLAG, MemeLiveTradingRefused
from hunter_core.execution.meme.signer import (
    ENV_SECRET_KEY,
    MemeSigner,
    SecretKeyMalformed,
    SecretKeyMissing,
    SignerError,
    boot_meme_execution,
    environment_has_secret,
)
from packages.core.tests.unit.execution.meme.conftest import TestKey, make_test_key

TODAY = date(2026, 10, 21)


def _renderings(signer: MemeSigner) -> list[str]:
    out = [repr(signer), str(signer), f"{signer}", f"{signer!r}"]
    out.append(json.dumps({"signer": repr(signer), "pubkey": signer.pubkey}))  # a heartbeat
    with structlog.testing.capture_logs() as logs:
        structlog.get_logger("test").info("boot", signer=signer, pubkey=signer.pubkey)
    out.append(repr(logs))
    try:
        signer.sign(b"")
    except SignerError:
        out.append(traceback.format_exc())
    try:
        MemeSigner.from_environment({ENV_SECRET_KEY: "not-base58-!!"})
    except SecretKeyMalformed:
        out.append(traceback.format_exc())
    return out


def _reachable_strings(obj: object, depth: int = 3) -> list[str]:
    """Every str/bytes reachable from ``obj`` through the GC graph, a few hops deep."""
    seen: set[int] = set()
    found: list[str] = []
    frontier: list[Any] = [obj]
    for _ in range(depth):
        nxt: list[Any] = []
        for item in frontier:
            for ref in gc.get_referents(item):
                if id(ref) in seen:
                    continue
                seen.add(id(ref))
                if isinstance(ref, bytes | bytearray):
                    found.append(ref.hex())
                elif isinstance(ref, str):
                    found.append(ref)
                else:
                    nxt.append(ref)
        frontier = nxt
    return found


def _secret_markers(key: TestKey) -> list[str]:
    return [key.base58, key.base58[:12], key.seed.hex(), key.seed[:6].hex(), key.json_array[:20]]


@pytest.mark.parametrize("shape", ["base58", "json_array", "seed32"])
def test_key_shapes_load_and_sign(test_key: TestKey, shape: str) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from hunter_core.execution.meme.base58 import b58encode

    value = {
        "base58": test_key.base58,
        "json_array": test_key.json_array,
        "seed32": b58encode(test_key.seed),
    }[shape]
    env = {ENV_SECRET_KEY: value}
    signer = MemeSigner.from_environment(env)
    assert signer.pubkey == test_key.pubkey
    signature = signer.sign(b"message")
    assert len(signature) == 64
    Ed25519PublicKey.from_public_bytes(test_key.pubkey_raw).verify(signature, b"message")


def test_key_is_read_once_and_scrubbed(test_key: TestKey) -> None:
    env = {ENV_SECRET_KEY: test_key.base58, "OTHER": "kept"}
    MemeSigner.from_environment(env)
    assert ENV_SECRET_KEY not in env and env["OTHER"] == "kept"
    assert not environment_has_secret(env)
    with pytest.raises(SecretKeyMissing):
        MemeSigner.from_environment(env)


def test_secret_never_leaks(test_key: TestKey) -> None:
    env = {ENV_SECRET_KEY: test_key.base58}
    signer = MemeSigner.from_environment(env)
    haystack = "\n".join(_renderings(signer) + _reachable_strings(signer))
    for marker in _secret_markers(test_key):
        assert marker not in haystack, f"secret material leaked: {marker[:6]}…"
    assert test_key.pubkey in repr(signer)  # the public key is the only identity rendered
    with pytest.raises(TypeError):
        pickle.dumps(signer)
    with pytest.raises(TypeError):
        copy.copy(signer)
    with pytest.raises(TypeError):
        copy.deepcopy(signer)
    with pytest.raises(TypeError):
        vars(signer)  # __slots__: there is no __dict__ to dump


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "0OIl",  # invalid base58 characters
        "[1,2,3]",
        "[300," + ",".join(["1"] * 63) + "]",
        '["a"]',
        "[not json",
    ],
)
def test_malformed_or_empty_keys_are_refused_without_echo(value: str) -> None:
    with pytest.raises(SignerError) as excinfo:
        MemeSigner.from_environment({ENV_SECRET_KEY: value})
    assert value.strip() == "" or value.strip() not in str(excinfo.value)


def test_mismatched_public_half_is_refused(test_key: TestKey) -> None:
    other = make_test_key(1)
    from hunter_core.execution.meme.base58 import b58encode

    tampered = b58encode(test_key.seed + other.pubkey_raw)
    with pytest.raises(SecretKeyMalformed, match="public key does not match"):
        MemeSigner.from_environment({ENV_SECRET_KEY: tampered})


def test_boot_refuses_live_with_red_gates_before_touching_the_key(
    tmp_path: Path, test_key: TestKey
) -> None:
    gates = tmp_path / "meme_gates.json"
    gates.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    env = {ENV_LIVE_FLAG: "true", ENV_GATES_FILE: str(gates), ENV_SECRET_KEY: test_key.base58}
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        boot_meme_execution(env, today=TODAY)
    assert excinfo.value.reason == "gates_schema_mismatch"
    assert env[ENV_SECRET_KEY] == test_key.base58  # never read: the process dies first


def test_boot_live_requires_the_key(tmp_path: Path) -> None:
    from packages.core.tests.unit.execution.meme.test_meme_gates import gates_doc

    gates = tmp_path / "meme_gates.json"
    gates.write_text(json.dumps(gates_doc()), encoding="utf-8")
    env = {ENV_LIVE_FLAG: "true", ENV_GATES_FILE: str(gates)}
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        boot_meme_execution(env, today=TODAY)
    assert excinfo.value.reason == "secret_key_missing"


def test_boot_paper_mode_without_key_is_fine_and_with_key_loads_it(test_key: TestKey) -> None:
    mode, signer = boot_meme_execution({}, today=TODAY)
    assert mode.live is False and signer is None
    env = {ENV_SECRET_KEY: test_key.base58}
    mode, signer = boot_meme_execution(env, today=TODAY)
    assert mode.live is False and signer is not None and signer.pubkey == test_key.pubkey
    assert ENV_SECRET_KEY not in env
