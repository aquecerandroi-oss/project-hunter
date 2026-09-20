# Revisão final de risco — mesa `spot/1` (T4.74-1…5) antes do pacote de deploy

**Revisor:** risk-engine-guardian · **Data:** 2026-09-19 · **Modo:** só leitura, sem rede, sem git de escrita, `.env*` não lido.
**Commits cobertos:** 1ae49cb0, c7aea2e9, f754c1c0, c58fa4eb, 141ac185, 4464c8dc, 71b595e8.
**Suíte executada uma vez:** `timeout 590 uv run pytest services/meme-executor -q -p no:cacheprovider -m "not integration and not live and not live_devnet"` → **630 passed, 53 deselected in 7.23s**.

## Veredito

| Passo | Veredito |
|---|---|
| (a) Deploy INERTE (`SPOT1_ENABLED` ausente/false) | **APROVADO** — com a ordem de deploy do item 11 (migração 0057 antes de recriar o executor; `compose.sh update` já faz isto). |
| (b) `SPOT1_ENABLED=true` + `SPOT1_MAX_OPEN=1` | **APROVADO COM RESSALVAS** — o caminho do dinheiro está correto (10/10 itens do §9 verificados); as ressalvas A1–A4 abaixo são de gestão de posição e de operação, não de assinatura. Nenhuma delas gasta SOL a mais; duas delas travam o resto da mesa (fail-closed) se acontecerem. |

## Checklist §9 do design, item a item

| # | Item | Veredito | Evidência |
|---|---|---|---|
| 1 | `signer.sign` só em `spot_leg`, depois de `verify` e da simulação com invariante lido de `simulation.accounts` | OK | `spot_send.py:146` `verify_spot_swap_tx(decoded.message, …)`; `:167-171` `simulate_transaction(raw_tx, accounts=(wallet, other_ata))`; `:177` `simulated_balances(simulation.accounts)`; `:185-196` `check_simulated_leg` → recusa; `:207` `ctx.signer.sign(decoded.message_bytes)` — os **mesmos bytes** verificados em `:146`. `grep -rn "\.sign(" hunter_meme_executor/` → só `spot_send.py:207` e `treasury_send.py:196` (tesouraria, pré-existente). `spot_reconcile.py`/`spot_settle.py`: zero `sign`/`send_transaction`. |
| 2 | Kill switch relido entre admissão e assinatura | OK | `spot_entries.py:245-251` (`kill.refresh()` após a linha `admitted`, antes de `spot_leg`) **e** `spot_send.py:200-202` (relido de novo após a simulação, imediatamente antes de assinar; venda nunca bloqueada — RISK_ENGINE §10). Teste `test_the_kill_switch_re_read_before_the_signature_blocks_a_buy`. |
| 3 | Ficha clampada por `max_sol_per_trade` e pelo escopo | OK | `spot_config.py:109-111` `min(ticket_sol, limits.max_sol_per_trade)`; `spot_entries.py:128-129` usa `ctx.config.limits`, que é `effective_limits` = `min(policy, small_test.max_sol_per_trade)` (`config.py:175-196`, recomposto no reload por `with_gates` `:201-208`). O motor repete o clamp em `spot_profile.py:318` e publica `trade_cap` como `LimitCap` (`:272`). `binding_constraint` sempre gravado (`:296-300`; `spot_entries.py:213-215` grava `decision.to_jsonable()` na recusa também). |
| 4 | Posições spot **e** compras em voo dentro de `MemeWalletState` para memes e lançamento | OK | `spot_brake.py:55-59` `brake_positions` = memes + lançamento + spot; `:62-66` `spot_pending_intents`. Consumidores: `admission_context.py:128-130` (memes), `launch_entries.py:148-150` (lançamento), `heartbeat.py:180`, `spot_entry_reads.py:208-214` (spot). `wallet_from` (`admission.py:274-291`) leva tudo a `positions`/`pending_intents`; `inputs.py:195-205` soma `reserved_sol`/`exposure_total_sol` sem olhar a pista; `spot_profile.py:259-262` `daily_cap = cap − perda − Σ gasto de toda pista − reservas`. Ressalva A3 (posição sem marca = valor 0). |
| 5 | `pending` nunca vira `confirmed`; uma assinatura por linha | OK | `spot_send.py:234-239` `_confirm` ≠ `confirmed` ⇒ `submitted_unconfirmed`; `:247-252` meta não servido ⇒ `submitted_unconfirmed`, nunca fill zero; `:257-262` fill inconsistente ⇒ idem. `spot_repo.py:132-138` `_SUBMITTED` só de `admitted`/`simulated` (jamais de `submitted_unconfirmed` ⇒ 1 assinatura por linha); `:139-143` `_CONFIRMED` só de `submitted_unconfirmed`. Reconcile `spot_reconcile.py:173-174` só liquida `confirmationStatus ∈ (confirmed, finalized)`. Testes `…stays_pending_is_submitted_unconfirmed_never_confirmed`, `…fill_is_not_visible_yet_is_not_confirmed_with_zero`. |
| 6 | Nenhuma leitura de `.env` fora de `spot_config` | OK | `grep os.environ/getenv/dotenv` no executor → só `config.py:315` (o `env` que `boot` injeta) e `exits.py:265` (memes, pré-existente). `SpotConfig.from_env(env, signer_present=…)` em `config.py:301`; `spot_config.py` recebe `Mapping`, nunca `os.environ`. |
| 7 | Prioridade capada (100 000) e verificada | OK | `spot_send.py:138-143` `client.swap(max_priority_fee_lamports=…)` → `jupiter/client.py:113-126` `priorityLevelWithMaxLamports{maxLamports, medium}`; `spot_verify.py:326-328` recalcula `ceil(limit × price / 1e6)` **da mensagem decodificada** (limit padrão 1 400 000 se ausente); `spot_send.py:151-153` recusa `priority_fee_above_cap` acima do cap do chamador. Padrão `spot_config.py:65` = 100 000, faixa `[0, 1e9]` (`:165-167`). Teste `test_a_priority_fee_above_the_caller_s_cap_is_refused_before_anything_else`. |
| 8 | `SPOT1_ENABLED=false` ⇒ zero entradas, zero cotações, zero vendas; freio e reconcile continuam | OK | `main.py:316-323` cria `spot-entries`/`spot-exits` só com `config.spot.enabled`; `spot_entries.py:71-73` e `spot_exits.py:70-72` retornam antes de qualquer consulta. `spot_reconcile.py:74-76` roda com signer presente **qualquer que seja a flag** e **nunca envia** (sem `send_transaction`/`sign`; só `get_signature_statuses`/`get_transaction`/`get_block_height` + escritas de banco). Freio: `brake_positions` lê `spot_positions` em todo modo (`heartbeat.py:180`). Testes `test_disabled_makes_no_query_no_quote_no_signature`, `test_a_disabled_lane_makes_no_query_and_no_quote`. Consequência: ver item 11 e ressalva A1. |
| 9 | Refutação inescapável sem `.env` (pior prefixo) | OK | `spot_repo_positions.py:110-121` `_CLOSED_STATS` com `min(run_pnl)` e `min(run_r/k WHERE k ≥ min_trades)` por janela ordenada `(exit_at, id)` desde `:since`; `spot_exit_rules.py:146-160` decide pelo pior prefixo; `spot_entries.py:88-102` relê do banco em **todo** tique antes de buscar candidato; `spot_settle.py:78-99` relê após cada saída. Único reset: `SPOT1_REFUTATION_RESET_AT` (`spot_config.py:236-250`, exige offset) ou versão nova. Estado só em memória não existe para a refutação. |
| 10 | `Decimal` em toda quantia, atoms `int` | OK | `grep float` em `spot_*.py` + `spot_profile.py` → zero ocorrências fora de type-narrowing; `spot_repo.py:166-185` parse por `Decimal(str(…))`; `models.py:36,60` `price_impact_pct: Decimal`; lamports/atoms `int` em `spot_send.py:130-134,186-192`, `spot_entry_writes.py:84-92`. |
| 11 | Ordem de deploy: 0057 antes do executor | OK | `infra/vps/compose.sh:241-243`: `build api web` → `run --rm migrate` (sozinho) → `up -d`. O executor lê `spot_positions` em todo modo (`heartbeat.py:180` via `brake_positions`; `admission_context.py:128`; reconcile) ⇒ sem 0057 o heartbeat e a admissão de memes quebrariam — o `update` já garante a ordem; **não** usar `up`/`restart` a mão antes do `migrate`. `HEAD_REVISION = "0057_spot_desk"` (`test_migrations.py:43`). |
| 12 | VPS sem linhas `SPOT1_*` ⇒ inerte | OK | `spot_config.py:73` `requested=False` por padrão; `from_env` `:151` `parse_flag(None)` → False; `inert_reason` `:97-98` = `disabled`; `main.py:287` publica `spot1=inert:disabled` no boot; `:316` nenhuma tarefa spot. Sem `SPOT1_*` ⇒ todos os demais valores caem no padrão (`:79-92`). |
| 13 | Recusas transitórias não contam nas 6 duras — posição pode nunca ser vendida? | **SIM, pode** — ressalva A2 | ver abaixo. |
| 14 | Compra aberta pelo reconcile com a flag false fica sem gestão — severidade | **MÉDIA (b) / não se aplica (a)** — ressalva A1 | ver abaixo. |

## Achados (ressalvas) — `file:line — severidade — afirmação — cenário — correção`

**A1 — `main.py:316-323` + `spot_exits.py:71` — MÉDIA (só passo b) — Posição spot aberta pelo reconcile com `SPOT1_ENABLED=false` nunca é marcada nem vendida, e trava as entradas de TODAS as pistas.**
Cenário: Everton liga a flag, uma compra fica `submitted_unconfirmed`, ele desliga a flag e roda `update`; a tx pousa; `spot_reconcile.py:175→251-261` abre a posição (`open_from_order`) com `mark_sol = NULL` (`_INSERT` `spot_repo_positions.py:81-88` não grava marca). Sem a tarefa `spot-exits` ninguém marca nem vende: sem stop, sem alvo, sem `time`. Pior: `admission.py:295` `marks_complete = all(mark_sol is not None)` ⇒ `wallet_status = marks_incomplete` (`checks.py:104`) para memes, lançamento e spot **enquanto a posição existir**, e `inputs.py:192` conta a posição como valendo 0 ⇒ `daily_loss_sol` sobe 0,05 SOL de forma fantasma (pode latch `daily_loss_cap_reached`, `spot_entries.py:211-212`). Dinheiro não some (fail-closed), mas a mesa inteira para até venda manual, e não há script para fechar a linha `spot_positions` depois de uma venda por `meme_spot_swap.py` (só `--sell-now`, que depende da própria pista). Verificável no heartbeat: `spot1_positions_open=1`, `spot1.open[0].mark_sol=null`, `last_refusal=marks_incomplete`.
Correção (uma frase): criar `spot-exits` sempre que `signer` existir e `config.live` (como o reconcile), lendo `cfg.enabled` só para **entradas** — saídas são sempre permitidas (RISK_ENGINE §10) — e dar ao operador um `spot_desk_markets.py --close-manual <id> --signature <sig> --reason` auditado.
Para o passo (a) não se aplica (não há linhas spot); para (b) mitigação operacional: **nunca desligar a flag com `spot1.buys_unconfirmed>0` ou `exit_pending=true`**; desligar preferencialmente pelo `meme.kill` (entradas param, saídas continuam).

**A2 — `spot_exits.py:283-285` + `spot_send.py:124-125` — MÉDIA (passo b) — Uma recusa "transitória" permanente nunca bloqueia, nunca aparece no heartbeat e gera 1 linha `spot_orders` por minuto para sempre.**
Cenário: token cuja rota a Jupiter deixa de servir para o lote inteiro (pool drenada, mint delistado, `400 no route`): a marca falha (`_mark` → `None`, marca antiga fica, `mark_stale`), `decide_exit` só dispara `time` após 4 h; `_sell` → `spot_leg` → `quote_failed:<qualquer exceção>` — `spot_send.py:124` não distingue `exc.retryable` (a entrada distingue em `spot_entry_reads.py:191-195`) ⇒ `TRANSIENT_EXIT_REFUSALS` (`spot_exit_repo.py:46-49`) ⇒ `hard` não incrementa ⇒ backoff 60 s (`BACKOFF_S[-1]`) ⇒ tentativa infinita: ~1 440 linhas `refused`/dia por posição, `blocked_exits` vazio, `exits_by_reason` vazio (só conta confirmadas), nada no painel além de `age_s > horizon_s`. A posição segue ocupando a vaga global e o cap diário.
Correção (uma frase): em `spot_leg`, `ExchangeError` com `retryable=False` deve recusar `quote_refused:<tipo>` (dura, como na entrada), e a partir de N (p. ex. 30) recusas transitórias seguidas publicar `spot1.stuck_exits[id]` no heartbeat.
O que o operador faz hoje: `--sell-now` não ajuda (mesmo caminho Jupiter); `meme_spot_swap.py --from <mint> --to SOL --apply` só ajuda se a Jupiter roteia; senão venda por outra DEX na carteira e — ver A1 — não há fechamento auditado da linha `spot_positions`.

**A3 — `admission.py:295` + `spot_repo_positions.py:81-88` — BAIXA (passo b) — Janela de ≤ 20 s após cada compra confirmada em que toda pista recusa `marks_incomplete` e a compra conta como perda integral.**
Cenário: compra spot confirma em T; até o próximo tique de `spot-exits` (`SPOT1_MARK_S` 20 s) `mark_sol=NULL` ⇒ memes/lançamento recusam `marks_incomplete` e `daily_loss_sol` vê −0,05 fantasma; com `MEME_DAILY_LOSS_CAP_SOL` apertado, `daily_loss_cap_reached` pode latch o kill switch por 20 s de foto errada. A pista de memes já convive com a mesma janela; com `SPOT1_MAX_OPEN=1` o efeito é uma recusa transitória, não perda. Correção: marcar a posição na abertura com a própria cotação de venda do lote (uma `GET /quote` extra em `open_position`) ou excluir de `marks_complete` posições com `age < 2×mark_s`.

**A4 — `spot_entries.py:144-156` — INFO — Sinal que chega sob kill switch bloqueado ganha linha `refused` e nunca é reavaliado (`NOT EXISTS … side='buy'`).** Conservador e correto (o sinal envelhece em 180 s de qualquer forma); registro apenas para que o `refused_by_reason.kill_switch_blocked` não seja lido como falha.

**Sem achados** em: idempotência (`spot_client_order_id(signal_id,'buy')` único parcial; `insert_order` `ON CONFLICT DO NOTHING` → `None` ⇒ retorno sem assinar, `spot_entries.py:238-239`; venda `(position_id, attempt)`, `spot_exits.py:217,227-228`); reinício (linhas `admitted`/`simulated` nunca são reexecutadas — nenhum caminho envia uma linha existente; `abandoned_orders` as marca `failed` após 300 s, `spot_reconcile.py:111-123`; a reserva vale enquanto isso, `spot_repo.py:153-157`); `EMERGENCY` + `MEME_AUTO_CLOSE_ON_EMERGENCY` vende (`spot_exit_rules.py:89-90`, `spot_exits.py:112-118`); `TRADING_DISABLED` não impede venda (`spot_send.py:201` só bloqueia `is_buy`); `sell_requested` via script com `system_events` (`spot_desk_markets.py:161-215`); geometria inválida recusada antes de abrir (`spot_signals.py:143-160`, `spot_entries.py:176-181`); reconcile só abre posição com `stop_frac>0` e `ticket>0` gravados na ordem (`spot_settle.py:118-124`), horizonte contado do `blockTime` (`:150-157`).

## Ordem de deploy e o que Everton confere (30 min após cada passo)

### Passo (a) — deploy inerte
`.env` da VPS: **nenhuma linha nova**. (Opcional, explícito: `SPOT1_ENABLED=false`.) Não mexer em `MEME_*`.
Comando: o `update` habitual com os mesmos perfis de hoje (`MEME_LIVE=1 MEME=1 MEME_ENABLED=true … bash infra/vps/compose.sh update`) — ele roda `migrate` **antes** do `up -d` (`compose.sh:242-243`). Não usar `restart`/`up` isolados antes do `migrate`.
Leituras (heartbeat, Redis): `HGET hb:meme:executor spot1` → `"mode":"inert:disabled"`, `"open":[]`, `"markets_enabled":null`; `HGET hb:meme:executor spot1_positions_open` → `0`; `HGET hb:meme:executor positions_open` inalterado; `rpc_errors` não subindo mais do que antes; `last_refusal` **não** pode ser `marks_incomplete`.
Leituras (psql):
```sql
SELECT version_num FROM alembic_version;                                     -- 0057_spot_desk
SELECT count(*) AS total, count(*) FILTER (WHERE enabled) AS ligados FROM spot_desk_markets;  -- 50 / 35
SELECT count(*) FROM spot_orders; SELECT count(*) FROM spot_positions;      -- 0 / 0
SELECT component, message, created_at FROM system_events WHERE component='spot_desk' ORDER BY created_at DESC LIMIT 5;  -- vazio
```
Painel: `/meme/mesa` → "Carteira real" mostra o bloco spot/1 com modo `inert:disabled`. Log: `meme_spot_config_invalid` **não** deve aparecer (nenhuma variável lida).

### Passo (b) — ligar com uma vaga
Pré-condição do próprio design §9(a): a ida-e-volta de 0,02 SOL com `meme_spot_swap.py --round-trip --apply` já conferida na Solscan.
`.env` (acrescentar exatamente):
```
SPOT1_ENABLED=true
SPOT1_MAX_OPEN=1
```
Conferir que `MEME_MAX_OPEN_POSITIONS` tem folga (a vaga é global: com 2 memes abertas a spot recusa `concurrent_positions`); `SPOT1_STRATEGY_VERSION` fica no padrão `v14`. Depois `compose.sh update` (ou só recriar o executor — 0057 já está aplicada).
Leituras (heartbeat, a cada 5 min):
- `spot1.mode` = `"on"`; `markets_enabled` = 35; `last_entries_tick_at`/`last_exits_tick_at` avançando (15 s / 20 s).
- `signals_seen`, `refused_by_reason` (esperado no começo: `parity_*`, `cost_above_r_cap`, `signal_stale`, `below_ticket:*` — nunca `marks_incomplete` persistente).
- Na 1.ª compra: `admitted=1`, `last_signature` preenchido, `buys_confirmed=1` **ou** `buys_unconfirmed=1` (então `reconciled_buys` deve virar 1 em ≤ 60 s); `spot1_positions_open=1`; `open[0].mark_sol` não nulo após ≤ 40 s, `r_now` entre −1 e +1,5, `mark_failures=0`, `exit_pending=false`, `blocked=false`.
- `blocked_exits` = `{}`; `tick_failures` = 0; `refutation.state` = `on`.
- **Não desligar a flag** enquanto `buys_unconfirmed>0` ou `open[].exit_pending=true` (A1); para parar entradas use `touch /opt/project-hunter/run/meme/meme.kill`.
Leituras (psql):
```sql
SELECT id, side, attempt, status, reason, tx_signature, received_at
  FROM spot_orders ORDER BY received_at DESC LIMIT 20;
SELECT id, market_symbol, status, sol_spent_lamports, mark_sol, mark_reason, mark_at,
       exit_intent->>'status' AS exit_pending, params->>'horizon_s' AS horizon_s, entry_at
  FROM spot_positions ORDER BY entry_at DESC;
-- após a venda: PnL ao lamport = fill da venda − gasto da compra
SELECT p.market_symbol, p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple,
       o.tx_signature AS sell_sig FROM spot_positions p JOIN spot_orders o ON o.id = p.exit_order_id
 WHERE p.status='closed' ORDER BY p.exit_at DESC LIMIT 5;
-- sinal de A2: vendas recusadas acumulando na mesma posição
SELECT position_id, count(*) FROM spot_orders WHERE side='sell' AND status IN ('refused','failed')
 GROUP BY position_id HAVING count(*) > 6;
```
Conferir a assinatura de compra e de venda na Solscan (delta de lamports bate com `fill.sol_delta_lamports`), gerar a ficha com `spot_ficha.py --position <id> --write`.

## Comandos e saída
```
$ timeout 590 uv run pytest services/meme-executor -q -p no:cacheprovider -m "not integration and not live and not live_devnet" -x
630 passed, 53 deselected in 7.23s
$ uv run python -c "…seed_rows()…"   → 50 35   (linhas semeadas / ligadas)
```
