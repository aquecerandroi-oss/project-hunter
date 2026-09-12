"""The seed of ``0030_meme_gate_v2`` — the two pre-registered arms of the flow
gate (T4.16, EXP-M5), frozen as strings so a later edit of the worker's
parsers cannot change what this revision planted.

**``flow_v2/1``** (``…0008``, EXP-M5, ``research_only``, ``clock = 15s``): the
study's E1 written as a gate — age 30–300 s, progress ≥ 5 % **and rising**,
net SOL flow > 0 (or the 60 s market-cap delta when the tape is absent),
≥ 10 distinct buyers, ``sells / buys ≤ 0,6``, holders rising over two
readings, snipers ≤ 2, ``dev_share ≤ 0,10`` (unknown refuses — the brief
names no exception here), creator not a net seller (unknown refuses),
participation ≤ 1 %; 0,05 SOL; exits: target 3×, trailing 35 % armed after
1,5×, ``max_hold_s = 1800``, ``creator_dump``, ``line_broken`` when a line
exists, ``max_loss`` 50 %. Judged on the **15-second series**
(``meme_features_15s``), filled on the next 15-second photo.

**``hype_probe_v0/2``** (``…0009``, EXP-M5 arm 2, ``research_only``): the
probe of ``hype_probe_v0/1`` with the same flow conditions **added** to the
hype score (flow > 0, ≥ 10 buyers, ``sells / buys ≤ 0,6``); everything else
verbatim (0,01 SOL, 3× / 40 % / 600 s, scale 0,04 through ``trendline_v0/1``).
It stays on the **minute** clock: ``hype_score`` is a per-minute feature (the
tape of the minute and the boards of the minute), and the 15-second series
carries no board standing — declared, not hidden.

Both arms carry ``pedigree_exclusions: true`` explicitly (EXP-M6 applies to
every set by default; the key exists so a falsification arm can say
``false``). Ids continue ``0022``'s sequence, fixed so two databases agree.
"""

from __future__ import annotations

FLOW_V2_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000008"
HYPE_PROBE_2_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000009"
SEEDED_RULE_SET_IDS_0030: tuple[str, ...] = (FLOW_V2_RULE_SET_ID, HYPE_PROBE_2_RULE_SET_ID)

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

FLOW_V2_PARAMS = (
    '"gate_key": "fluxo_e_holders", "gate_version": 1, '
    '"exit_key": "alvo_3x_trailing_35_apos_1_5x_tempo_30m", "exit_version": 1, '
    '"clock": "15s", "pedigree_exclusions": true, '
    '"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "5", "max_progress_pct": "100", '
    '"require_progress": true, "require_progress_rising": true, '
    '"require_positive_flow": true, "min_unique_buyers": 10, "max_sells_to_buys": "0.6", '
    '"require_holders_rising": true, "max_snipers": 2, '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": false, '
    '"require_creator_not_net_seller": true, "max_participation_pct": "1", '
    '"size_sol": "0.05", "target_x": "3", "trailing_pct": "35", "trailing_arm_x": "1.5", '
    '"max_hold_s": 1800, "max_loss_pct": "50", '
    '"exit_on_line_break": true, "line_break_snapshots": 2, '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.05", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 5, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""Numbers the brief does not fix, declared: ``max_open_positions = 5``
(the probe's ceiling, not EXP-M1's 3 — a 30-minute horizon on a 15-second
clock opens more than three at once), ``wallet_max_sol = 2,0`` and
``daily_loss_cap_sol = 0,20`` (every arm's), ``line_break_snapshots = 2``
(EXP-M2's), ``dev_share_unknown_allowed = false`` (the brief writes
"dev_share ≤ 0,10" with no exception)."""

HYPE_PROBE_2_PARAMS = (
    '"gate_key": "sonda_de_hype", "gate_version": 2, '
    '"exit_key": "alvo_3x_trailing_40_tempo_10m", "exit_version": 1, '
    '"pedigree_exclusions": true, '
    '"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "0", "max_progress_pct": "100", '
    '"require_progress": false, "max_participation_pct": "1", '
    '"require_creator_not_net_seller": true, "min_hype_score": "0.6", '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": true, "max_snipers": 2, '
    '"require_positive_flow": true, "min_unique_buyers": 10, "max_sells_to_buys": "0.6", '
    '"size_sol": "0.01", "target_x": "3", "trailing_pct": "40", "max_hold_s": 600, '
    '"max_loss_pct": "50", "scale_size_sol": "0.04", "scale_gate": "trendline_v0/1", '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.04", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 5, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""``hype_probe_v0/1`` (``0026``) verbatim plus the three flow keys; the gate
version bumps to 2 because the criteria moved."""

SEED_0030 = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_RULE_SET_ID}', 'flow_v2', '1', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb, '{_CODE_REF}', 'EXP-M5', 'active'),
  ('{HYPE_PROBE_2_RULE_SET_ID}', 'hype_probe_v0', '2', 'research_only',
   '{{{HYPE_PROBE_2_PARAMS}}}'::jsonb, '{_CODE_REF}', 'EXP-M5', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants

UNSEED_0030 = (
    "DELETE FROM meme_rule_sets WHERE id IN "  # noqa: S608 - this module's own frozen ids
    f"('{FLOW_V2_RULE_SET_ID}', '{HYPE_PROBE_2_RULE_SET_ID}')"
)
SEEDED_IDS_SQL_0030 = f"('{FLOW_V2_RULE_SET_ID}', '{HYPE_PROBE_2_RULE_SET_ID}')"

__all__ = [
    "FLOW_V2_PARAMS",
    "FLOW_V2_RULE_SET_ID",
    "HYPE_PROBE_2_PARAMS",
    "HYPE_PROBE_2_RULE_SET_ID",
    "SEED_0030",
    "SEEDED_IDS_SQL_0030",
    "SEEDED_RULE_SET_IDS_0030",
    "UNSEED_0030",
]
