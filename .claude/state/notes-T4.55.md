# T4.55 — Reenvio, prioridade dinâmica e slippage de saída (R56 §2.1)

**Data:** 18/09/2026. **Não commitado** — lista de arquivos no fim. Nenhuma transação real enviada;
todos os testes usam fakes/fixtures gravadas.

## O achado (R56 §2.1) e o que mudou

3 de ~23 envios reais em 30 h terminaram `blockhash_expired_never_landed` (13 %) e uma venda morreu
em `6003 TooLittleSolReceived`. Causa: (a) prioridade fixa 10 000 µL/CU (0,000004 SOL), (b)
`maxRetries: 0`, (c) nenhum reenvio durante os 30 s do `_confirm`, (d) 1 % de slippage na venda.

| Item | Onde | O que faz |
|---|---|---|
| 1. Reenvio | `packages/core/hunter_core/execution/meme/confirm.py` (`poll_until_settled`), chamado por `submit.py` | a cada `resend_interval_s` (2 s) reenvia os **mesmos bytes assinados** enquanto `getSignatureStatuses` devolve `None`; para quando confirma, quando `getBlockHeight > last_valid_block_height` (⇒ `failed:blockhash_expired_never_landed`, decidido no laço, não 50 s depois na reconciliação) ou nos 30 s (⇒ `submitted_unconfirmed:confirmation_timeout`). Reenvio recusado pelo nó é contado (`resend_errors`) e ignorado; `processed` não é reenviado. `SubmitResult.resends`/`resend_errors`. `maxRetries: 0` e `skipPreflight: false` intocados; bundle Jito não reenvia |
| 2. Prioridade | `services/meme-executor/hunter_meme_executor/priority_fee.py` | `choose_priority_fee` (pura): `min(max(p75, piso), teto)` com a fonte nomeada; `PriorityFeeReader`: `getRecentPrioritizationFees([programa pump, curva do mint])` via `rpc.call` (o `tx_rpc.py` não foi tocado), 50 slots mais recentes, ≤ 1 leitura/s, 1,5 s de prazo, cache 10 s por conjunto de contas; falha ⇒ piso (`floor:read_failed`). Piso `MEME_PRIORITY_FEE_FLOOR_MICRO_LAMPORTS` (100 000), teto `MEME_PRIORITY_FEE_MAX_SOL` (0,002) / `compute_unit_limit` (= 5 000 000 µL/CU com 400 k) |
| 3. Slippage de saída | `send_tuning.py` (`SendTuning.exit_slippage_bps(reason)`) | `MEME_EXIT_MAX_SLIPPAGE_PCT` (5 %) para toda venda; `MEME_PANIC_EXIT_MAX_SLIPPAGE_PCT` (15 %) para `creator_dump`/`rug_signal`; compra continua com `limits.max_slippage_pct` (1 %). Vale na curva (`exits.py`) e na PumpSwap (`pumpswap_exit.py`) |

**Onde entra na admissão:** em `entries.py` a taxa é lida em paralelo com a leitura da curva
(`asyncio.gather`) e o valor **escolhido** vai para `proposal_from(priority_fee_sol=…)` — o check 20
(`fee_caps`) confere a taxa real, não a constante. Nenhum check foi alterado; a simulação pré-envio
continua igual. Nas vendas a taxa é lida **antes** do blockhash para não gastar a validade dele.

**O que fica gravado:** `meme_live_orders.intent.priority_fee` (`micro_lamports`, `source`,
`p75_micro_lamports`, `floor`, `cap`, `samples`, `fee_sol`), `intent.max_slippage_bps` (já existia) e,
depois de liquidada, `intent.resends`/`intent.resend_errors` (`repo.record_send_stats`). Heartbeat:
`resends_total`, `resend_errors_total`, `last_resends`, `resend_interval_s`, `priority_fee_reads`,
`priority_fee_read_failures`, `priority_fee_last`, `exit_max_slippage_pct`, `panic_exit_max_slippage_pct`.

**Divisões por orçamento de 350 linhas:** `submit.py` (439 → 299) ⇒ `submit_types.py` (tipos,
reexportados por `submit`) + `confirm.py` (laço); `config.py` (356 → 292) ⇒ `config_env.py`
(helpers de env, nomes públicos `float_env`, `int_env`, …); `exits.py` (357 → 347) ⇒
`close_ata_on_full_sell` foi para `exit_common.py` (o teste `test_build_and_fills` importa de lá).
`entries.py` ficou em 348.

## Testes (todos passando)

- `packages/core/tests/unit/execution/meme/test_meme_submit_resend.py` (7): confirma no 3.º envio
  (bytes idênticos, `resends == 2`), expira pelo `last_valid_block_height` (3 envios, `failed`,
  uma assinatura no journal), teto de 30 s (15 envios, `confirmation_timeout`), reenvio com erro não
  muda o estado, `processed` não reenvia, `resend_interval_s = 0` = comportamento antigo, falha de
  transporte no 1.º envio continua VM5 (replay sem 2.ª assinatura).
- `services/meme-executor/tests/test_priority_fee.py` (17): teto por custo, p75 nearest-rank, piso,
  teto, leitura falha/vazia/malformada/lenta (timeout), piso > teto, JSON da escolha, cache 10 s,
  1 leitura por tique (`floor:throttled`), janela de 50 slots.
- `services/meme-executor/tests/test_send_tuning.py` (4): padrões, env + valores absurdos, bps por
  motivo, `build_sell` com 1 % / 5 % / 15 % — `min_sol_output` = `net × (1 − tol)`, e o caso da PS
  (−14 %) cabe só nos 15 %.
- Suíte pedida (`services/meme-executor/tests packages/exchange-adapters/tests -m "not live"`) +
  `packages/core/tests/unit/execution/meme`: **1150 passed, 2 skipped** (ver saída no relatório).

## Fora do escopo / concerns

1. `compute_unit_limit` continua 400 000 (R56 item 3): baixar exige gravar `computeUnitsConsumed`
   nas fills antes. Com o teto por custo, 400 k CU × 5 000 000 µL = 0,002 SOL no pior caso.
2. `getRecentPrioritizationFees` com contas devolve, por slot, a taxa **mínima** que travou todas as
   contas — em slots sem transação na curva o valor é 0; o p75 de uma curva quieta é o piso, por
   desenho. A primeira leitura real na VPS deve ser conferida em `priority_fee_last`.
3. O reenvio usa o mesmo `sendTransaction` (`skipPreflight: false`): uma transação já `processed`
   não é reenviada (o laço checa o status antes); uma que o nó ainda não viu passa pela preflight de
   novo — custo ~400 ms por reenvio no nó, não no executor.
4. O throttle de 1 leitura/s é global: uma venda e uma compra em mints diferentes no mesmo segundo
   fazem a segunda pagar o piso (`floor:throttled`), nunca esperar.
5. Não tocado: `treasury*.py`, `jupiter/`, `tx_rpc.py`. `ruff format --check` do repo inteiro aponta
   só `infra/scripts/research/*` (de outros agentes).
