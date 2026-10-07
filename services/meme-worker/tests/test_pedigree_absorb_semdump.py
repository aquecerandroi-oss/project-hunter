"""H-031b (EXP-M27): the twin ``absorb_semdump_v0/1``'s bets are subtracted from
the desk's ``creator_prior_dump_count``, by id, like the probe's, the pullback
pair's and EXP-M26's — through the existing id list, so the statement the 15 s
lane runs stays byte for byte the one ``test_pedigree_light`` pins.

Why: the twin admits bets the original does not (its own ceilings) and stays
open after the original's ``creator_dump``; a ``creator_sold_seen_at`` stamped
only on a twin bet would be evidence ``operator/5`` never had.
"""

from __future__ import annotations

import pytest

from hunter_indicators.meme.pedigree import PEDIGREE_V1
from hunter_meme_worker.lab_opportunities import MATURE_CHART_RULE_SET_IDS
from hunter_meme_worker.lab_repo_pedigree import ABSORB_SEMDUMP_RULE_SET_ID, pedigree_params

pytestmark = pytest.mark.unit


def test_the_twin_id_is_the_one_its_migration_seeds() -> None:
    assert ABSORB_SEMDUMP_RULE_SET_ID == "01994d00-6c1a-7000-8000-000000000022"


def test_the_full_read_subtracts_the_twin_beside_the_three_mature_arms() -> None:
    subtracted = pedigree_params(["MINT"], PEDIGREE_V1, full=True)["mature_rule_set_ids"]
    assert subtracted == [*MATURE_CHART_RULE_SET_IDS, ABSORB_SEMDUMP_RULE_SET_ID]


def test_the_light_read_still_binds_no_id() -> None:
    assert "mature_rule_set_ids" not in pedigree_params(["MINT"], PEDIGREE_V1, full=False)
