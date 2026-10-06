# pump.fun realtime latency probe

window analysed: 1997 s; stalls dropped events: 0; loop lag p50/p99 (whole run; the max includes any sleep): 0.009/0.025 s; refused: none
segment analysed 2102 s of 1 unbroken segment(s); connection events inside it: {'pp': {'disconnect': 1, 'backoff': 2, 'error': 1}}
clock offset vs pump.fun server-time: 0.056 s (min 0.034, max 0.152, n 18, rtt median 0.270 s; positive = local behind)

## Creations (pump program only)

**coverage by signature** — union 1100, in all 962; nats_u: 1100 (100.0 %), pp: 962 (87.5 %), rpc: 1100 (100.0 %)

trenches `new` board saw 99.4 % of the 1100 mints NATS announced.

### creation delivery

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| pp vs nats | 962 | 0 | 138 | 0.022 | 0.032 | 0.123 | 0.2% | 97.9% | 1.9% |
| rpc vs nats | 1100 | 0 | 0 | 0.055 | 0.154 | 0.241 | 0.4% | 99.3% | 0.4% |
| rpc vs pp | 962 | 138 | 0 | -0.004 | 0.104 | 0.207 | 8.5% | 86.5% | 5.0% |
| tr_new vs nats | 1093 | 0 | 7 | 0.224 | 0.446 | 0.685 | 0.0% | 100.0% | 0.0% |

## Trades on the watched coins

watched coins 180, followed wallets 20, replay-like share of NATS frames 0.0 % (an inference from a one-second timestamp); NATS frames by program {'pump': 11410, 'pump_amm': 4275}; cohort 10787 signatures (pump program only: PumpSwap legs have no reference here)

rpc vs nats under different replay slacks (s): 0 s -> n 10787, p50 0.156, replay-like 1.19 % of frames; 2 s -> n 10787, p50 0.156, replay-like 0.00 % of frames; 4 s -> n 10787, p50 0.156, replay-like 0.00 % of frames

**coverage by signature (watched coins)** — union 10787, in all 10787; nats_u: 10787 (100.0 %), rpc: 10787 (100.0 %)

### trade delivery

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| rpc vs nats | 10787 | 0 | 0 | 0.058 | 0.156 | 0.241 | 0.2% | 99.4% | 0.4% |
| lite vs nats | 4033 | 0 | 6754 | 0.187 | 0.296 | 0.425 | 0.0% | 100.0% | 0.0% |
| balance vs nats | 1315 | 0 | 2 | 0.347 | 0.469 | 0.622 | 0.0% | 100.0% | 0.0% |
| balance vs rpc | 1315 | 0 | 2 | 0.251 | 0.319 | 0.431 | 0.1% | 99.9% | 0.0% |

balance feed coverage: delivered 1315 of 1317 expected (99.8 %)

delay against block time (s, with the clock offset; see the note):

| source | n | p10 | p50 | p90 |
|---|---|---|---|---|
| nats_u | 10787 | 0.626 | 1.045 | 1.444 |
| rpc | 10787 | 0.780 | 1.204 | 1.591 |
| lite | 4033 | 0.913 | 1.332 | 1.746 |
| balance | 1315 | 1.105 | 1.552 | 1.925 |

balance feed: our arrival minus the server's own millisecond stamp: n 20819 p10 0.152 p50 0.184 p90 0.257

Block time is an estimate (the chain's getBlockTime is built from validator timestamps) published with one-second resolution; its total error was not measured (the check against getBlockTime was not obtained). The local clock's skew is corrected with the server-time offset (uncertainty about half the sample round trip). Compare sources with each other (the pair deltas), not with zero.

NATS block second minus the chain's getBlockTime: n 0 p10 - p50 - p90 -

## Migrations

PumpPortal migrations 28, trenches `graduated` adds 75

### graduation delivery (by mint)

Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).

| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |
|---|---|---|---|---|---|---|---|---|---|
| tr_grad vs pp | 12 | 63 | 16 | 0.219 | 0.499 | 0.982 | 0.0% | 100.0% | 0.0% |

## KOL flag on the `new` board

pump add events 1134 = 1111 distinct coins (first add in the window); kol>0 at first add 12; kol updates 406; delay first add -> first kol>0 update: n 376 p50 1.063 s

## Field inventory (keys on the wire)

- `rpc:ack` (3): id, jsonrpc, result
- `pp` (1): message
- `nats_u:unifiedCoinCreationEvent` (39): base_decimals, bonding_curve, complete, created_timestamp, creator, depth, derived_pool, description, game_mode, initialized, is_banned, is_cashback_enabled, is_holder_reward, market_cap, market_cap_usd, mayhem_state, metadata_uri, mint, name, platform, program, quote_decimals, quote_mint, quote_token_program, real_quote_reserves, real_sol_reserves, real_token_reserves, show_name, signer, slot_index_id, supply, symbol, token_program, transfer_fee_bps, transfer_hook_program, tx, virtual_quote_reserves, virtual_sol_reserves, virtual_token_reserves
- `tr_new` (6): baseVersion, board, patches, serverTs, type, version
- `nats_u:unifiedTradeEvent.processed` (61): amountSol, amountUsd, app, appFee, appFeeUsd, baseAmount, baseReserves, baseTransferFee, baseTransferFeeUsd, buybackFee, buybackFeeBasisPoints, cashback, cashbackFeeBasisPoints, cashbackUsd, coinMeta, creatorAddress, creatorFee, creatorFeeUsd, isBondingCurve, lpFee, lpFeeUsd, marketCap, marketCapNative, marketCapUsd, mintAddress, platform, platformFee, platformFeeUsd, poolAddress, priceBasePerQuote, priceQuotePerBase, priceSol, priceUsd, priorityFee, priorityFeeUsd, program, protocolFee, protocolFeeUsd, quoteAmount, quoteMintAddress, quoteReserves, quoteTokenProgram, quoteTransferFee, quoteTransferFeeUsd, relayer, relayerFee, relayerFeeUsd, slotIndexId, solPriceUsd, supply, surface, surfaceAttribution, timestamp, tx, txFee, txFeeUsd, type, userAddress, virtualQuoteReserves, virtualSolReserves, virtualTokenReserves
- `nats_u:unifiedTradeEvent.lite` (12): amountSol, amountUsd, baseAmount, marketCap, mint, priceSol, priceUsd, slotIndexId, timestamp, tx, type, userAddress
- `nats_c:account_balance_change` (7): balance, slot, timestamp, tokenMint, txIndex, txSignature, walletAddress
- `tr_new entry (union of adds)` (51): age, ath, bc, bo, c, cb, desc, dh, dw, gd, hr, hs, i, ic, kol, lp, lv, m, mc, mh, mm, ms, n, nh, np, p, pa, pg, pl, sc, sn, so, t, t10, tf, tfUsd, tg, tw, tx5, txc, v, v15, v1h, v24h, v5, vUsd, vUsd15, vUsd1h, vUsd24h, vUsd5, ws
- `tr_grad entry (union of adds)` (49): age, ath, bc, bo, c, cb, desc, dh, dw, gd, hr, hs, i, ic, kol, lp, lv, m, mc, mh, n, nh, np, p, pa, pg, pl, sc, sn, so, t, t10, tf, tfUsd, tg, tw, tx5, txc, v, v15, v1h, v24h, v5, vUsd, vUsd15, vUsd1h, vUsd24h, vUsd5, ws

