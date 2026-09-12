# Contrato congelado — Lab meme contínuo (T4.6) × Mesa do operador (T4.7) — 12/09/2026 04:25 BRT

Everton (12/09 04:0x BRT): "já quero completamente funcional para operarmos; quero dar o aval da compra do meme, quanto de espera, vender; preciso o trader total funcionando". Dois agentes constroem em paralelo sem se falar; **este arquivo é o único acordo**. Quem precisar mudar algo escreve uma linha em "Emendas" no fim, nunca reescreve.

## Papéis
- **T4.6 (backend, `services/meme-worker/` + migração `0022_meme_lab`)** é dono das tabelas abaixo, do laço por minuto, do motor de papel (usa `hunter_indicators.meme` da T4.5) e de `GET /api/v1/orgs/{org}/meme/lab` (placar). Escreve como `hunter_worker`.
- **T4.7 (API + web, `apps/**`)** é dono das rotas de operador e da tela `/meme/mesa`. A API escreve **só** em `meme_proposals` (aprovar/recusar/criar manual) e `meme_operator_commands` (vender agora / cancelar), como `hunter_app` — a migração 0022 concede `INSERT` em `meme_proposals` e `meme_operator_commands` e `UPDATE` só em `meme_proposals` (colunas de decisão) ao `hunter_app`; tudo o mais é `SELECT`.
- Dinheiro real: **nenhum** nesta fatia. Toda aposta é papel (`mode = 'paper'`); a coluna existe para a T4.8 (caminho de assinatura) ligar depois, atrás de `ENABLE_MEME_LIVE_TRADING`, nunca por default.

## Tabelas (todas globais, sem RLS; horários `timestamptz` em UTC; dinheiro em `numeric(28,10)` SOL)

### `meme_rule_sets` — um conjunto de regras congelado
| coluna | tipo | nota |
|---|---|---|
| `id` | uuid PK | |
| `name`, `version` | text | `UNIQUE (name, version)`; ex.: `meme_paper_v0` / `1` (EXP-M1), `operator` / `1` |
| `kind` | text | `research_only` (o laço aprova sozinho, papel) \| `operator` (propõe e **espera o aval**) |
| `params` | jsonb | congelado no pré-registro: porta (idade, progresso, participação), tamanho `size_sol`, `target_x`, `trailing_pct`, `max_hold_s`, tetos da carteira (`wallet_max_sol`, `max_sol_per_bet`, `daily_loss_cap_sol`) |
| `code_ref` | text | módulo/função de `hunter_indicators.meme.rules` |
| `exp_ref` | text | `EXP-M1` etc. (nulo só para `operator`) |
| `status` | text | `active` \| `retired` |
| `created_at`, `retired_at` | timestamptz | |

### `meme_proposals` — uma intenção de compra (do laço ou do operador)
| coluna | tipo | nota |
|---|---|---|
| `id` | uuid PK (uuid7) | |
| `mint` | text | FK lógica para `meme_tokens.mint` |
| `rule_set_id` | uuid | FK `meme_rule_sets` |
| `origin` | text | `rules` (o laço) \| `operator` (manual: Everton colou o mint) |
| `status` | text | `proposed` → `approved` \| `rejected` \| `expired` → (`approved`) `filled` \| `unfilled` |
| `proposed_at` | timestamptz | |
| `expires_at` | timestamptz | `proposed_at + 120 s` por default (memes andam rápido); o laço marca `expired` |
| `features_end_time` | timestamptz | o minuto fechado que motivou (não-antecipação) |
| `quote` | jsonb | fotografia usada: reservas, `mcap_sol`, `curve_progress_pct`, `observed_at`, `source`, preço marginal, custo cotado para `size_sol` **com** taxa 1,75 % |
| `reasons` | jsonb | lista de features/regra que dispararam (ou `["operator_manual"]`) |
| `suggested` | jsonb | `{size_sol, target_x, trailing_pct, max_hold_s}` do conjunto |
| `decision` | jsonb | **escrito pela API** ao aprovar: `{size_sol, target_x, trailing_pct, max_hold_s, note}` — o operador pode mudar qualquer um; o laço aplica **os tetos do conjunto** por cima (recusa nomeada se exceder) |
| `decided_by` | text | `user_id` do Clerk (ou `rules` para research_only) |
| `decided_at` | timestamptz | |
| `bet_id` | uuid NULL | preenchido quando vira aposta |
| `refusal` | text NULL | motivo nomeado se `unfilled` (ex.: `no_later_snapshot`, `migrated_before_fill`, `exceeds_max_sol_per_bet`, `daily_loss_cap`) |

Índices: `(status, proposed_at DESC)`, `(mint, proposed_at DESC)`.

### `meme_operator_commands` — ordens do operador sobre uma aposta aberta
| coluna | tipo | nota |
|---|---|---|
| `id` | uuid PK | |
| `bet_id` | uuid | FK `meme_paper_bets` |
| `command` | text | `sell_now` \| `cancel` (cancelar só se `proposed`/`approved` ainda sem fill — aí o alvo é a proposta: coluna `proposal_id` alternativa, exatamente uma das duas não nula) |
| `proposal_id` | uuid NULL | ver acima |
| `issued_by`, `issued_at` | text, timestamptz | |
| `applied_at` | timestamptz NULL | o laço marca ao executar (venda na fotografia seguinte) |
| `result` | jsonb NULL | o que aconteceu (`{status, refusal}`) |

### `meme_paper_bets` — a aposta (papel), uma linha por entrada
| coluna | tipo | nota |
|---|---|---|
| `id` | uuid PK | |
| `proposal_id` | uuid | FK |
| `rule_set_id` | uuid | FK |
| `mint` | text | |
| `mode` | text | `paper` (único valor hoje) |
| `status` | text | `open` \| `closed` |
| `entry_at` | timestamptz | `observed_at` da fotografia de fill (estritamente posterior à decisão) |
| `entry` | jsonb | reservas, preço marginal, `sol_spent`, `fee_sol`, `tokens`, `fill_delay_snapshots`, `participation_pct` |
| `initial_risk_sol` | numeric | = `sol_spent` (RISK_ENGINE_MEME §5) |
| `params` | jsonb | os efetivamente aplicados (`target_x`, `trailing_pct`, `max_hold_s`, `size_sol`) |
| `exit_at` | timestamptz NULL | |
| `exit` | jsonb NULL | reservas, `sol_received`, `fee_sol`, `reason` (`target` \| `trailing` \| `time_stop` \| `migrated` \| `creator_dump` \| `sell_now` \| `rug_no_snapshot`) |
| `pnl_sol` | numeric NULL | líquido de taxas |
| `r_multiple` | numeric NULL | `pnl_sol / initial_risk_sol` |
| `mark_sol` | numeric NULL | última marca (posição aberta), pela última fotografia |
| `mark_at` | timestamptz NULL | |
| `high_water_x` | numeric NULL | para o trailing |
| `sol_usd_at_entry`, `sol_usd_at_exit` | numeric NULL | cotação observada (fonte + hora em `entry`/`exit` jsonb) |

Índices: `(status, entry_at DESC)`, `(rule_set_id, entry_at DESC)`, `(mint)`.

### Vistas para a API (criadas na 0022)
- `meme_lab_scoreboard_v1`: por `rule_set_id` × dia (Brasília = `date(entry_at AT TIME ZONE 'America/Sao_Paulo')`): apostas, fechadas, acertos (`pnl_sol > 0`), `sum(pnl_sol)`, `sum(r_multiple)`, `max drawdown` (aproximado por soma cumulativa ordenada por `exit_at`), rugs (`exit.reason = 'rug_no_snapshot'`).
- `meme_desk_v1`: `meme_proposals` JOIN `meme_tokens` (nome, símbolo, criador, `created_at`, mayhem) LEFT JOIN `meme_paper_bets` (status, `mark_sol`, `pnl_sol`, `r_multiple`) — a linha da mesa.

## Semântica do laço (T4.6) que a tela (T4.7) pode assumir
1. A cada minuto fechado: para cada `meme_rule_sets.status='active'`, avalia a porta sobre `meme_features_1m` (`end_time <= agora − 1 min`); dispara `meme_proposals` (`origin='rules'`). `research_only` → o próprio laço grava `decision = suggested`, `decided_by='rules'`, `status='approved'` no mesmo instante. `operator` → fica `proposed` até a API decidir ou `expires_at`.
2. Propostas `approved` (por quem for) são preenchidas **na fotografia seguinte** de `meme_curve_snapshots` (`observed_at > decided_at`); sem fotografia em 3 min → `unfilled` com `refusal`.
3. Aposta aberta: a cada fotografia nova, marca `mark_sol`, aplica saídas (`target_x`, `trailing_pct` a partir de `high_water_x`, `max_hold_s`, migração, `creator_dump` quando a feature existir) e **`sell_now`** pendente em `meme_operator_commands` — a venda também só na fotografia seguinte.
4. Tetos por conjunto (`params`): `wallet_max_sol` (saldo de papel inicial), `max_sol_per_bet`, `daily_loss_cap_sol` (perda realizada no dia Brasília); estourou → propostas do conjunto viram `unfilled` com `refusal='daily_loss_cap'` e a mesa mostra o motivo.
5. Nada de zero silencioso: quando o laço não roda (worker fora, feed fora), `GET /meme/lab` traz `sources` com `last_tick_at` e a mesa mostra "laço parado desde …".

## Rotas (T4.7, todas sob `/api/v1/orgs/{org_id}/meme`, VIEWER+ para GET, OPERATOR+ para POST — usar o papel já existente que hoje libera `order-requests`)
- `GET /desk?status=&limit=&cursor=` → linhas de `meme_desk_v1` (propostas abertas primeiro, depois apostas abertas, depois histórico).
- `POST /proposals/{id}/approve` body `{size_sol, target_x, trailing_pct, max_hold_s, note?}` → 200 com a proposta; 409 se não estiver `proposed`; 422 se exceder `max_sol_per_bet` do conjunto (recusa nomeada `exceeds_max_sol_per_bet`).
- `POST /proposals/{id}/reject` body `{note?}`.
- `POST /proposals/manual` body `{mint, size_sol, target_x, trailing_pct, max_hold_s, note?}` → cria `origin='operator'` já `approved` com `decision` = body, `rule_set = operator/1`; 422 se o mint não existir em `meme_tokens` ou já estiver `completed_at` não nulo (curva encerrada).
- `POST /bets/{id}/sell-now` → cria `meme_operator_commands(sell_now)`; 409 se a aposta não estiver `open`.
- `POST /proposals/{id}/cancel` → `meme_operator_commands(cancel)`; 409 se já `filled`.
- Idempotência: header `Idempotency-Key` obrigatório nos POST (mesmo padrão de `order-requests`).
- Auditoria: cada POST grava em `audit_logs` (ator, ação, alvo, corpo sem segredo).

## Tela `/meme/mesa` (T4.7; `docs/DESIGN.md`; mobile 375 primeiro)
- Faixa: saldo de papel por conjunto (SOL e US$ com cotação observada + hora), PnL do dia, laço vivo/parado.
- Lista "Propostas" com contagem regressiva até `expires_at`, motivo da proposta (features), cotação e custo com taxa; botões **Aprovar** (abre a folha com `size_sol`, `alvo (×)`, `trailing (%)`, `espera máx (s)` pré-preenchidos com `suggested`, editáveis) e **Recusar**.
- "Comprar manual": campo mint + os mesmos 4 parâmetros → `POST /proposals/manual`.
- "Abertas": marca ao vivo, PnL, R, tempo restante da espera, botão **Vender agora** (confirmação em 1 toque com o preço da última fotografia e o aviso "vende na próxima fotografia, não neste preço").
- "Fechadas hoje": lista com motivo de saída e PnL; link para `/meme/{mint}`.
- Rótulo permanente e visível: **"PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo"**.
- Estados honestos: sem proposta → "nenhuma proposta nos últimos N min (laço vivo)" ≠ "laço parado".

## Emendas
- T4.7 (12/09 ~05:15 BRT): `GET /desk` lê as tabelas base (`meme_proposals` JOIN `meme_tokens` LEFT JOIN `meme_paper_bets`, mais `meme_rule_sets`) em vez de `meme_desk_v1` — o contrato nomeia a vista mas não as colunas dela, e a mesa precisa de `entry`/`params`/`exit_at`/`exit` da aposta (espera restante, motivo de saída); a vista continua da T4.6, ninguém a altera.
- T4.7: chaves do `quote` jsonb que a mesa lê (e que `POST /proposals/manual` grava exatamente): `observed_at`, `source`, `mcap_sol`, `curve_progress_pct`, `price_sol_per_token`, `size_sol`, `fee_pct` (`1.75`), `fee_sol`, `cost_sol`, `tokens`, `reason` (`no_snapshot_yet` \| `unpriceable_reserves` \| null). Chave ausente aparece como "sem cotação"/`null` na tela, nunca inventada. `entry.sol_usd_source` / `exit.sol_usd_source` (texto) são lidos, se existirem, como fonte da cotação SOL/USD.
- T4.7: `POST /bets/{id}/sell-now` recusa com 409 `sell_now_already_pending` enquanto houver um `sell_now` com `applied_at IS NULL` na mesma aposta — o laço pode assumir no máximo um pendente por aposta. `POST /proposals/{id}/approve` recusa com 409 `expired` quando `now >= expires_at` mesmo que o laço ainda não tenha carimbado `expired`.
- T4.7: `Idempotency-Key` dos POST é lembrada no Redis (`idem:meme-desk:{org_id}:{sha256}`, 24 h, chave → entidade produzida + impressão do corpo), não em coluna — as tabelas do contrato não têm coluna de idempotência e a 0022 é da T4.6. Replay relê a entidade no Postgres; corpo diferente sob a mesma chave → 409 `idempotency-key-conflict`.
- T4.7: `decided_by`/`issued_by` recebem o id do usuário no Clerk (`principal.external_auth_id`), como o contrato diz; a linha de `audit_logs` usa o `users.id` interno como `actor_id` (convenção da `order-requests`).
- T4.6 (12/09 ~05:20 BRT), migração `0022_meme_lab`: (1) `meme_paper_bets.mode` tem `CHECK (mode = 'paper')` — a T4.8 acrescenta `'live'` com revisão própria; (2) `meme_paper_bets.exit_intent jsonb NULL` — a regra que disparou na fotografia k (`{reason, decided_at, snapshot_observed_at, trigger: rules|operator, command_id?}`) enquanto a venda espera a fotografia k+1; fica na linha depois do fechamento; (3) `meme_proposals.features_end_time` é NULL para `origin='operator'` (manual não nasce de um minuto fechado) e obrigatório para `origin='rules'`; índice único parcial `(rule_set_id, mint, features_end_time) WHERE origin='rules'` (idempotência do laço); (4) índices ascendentes em vez de `DESC` (mesmo plano, comparável pelo `alembic check`); (5) `meme_desk_v1` usa `LEFT JOIN meme_tokens` (a retenção de 90 d não pode sumir com a proposta da mesa); (6) `meme_lab_scoreboard_v1` traz também `pnl_usd` (só apostas com `sol_usd_at_exit`) e `unpriced_usd` (quantas não têm cotação), `r_sum`, `max_drawdown_sol` (magnitude ≥ 0; NULL sem fechadas) e `rule_set_status`; (7) `exit.reason` também pode ser `max_loss` (piso de perda de 50 % pré-registrado na EXP-M1) e `exit.trigger` diz `rules`|`operator`; conclusão da curva (`complete=true`) fecha como `migrated`; (8) vocabulário de `refusal`: `no_later_snapshot`, `fill_not_after_intent`, `migrated_before_fill`, `curve_complete`, `exceeds_max_sol_per_bet`, `size_not_positive`, `daily_loss_cap`, `max_open_positions`, `exposure_per_mint_cap`, `wallet_balance_insufficient`, `insufficient_curve_reserves`, `rule_set_inactive`; (9) `rug_no_snapshot` = a saída (regra ou `sell_now`) não achou fotografia posterior em 3 min → fecha com `sol_received = 0`, `pnl = −sol_spent`, R = −1, `exit.pending_reason` diz a regra que esperava (doutrina §5: o resultado plausível de uma compra na curva é −100 %); aposta sem fotografia nenhuma por `max_hold_s` + 3 min fecha igual com `pending_reason='time_stop'`; (10) `meme_operator_commands.result`: `{status: applied, exit_reason}` quando a venda foi pela ordem, `{status: superseded, exit_reason}` quando outra regra vendeu antes, `{status: refused, refusal: bet_not_open}`; `cancel` → proposta `rejected` com `decided_by = issued_by` se ainda não decidida e `decision || {cancelled_by, command_id}`, ou `{status: refused, refusal: proposal_<status>}`; (11) `quote` do laço grava exatamente as chaves da emenda da T4.7 (`price_sol_per_token`, `cost_sol`, `reason: null`, …) mais as reservas; `entry`/`exit` carregam `sol_usd` (objeto: `price_usd`, `source`, `as_of`, `observed_at`, `stale`), `sol_usd_source` (texto) e `sol_usd_reason` quando não há cotação; (12) heartbeat: campos `lab_*` na hash `hb:meme:radar` (`lab_last_tick_at`, `lab_tick_minute`, `lab_gate_refusals` json por conjunto, `lab_proposals_total`, `lab_fills_total`, `lab_unfilled_total`, `lab_closes_total`, `lab_bets_open`, `lab_sol_usd`, `lab_sol_usd_observed_at`, `lab_sol_usd_source`, `lab_enabled`); `GET /meme/lab` traz `sources.lab_status` ∈ {alive, stalled, never, disabled, heartbeat_missing, redis_unavailable} — "laço parado desde …" é `stalled` com `lab_last_tick_at`; (13) hoje o portão congelado da EXP-M1 recusa toda linha por `creator_net_seller_unknown` e `curve_volume_1m_unknown` (não há leitor de holders nem feed de trades — DATABASE.md §33.5): o laço conta as recusas em `lab_gate_refusals`, e a mesa recebe propostas do laço só quando essas fontes existirem; até lá a compra é `POST /proposals/manual`.
