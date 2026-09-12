"""Boot refusals (brief item 4e): with the live flag on and anything missing the
process refuses by name, in the order gates → policy → RPC → key; with the flag
off it boots inert. Test keys are generated in memory and discarded."""

from __future__ import annotations

import json
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.gates import MemeExecutionMode, MemeLiveTradingRefused
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_meme_executor.config import ExecutorConfig, boot

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 12)
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.2",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "3600",
}


def _gates(tmp_path: Path, *, small_test: bool = False, passed: bool = True) -> str:
    doc: dict[str, object] = {
        "schema": "hunter.meme_gates/v1",
        "gate_a_engineering": {"passed": passed, "date": "2026-09-12", "evidence": "notes-T4.14"},
        "gate_b_evidence": {"passed": passed, "date": "2026-09-12", "evidence": "EXP-M1"},
        "gate_c_owner": {"enabled": True, "date": "2026-09-12"},
        "signed_by": "everton",
        "signed_at": "2026-09-12",
        "valid_until": "2026-10-12",
    }
    if small_test:
        doc["small_test_authorization"] = {
            "authorized_by": "everton",
            "scope": {"max_sol_per_trade": "0.01", "max_total_sol": "0.03", "max_trades": 3},
            "expires_at": "2026-09-13",
            "decision_note": "obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
        }
    path = tmp_path / "meme_gates.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


def _test_key() -> str:
    seed = random.Random(20260912).randbytes(32)
    pub = (
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return b58encode(seed + pub)


def _boot(env: dict[str, str]) -> tuple[ExecutorConfig, MemeExecutionMode, MemeSigner | None]:
    return boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)


def test_flag_off_boots_inert_without_gates_policy_or_key() -> None:
    config, mode, signer = _boot({})
    assert signer is None and mode.live is False
    assert config.live is False
    assert config.limits.profile == "meme_paper_v0"


def test_flag_on_without_gates_file_is_refused_first(tmp_path: Path) -> None:
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot({"ENABLE_MEME_LIVE_TRADING": "true", **POLICY, "SOLANA_RPC_URL": "https://x"})
    assert info.value.reason == "gates_file_not_configured"


def test_flag_on_with_gates_but_without_policy_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot({"ENABLE_MEME_LIVE_TRADING": "true", "MEME_GATES_FILE": _gates(tmp_path)})
    assert info.value.reason == "policy_missing"
    assert "MEME_WALLET_MAX_SOL" in str(info.value)


def test_flag_on_without_rpc_url_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot({"ENABLE_MEME_LIVE_TRADING": "true", "MEME_GATES_FILE": _gates(tmp_path), **POLICY})
    assert info.value.reason == "rpc_url_missing"


def test_flag_on_without_key_is_refused_last(tmp_path: Path) -> None:
    env = {
        "ENABLE_MEME_LIVE_TRADING": "true",
        "MEME_GATES_FILE": _gates(tmp_path),
        **POLICY,
        "SOLANA_RPC_URL": "https://rpc.example",
    }
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot(env)
    assert info.value.reason == "secret_key_missing"


def test_everything_present_boots_live_and_scrubs_the_key(tmp_path: Path) -> None:
    env = {
        "ENABLE_MEME_LIVE_TRADING": "true",
        "MEME_GATES_FILE": _gates(tmp_path),
        **POLICY,
        "SOLANA_RPC_URL": "https://rpc.example",
        ENV_SECRET_KEY: _test_key(),
    }
    config, mode, signer = _boot(env)
    assert config.live and mode.live and signer is not None
    assert ENV_SECRET_KEY not in env, "the key is read once and removed from the environment"
    assert config.limits.max_sol_per_trade == Decimal("0.02")


def test_the_written_small_test_replaces_gates_a_and_b_and_caps_the_policy(tmp_path: Path) -> None:
    env = {
        "ENABLE_MEME_LIVE_TRADING": "true",
        "MEME_GATES_FILE": _gates(tmp_path, small_test=True, passed=False),
        **POLICY,
        "SOLANA_RPC_URL": "https://rpc.example",
        ENV_SECRET_KEY: _test_key(),
    }
    config, mode, _ = _boot(env)
    limits = config.limits
    assert limits.max_sol_per_trade == Decimal("0.01")
    assert limits.wallet_max_sol == Decimal("0.03")
    assert config.small_test_max_trades == 3
    assert mode.gates is not None and mode.gates.small_test is not None
    assert mode.gates.small_test.decision_note.startswith("obsidian/06-DECISIONS/")


def test_the_small_test_without_a_decision_note_is_refused(tmp_path: Path) -> None:
    path = _gates(tmp_path, small_test=True, passed=False)
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    doc["small_test_authorization"]["decision_note"] = "notes-T4.14.md"
    Path(path).write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot({"ENABLE_MEME_LIVE_TRADING": "true", "MEME_GATES_FILE": path, **POLICY})
    assert info.value.reason == "small_test_without_decision_note"


def test_a_devnet_url_with_cluster_mainnet_is_refused(tmp_path: Path) -> None:
    env = {
        "ENABLE_MEME_LIVE_TRADING": "true",
        "MEME_GATES_FILE": _gates(tmp_path),
        **POLICY,
        "SOLANA_RPC_URL": "https://api.devnet.solana.com",
    }
    with pytest.raises(MemeLiveTradingRefused) as info:
        _boot(env)
    assert info.value.reason == "rpc_url_cluster_mismatch"
