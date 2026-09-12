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
(nenhuma)
