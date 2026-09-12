# T4.6 — o Lab meme contínuo: propostas, fills na fotografia seguinte, marcas e saídas em papel (migração `0022_meme_lab`)

Execução de 12/09/2026, das ~04:5x às ~05:4x BRT (UTC−3). Papel: backend-specialist.
Sem commit (o orquestrador commita por pathspec). Contrato obedecido:
`.claude/state/contrato-T4.6-T4.7-mesa-meme.md` — 13 emendas da T4.6 acrescentadas na seção
"Emendas" (nunca reescrevi nada; as 5 emendas da T4.7 já estavam lá quando reli o arquivo e
alinhei as chaves de `quote`/`entry`/`exit` a elas).

## Arquivos

**Criados**
- `infra/migrations/versions/0022_meme_lab.py`, `infra/migrations/ddl/meme_lab.py` (tabelas, índices, grants, drop), `infra/migrations/ddl/meme_lab_views.py` (vistas, seed dos dois conjuntos, guarda de downgrade)
- `packages/core/hunter_core/db/models/meme_lab.py` (`MemeRuleSet`, `MemeProposal`, `MemePaperBet`, `MemeOperatorCommand`)
- `packages/exchange-adapters/tests/fixtures/pumpfun/sol_price_raw.json` (captura do plantão, 12/09 02:34 BRT)
- `services/meme-worker/hunter_meme_worker/{lab.py, lab_bets.py, lab_models.py, lab_repo.py, lab_repo_bets.py, lab_rows.py, paper_engine.py, proposals.py}`
- `services/meme-worker/tests/{test_paper_engine.py, test_proposals.py, test_lab_persistence.py}`
- `apps/api/hunter_api/{routers/meme_lab.py, services/meme_lab.py, services/meme_lab_goal.py, repositories/meme_lab.py, schemas/meme_lab.py}`, `apps/api/tests/unit/test_meme_lab_service.py`
- `infra/scripts/meme_diary.py`, `infra/scripts/meme_diary_render.py`, `infra/scripts/tests/test_meme_diary.py`

**Modificados**
- `packages/core/hunter_core/db/models/__init__.py` (registro dos 4 modelos)
- `packages/exchange-adapters/hunter_exchanges/pumpfun/models.py` (`NormalizedSolPrice`), `.../rest.py` (`get_sol_price`), `packages/exchange-adapters/tests/unit/test_pumpfun_clients.py` (+3 testes)
- `services/meme-worker/hunter_meme_worker/main.py` (quinta cadência `lab`, cliente `/sol-price` com bucket próprio de 50/min, heartbeat `lab_*`, detalhe `lab` no readiness), `config.py` (`MEME_LAB_ENABLED` e cadências do Lab), `collect.py` (`forever` genérico no tipo do contexto), `README.md`
- `apps/api/hunter_api/app.py` (registro do router `meme_lab`)
- `packages/core/tests/integration/test_migrations.py` (HEAD → `0022_meme_lab`; testes da 0021 posicionam em `0021_meme_radar` antes de reverter; +5 testes da 0022), `test_schema_privileges.py` (3 classes novas de `hunter_app` na união; +2 sondas como o papel)
- `docs/DATABASE.md` §34, `docs/plans/T4-MEME-RADAR.md` §T4.6, `docs/PIPELINE.md` §1e, `docs/DEPLOYMENT.md` §3.6 + linha `MEME_LAB_ENABLED`
- `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` (Emendas da T4.6)

**Não toquei**: `apps/web/**`, `apps/api/hunter_api/{routers/meme_desk.py, services/meme_desk*.py, repositories/meme_desk*.py}` (T4.7), `docs/DESIGN.md` e `packages/shared-types/src/generated/api.d.ts` (já estavam modificados na árvore antes de mim — não são meus).

## Decisões que vale registrar

1. **Laço no próprio `meme-worker`** (`lab.py`), sem serviço irmão: só lê o que o coletor escreveu e fala com um endpoint a mais (`/sol-price`, grupo próprio de rate limit 50/60 s, ≤ 1 req/min por cache). `MEME_LAB_ENABLED` padrão **true** quando `MEME_ENABLED` — desligado por padrão só produziria um radar que parece vivo e não propõe; desligado diz `lab: disabled` no readiness e `lab_enabled=false` no heartbeat.
2. **Carteira derivada das linhas** (`wallet_max_sol + Σ pnl fechado − Σ stake aberto`), nunca em memória: restart não é reset. A `PaperCurveWallet` da T4.5 é o simulador de replay; aqui uso a aritmética (`quote_buy`/`quote_sell`) e as regras (`evaluate_entry`/`evaluate_exit`) dela sobre linhas duráveis.
3. **Não-antecipação três vezes**: porta só sobre minutos fechados (`end_time <= now − 1 min`, backlog de 3 minutos); fill na **primeira** fotografia com `observed_at > decided_at` (`pick_fill_snapshot`), nunca a mais recente; venda na fotografia seguinte à que disparou (`exit_intent`). Sem fotografia posterior em 3 min: `unfilled: no_later_snapshot` / `rug_no_snapshot` (fecha a zero, R = −1, doutrina §5).
4. **`meme_paper_bets.mode` é `CHECK (mode = 'paper')`**: nenhum papel, dono incluído, escreve uma aposta que se diga real até a T4.8 trazer revisão própria.
5. **`priority_fee_sol = 0` na seed, declarado**: nenhum priority fee foi observado; a EXP-M1 já chama todo número de teto otimista.
6. **A cotação SOL/USD nunca bloqueia um fill**: `sol_usd_at_entry/exit` NULL com `sol_usd_reason` quando o `/sol-price` falha; a API cai para a última cotação de uma aposta e, sem nenhuma, `capital_usd` é `null` com `no_sol_usd_quote`.
7. **A verdade medida de hoje**: com `creator_sold` NULL (`no_holders_reader`) e sem volume do minuto (sem feed de trades), o portão congelado da EXP-M1 recusa **toda** linha (`creator_net_seller_unknown`, `curve_volume_1m_unknown`) — provado em `test_proposals.py` e sobre linhas reais no testcontainer. O laço conta as recusas por conjunto no heartbeat (`lab_gate_refusals`) e em `GET /meme/lab` → `sources`. A aposta hoje entra pela mesa (`POST /proposals/manual`, T4.7) e o laço faz o resto. Afrouxar a porta sem pré-registro está fora de questão (brief, item 4).

## Comandos e saídas reais

```
$ timeout 290 uv run ruff check <todos os arquivos da tarefa>
All checks passed!
$ timeout 290 uv run ruff format --check <idem>
39 files already formatted
$ timeout 290 uv run pyright services/meme-worker apps/api/hunter_api/routers/meme_lab.py apps/api/hunter_api/services/meme_lab.py apps/api/hunter_api/services/meme_lab_goal.py apps/api/hunter_api/repositories/meme_lab.py apps/api/hunter_api/schemas/meme_lab.py apps/api/tests/unit/test_meme_lab_service.py packages/core/hunter_core/db/models/meme_lab.py packages/exchange-adapters/hunter_exchanges/pumpfun/models.py packages/exchange-adapters/hunter_exchanges/pumpfun/rest.py infra/scripts/meme_diary.py infra/scripts/meme_diary_render.py infra/migrations/ddl/meme_lab.py infra/migrations/ddl/meme_lab_views.py infra/migrations/versions/0022_meme_lab.py
0 errors, 0 warnings, 0 informations

$ timeout 290 uv run pytest services/meme-worker/tests/test_paper_engine.py services/meme-worker/tests/test_proposals.py services/meme-worker/tests/test_tracker.py services/meme-worker/tests/test_features.py packages/exchange-adapters/tests/unit/test_pumpfun_clients.py apps/api/tests/unit/test_meme_lab_service.py apps/api/tests/unit/test_meme_service.py infra/scripts/tests/test_meme_diary.py packages/core/tests/unit/test_runtime.py -q
118 passed in 2.95s
   (motor 23 · porta 14 · adapter 15 [+3 sol-price] · API lab 12 · diário 4 · o resto = suítes vizinhas sem regressão)

$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q      # testcontainer, alembic head = 0022
12 passed in 89.11s (0:01:29)
   seed; portão sobre linhas reais contando recusas; fill na 1.ª fotografia posterior + look-ahead (futuro reescrito não move a entrada);
   unfilled no_later_snapshot / exceeds_max_sol_per_bet / daily_loss_cap; expired + cancel; fechamento por target, time_stop, migrated,
   sell_now (cada um na fotografia seguinte); rug_no_snapshot; scoreboard + desk; grants como o papel; mode='live' recusado pelo CHECK

$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q
137 passed in 361.86s (0:06:01)
$ timeout 590 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q
57 passed in 164.99s (0:02:44)

$ timeout 290 uv run python infra/scripts/check_file_size.py
scanned 717 files; 0 over budget, 0 grandfathered
$ timeout 290 uv run python infra/scripts/obsidian_lint.py     # não toquei o vault; rodado por segurança
RESULTADO: 1 achado(s) — Notas órfãs (1): 11-KNOWLEDGE/KB-0092-... (pré-existente, não é desta tarefa)

$ DATABASE_URL=<postgres descartável em localhost:55446, migrado até head na hora> REDIS_URL=redis://127.0.0.1:1/0 \
  timeout 290 uv run python infra/scripts/meme_diary.py --dry-run
---
tags: [operacoes, diario, meme, m4]
status: registro
owner: sexta-feira
updated: 2026-09-12
---

# Diário Meme — 2026-09-12

Gerado por `infra/scripts/meme_diary.py` em 2026-09-12 05:37 BRT a partir de `meme_paper_bets`, `meme_proposals`, `meme_rule_sets` e `meme_ingest_gaps`. **PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo.** Nenhum número financeiro abaixo foi digitado à mão; só a seção 6 é do arquivista.

## 1. Estado da carteira paper

| conjunto | tipo | teto (SOL) | saldo início | saldo fim | PnL do dia | PnL acumulado | abertas ao fechar |
|---|---|---|---|---|---|---|---|
| `meme_paper_v0/1` (EXP-M1) | research_only | 2 | 2 | 2 | 0 | 0 | 0 |
| `operator/1` | operator | 2 | 2 | 2 | 0 | 0 | 0 |

## 2. Apostas do dia

Nenhuma aposta aberta neste dia (o laço propõe só quando o portão libera).

## 3. R em SOL do dia e acumulado

| conjunto | apostas | fechadas | acertos | R do dia | R acumulado | drawdown do dia (SOL) | drawdown acumulado (SOL) | rugs |
|---|---|---|---|---|---|---|---|---|
| `meme_paper_v0/1` | 0 | 0 | 0 | — (sem fechada) | — (sem fechada) | — (sem fechada) | — (sem fechada) | 0 |
| `operator/1` | 0 | 0 | 0 | — (sem fechada) | — (sem fechada) | — (sem fechada) | — (sem fechada) | 0 |

## 4. Distância à meta

> [!alerta] Conta sobre o alvo declarado (US$ 7 M em 30 dias), nunca previsão de retorno.

- Capital (paper, soma dos conjuntos ativos ao fechar o dia): 4 SOL = — (sem cotação SOL/USD observada)
- Retorno diário exigido: — (sem cotação SOL/USD observada)
- Retorno diário medido: — (nenhuma aposta fechada no dia)
- Início do relógio: 2026-09-12 (primeiro conjunto ativo; seed da migração 0022)

## 5. Incidentes

- Laço: sem heartbeat lido (`hb:meme:radar` sem `lab_last_tick_at`) — laço parado ou nunca rodou

## 6. O que o Lab aprendeu

(a preencher pelo arquivista — Sexta-feira)

--- dry-run: nada escrito; --apply gravaria obsidian\09-OPERATIONS\Diario-Meme\2026-09-12.md
== exit 0 ==
```
(`--apply` **não** rodado: nenhuma aposta fechada hoje; o script recusa sem `--allow-empty` e recusa sobrescrever nota existente.)

## Preocupações / pendências

1. **Zero propostas do laço com as fontes de hoje** (decisão 7 acima): é o resultado honesto do portão pré-registrado, não um bug; a mesa só recebe propostas automáticas quando o leitor de holders (T4.2c) e o feed de trades (T4.2b) existirem. Até lá, `POST /proposals/manual` (T4.7) + o laço.
2. **`rug_no_snapshot` fecha a zero** por decisão declarada (Emenda 9). A doutrina §6 preferiria "pendente degradada com alerta"; escolhi o contrato (o motivo é um `exit.reason` fechado) para o placar e a carteira não carregarem uma posição impreçável para sempre. Se o Everton preferir o outro caminho, é uma linha no `paper_engine.close_without_snapshot` e uma emenda.
3. **Venda pós-migração**: hoje fecha contra a fotografia da curva concluída, com 1,75 % (`exit.trigger` diz). O PumpSwap não é observado nesta fatia.
4. **`packages/shared-types/src/generated/api.d.ts`** apareceu modificado na árvore (gen:types de outro agente); depois de T4.6 + T4.7 pousarem, `pnpm gen:types` deve rodar de novo para incluir `GET /meme/lab`.
5. Sem teste de integração de rota HTTP para `GET /meme/lab` (o serviço é testado com repositório falso e as vistas/grants no testcontainer do worker); se o orquestrador quiser, cabe em `apps/api/tests/integration` no mesmo padrão do `test_lab_daily_goal_api.py`.
6. Astra não foi consultada (o brief não pedia e o `SendMessage` está desabilitado); a revisão do diff foi minha.
