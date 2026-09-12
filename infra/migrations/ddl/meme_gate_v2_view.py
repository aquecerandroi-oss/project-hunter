"""The ``meme_lab_scoreboard_v1`` of ``0030_meme_gate_v2`` (T4.16) — split from
``ddl/meme_gate_v2.py`` for the 350-line budget, the cut ``meme_lab_views.py``
took from ``meme_lab.py``. ``0027``'s board (``ddl/meme_wallets.py``) with
``measured`` deciding every sum and one more column, ``indeterminate``.
"""

from __future__ import annotations

from ddl.meme_lab_views import MEME_LAB_SCOREBOARD_VIEW

SCOREBOARD_0030 = f"""
CREATE VIEW {MEME_LAB_SCOREBOARD_VIEW} AS
WITH bets AS (
    SELECT b.rule_set_id,
           (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt,
           b.id, b.status, b.pnl_sol, b.r_multiple, b.exit_at, b.sol_usd_at_exit,
           b.exit ->> 'reason' AS exit_reason,
           b.status = 'closed' AND b.outcome_quality = 'measured' AS measured
    FROM meme_paper_bets b
), curve AS (
    SELECT rule_set_id, day_brt, exit_at, id,
           sum(pnl_sol) OVER (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id) AS cum_pnl
    FROM bets WHERE measured
), excursions AS (
    SELECT rule_set_id, day_brt,
           cum_pnl - GREATEST(0, max(cum_pnl) OVER
               (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id)) AS drawdown
    FROM curve
), drawdowns AS (
    SELECT rule_set_id, day_brt, -min(drawdown) AS max_drawdown_sol
    FROM excursions GROUP BY rule_set_id, day_brt
), positions AS (
    SELECT p.wallet, p.mint, p.status, p.realized_pnl_sol, p.r_multiple, p.last_trade_at,
           p.sol_spent,
           (p.first_buy_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt
    FROM meme_wallet_positions p WHERE p.first_buy_at IS NOT NULL
), wallet_curve AS (
    SELECT wallet, day_brt, last_trade_at, mint,
           sum(realized_pnl_sol) OVER
               (PARTITION BY wallet, day_brt ORDER BY last_trade_at, mint) AS cum_pnl
    FROM positions WHERE status = 'closed'
), wallet_excursions AS (
    SELECT wallet, day_brt,
           cum_pnl - GREATEST(0, max(cum_pnl) OVER
               (PARTITION BY wallet, day_brt ORDER BY last_trade_at, mint)) AS drawdown
    FROM wallet_curve
), wallet_drawdowns AS (
    SELECT wallet, day_brt, -min(drawdown) AS max_drawdown_sol
    FROM wallet_excursions GROUP BY wallet, day_brt
)
SELECT r.id AS rule_set_id, r.name, r.version, r.kind, r.exp_ref, r.status AS rule_set_status,
       b.day_brt,
       count(*) AS bets,
       count(*) FILTER (WHERE b.status = 'closed') AS closed,
       count(*) FILTER (WHERE b.measured AND b.pnl_sol > 0) AS wins,
       sum(b.pnl_sol) FILTER (WHERE b.measured) AS pnl_sol,
       sum(b.pnl_sol * b.sol_usd_at_exit)
           FILTER (WHERE b.measured AND b.sol_usd_at_exit IS NOT NULL) AS pnl_usd,
       count(*) FILTER (WHERE b.measured AND b.sol_usd_at_exit IS NULL) AS unpriced_usd,
       sum(b.r_multiple) FILTER (WHERE b.measured) AS r_sum,
       d.max_drawdown_sol,
       count(*) FILTER (WHERE b.exit_reason = 'rug_no_snapshot') AS rugs,
       count(*) FILTER (WHERE b.status = 'closed' AND NOT b.measured) AS indeterminate
FROM bets b
JOIN meme_rule_sets r ON r.id = b.rule_set_id
LEFT JOIN drawdowns d ON d.rule_set_id = b.rule_set_id AND d.day_brt = b.day_brt
GROUP BY r.id, r.name, r.version, r.kind, r.exp_ref, r.status, b.day_brt, d.max_drawdown_sol
UNION ALL
SELECT md5('wallet:' || p.wallet)::uuid AS rule_set_id,
       'wallet:' || left(p.wallet, 8) AS name, '1' AS version, 'real_observed' AS kind,
       NULL::text AS exp_ref, 'active' AS rule_set_status,
       p.day_brt,
       count(*) AS bets,
       count(*) FILTER (WHERE p.status = 'closed') AS closed,
       count(*) FILTER (WHERE p.status = 'closed' AND p.realized_pnl_sol > 0) AS wins,
       sum(p.realized_pnl_sol) FILTER (WHERE p.status = 'closed') AS pnl_sol,
       NULL::numeric AS pnl_usd,
       count(*) FILTER (WHERE p.status = 'closed') AS unpriced_usd,
       sum(p.r_multiple) FILTER (WHERE p.status = 'closed') AS r_sum,
       w.max_drawdown_sol,
       count(*) FILTER (WHERE p.status = 'closed' AND p.sol_spent > 0
                        AND p.realized_pnl_sol <= -0.9 * p.sol_spent) AS rugs,
       0::bigint AS indeterminate
FROM positions p
LEFT JOIN wallet_drawdowns w ON w.wallet = p.wallet AND w.day_brt = p.day_brt
GROUP BY p.wallet, p.day_brt, w.max_drawdown_sol
"""  # noqa: S608 - the only interpolation is the frozen view name
"""``0027``'s board with ``measured`` deciding every sum and one more column."""

__all__ = ["SCOREBOARD_0030"]
