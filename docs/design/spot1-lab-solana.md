# Mesa `spot/1` — sinal do Lab (Binance) executado na Solana pela carteira do robô (T4.74)

**Decisão de origem:** Everton, 19/09/2026 10:2x–10:3x BRT (`obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md`,
último adendo): "quero ir no dinheiro real e testar no real mesmo". Aprendizado com perda aceita, mesma régua da mesa de memes.
**Insumos:** R63 (`.claude/state/notes-R63.md` §2a/§3a/§6), T4.73 + revisão (`notes-T4.73.md`, `review-T4.73.md`; T4.73b em
curso no caminho de envio do script), T4.72 (sinais/admissão em papel), `docs/RISK_ENGINE_MEME.md` §3/§5/§7/§16/§18.
**Status:** desenho; nada aqui liga dinheiro. `SPOT1_ENABLED` nasce `false`.

## 0. Resumo em cinco linhas
1. Uma **pista nova dentro do `meme-executor`** (`spot_*.py`), como a pista de lançamento (T4.67b): mesma chave, mesmo
   kill switch, mesma âncora do dia, mesmos cinco `MEME_*`. Nenhum serviço novo.
2. Fonte: linhas de `agent_signals` da `mean_reversion` **v14** (padrão), `long`, em mercados do mapa R63 guardado em
   banco (`spot_desk_markets`, migração `0057`), com paridade Jupiter × Binance ≤ 3 % **na hora da decisão**.
3. Ficha fixa **0,05 SOL** (clampada por `MEME_MAX_SOL_PER_TRADE` e pelo escopo), 1 posição por mercado, ≤ 3 abertas na
   mesa, contando nas mesmas vagas e no mesmo cap diário das memes; `binding_constraint` gravado.
4. Saída pela geometria do próprio sinal (stop 1,5 ATR / alvo 2,25 ATR = 1,5 R / 4 h) avaliada sobre a **cotação Jupiter
   do nosso lote** a cada 20 s; venda pelo mesmo primitivo verificar→simular→assinar→enviar; pânico a 3 %.
5. Refutação dura no código: 20 operações fechadas com expectância ≤ 0 R **ou** Σ PnL ≤ −0,15 SOL ⇒ entradas recusadas
   `spot1_refuted` até uma linha nova do Everton no `.env`.

## 1. Onde roda — pista no `meme-executor` (rejeitado: serviço novo)
**Escolha:** três tarefas novas no mesmo `TaskGroup` de `main.py` (`spot-entries` 15 s — polling simples, sem o `wake`;
`spot-exits` `SPOT1_MARK_S` = 20 s; `spot-reconcile` cavalga no `reconcile` de 30 s). Reaproveita de
`ExecutorContext`: `signer` (único objeto que assina no processo), `chain` (RPC), `kill` (`meme_live_kill_switch`
escopo `wallet` + `meme:kill` Redis + `meme.kill` arquivo + `SYSTEM_KILL_SWITCH`), `wallet_refresh_once`,
`ensure_anchor`/`treasury_inflow` (perda do dia com entrada da tesouraria), `config.limits` (`MemeLimits`),
`treasury_client` (`JupiterClient`), `priority_fees`, `spot_verify.verify_spot_swap_tx`, `treasury_rules.classify_submitted`.
**Por que não um `spot-executor`:** precisaria de uma **segunda cópia da chave** em outro processo, um segundo leitor de
kill switch, uma segunda âncora do dia e um segundo cálculo de `daily_loss` sobre a mesma carteira — dois freios que
não se veem (uma compra de 0,05 na mesa spot apareceria como "perda" de 0,05 no executor de memes e vice-versa). A pista
custa ~1 200 linhas novas em módulos ≤ 350 e zero superfície de deploy nova.
**Consequência declarada:** o executor continua sendo o único processo com a chave; tudo que assina passa pela revisão
do risk-engine-guardian antes de subir (regra do dia, 19/09).

## 2. Fonte do sinal e o mapa
**Consulta (`spot_signals.py`, um `SELECT` limitado por tique):** `agent_signals s JOIN strategy_versions v JOIN strategies
st` com `st.key = 'mean_reversion' AND v.version = :ver AND s.direction = 'long' AND s.status = 'active' AND
s.emitted_at ≥ now − SPOT1_MAX_SIGNAL_AGE_S (180 s) AND s.expires_at > now`, `LEFT JOIN signal_outcomes o` (para
`meta->>'reference_price'`), `JOIN markets m ON s.market_id = m.id`, `JOIN spot_desk_markets d ON d.binance_symbol =
m.symbol AND d.enabled`, `NOT EXISTS spot_orders WHERE signal_id = s.id AND side = 'buy'`. Ordem: `emitted_at DESC`,
**no máximo 1 compra por tique**.
**Versão padrão `SPOT1_STRATEGY_VERSION = v14`.** É a linha `paper` da `v6` (criada por `--paper-line`, T3.61; mesmos
parâmetros: stop 1,5 ATR, alvo 2,25 ATR, horizonte 14 400 s), Σ R **+14,90** em 23 sinais (15 alvos / 4 stops) nos 10
mercados executáveis nos 7 dias do R63 §3a — e é a única versão da `mean_reversion` que o caminho de papel auditado
(T4.72, `agents`) pode operar em paralelo, dando o contraste papel × real na **mesma** versão.
Rejeitadas: `momentum v3` (223 sinais, Σ R −42,9, negativa em 9 de 10 mercados); `v7` (+12,6, só 2 stops, mas stop de
2 ATR = perda 33 % maior em SOL por ficha e menos sinais); `mean_reversion_h1 v1` (9 sinais).
**Mapa em banco, não JSON (rejeitado: JSON no repo).** `spot_desk_markets` semeada pela `0057` a partir da constante
`ddl/spot_desk_seed.py` (R63 §2a, 52 − `SOLUSDT` (comprar SOL com SOL não é posição) − `ENAUSDT` (1,02 % ida-e-volta)
= **50 linhas**): `binance_symbol` (único), `base`, `mint`, `units_per_binance_unit` (1000 para `1000BONK`/`1000PEPE`),
`kind` (`nativo`/`ponte`/`representacao`), `tier`, `liquidity_usd_at_seed`, `round_trip_cost_pct_at_seed`, `decimals`
(NULL; o executor lê o mint uma vez por RPC e grava), `enabled`, `note`, `updated_at`, `updated_by`. **Sem FK para
`markets`** (a semente tem de plantar em banco vazio; o `JOIN` é por símbolo, como o R63 fez). `enabled` na semente =
`tier ≠ 'C' AND custo ≤ 0,4 %` (R63 §5.5: representações de 40–75 k US$ com emissor não identificado ficam fora até
alguém ligar — `SUIUSDT`, `AVAXUSDT`, `STRKUSDT`, `CAKEUSDT`, `GALAUSDT`, `CHZUSDT`, `MEGAUSDT`, `WLFIUSDT`, `GRASSUSDT`,
`DRIFTUSDT`; `VIRTUALUSDT` 0,60 % também). Editar é `infra/scripts/spot_desk_markets.py --enable/--disable/--set-mint
--reason` (dry-run padrão, `--apply`, linha em `system_events` componente `spot_desk`), nunca a mão no banco.
Motivo do banco: auditável (`system_events`), editável na VPS sem deploy, e a posição aberta referencia a linha que
a comprou (`spot_positions.market_symbol`); um JSON no repo exigiria deploy para trocar um mint e não teria histórico.
**Paridade na decisão (check `parity`):** `bin_usd` = último fechamento **final** de 1 m do mercado (`candles`),
`sol_usd` = idem `SOLUSDT`, ambos com `close_time ≥ now − 180 s`, senão `market_price_unavailable`/`sol_usd_unavailable`
(nunca zero). `jup_usd = ticket_sol × sol_usd ÷ (out_amount ÷ 10^decimals) × units_per_binance_unit`; recusa
`parity_above_cap` se `|jup_usd ÷ bin_usd − 1| > SPOT1_MAX_PARITY_PCT` (3 %). É o filtro que separou 54 homônimos
falsos no R63 — aqui protege contra um mint trocado no mapa e contra desancoragem de ponte/representação.

## 3. Sizing — ficha fixa ou nada
`ticket = min(SPOT1_TICKET_SOL 0,05; limits.max_sol_per_trade; gates.small_test.max_sol_per_trade)`. Tetos (os de §5 do
motor, mesma ordem e mesmo `MemeSizing`/`LimitCap`): `trade_cap`, `daily_cap` (= cap − perda do dia − Σ gasto das
posições abertas **memes + lançamento + spot**, porque a perda plausível de uma compra é o gasto inteiro — §5), `wallet_cap`,
`available` (saldo − rent de ATA 0,00204 − 2 × priority fee − reservas). Se `min(tetos) < ticket` ⇒ recusa
`below_ticket:<binding_constraint>` — a mesa **não** opera ficha parcial (a geometria do sinal foi medida a tamanho fixo e
os custos fixos por operação não encolhem). `binding_constraint` vai em `spot_orders.admission.sizing`, sempre.
**Vagas:** `SPOT1_MAX_OPEN` = 3 (check `spot1_open_cap`, só posições `lane = spot`), `duplicate_market` (1 por mercado,
posição aberta **ou** compra pendente), e o **global** `MEME_MAX_OPEN_POSITIONS` conta memes + lançamento + spot
(`hunter_risk_meme.checks_wallet.concurrent_positions_check` sobre `MemeWalletState.positions`, que a pista passa a
preencher com as suas). Consequência para o Everton: com `MEME_MAX_OPEN_POSITIONS=2` hoje, a mesa spot disputa as duas
vagas com as memes; para ter 3 + 2 ele sobe para 5 no `.env` — é a única forma de "um freio só" ser verdade.
**Custo em R (check `cost_r`, novo; T4.74-2):** `est_cost_sol = 2 × (priority_fee_sol + taxa_de_rede_sol) + ticket ×
(2 × impacto_da_cotação + 0,003)`; `r_unit_sol = ticket × stop_frac`; recusa `cost_above_r_cap` se `est_cost_sol ÷
r_unit_sol > SPOT1_MAX_COST_R` (0,5). **Honestidade sobre 0,05 SOL:** com stop de 1–2,5 % o R vale 0,0005–0,00125 SOL; a
taxa de prioridade "auto" da Jupiter pode chegar a 0,005 SOL (4–10 R!). Por isso a pista **capa a prioridade** em
`SPOT1_PRIORITY_FEE_MAX_LAMPORTS` = **100 000** (0,0001 SOL/perna; pools fundas não disputam bloco — com 200 000 e stop
de 2 % o check dá 0,66 R e recusa) e ainda assim o custo fixo fica em 0,3–0,5 R por operação.
A ficha 0,05 é tamanho de **encanamento**; a leitura de expectância tem de ser publicada em `R_bruto` (antes das taxas
de rede) **e** `R_líquido`. Subir para ≥ 0,15 SOL depois de 5 operações limpas é decisão dele, registrada como sugestão.

## 4. Saídas — a regra do sinal, avaliada na Jupiter
**Geometria gravada na entrada** (`spot_positions.params`): `ref` = `signal_outcomes.meta.reference_price` (fallback
`supporting_features.features.close_15m`), `stop_frac = (ref − stop)/ref`, `target_frac = (targets[0] − ref)/ref`,
`horizon_s = min(expected_holding_s, SPOT1_MAX_HOLD_S 14 400)`, `entry_sol_per_atom = sol_spent ÷ tokens`, `r_unit_sol`,
`sol_usd_at_entry`, `bin_usd_at_entry`, `jup_usd_at_entry`. `geometry_invalid` recusa se `stop_frac ≤ 0` ou `target_frac ≤ 0`.
**Marca (`spot_exits.py`, a cada `SPOT1_MARK_S` = 20 s, ≤ 3 posições ⇒ ≤ 9 `GET /quote`/min):** `mark_sol = out_amount`
da cotação **token → SOL do lote inteiro** (`slippageBps` 50) — "o que uma venda completa rende agora", mesma doutrina da
marca de memes (§6), `mark_source = 'jupiter_quote'`. `r_now = (mark_sol − sol_spent) ÷ r_unit_sol`. Cotação falha ⇒ marca
antiga fica, `mark_reason = quote_failed:<tipo>`, `blocked_exits` não; três falhas seguidas ⇒ heartbeat `spot1.mark_stale_s`.
**Regras, nesta ordem:** `emergency` (kill switch `EMERGENCY` + `MEME_AUTO_CLOSE_ON_EMERGENCY`), `sell_requested`
(`sell_requested_at` gravado pelo script `spot_desk_markets.py --sell-now <id> --reason`, coluna que `hunter_app` também
pode escrever — botão fica para depois), `stop` (`r_now ≤ −1`), `target` (`r_now ≥ target_frac ÷ stop_frac`, 1,5 R),
`time` (`now − entry_at ≥ horizon_s`). **Sem trailing** na v1: o sinal não tem e pôr um mudaria a regra medida (EXP depois).
Um `TRADING_DISABLED`/`WARNING` **não** impede saída (saídas sempre permitidas, §6).
**Venda:** mesmo primitivo da compra (`spot_send.spot_leg`, §5.1) com `input_mint = mint`, `amount = tokens` (o lote
inteiro; nunca parcial), `slippage_bps = SPOT1_EXIT_SLIPPAGE_BPS` 50. **Falha:** cada tentativa é uma linha
`spot_orders` (`attempt` n) — nunca re-assina os mesmos bytes; recotação a cada tentativa; backoff `(2,4,8,16,32,60) s`
(`exit_common.BACKOFF_S`); a partir da 3.ª tentativa, ou desde a 1.ª quando o motivo é `stop`/`emergency`, usa
`SPOT1_PANIC_SLIPPAGE_BPS` = 300 (3 %); após 6 falhas a posição entra em `blocked_exits[id] = motivo` (heartbeat,
painel), continua marcada, e a venda manual é `meme_spot_swap.py --from <mint> --to SOL` (T4.73). `pending` ao fim dos
20 s ⇒ ordem `submitted_unconfirmed`, posição intacta, `reconcile` liquida pela assinatura; nunca `confirmed` sem fill.
**Deriva SOL/USD:** stop/alvo em SOL por token embutem o movimento do próprio SOL em 4 h; aceito porque PnL, cap diário e
carteira são em SOL; `sol_usd_at_entry/exit` ficam gravados para a análise separar as duas coisas.
**Rent de ATA:** a venda pela Jupiter não fecha a ATA do token (o verificador só aceita `CloseAccount` da WSOL própria):
0,00204 SOL fica preso por mint (≤ 50 mints = 0,10 SOL, recuperável à mão); `ata_rent_lamports` gravado na posição e
**não** entra no `pnl_sol` — declarado, não escondido.

## 5. Persistência — tabelas próprias (rejeitado: `meme_live_*` com discriminador)
**`0057_spot_desk`** (`revises 0056_meme_spot_swaps`; `HEAD_REVISION` do `test_migrations.py` → `0057_spot_desk`;
DDL em `ddl/spot_desk.py` + semente `ddl/spot_desk_seed.py`; ORM `hunter_core/db/models/spot_desk.py`).
- `spot_desk_markets` (§2).
- `spot_orders`: forma da `meme_live_orders` (mesmos rótulos de `status`, mesmos CHECKs "recusa nomeia motivo",
  "confirmada carrega fill e assinatura", "enviada tem assinatura", `attempt ≥ 1`, `client_order_id` único), mais
  `desk text NOT NULL DEFAULT 'spot/1'`, `signal_id uuid NOT NULL REFERENCES agent_signals(id)` (único parcial para
  `side = 'buy'`), `position_id uuid NULL REFERENCES spot_positions(id)` (vendas), `market_symbol`, `mint`,
  `quote jsonb` (a cotação que gerou a tx), `tx_signature` único parcial. `fill` = deltas reais (lamports da carteira e
  atoms da ATA, antes/depois, lidos da cadeia após `confirmed`), nunca a cotação.
- `spot_positions`: forma da `meme_live_positions` (`status`, `entry_at`, `tokens`, `sol_spent_lamports`,
  `initial_risk_sol` = `r_unit_sol` — o R da linha é R de verdade —, `params`, `mark_sol/mark_at/mark_source/mark_reason`,
  `high_water_sol`, `exit_intent`, `sell_requested_at/by`, `exit_order_id`, `exit_at`, `exit`, `sol_received_lamports`,
  `pnl_sol`, `r_multiple`) com `signal_id` único, `market_symbol`, `mint`, `ata_rent_lamports`, `mark_source IN
  ('jupiter_quote')`, mesmos CHECKs "saída carrega os números", "marca diz quando e de onde", "pedido de venda diz quem".
- Grants (forma da `0028`): `hunter_worker` SELECT/INSERT/UPDATE nas três; `hunter_app` SELECT nas três + UPDATE
  (`sell_requested_at`, `sell_requested_by`) em `spot_positions`. Globais, sem RLS, sem partição.
- **Downgrade (§17.7):** recusa com `RAISE EXCEPTION` + `HINT` de `COPY` enquanto `spot_orders` tiver linha com
  `tx_signature IS NOT NULL` ou qualquer linha em `spot_positions` (uma transação real perderia o seu livro-razão;
  T4.74-1: `LOCK TABLE … ACCESS EXCLUSIVE` antes de contar); limpo, derruba `spot_positions`, `spot_orders`,
  `spot_desk_markets`, nesta ordem (a FK `entry_order_id` obriga).
**Por que não reaproveitar `meme_live_*`:** `meme_live_orders.proposal_id` é `NOT NULL` FK para `meme_proposals`, que
exige `rule_set_id` e `origin IN ('rules','operator')` — cada sinal viraria uma proposta sintética que o laço de papel,
`/meme/mesa`, `meme_close_day.py`, `wallet-summary` e o fechamento diário contariam como aposta de meme;
`mark_source` tem CHECK de fontes de curva; `migrated`/`creator_*` não fazem sentido. E `meme_treasury_swaps` é
auditoria de troca, não livro de posição (sem par entrada/saída, sem R).

### 5.1 O primitivo `spot_leg` (assinatura fixa para as tarefas 4 e 5)
`async def spot_leg(ctx, *, order_id, input_mint, output_mint, amount_atoms, slippage_bps, max_priority_fee_lamports)
-> LegResult(status: 'refused'|'failed'|'submitted_unconfirmed'|'confirmed', reason, signature, filled_atoms,
sol_delta_lamports, quote)`. Espelha `treasury_send.attempt_swap` (já correto nos três pontos que a revisão da T4.73
bloqueou: lê `simulation.accounts` para o invariante, `pending` fica `submitted`, uma escrita de banco por passo), com
`verify_spot_swap_tx(SpotSwapIntent(...))`, recusa `priority_fee_above_cap` se `verified.priority_fee_lamports >
max_priority_fee_lamports` (sem tocar `spot_verify.py`, que a T4.73b está editando), simulação com `accounts =
(carteira, ATA do token)` e invariante `simulation_token_short`/`simulation_sol_short`, kill switch relido **entre a
admissão e a assinatura**, `signer.sign` só aqui. `JupiterClient.swap` ganha `max_priority_fee_lamports: int | None`
(padrão `None` = `"auto"`, comportamento da tesouraria intacto) que envia `prioritizationFeeLamports:
{"priorityLevelWithMaxLamports": {"maxLamports": N, "priorityLevel": "medium"}}`.

## 6. Flags e o que nunca liga sozinho
| Variável | Padrão | Nota |
|---|---|---|
| `SPOT1_ENABLED` | `false` | lida só com `ENABLE_MEME_LIVE_TRADING` ligada e signer presente; senão `spot1.mode = inert:<motivo>` |
| `SPOT1_STRATEGY_VERSION` | `v14` | qualquer versão de `mean_reversion`; outra estratégia = boot recusa `spot1_strategy_unsupported` |
| `SPOT1_TICKET_SOL` / `SPOT1_MAX_OPEN` | `0.05` / `3` | ficha clampada por `MEME_MAX_SOL_PER_TRADE` e pelo escopo |
| `SPOT1_MAX_SIGNAL_AGE_S` / `SPOT1_MAX_HOLD_S` | `180` / `14400` | `max_entry_delay_s` do sinal (120) + uma vela |
| `SPOT1_MAX_PARITY_PCT` / `SPOT1_MAX_IMPACT_PCT` / `SPOT1_MAX_COST_R` | `3` / `0.5` / `0.5` | checks §2–§3 |
| `SPOT1_MARK_S` / `SPOT1_EXIT_SLIPPAGE_BPS` / `SPOT1_PANIC_SLIPPAGE_BPS` | `20` / `50` / `300` | §4 |
| `SPOT1_PRIORITY_FEE_MAX_LAMPORTS` | `100000` | por perna; o verificador confere `limit × price` (T4.74-2: 200 000 estourava `cost_r` a 0,05 SOL) |
| `SPOT1_REFUTE_MIN_TRADES` / `SPOT1_REFUTE_MAX_LOSS_SOL` / `SPOT1_CONSECUTIVE_STOPS_PAUSE_S` | `20` / `0.15` / `7200` | §8 |
| `SPOT1_REFUTATION_RESET_AT` | vazio | ISO; só operações fechadas depois disto contam — a "assinatura" dele para reabrir |
Valores fora de faixa caem no padrão com aviso (padrão `launch_config.py`). Estágio 1 = **sem clique**, como
`MEME_LIVE_AUTO_APPROVE`: o sinal é a proposta; `spot_orders.admission.decided_by = 'executor:spot1_auto'`. O escopo do
`meme_gates.json` vale (`max_sol_per_trade` clampa a ficha); `max_total_sol` (10 SOL) e `max_trades` (1000) não mordem
hoje — consequência declarada, não somamos gasto spot ao escopo. Desligar: `SPOT1_ENABLED=false` + `update`, ou
`touch /opt/project-hunter/run/meme/meme.kill` (entradas param em ≤ 10 s; `EMERGENCY` vende se a flag de fechar existir).

## 7. Observabilidade
**Heartbeat `hb:meme:executor`, campo JSON `spot1`:** `mode` (`on`/`inert:<motivo>`/`refuted`/`cooldown`),
`strategy_version`, `ticket_sol`, `max_open`, `markets_enabled`, `open` (≤ 3: `market`, `mint8`, `entry_at`, `sol_spent`,
`mark_sol`, `r_now`, `age_s`, `horizon_s`, `mark_stale_s`), `signals_seen`, `admitted`, `refused_by_reason` (top 8),
`exits_by_reason`, `blocked_exits`, `closed` (n, `sum_r_gross`, `sum_r_net`, `sum_pnl_sol`, `expectancy_r_net`),
`refutation` (`trades`, `threshold`, `state`), `last_signature`, `last_refusal`, `last_entries_tick_at`,
`last_exits_tick_at`. `equity_sol`/`daily_loss_sol` passam a incluir as marcas spot (§3). `positions_open` continua só
memes; `spot1_positions_open` separado.
**Painel mínimo:** `LiveExecutorOut.spot1: dict | None` na API (`schemas/meme_live.py` + `services/meme_live.py`) e um
`spot1-panel.tsx` dentro de "Carteira real" em `/meme/mesa`: modo, tabela das abertas com R agora, fechadas/Σ R/PnL,
medidor de refutação, última recusa. Sem página nova, sem POST (venda manual pelo script, §4).
**Ficha por operação no vault:** `infra/scripts/spot_ficha.py --position <id>` (dry-run; `--write`) gera
`obsidian/03-TRADING/Spot/Ficha-<AAAA-MM-DD>-<SÍMBOLO>-<id8>.md` (sinal, geometria, cotações de entrada/saída,
assinaturas, paridade, SOL/USD, custo em R, R bruto/líquido, campo "lição") e acrescenta uma linha ao placar
`obsidian/03-TRADING/Spot/Mesa-spot-1.md` (idempotente por marcador `<id8>`). Regra do Everton (18/09): cada compra real
vira ficha no mesmo dia.

## 8. Evidência honesta e regra de refutação
A vantagem da v14 é **23 sinais em 7 dias, 4 mercados** (UNI responde por 6,9 dos 14,9 R), com resultado sombra sobre
velas de 1 m da Binance e custo assumido de 11 bp; a mesa real paga 0,14–0,4 % de ida-e-volta, +9 bp de prêmio da
cotação (R63 §7), taxas de rede (0,3–0,7 R a 0,05 SOL) e a latência de pouso (1,6 s mediana). A taxa de acerto de
empate sobe de 40 % (1,5 R sem custo) para ~52 % com 0,3 R de custo; o papel mostra 65 % (15/23) — fino. Expectativa
honesta para 20 operações a 0,05 SOL: **−0,02 a +0,02 SOL**, e a leitura útil é o `R_net` médio, não o SOL.
**Parada dura (código, não prosa):** ao fim de cada saída confirmada, com `n ≥ SPOT1_REFUTE_MIN_TRADES` (20) e
`expectancy_r_net ≤ 0`, **ou** a qualquer momento com `Σ pnl_sol ≤ −SPOT1_REFUTE_MAX_LOSS_SOL` (0,15), a pista entra em
`refuted`: entradas recusam `spot1_refuted`, saídas continuam, heartbeat e painel mostram; reabrir exige
`SPOT1_REFUTATION_RESET_AT` ou `SPOT1_STRATEGY_VERSION` novos no `.env` dele. **Pausa de qualidade:** 3 stops seguidos ⇒
`cooldown` por `SPOT1_CONSECUTIVE_STOPS_PAUSE_S` (2 h). Nada disto é fim do programa; é o freio que a decisão de 18/09 pediu.

## 9. Plano de testes, revisão e prova ao vivo
**Testes (só fakes, sem rede):** `FakeChain`/`FakeRpc`/`FakeJupiter`/`FakeKill`/`FakeSigner` de `test_treasury_tick.py`;
sinais sintéticos; tabela de casos por check (cada recusa nomeada aparece uma vez); `spot_leg` com simulação aceita,
`simulation_token_short`, `pending` → `submitted_unconfirmed` (nunca `confirmed`), `priority_fee_above_cap`; regras de
saída puras (`target`/`stop`/`time`/`emergency`/`sell_requested`, empate `emergency` primeiro); refutação (19 → 20
operações, Σ perda); paridade indisponível ⇒ recusa; brake: uma posição spot aberta reduz `daily_cap` e ocupa vaga global;
migração `0057` (testcontainers, `-m integration`, upgrade/downgrade/recusa do downgrade com assinatura).
**O guardião do motor de risco revisa, item a item:** (1) `signer.sign` só em `spot_leg`, depois de `verify` e da
simulação com invariante lido de `simulation.accounts`; (2) kill switch relido entre admissão e assinatura; (3) ficha
clampada por `max_sol_per_trade` e escopo; (4) posições spot dentro de `MemeWalletState` (equity, cap diário, vagas);
(5) `pending` nunca vira `confirmed`; uma assinatura por linha; (6) nenhuma leitura de `.env` fora de `spot_config`;
(7) prioridade capada; (8) `SPOT1_ENABLED=false` ⇒ zero consultas, zero cotações; (9) refutação inescapável sem `.env`;
(10) `Decimal` em toda quantia, atoms inteiros. Depois: revisão do Codex do diff inteiro.
**Prova ao vivo, nesta ordem, cada passo é do Everton:** (a) T4.73b fechada e re-revisada → ida-e-volta de **0,02 SOL**
com `meme_spot_swap.py --round-trip --apply` (SOL→WIF→SOL), conferida na Solscan e em `meme_treasury_swaps`; (b) deploy
da T4.74 com `SPOT1_ENABLED=false`: heartbeat `spot1.mode = inert:disabled`, `0057` aplicada, 50 linhas no mapa, painel
renderiza; (c) `SPOT1_ENABLED=true`, `SPOT1_MAX_OPEN=1` → **1 operação real por sinal**: linhas `spot_orders` (buy +
sell), posição fechada, PnL batendo ao lamport com a cadeia, ficha no vault; (d) `SPOT1_MAX_OPEN=3` → 20 operações →
veredito da refutação e balanço papel (T4.72 §8a ligado na v14) × real, na mesma versão.
