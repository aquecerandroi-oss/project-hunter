"""T4.8g — the mainnet simulation of OUR OWN bytes against the 2026-10-08 programs has an artefact
(guardian F2 of T4.8f asked for it): ``t48g_simulation_proof_mainnet.json``. The simulation itself is
a live action (``live`` marker, never in CI); this test pins what it found so a later edit of the
builders cannot quietly contradict it.

Every case: ``err`` null, no ``sendTransaction``, and ``unexplained_lamports`` equal to one of three
named quantities — 0, the rent of the ATA the transaction creates (293 / 298 bytes x 5080 lamports
per byte, measured), or the 15-byte growth of an old curve (15 x 5080 = 76 200). A residual that is
none of them would be a program change nobody read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

FIXTURE = Path(__file__).parents[1] / "fixtures/pumpfun/t48g_simulation_proof_mainnet.json"
RENT = 5080
ATA_SPL, ATA_T22, GROWTH = 293 * RENT, 298 * RENT, 15 * RENT
EXPLAINED = {0, ATA_SPL, ATA_T22, GROWTH, ATA_T22 + GROWTH}
DEPLOY = {"pump": 454_596_459, "pumpswap": 454_596_406}


def _proof() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE.read_text()))


def test_every_simulated_case_was_accepted_by_the_new_programs_and_nothing_was_sent() -> None:
    proof = _proof()
    assert proof["send_transaction_calls"] == 0
    assert {c["venue"] for c in proof["cases"]} == {"pump", "pumpswap"}
    for case in proof["cases"]:
        assert case["err"] is None, case["case"]
        assert case["sim_slot"] > DEPLOY[case["venue"]], case["case"]
        assert case["event_layout"] in (
            "2026-10-02/trailing_u64",
            "2026-10-02/idl_extension_trailing_u64",
        ), case["case"]
        assert case["compute_units"] < 150_000, case["case"]


def test_the_only_residuals_are_named_rent() -> None:
    for case in _proof()["cases"]:
        assert case["unexplained_lamports"] in EXPLAINED, case["case"]
    pumpswap = [c for c in _proof()["cases"] if c["venue"] == "pumpswap"]
    assert len(pumpswap) == 4 and all(c["unexplained_lamports"] == 0 for c in pumpswap)
    assert {c["case"] for c in pumpswap} >= {"swap_cb_acc", "swap_cb_noacc"}  # cashback pools


def test_the_rent_arithmetic_is_the_one_the_atas_obey() -> None:
    assert (ATA_SPL, ATA_T22, GROWTH) == (1_488_440, 1_513_840, 76_200)
    by_case = {c["case"]: c["unexplained_lamports"] for c in _proof()["cases"]}
    assert by_case["curve_buy_classic"] == ATA_SPL  # SPL Token account, 165 bytes + 128
    assert by_case["curve_buy_t22"] == ATA_T22  # Token-2022 account with ImmutableOwner
    assert by_case["curve_buy_hr"] == by_case["curve_buy_hr_small"] == GROWTH  # a constant
    assert by_case["curve_buy_3VRU"] == ATA_T22 + GROWTH
    assert by_case["curve_sell_hr_t22"] == 0


def test_what_the_simulation_did_not_cover_is_written_down() -> None:
    not_covered = " ".join(_proof()["not_covered"])
    assert "OLD 151-byte curve" in not_covered and "Mayhem" in not_covered
    assert "cashback" in not_covered
