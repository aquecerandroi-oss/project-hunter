# T4.2g — a fita por lote: `POST /v1/coins/market-activity/batch` no lugar da fita por mint (migração `0032_meme_activity`)

Execução de 12/09/2026, 17:2x–18:1x BRT (20:2x–21:1x UTC). Papel: exchange-integration. Brief:
`.claude/state/brief-T4.2g-atividade-em-lote.md`. Sem commit; nada real; `.env*` intocado; `apps/web/**`,
`infra/migrations/**` (fora da minha `0032` + `ddl/meme_activity.py`), `services/meme-executor/**`,
`tracker*.py`/`lab_pins.py`/`lab_point_read.py`/`warmup.py` intocados. Nenhum processo em segundo plano; todo
comando com `timeout 290` (590 nos testcontainers).

**Árvore ao começar (20:2x Z):** HEAD `b25c96f`. Já modificados por outros: `.claude/launch.json`, `docs/DESIGN.md`,
`apps/web/**` (6 ` M`), `??` em `.claude/state/**`. **Durante a sessão** um agente paralelo (T4.19, `operator/3`) editou a
mesma árvore: `0033_meme_operator_3.py` (que ele pôs **sobre a minha `0032`** — cadeia linear 0031 → 0032 → 0033),
`HEAD_REVISION = "0033_meme_operator_3"` em `test_migrations.py`, `MEME_ACTIVITY_REVISION` (constante que os meus testes
de descida usam para estagiar), `GateRow.symbol` em `proposals.py`/`lab_repo*.py`, `docs/DATABASE.md` §45,
`docs/RISK_ENGINE_MEME.md`, `meme_desk*`. Meus hunks são cirúrgicos (Edit); não formatei arquivos dele.

## Leitura (20:2x Z)

O brief, `notes-T4.16.md`, `notes-T4.16b.md`, `notes-T4.2f.md`, `notes-T4.0c.md` (a captura do lote),
`docs/EXCHANGE_INTEGRATION.md`, `docs/PIPELINE.md` §1/§1e, `docs/ARCHITECTURE.md` §6, `docs/PUMPFUN.md` §2,
`docs/DATABASE.md` §42/§43, o plano §T4.2f/§T4.16b, e no código: `swap_api.py`, `rate_shared.py`, `models.py`,
`board_models.py`, `rpc_curves.py` (adaptador); `trades.py`, `tape_budget.py`, `features.py`, `features_tape.py`,
`features_fast.py`, `fold.py`, `fast_lane.py`, `sources.py`, `source_stats.py`, `config.py`, `context.py`, `wiring.py`,
`main.py`, `repo.py`, `repo_tape.py`, `repo_fast.py`, `lab_repo*.py`, `collect.py` (`forever`, `persist_reading`);
`hunter_indicators.meme.rules_criteria` (o portão de fluxo); a `0030`/`0031` e os DDLs; `test_migrations.py`,
`test_schema_privileges.py`, `test_chain*.py`, `test_fast_lane.py`, `test_trades.py`, `test_sources.py`.

## A sonda ao vivo (17:24–17:25 BRT; 5 requisições, ritmo 4 s; fixtures `t42g_*`)

`C:/Users/evert/AppData/Local/Temp/claude/t42g/probe.py` (a scratchpad tem 261 caracteres de caminho — acima do
`MAX_PATH`, o mesmo achado da T4.16 — por isso o destino curto). Saída real:

```
2026-09-12T20:24:01Z
fixture mints: 140
[A_shape] call 1: 201 243 ms 631 B headers={'date': 'Sat, 12 Sep 2026 20:24:02 GMT', …, 'x-ratelimit-limit': '1000', 'x-ratelimit-remaining': '987', 'server': 'cloudflare', 'cf-ray': 'a3a1a224885bf1c7-GRU'}
  EV4JbtMh: intervals=['1m', '5m', '1h', '6h', '24h']   1m: None  5m: None  1h: None  6h: None
    24h: {'numTxs': 2, 'volumeUSD': 99.20229804272005, 'numUsers': 1, 'numBuys': 1, 'numSells': 1, 'buyVolumeUSD': 49.60028645179046, 'sellVolumeUSD': 49.602011590929585, 'numBuyers': 1, 'numSellers': 1, 'priceChangePercent': -2.699026967752155}
[B_140] call 2: 400 175 ms 214 B  body: {"message":["addresses must contain no more than 50 elements"],"error":"Bad Request","statusCode":400}
[B_100] call 3: 400 172 ms 214 B  body: idem
[B_50] call 4: 201 982 ms 17103 B headers={'date': 'Sat, 12 Sep 2026 20:24:15 GMT', …, 'x-ratelimit-remaining': '986', 'server': 'cloudflare'}
  mints in response: 50
total calls: 4
2026-09-12T20:25:20Z
non-null windows in the 50-mint capture: {'1m': 0, '5m': 0, '1h': 0, '6h': 7, '24h': 50}
active-candidate mints: 0
[E_active] call 5: 400 206 ms 209 B  body: {"message":["addresses must contain at least 1 elements"],…}
```

**Medido:** (a) o lote aceita **todas as 10 métricas** (`numBuys`, `numSells`, `buyVolumeUSD`, `sellVolumeUSD`,
`numBuyers`, `numSellers` incluídas); (b) **máximo 50 endereços por requisição** (400 nomeado em 140 e 100; 201 em 50,
982 ms, 17 KB); (c) as janelas `1m`/`5m`/`1h`/`6h`/`24h` passam pelo validador (estrito: recusa > 50 e 0 por nome) e são
ecoadas como chaves; (d) **janela sem trade = `null`** — em 50 moedas de 7 h, `24h` preenchida em 50, `6h` em 7,
`1h`/`5m`/`1m` em nenhuma: `null` é "janela vazia" numa janela suportada; (e) USD em floats, sem carimbo próprio
(`Date` = fim das janelas); mesmo `x-ratelimit-limit: 1000` e `server: cloudflare` da fita.
**Não provado:** `1m` não-nulo numa moeda ativa — **a 5.ª requisição foi gasta por um bug meu** (a extração de mints
dos boards `trenches_*.json` devolveu lista vazia → 400 "at least 1 elements"). Não fiz uma 6.ª. O desenho carrega o
guarda em runtime (`windows_live`) e o heartbeat prova na VPS (`activity_live_1m`).

## Desenho (decisões que o brief não fixa)

1. **USD, não SOL, no adaptador** (`NormalizedMarketActivity.buy_volume_usd`/`sell_volume_usd`): a rota só fala USD; o
   pacote não tem cotação. O worker deriva SOL com a cotação de `/sol-price` (bucket próprio `pumpfun_sol_price_activity`,
   50/60 s; ≤ 1 leitura/min; válida 5 min) e grava `sol_usd` + `sol_usd_observed_at` **ao lado** na linha
   (`sol_figures_name_their_quote`); sem cotação: `no_sol_quote` (motivo novo no vocabulário).
2. **`null` só vira zero num ciclo em que a mesma janela veio preenchida para alguma moeda** (`ActivityBatch.windows_live`,
   união dos ≤ 3 lotes do ciclo): é a prova de que a janela é computada. Senão nada é escrito e o ciclo conta
   `activity_dark_60s`. Como o `1m` não foi provado vivo pela sonda, isto é o que impede escrever "ninguém comprou" no
   lugar de "não sei" (o MUST-FIX 1 da Astra).
3. **Só a janela `1m` alimenta as features** (`tape_source = 'activity_1m'`, `tape_window_s = 60`, `tape_as_of` = o
   `Date` da resposta). A `5m` é gravada em `meme_market_activity_1m` (registro), nunca dividida por 5 nem chamada de 1 m;
   se a `1m` ficar escura na VPS, uma T4.2g-b acrescenta `*_5m` às features com o portão lendo `curve_volume_5m_sol`.
4. **Disparo 3 s antes de cada fecho** (`MEME_ACTIVITY_LEAD_S`): a janela `1m` da resposta termina logo antes do minuto
   que o fold julga — o mais perto que um agregado consultado chega de "a janela cujo fim coincide com o minuto";
   `tape_as_of` guarda o fim exato. Fold e linha de 15 s usam a leitura `1m` mais nova com `received_at <= instante` e
   fim há < 60 s (`activity_for`); guardo 2 leituras por mint para uma posterior nunca esconder a anterior.
5. **A fita por mint tem prioridade**; o lote entra só quando ela não cobriu (`fold._tape_inputs`, `fast_lane.fold_fast`).
   `unique_buyers` do lote inclui o criador; `creator_sold`/`creator_net_seller` ficam `no_trade_feed`.
6. **Mesmo orçamento do Cloudflare:** um só `SwapApiClient` (bucket) para fita e lote; `TapeBudget.reserve(ceil(n/50))`
   tira as chamadas do lote do topo (16 → 13 para a fita); um 429 real no lote é o mesmo `record_refusal`
   (mede/encolhe/bloqueia) e o lote não dispara no bloqueio (`skipped = blocked`). Contado em `swap_api.used_60s` e na
   fonte nova `swap_api_activity`.
7. `meme_market_activity_1m`: PK `(end_time, mint, window_name)` — **`window` é palavra reservada** no Postgres
   (`syntax error at or near "window"` na 1.ª subida), daí o sufixo; retenção **30 d** (declarada: ~375 k linhas/dia; as
   features guardam os números pelo `MEME_RETENTION_DAYS`).
8. Um CHECK por série para a procedência, **`tape_source_is_consistent`** — o nome original tinha 65 caracteres, o
   Postgres truncou em 63 e o `alembic check` acusou (6 falhas); a recíproca (fita ⇒ fonte) não é exigida para as linhas
   anteriores à `0032` continuarem legais.

## Comandos e saídas reais (em ordem; BRT = UTC − 3)

```
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_market_activity.py test_pumpfun_swap_api.py test_pumpfun_indexer_rest.py -q
23 passed in 1.80s                                                     # 20:33Z — 6 novos + 17 existentes (POST orçado)
$ timeout 290 uv run ruff check <adaptador> → All checks passed!   ruff format → 1 file reformatted
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0032 or upgrade_head_reaches or partitioned_parent or alembic_check or every_table_in_the_metadata or new_revision_reverses"
8 errors in 21.91s     # 20:38Z — syntax error at or near "window" (reservada) → window_name
4 failed, 4 passed     # 20:40Z — guarda de descida com apóstrofo sem escape ("route's") → safe_why; asyncpg exige datetime, não str, em CAST(:x AS timestamptz)
8 passed, 160 deselected in 41.94s                                     # 20:41Z
$ timeout 290 uv run pytest services/meme-worker/tests/test_activity.py test_sources.py -q
2 failed, 14 passed    # 20:52Z — aritmética do teste (idade da cotação 20 s, não 23; 5 min = NOW+279/281)
$ timeout 290 uv run pytest services/meme-worker/tests -q -m "not integration"
221 passed, 56 deselected in 3.11s                                     # 20:54Z (test_activity 8, test_sources +1)
$ timeout 290 uv run pytest apps/api/tests/unit -q -k meme → 121 passed   (test_meme_sources_service +1)
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit -q -k pumpfun → 170 passed, 375 deselected in 3.72s
$ timeout 590 uv run pytest services/meme-worker/tests/test_activity_persistence.py -q
1 passed in 17.91s                                                     # 20:57Z — testcontainer, head = 0033
$ timeout 590 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -k "grant_lists_cover or no_partition_child or read_only_tables_grant"
3 passed, 54 deselected in 152.05s                                     # 21:00Z
$ timeout 290 pnpm gen:types → openapi.json → api.d.ts [435.5ms]; 30 insertions(+), 8 deletions(-)   # 21:04Z
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0032 or 0033 or upgrade_head_reaches or alembic_check or partitioned_parent or every_table_in_the_metadata or new_revision_reverses"
6 failed, 6 passed in 53.80s   # 21:06Z — AutogenerateDiffsDetected: ck_…_with_a_ta (63 chars) ≠ …_with_a_tape → tape_source_is_consistent
12 passed, 160 deselected in 51.45s                                    # 21:08Z — 0032 sobe/recusa/reverte, 0033 (T4.19) sobre ela, head, alembic check, partições
$ timeout 290 uv run ruff check <35 arquivos meus> → All checks passed!
$ timeout 290 uv run ruff format --check <idem> → 35 files already formatted
$ timeout 290 uv run pyright apps/api/hunter_api services/meme-worker/hunter_meme_worker packages/exchange-adapters/hunter_exchanges/pumpfun packages/core/hunter_core/db/models <testes/ddl/migração>
0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt
scanned 853 files; 0 over budget, 0 grandfathered   # meme_features.py 350, sources.py 349, activity.py 346, main.py 345
$ timeout 290 uv run pytest services/meme-worker/tests -q -m "not integration" → 221 passed, 57 deselected in 3.05s   # 21:06Z, rerodada
```

Não rodado: o SQL de cobertura (`2026-09-12-t42g-cobertura.sql`) — só na VPS, antes × depois do deploy.

## Arquivos (meus)

**Criados:** `packages/exchange-adapters/hunter_exchanges/pumpfun/market_activity.py`;
`packages/exchange-adapters/tests/unit/test_pumpfun_market_activity.py`; fixtures
`packages/exchange-adapters/tests/fixtures/pumpfun/t42g_market_activity_batch_{raw,50_raw,probes}.json`;
`packages/core/hunter_core/db/models/meme_activity.py`; `infra/migrations/versions/0032_meme_activity.py`;
`infra/migrations/ddl/meme_activity.py`; `services/meme-worker/hunter_meme_worker/{activity,repo_activity}.py`;
`services/meme-worker/tests/{test_activity,test_activity_persistence}.py`;
`infra/scripts/sql/research/2026-09-12-t42g-cobertura.sql`; estas notas.

**Modificados:** `packages/exchange-adapters/hunter_exchanges/pumpfun/{swap_api,rate_shared}.py`;
`packages/core/hunter_core/db/models/{__init__,meme_features,meme_features_15s}.py`;
`packages/core/tests/integration/{test_migrations,test_schema_privileges}.py`; `infra/scripts/partition_retention.py`;
`services/meme-worker/hunter_meme_worker/{config,context,fast_lane,features,features_fast,features_tape,fold,main,repo,sources,tape_budget,wiring}.py`;
`services/meme-worker/tests/test_sources.py`; `apps/api/hunter_api/{schemas/meme,schemas/meme_sources,services/meme_sources,repositories/meme_sources}.py`;
`apps/api/tests/unit/test_meme_sources_service.py`; `packages/shared-types/src/generated/api.d.ts` (gerado);
`docs/{PUMPFUN,DATABASE,DEPLOYMENT,PIPELINE,EXCHANGE_INTEGRATION}.md`, `docs/plans/T4-MEME-RADAR.md`.

**Não meus, vistos na árvore:** T4.19 (`0033_meme_operator_3.py`, `ddl/meme_operator_3.py`, `proposals_plan.py`,
`proposals.py`, `lab_models.py`, `lab_repo*.py`, `meme_desk*`, `test_lab_moonshot.py`, `test_meme_desk_*`,
`docs/RISK_ENGINE_MEME.md`, §45 do `DATABASE.md`, §T4.19 do plano, `brief-T4.19-*`), plantão (`obsidian/**`,
`.claude/state/plantao-meme/**`), `tests/e2e/design-audit.*`, `apps/web/**`, `docs/DESIGN.md`, `.claude/launch.json`.

## Preocupações / pendências

1. **A janela `1m` não foi provada viva** (bug da sonda, 5.ª requisição em lista vazia). O worker não escreve zero para
   `null` de `1m` num ciclo em que ninguém a teve preenchida (`activity_dark_60s`); a prova vem do 1.º minuto na VPS:
   `activity_live_1m > 0` no heartbeat/`GET /meme/sources` e §4 do SQL. Se ficar escura, T4.2g-b (colunas `*_5m` +
   portão lendo `curve_volume_5m_sol`).
2. **Meta `tape_coverage_pct ≥ 90` só se prova na VPS** (SQL §1/§1b antes × depois); aritmética a favor: 3 requisições
   cobrem 130 rastreados por minuto; o que faltar é `no_sol_quote` (raro) e moedas fora da curva.
3. **A série de 15 s recebe a janela `1m` com até 60 s de atraso** (`tape_as_of` diz quanto); `MEME_ACTIVITY_CYCLE_S=30`
   reduz para 30 s ao custo de 6 req/min do mesmo orçamento (16). Decisão do operador.
4. **`unique_buyers` do lote inclui o criador** (a fita por mint o exclui) — ±1 no `min_unique_buyers 10` do `flow_v2/1`;
   nomeado por `tape_source`.
5. **SOL derivado de USD** com a cotação do minuto (drift < 1 %); o sinal de `net_sol_flow_1m` não depende da cotação.
6. Árvore compartilhada com a T4.19 durante a sessão: `test_migrations.py` tem hunks dos dois (`HEAD_REVISION` dele,
   `MEME_ACTIVITY_REVISION` dele, os meus testes `0032` estagiam em `MEME_ACTIVITY_REVISION`); o commit por pathspec
   precisa levar os dois ou negociar a ordem. `docs/DATABASE.md` e `docs/plans/T4-MEME-RADAR.md` idem (§44/§T4.2g meus,
   §45/§T4.19 dele).
7. Rótulos do `apps/web` para os campos novos (`activity_*`, `tape_activity_pct`, fonte `swap_api_activity`, motivo
   `no_sol_quote`) fora desta tarefa; `api.d.ts` já os traz.
8. Astra não consultada (`SendMessage` desabilitado).

## `git status --porcelain` (21:0x Z; só os meus — os do T4.19/plantão/web listados acima ficam de fora)

```
 M apps/api/hunter_api/repositories/meme_sources.py
 M apps/api/hunter_api/schemas/meme.py
 M apps/api/hunter_api/schemas/meme_sources.py
 M apps/api/hunter_api/services/meme_sources.py
 M apps/api/tests/unit/test_meme_sources_service.py
 M docs/DATABASE.md
 M docs/DEPLOYMENT.md
 M docs/EXCHANGE_INTEGRATION.md
 M docs/PIPELINE.md
 M docs/PUMPFUN.md
 M docs/plans/T4-MEME-RADAR.md
 M infra/scripts/partition_retention.py
 M packages/core/hunter_core/db/models/__init__.py
 M packages/core/hunter_core/db/models/meme_features.py
 M packages/core/hunter_core/db/models/meme_features_15s.py
 M packages/core/tests/integration/test_migrations.py
 M packages/core/tests/integration/test_schema_privileges.py
 M packages/exchange-adapters/hunter_exchanges/pumpfun/rate_shared.py
 M packages/exchange-adapters/hunter_exchanges/pumpfun/swap_api.py
 M packages/shared-types/src/generated/api.d.ts
 M services/meme-worker/hunter_meme_worker/config.py
 M services/meme-worker/hunter_meme_worker/context.py
 M services/meme-worker/hunter_meme_worker/fast_lane.py
 M services/meme-worker/hunter_meme_worker/features.py
 M services/meme-worker/hunter_meme_worker/features_fast.py
 M services/meme-worker/hunter_meme_worker/features_tape.py
 M services/meme-worker/hunter_meme_worker/fold.py
 M services/meme-worker/hunter_meme_worker/main.py
 M services/meme-worker/hunter_meme_worker/repo.py
 M services/meme-worker/hunter_meme_worker/sources.py
 M services/meme-worker/hunter_meme_worker/tape_budget.py
 M services/meme-worker/hunter_meme_worker/wiring.py
 M services/meme-worker/tests/test_sources.py
?? .claude/state/notes-T4.2g.md
?? infra/migrations/ddl/meme_activity.py
?? infra/migrations/versions/0032_meme_activity.py
?? infra/scripts/sql/research/2026-09-12-t42g-cobertura.sql
?? packages/core/hunter_core/db/models/meme_activity.py
?? packages/exchange-adapters/hunter_exchanges/pumpfun/market_activity.py
?? packages/exchange-adapters/tests/fixtures/pumpfun/t42g_market_activity_batch_50_raw.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/t42g_market_activity_batch_probes.json
?? packages/exchange-adapters/tests/fixtures/pumpfun/t42g_market_activity_batch_raw.json
?? packages/exchange-adapters/tests/unit/test_pumpfun_market_activity.py
?? services/meme-worker/hunter_meme_worker/activity.py
?? services/meme-worker/hunter_meme_worker/repo_activity.py
?? services/meme-worker/tests/test_activity.py
?? services/meme-worker/tests/test_activity_persistence.py
```
