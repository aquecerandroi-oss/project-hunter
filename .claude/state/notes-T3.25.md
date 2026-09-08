# Notes T3.25 — four "Planejado" pages that already have real data behind them

## Section A — API (backend-specialist, 2026-09-08)

### O que foi feito

**1. Strategies — `GET /api/v1/lab/shadow/strategies`** (global, sem RLS, como o resto do Lab).
Um item por `strategies.key`, cada um com a lista de `strategy_versions`: `version`, `purpose`,
`status`, `activated_at`/`deprecated_at`, `code_ref`, `default_parameters` **e** `parameters_schema`
(JSON Schema completo — tipo, padrão/enum e descrição por parâmetro, o "cada diâmetro" que o brief
pediu), linhagem (`replication_parent_id`/`replication_index`, `null` quando a versão não é uma irmã),
`promising_at`/`promising_by`, o veredito e a maturidade **reaproveitados literalmente** de
`lab_scoreboard` (mesma população `prospective`, mesma regra mecânica — `test_verdict_matches_the_
scoreboards_own_computation` prova que os dois endpoints nunca discordam), contagem de sinais por
família de coorte (`prospective`/`replay`/`replication`, DATABASE.md §24.1) e o link do Obsidian por
convenção fixa `03-TRADING/Estrategias/<key>-<version>.md` (nunca uma consulta ao vault).

**2. Backtests = replay — `GET /api/v1/lab/shadow/replays` e `GET /api/v1/lab/shadow/replays/{run_id}`**.
`replay_runs` é uma linha por **fatia** (DATABASE.md §25.1); a listagem agrupa por `run_id` e soma o
que o schema documenta como somável (`bars_evaluated`, `seconds`, `evaluations_by_state`) e usa o
valor da **última** fatia para o que é total corrente (`signals`, `outcomes_resolved`,
`outcomes_open`) — nunca soma os dois tipos com a mesma regra. O detalhe devolve as fatias cruas mais
a população somada por estado. Confirmado por teste (item 2 do brief): `GET /lab/shadow/signals?
cohort=replay:<uuid>` já aceitava o filtro desde a `0012_replication` — nenhuma mudança precisou ser
feita ali, só a prova.

**3. Trades/Orders/Positions — `GET /orgs/{org}/portfolios/{id}/{trades,orders,positions}`** (T3.8a)
já tinham entry/exit, qty, exit_reason. Faltava, comparado com a promessa de PRODUCT.md §8: fees e
PnL realizado em **BRL** (`fees_brl`/`pnl_brl`, `null` com `..._unavailable_reason` quando não há
`fx_observations` cobrindo `closed_at` — nunca extrapolado, a mesma convenção de `PortfolioSummaryOut.
brl`), o snapshot de features na entrada/saída (`entry_snapshot`/`exit_snapshot`, já gravados em
`trades` e nunca expostos) e os "protection intents" (`portfolio_exit_intents`, DATABASE.md §18.4) —
adicionados a `PositionOut` e a `PortfolioTradeOut`. Nenhuma tabela nova; `Orders` ficou como estava
(a promessa da página de Trades não pede nada dele além do que já expõe).

**4. Risk Center — `GET /orgs/{org}/portfolios/{id}/risk/limits`**. O preset numérico completo de
`paper_v1` (`risk_per_trade_pct` 0,25 %, `max_aggregate_planned_risk_pct` 1 %, `max_participation_pct`
1 %, `warning_size_multiplier` 0,5×, `max_total_exposure_pct` 40 %, `max_asset_exposure_pct` 10 %,
`max_concurrent_positions` 5, kill switch warning 1 %/4 %, blocked 2 %/8 %, `min_liquidity_usd_24h`
50.000.000) lido de `Portfolio.risk_profile_id → risk_profiles.limits` quando existe, e do próprio
`hunter_risk.limits.PAPER_V1` quando não (achado: **nenhum caminho de produção hoje passa
`risk_profile_id` ao abrir a carteira principal** — nem `hunter_core.portfolio.opening.
open_paper_wallet`, nem nenhum script/rota chama com esse argumento — então a carteira real está sem
esse vínculo; `source` no payload diz qual dos dois caminhos respondeu, e o teste prova que os números
são byte a byte `PAPER_V1` nos dois casos). Uso atual contra cada teto — exposição total, por moeda,
beta-ponderada, posições abertas, reservado — lido de `build_portfolio_state` (reaproveitado
exatamente como `portfolio_queries.build_summary` já faz, `marks={}`), com `null` honesto quando o
motor não conseguiu reconstruir a referência diária (mesmo `unavailable` que a carteira já reporta).
Kill switch e transições recentes embutidos, reaproveitando a mesma leitura de `read_kill_switch`
(extraída para `build_kill_switch_out`, sem duplicar lógica).

### Achado que fecha a fala do Everton
"A API ainda não expõe os valores numéricos do preset" — fechado por `GET .../risk/limits`. Exemplo
real (carteira recém-aberta, sem posições): `preset.risk_per_trade_pct = "0.0025"`,
`preset.max_total_exposure_pct = "0.4"`, `preset.source = "engine_default"` (porque a carteira não tem
`risk_profile_id`, achado acima).

### Arquivos criados
- `apps/api/hunter_api/routers/lab_strategies.py`
- `apps/api/hunter_api/repositories/lab_strategies.py`
- `apps/api/hunter_api/schemas/lab_strategies.py`
- `apps/api/hunter_api/services/lab_strategies.py`
- `apps/api/hunter_api/routers/lab_replays.py`
- `apps/api/hunter_api/repositories/lab_replays.py`
- `apps/api/hunter_api/schemas/lab_replays.py`
- `apps/api/hunter_api/services/lab_replays.py`
- `apps/api/hunter_api/schemas/risk_limits.py`
- `apps/api/hunter_api/services/risk_limits.py`
- `apps/api/hunter_api/services/portfolio_trade_extras.py`
- `apps/api/tests/integration/test_lab_strategies_api.py` (5 testes)
- `apps/api/tests/integration/test_lab_replays_api.py` (5 testes)
- `apps/api/tests/integration/test_risk_limits_api.py` (6 testes)
- `apps/api/tests/integration/test_portfolio_trades_extra_api.py` (3 testes)

### Arquivos modificados
- `apps/api/hunter_api/app.py` (registra os dois novos routers)
- `apps/api/hunter_api/routers/risk.py` (nova rota `/limits`; `read_kill_switch` refatorado para
  `build_kill_switch_out`, reaproveitado pela rota nova — sem mudança de comportamento, os 11 testes
  de `test_risk_api.py` continuam verdes)
- `apps/api/hunter_api/schemas/portfolio_lists.py` (`ExitIntentOut`; `PositionOut`/`PortfolioTradeOut`
  ganham os campos do item 3)
- `apps/api/hunter_api/services/portfolio_lists.py` (`list_positions`/`list_trades` passam a montar
  os campos novos)
- `apps/api/tests/integration/lab_fixtures.py` (`seed_strategy_version` ganha `purpose`,
  `parameters_schema`, `replication_parent_id`/`_index`, `promising_at`/`_by`; nova
  `seed_replay_slice`)
- `packages/shared-types/src/generated/api.d.ts` (via `pnpm gen:types` — `openapi.json` não commitado,
  gitignored)

### Testes — saída real
```
uv run pytest apps/api/tests/integration/test_lab_strategies_api.py -q      → 5 passed
uv run pytest apps/api/tests/integration/test_lab_replays_api.py -q        → 5 passed
uv run pytest apps/api/tests/integration/test_risk_limits_api.py -q        → 6 passed
uv run pytest apps/api/tests/integration/test_portfolio_trades_extra_api.py -q → 3 passed
uv run pytest apps/api/tests/integration/test_risk_api.py -q (pré-existente, prova que a
  refatoração de read_kill_switch não quebrou nada)                        → 11 passed
uv run ruff check apps/api/hunter_api ... → All checks passed
uv run ruff format --check ... → already formatted
uv run pyright apps/api/hunter_api → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py → 0 over budget
```

### CONCERNS

1. **Achado, não corrigido**: nenhum caminho de produção passa `risk_profile_id` ao abrir a carteira
   paper principal (`open_paper_wallet` sempre recebe `None`). O endpoint novo cobre isso com um
   fallback honesto (`source: "engine_default"`), mas a lacuna arquitetural em si — a carteira real
   não está de fato ligada a uma linha de `risk_profiles` — é do database-architect/risk-engine-
   guardian decidir se fecha (provavelmente um `--risk-profile-id` no script de abertura).
2. **Ambiente local, não causado por esta tarefa**: `apps/api/tests/integration/test_portfolio_api.py`
   (não tocado por mim) falha localmente porque seu helper `_open()` chama `open_paper_wallet` via
   `tenant_session(...)` (role `hunter_app`), e `hunter_app` não tem `INSERT` em
   `portfolio_equity_snapshots` (só `hunter_worker` tem — confirmado em `notes-T3.5.md` §4, item 5).
   Meus três testes que abrem carteira usam `db_role="hunter_worker"` explicitamente e passam. Vale
   avisar quem for revisar/rodar a suíte completa: 15 erros + 1 falha em `test_portfolio_api.py` nesta
   máquina, mesmo sem nenhuma mudança minha nesse arquivo.
3. **Ruff tier estrito (não bloqueante, CI-only)**: `_version_detail` (services/lab_strategies.py, 6
   argumentos) e `build_risk_limits` (services/risk_limits.py, 36 statements) entram para a contagem
   de violações que `ruff.strict.toml` anota no relatório do milestone — não bloqueiam, mas registro
   aqui para quem for zerar a contagem depois.
4. **`bars_per_second`/agregação de `replay_runs`**: decisão declarada (não pedida explicitamente pelo
   brief): a listagem soma `bars_evaluated`/`seconds` das fatias e toma o **rate agregado**
   (`sum(bars)/sum(seconds)`), não a média das taxas por fatia — mesma convenção que o `to_jsonable()`
   documentado em DATABASE.md §25.2 usa por fatia, estendida para o total do run.
5. **N+1 em `list_trades`**: a conversão BRL de `fees`/`pnl` consulta `fx_observations` uma vez por
   trade (não em lote), porque `closed_at` varia por linha. Aceitável no volume atual (M3, carteira
   única); se o volume crescer, cabe um cache por instante arredondado.

## Section B — Web (frontend-specialist, depois de T3.23/T3.24)

_A preencher pelo agente de frontend._
