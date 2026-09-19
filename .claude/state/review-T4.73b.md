# Re-revisão de risco — T4.73b (commit `d892c1ae`) contra os 7 achados de `review-T4.73.md`

**Veredito para o `--apply` do round trip de 0,02 SOL: APROVADO COM RESSALVAS**, condicionado a
**uma** coisa: o filtro `input_mint IS NULL` da T4.73c (Parte A desta rodada, árvore de trabalho,
**não commitado**) precisa estar commitado e na VPS **antes** do `--apply`. Sem ele, a primeira compra
spot confirmada grava 10 402 273 átomos de WIF em `sol_out_filled` e o freio de perda diária da mesa
real (`treasury_inflow_once`, roda a cada tick do `reconcile` mesmo com a tesouraria desligada) lê
10,4 M de "SOL" de entrada — `daily_loss_sol` negativo para sempre, `MEME_DAILY_LOSS_CAP_SOL` nunca
arma enquanto a mesa real opera. Isso não é risco do swap de 0,02; é risco da mesa que está ligada.

Somente leitura no código da T4.73b; nenhum `.env*` lido; nenhum comando git de escrita; sem rede.
Revisor: guardião do motor de risco, 2026-09-19. Lido: `git show --stat d892c1ae`,
`infra/scripts/meme_spot_swap{,_send,_rules,_db,_plan,_kill}.py`, `meme_ops_db.record_event`,
`services/meme-executor/hunter_meme_executor/{spot_verify,treasury_send,chain,treasury_db,treasury_reconcile,treasury_inflow}.py`,
os 4 arquivos de teste, `0056` + `ddl/meme_spot_swaps.py`, `.claude/state/notes-T4.73.md` §T4.73b,
`.claude/state/astra-review-review-T4.73b-send-path.md`.

## 1. Os 7 achados — o que fechou, onde, e o teste que prova

| # | Achado (T4.73) | Correção (file:line) | Teste que prova | Estado |
|---|---|---|---|---|
| 1 | invariante pós-simulação não lia a simulação | `meme_spot_swap_send.py:157-167` — `simulate_transaction(raw_tx, sig_verify=False, accounts=(wallet, other_ata))`, `simulated_balances(simulation.accounts)` (o parser de `treasury_send.py:56-68`, uma fonte), `None` → `simulation_accounts_unreadable`; `:168-188` passa `sol_after`/`token_after` simulados aos dois checks | `test_meme_spot_swap_send.py::test_buy_leg_end_to_end_confirms_and_commits_every_step` (fixture real 0,02 SOL, threshold 10 402 273 → `confirmed`, `filled == THRESHOLD`), `::test_buy_leg_refuses_when_the_simulated_post_state_is_short` (2 casos), `::test_buy_leg_refuses_when_simulation_accounts_are_unreadable`, `::test_sell_leg_refuses_when_the_simulated_sol_is_short` | **FECHADO** |
| 2 | timeout de confirmação virava `confirmed` com fill 0 | `meme_spot_swap_send.py:223-225` — `verdict != "confirmed"` → `LegResult("submitted", 0, signature)`, linha fica `submitted`; `:210-218` erro em `getSignatureStatuses` → idem; `meme_spot_swap.py:233-234` — `status != "confirmed"` encerra sem a volta, código 66 | `::test_confirmation_timeout_leaves_the_row_submitted` (20 × `None`, `"confirmed" not in statuses`), `::test_failure_after_mark_submitted_keeps_the_committed_row`, `test_meme_spot_swap.py::test_apply_never_fires_the_sell_back_when_the_buy_is_only_submitted` (`EX_UNCONFIRMED`, 1 perna) | **FECHADO** |
| 3 | uma transação de banco envolvia assinar/enviar/confirmar as duas pernas | `meme_spot_swap.py:286` — `engine.connect()` **sem** `begin()`; `meme_spot_swap_db.py:81,86,91,96,110,115` — `await conn.commit()` após cada escrita; `meme_spot_swap_send.py:244` — commit após `record_event` (que não commita sozinho, `meme_ops_db.py:60-78`) | `::test_buy_leg_end_to_end_confirms_and_commits_every_step` (sequência `insert:quoted, COMMIT, simulated, COMMIT, submitted, COMMIT, confirmed, COMMIT, event, COMMIT`), `::test_failure_after_mark_submitted_keeps_the_committed_row` | **FECHADO** |
| 4 | `--i-know` removia o teto; sem piso de carteira | `meme_spot_swap_rules.py:34` `HARD_CAP_SOL_EQUIVALENT = 0.10`; `:98-109` teto duro checado **antes** do brando e ignorando `i_know`; `:113-125` `classify_wallet_floor` (`carteira − amount − 0,01 ≥ piso`); `:128-140` `parse_wallet_floor` falha fechado; `meme_spot_swap.py:196-206` aplica o piso na perna de compra, lido da cadeia, antes da cotação | `test_meme_spot_swap_rules.py::test_hard_cap_is_not_lifted_by_i_know`, `::test_wallet_floor_keeps_amount_plus_fee_allowance_above_the_floor`, `::test_wallet_floor_env_defaults_to_0_30_and_refuses_garbage`; `test_meme_spot_swap.py::test_apply_refuses_a_hard_cap_amount_even_with_i_know` (`0.7>0.10`), `::test_apply_refuses_when_the_wallet_would_drop_below_the_floor` (`0.29<0.30`, com `--i-know`), `::test_apply_reads_the_wallet_floor_from_the_environment`, `::test_dry_run_amount_above_hard_cap_is_refused_even_with_i_know` | **FECHADO** |
| 5 | volta sem teto de impacto e sem reler o interruptor | `meme_spot_swap_send.py:120,133-134` — `classify_impact_cap` dentro de `run_apply_leg` (toda perna, antes do `POST /swap`); `meme_spot_swap.py:240-245` — relê `read_effective_kill_switch_state` após `--hold-s`, imprime/loga; a volta é saída e prossegue | `::test_impact_cap_runs_inside_the_leg` (`swap_calls == 0`), `test_meme_spot_swap.py::test_apply_round_trip_sells_back_what_was_filled_with_the_impact_cap` (`kill.calls == 2`, `max_impact_pct` na 2ª perna), `::test_apply_sell_back_is_an_exit_and_proceeds_after_the_switch_changed` | **FECHADO** |
| 6 | `Create ATA` com mint/ATA via lookup table pulava a checagem | `spot_verify.py:153-158` — `mint is None or ata is None` → `ata_account_via_lookup_table` | `test_spot_verify.py::test_a_create_ata_whose_mint_is_behind_a_lookup_table_is_refused`, `::test_a_create_ata_whose_ata_is_behind_a_lookup_table_is_refused` | **FECHADO** |
| 7 | `plan.verify_reason` ignorado no `--apply` | `meme_spot_swap.py:217-219` — recusa por `amount_cap_refusal`, `impact_refusal` **e** `verify_reason` antes de `run_apply_leg` | `test_meme_spot_swap.py::test_apply_refuses_on_the_plan_verify_reason_before_a_second_swap_post` (`swap_calls == 1`, `legs.calls == []`) | **FECHADO** |

### Os 4 pontos da Astra sobre o diff da T4.73b

| Ponto | Correção | Teste | Estado |
|---|---|---|---|
| envio ambíguo virava `failed` sem assinatura | `meme_spot_swap_send.py:192-195` — assinatura = `b58encode(signer.sign(message_bytes))` (o id da tx Solana é exatamente a primeira assinatura ed25519) e `mark_submitted` **antes** de `send_transaction` (`:197`); exceção no envio → `LegResult("submitted", 0, signature)` (`:198-204`), nunca `failed`; `:205-206` loga se o RPC devolver id diferente | `::test_the_signature_is_persisted_before_the_broadcast_and_a_send_error_keeps_it` (linha `submitted` com `SIGNATURE`, `"failed" not in statuses`) | **FECHADO** (ver ressalva R6 sobre a força do teste) |
| `filled` da venda medido no lado errado | `meme_spot_swap_send.py:226-231` — venda: `filled = max(0, lamports_after − sol_before)`; `sol_before` é a leitura de `:154`, antes de assinar | `::test_sell_leg_end_to_end_measures_the_fill_in_lamports` (`filled == SELL_OUT − 5_000`) | **FECHADO** |
| `refused`/`failed` saíam com 0 | `meme_spot_swap.py:95-97, 266-269` — 65/66/67 | `::test_apply_exits_non_zero_when_the_buy_leg_is_refused_or_failed` | **FECHADO** |
| leitores da tesouraria (`_SOL_INFLOW`, `_USDC_24H`, `_SUBMITTED`) sem filtro de par | **T4.73c, Parte A desta rodada** — `treasury_db.py:45-60` `WHERE input_mint IS NULL AND …` nas três consultas | `test_treasury_db.py::test_a_spot_swap_row_is_neither_inflow_nor_spend_nor_picked_by_the_reconcile` (Postgres real: antes do fix devolvia `20 804 546,109` de inflow; depois `0,109`), `test_treasury_db_spot_rows.py` (3 unitários, sessão falsa) | **FECHADO na árvore, NÃO COMMITADO** |

## 2. Achados residuais (nenhum bloqueia o round trip de 0,02 SOL)

Formato: `file:line — severidade — afirmação — cenário concreto de falha`.

- **R1** `infra/scripts/meme_spot_swap.py:235-237` — BAIXA — compra `confirmed` com `filled == 0` sai com **0** e pula a volta. Cenário: a tx confirma; a leitura `chain.token_account` de `_send.py:228` (commitment do `ChainReader`) ainda não vê o saldo da ATA recém-criada → `filled = max(0, 0 − 0) = 0`, linha `confirmed`/`sol_out_filled = 0`, WIF na carteira sem venda, e um wrapper lê "sucesso". O invariante da simulação garantiu ≥ threshold, então `confirmed` com 0 é contradição, não fill. Correção: código de saída ≠ 0 (66 serve: "reconciliar pela assinatura") e imprimir a assinatura; opcionalmente reler a ATA 2-3 × antes de gravar.
- **R2** `infra/scripts/meme_spot_swap.py:240` + `meme_spot_swap_kill.py:56` — BAIXA — a releitura do interruptor antes da volta faz `conn.execute(_ROW)`; erro de Postgres **propaga** (só o Redis é absorvido em `EMERGENCY`, `:49-51`) → exceção antes da venda, traceback, exit 1, moeda fica na carteira. Doutrina: trava de entrada não impede saída — a leitura falha deveria virar "estado desconhecido, logado" e a venda prosseguir. Perda: zero em SOL; custo é uma venda manual.
- **R3** `infra/scripts/meme_spot_swap_send.py:226-235` — BAIXA — entre `verdict == "confirmed"` e `mark_confirmed`, `chain.wallet`/`chain.token_account` podem levantar (RPC público) → exceção sai de `run_apply_leg`; a linha fica `submitted` (correto, commitada), mas o processo morre com traceback e exit 1 em vez de 66, e a volta não roda. Reconciliável pela assinatura. Correção: `try/except` → `LegResult("submitted", 0, signature)` com log `confirm_fill_unreadable`.
- **R4** `infra/scripts/meme_spot_swap_rules.py:189` — nota — numa venda cujo `min_sol_out ≤ 0,01 SOL`, o lado SOL do invariante tolera queda de até (0,01 − min) SOL; o lado token agora é real (achado 1). Perda máxima 0,01 SOL, por desenho da franquia de taxa. **Não afeta o round trip de 0,02** (threshold da volta ≈ 19,85 M lamports > 10 M).
- **R5** `infra/scripts/meme_spot_swap_plan.py:109` via `sol_equivalent` — nota — o teto duro de 0,10 também limita **vendas** (`--from <MINT> --to SOL`) pelo `out_amount` da cotação: uma posição que valha > 0,10 SOL não sai por este script. Conservador (nunca aumenta perda); registrar para o Everton não estranhar um `amount_above_hard_cap` numa saída.
- **R6** `infra/scripts/tests/test_meme_spot_swap_send.py:557-578` — nota — o teste prova "linha `submitted` com assinatura e sem `failed`" quando o envio levanta, mas não prova a **ordem** (escrita antes do broadcast): passaria igual se alguém movesse `mark_submitted` para o `except`. A ordem está no código (`:195` antes de `:197`). Sugestão: fake de RPC que anote `send` no mesmo log do `FakeConn` e asserção `statuses().index("submitted") < log.index("send")`.
- **R7** `services/meme-executor/hunter_meme_executor/treasury_db.py:44` — nota — `_LAST_ATTEMPT` (`max(requested_at)`) continua sem filtro de par (fora das três consultas do brief): um swap spot adia o próximo top-up da tesouraria pelo `min_interval`. Falha fechado (adia, nunca antecipa); vale um `AND input_mint IS NULL` na próxima passada por consistência.
- **R8** dry-run **não** mostra o piso da carteira (só `--apply` o avalia, `meme_spot_swap.py:196-206`): o Everton precisa saber que a carteira tem ≥ 0,33 SOL (0,30 + 0,02 + 0,01) antes do `--apply`, ou verá `wallet_below_floor_after_swap` só na hora.

## 3. O que foi conferido e continua certo

- Verificador instrução a instrução (`spot_verify.py`) inalterado fora de `:153-158`; Token-2022 na ATA da rota → `route_source/destination_mismatch`; a verificação (`_send.py:143-151`) precede a assinatura (`:192`).
- `--apply` exige interruptor **exatamente** `ACTIVE` (`meme_spot_swap.py:189-191`); signer carregado **depois** (`:192`), uma vez, nunca renderizado.
- `apply_requires_a_sol_leg` antes de engine/Redis/RPC (`:282`).
- Dry-run continua sem `simulateTransaction`/`sendTransaction` (`_dry_run`, `:133-172`; `SolanaTxRpcClient(args.rpc)` sem `allow_send`).
- `classify_submitted(..., age_s=0.0)` em `_confirm` (`_send.py:258`): sem veredito "expirou sem ser visto" dentro do script — nunca `failed` por idade; só a cadeia diz `failed`.

## 4. Comandos executados (saída real)

```
timeout 590 uv run pytest infra/scripts/tests services/meme-executor/tests/test_spot_verify.py -q -p no:cacheprovider -k "spot"
49 passed, 321 deselected in 4.12s

timeout 590 uv run pytest services/meme-executor/tests -q -p no:cacheprovider -k "treasury"
106 passed, 399 deselected in 27.11s        # inclui os 4 testes novos da T4.73c (1 integração + 3 unitários)

# RED da T4.73c antes do fix (Postgres real, testcontainers):
E   assert Decimal('20804546.1090000000') == (Decimal('0.079') + Decimal('0.03'))
```

## 5. Dry-run que o Everton roda primeiro (VPS, sem chave)

```bash
bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
    --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
    --round-trip --reason "T4.73 prova SOL->WIF" \
    --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4
```

A saída **tem** de mostrar, nos dois blocos (`quote So111… -> EKpQ…` e, depois de
`round-trip sell-back:`, `quote EKpQ… -> So111…`):

- `in=0.02 (20000000 atoms)` no primeiro bloco; no segundo, `in=` igual ao `threshold=` do primeiro;
- `out~=` e `threshold=` com `threshold ≈ out × 0,995` (50 bps);
- `route=` com rótulos de DEX conhecidos (nunca `(empty)`);
- `price_impact_pct=` bem abaixo de `0.01` (fixture real: `0.0006…`);
- `amount_cap: ok` e `impact_cap: ok` nos dois blocos;
- **`verify: OK`** nos dois blocos — qualquer `verify: REFUSED …` ou `verify_unavailable:…` = **parar**;
  `route_instruction_unknown:…` = a Jupiter mudou o layout da rota e o verificador não o cobre;
- `round_trip_cost_fraction=` abaixo de ~`0.015`;
- última linha `dry-run: nothing written (add --apply)` (e **não** `dry-run: would refuse: …`).

Depois disso, com a T4.73c commitada e na VPS, e a carteira ≥ 0,33 SOL:

```bash
bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
    --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
    --round-trip --apply --reason "T4.73 prova SOL->WIF"
```

Leitura da saída: `buy leg: confirmed filled=<átomos WIF> signature=<sig>` e
`sell-back leg: confirmed filled=<lamports> signature=<sig>`, exit 0. Exit **66** = perna
`submitted`, reconciliar pela assinatura impressa (a tesouraria automática **não** toca nessa linha
depois da T4.73c); exit **65** = recusa nomeada, nada saiu; exit **67** = falhou na cadeia, nada saiu
além da taxa. Exit **1** com traceback = R2/R3 acima: a linha está correta no banco, a volta não rodou,
vender manualmente com `--from EKpQ… --to SOL --amount <saldo>`.
