# pump.fun realtime latency probe

window analysed: 1060 s; stalls dropped events: 10; loop lag p50/p99 (whole run; the max includes any sleep): 0.009/0.025 s; refused: none
segment analysed 1165 s of 2 unbroken segment(s); connection events inside it: none
clock offset vs pump.fun server-time: 0.057 s (min 0.019, max 0.111, n 10, rtt median 0.257 s; positive = local behind)

## Creations (pump program only)

**coverage by signature** — union 580, in all 520; nats_u: 580 (100.0 %), pp: 520 (89.7 %), rpc: 580 (100.0 %)

trenches `new` board saw 98.8 % of the 580 mints NATS announced.

### creation delivery

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| pp vs nats | 520 | 0 | 60 | 0.080 | 0.093 | 0.228 | 0.0% | 99.4% | 0.6% |
| rpc vs nats | 580 | 0 | 0 | 0.035 | 0.136 | 0.236 | 0.3% | 97.4% | 2.2% |
| rpc vs pp | 520 | 60 | 0 | -0.114 | 0.022 | 0.133 | 35.4% | 54.4% | 10.2% |
| tr_new vs nats | 573 | 0 | 7 | 0.213 | 0.454 | 0.680 | 0.0% | 99.8% | 0.2% |

## Trades on the watched coins

watched coins 105, followed wallets 20, replay-like share of NATS frames 0.0 % (an inference from a one-second timestamp); NATS frames by program {'pump': 3204, 'pump_amm': 747}; cohort 2893 signatures (pump program only: PumpSwap legs have no reference here)

rpc vs nats under different replay slacks (s): 0 s -> n 2893, p50 0.142, replay-like 2.28 % of frames; 2 s -> n 2893, p50 0.142, replay-like 0.00 % of frames; 4 s -> n 2893, p50 0.142, replay-like 0.00 % of frames

**coverage by signature (watched coins)** — union 2893, in all 2893; nats_u: 2893 (100.0 %), rpc: 2893 (100.0 %)

### trade delivery

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| rpc vs nats | 2893 | 0 | 0 | 0.042 | 0.142 | 0.232 | 0.5% | 97.5% | 2.0% |
| lite vs nats | 436 | 0 | 2457 | 0.181 | 0.293 | 0.447 | 0.0% | 100.0% | 0.0% |
| balance vs nats | 415 | 0 | 0 | 0.348 | 0.491 | 0.635 | 0.0% | 100.0% | 0.0% |
| balance vs rpc | 415 | 0 | 0 | 0.267 | 0.339 | 0.468 | 0.2% | 99.8% | 0.0% |

balance feed coverage: delivered 415 of 415 expected (100.0 %)

delay against block time (s, with the clock offset; see the note):

| source | n | p10 | p50 | p90 |
|---|---|---|---|---|
| nats_u | 2893 | 0.647 | 1.084 | 1.483 |
| rpc | 2893 | 0.794 | 1.224 | 1.613 |
| lite | 436 | 0.952 | 1.378 | 1.763 |
| balance | 415 | 1.136 | 1.542 | 1.947 |

balance feed: our arrival minus the server's own millisecond stamp: n 11313 p10 0.156 p50 0.192 p90 0.267

Block time is an estimate (the chain's getBlockTime is built from validator timestamps) published with one-second resolution; its total error was not measured (the check against getBlockTime was not obtained). The local clock's skew is corrected with the server-time offset (uncertainty about half the sample round trip). Compare sources with each other (the pair deltas), not with zero.

NATS block second minus the chain's getBlockTime: n 0 p10 - p50 - p90 -

## Migrations

PumpPortal migrations 12, trenches `graduated` adds 51

### graduation delivery (by mint)

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| tr_grad vs pp | 10 | 41 | 2 | 0.086 | 0.422 | 0.616 | 10.0% | 90.0% | 0.0% |

## KOL flag on the `new` board

pump add events 676 = 587 distinct coins (first add in the window); kol>0 at first add 2; kol updates 126; delay first add -> first kol>0 update: n 112 p50 0.999 s

## Field inventory (keys on the wire)

- `pp` (1): message
- `rpc:ack` (3): id, jsonrpc, result
- `nats_u:unifiedCoinCreationEvent` (39): base_decimals, bonding_curve, complete, created_timestamp, creator, depth, derived_pool, description, game_mode, initialized, is_banned, is_cashback_enabled, is_holder_reward, market_cap, market_cap_usd, mayhem_state, metadata_uri, mint, name, platform, program, quote_decimals, quote_mint, quote_token_program, real_quote_reserves, real_sol_reserves, real_token_reserves, show_name, signer, slot_index_id, supply, symbol, token_program, transfer_fee_bps, transfer_hook_program, tx, virtual_quote_reserves, virtual_sol_reserves, virtual_token_reserves
- `nats_u:unifiedTradeEvent` (12): amountSol, amountUsd, baseAmount, marketCap, mint, priceSol, priceUsd, slotIndexId, timestamp, tx, type, userAddress
- `tr_new` (6): baseVersion, board, patches, serverTs, type, version
- `nats_c:account_balance_change` (7): balance, slot, timestamp, tokenMint, txIndex, txSignature, walletAddress
- `tr_new entry (union of adds)` (51): age, ath, bc, bo, c, cb, desc, dh, dw, gd, hr, hs, i, ic, kol, lp, lv, m, mc, mh, mm, ms, n, nh, np, p, pa, pg, pl, sc, sn, so, t, t10, tf, tfUsd, tg, tw, tx5, txc, v, v15, v1h, v24h, v5, vUsd, vUsd15, vUsd1h, vUsd24h, vUsd5, ws
- `tr_grad entry (union of adds)` (49): age, ath, bc, bo, c, cb, desc, dh, dw, gd, hr, hs, i, ic, kol, lp, lv, m, mc, mh, n, nh, np, p, pa, pg, pl, sc, sn, so, t, t10, tf, tfUsd, tg, tw, tx5, txc, v, v15, v1h, v24h, v5, vUsd, vUsd15, vUsd1h, vUsd24h, vUsd5, ws

