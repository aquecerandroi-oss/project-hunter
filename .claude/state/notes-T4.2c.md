# T4.2c — segundo coletor do Meme Radar: boards do site (`/ws/trenches`), fita do `swap-api`, risco por consulta, qualidade do radar (migração `0023_meme_boards_trades`)

Execução de 12/09/2026, das ~05:50 às ~07:20 BRT (UTC−3). Papel: exchange-integration.
Sem commit (o orquestrador commita por pathspec). Nada real: nenhuma ordem, nenhuma chave, nenhum
login, nenhum canal pago; toda captura ao vivo foi anônima (`User-Agent` + `Origin`), ≤ 30 s por
conexão WS, uma conexão por vez, 1 request por endpoint HTTP.

**Antes de mim, na árvore (não são meus, não tocados):** `.claude/launch.json`, `docs/DESIGN.md`,
`apps/web/app/(app)/[orgSlug]/meme/mesa/page.tsx` e as versões T4.6 de
`services/meme-worker/hunter_meme_worker/{collect,config,main}.py` (o f7edcfe não as levou; eu
construí sobre a árvore de trabalho, nunca sobre o HEAD).

## Arquivos

**Adaptador (`packages/exchange-adapters/hunter_exchanges/pumpfun/`)** — novos: `board_models.py`
(`NormalizedBoardEntry`, `NormalizedRiskSnapshot`, `NormalizedSwapTrade`), `trenches_entry.py` (parser
de entrada, chaves curtas → nomes longos, `t10`/`dh` → fração), `trenches_state.py` (`BoardState`,
`BoardEvent`, `OutOfOrderDelta`), `trenches.py` (`TrenchesWsClient`: URL + `subscribe`, backoff
`min(1000·2^n, 30000)` ms + jitter, idle 90 s, ressincronização), `indexer_rest.py`
(`AdvancedIndexerClient`: `/boards/{board}`, `/in-memory-coin/{mint}`, 60/60 s declarado),
`rate_shared.py` (o GET orçado que os dois clientes novos compartilham), `swap_api.py`
(`SwapApiClient`, 900/60 s, cursor, `parse_trades_page`). Modificados: `models.py` (`ReceivedAtMixin`
público), `normalize.py` (`UnsupportedQuote`), `ws.py` (`ConnectionState.malformed_messages`).
Testes: `tests/unit/test_pumpfun_{trenches,swap_api,indexer_rest}.py`.

**Fixtures reais (`packages/exchange-adapters/tests/fixtures/pumpfun/`)**: `trenches_new.json`
(1 snapshot + 25 deltas, 339 update/3 add/3 remove, 21,9 s), `trenches_graduated.json` (1 + 25, 18,7 s),
`trenches_movers.json` (2 + 25, 15,1 s), `trenches_graduating.json` (**1 + 7 em 34 s — o board é
quieto por natureza: deltas só quando algo muda; três tentativas de 30 s deram 7, 2 e 5**),
`indexer_boards_new_raw.json`, `indexer_in_memory_coin_raw.json` (65 campos),
`swap_api_trades_page1_raw.json` + `page2` (cursor, 100 + 100, `raydium_cpmm`),
`swap_api_trades_graduated_pump_raw.json` (100 `pump_amm`), `frontend_api_v3_coin_graduated_raw.json`,
`rpc_get_transaction_slot_evidence_raw.json`, `capture_t42c_http_log.json` (hora, status, bytes,
cabeçalhos de rate limit de cada request).

**Migração**: `infra/migrations/versions/0023_meme_boards_trades.py`, `ddl/meme_boards.py`,
`ddl/meme_boards_guards.py`; modelos `packages/core/hunter_core/db/models/meme_boards.py` (novo),
`meme_features.py` (novo — `MemeFeatures1m` saiu de `meme_series.py` com as 15 colunas),
`meme_series.py` (só snapshots + trades; `commitment` anulável), `__init__.py`; testes
`packages/core/tests/integration/test_migrations.py` (HEAD → `0023`, staging dos testes da 0022 em
`0022_meme_lab`, união de partições, +5 `test_0023_*`), `test_schema_privileges.py` (união de grants).

**Worker (`services/meme-worker/hunter_meme_worker/`)** — novos: `boards.py`, `trades.py`, `risk.py`,
`fold.py`, `sources.py`, `features_tape.py`, `repo_boards.py`, `repo_tape.py`, `wiring.py`.
Modificados: `tracker.py` (`final_read_pending`, `quote_unsupported`, `board`, `creator`, tiers),
`features.py` (15 colunas, `no_sells`), `repo.py` (colunas, `_LOAD_TRACKED` com leitura final),
`collect.py` (prioridade com apostas abertas, `UnsupportedQuote`, fontes, fold delegado),
`context.py`, `config.py`, `discovery.py`, `metrics.py`, `main.py`, `README.md`. Testes novos:
`tests/test_tracker_priority.py`, `test_features_tape.py`, `test_boards.py`, `test_trades.py`,
`test_sources.py`, `test_boards_trades_persistence.py` (testcontainer); ajustados: `test_features.py`
(`creator_sold` é coluna da fita → `no_trade_feed`), `test_persistence.py` (mint migrado volta para a
leitura final).

**API**: `apps/api/hunter_api/{routers,services,repositories,schemas}/meme_sources.py` (novos),
`app.py` (registro), `schemas/meme.py` (`MemeSource` + `trenches_ws`, `NullReason` + `no_sells`),
`apps/api/tests/unit/test_meme_sources_service.py`.

**Docs**: `docs/PUMPFUN.md` §3.1 (o que gravamos), `docs/plans/T4-MEME-RADAR.md` §T4.2c,
`docs/DATABASE.md` §35, `docs/PIPELINE.md` §1e, `docs/DEPLOYMENT.md` (env + §3.6),
`.claude/state/notes-T4.2.md` §contrato — emendas 2–6.

## O que foi medido ao vivo (BRT)

- 05:55–05:56 WS `new`/`graduated`/`movers`; 05:56–05:57 e 06:02–06:03 `graduating` (3 tentativas).
  `filterKey: "default"` responde com snapshot. `serverTs` em ms (lag ≈ 0,2 s), `age` em segundos,
  `t10`/`dh` percentuais com decimais, `pa = SOL`, `pg ∈ {pump, raydium_launchpad, pons}`, `c` mistura
  `eip155:*` no `movers`, `p` = progresso %, `ms` só com Mayhem.
- **Versões saltam no `graduating`** (snapshot 3137948 → deltas base 3137954, 3137976, 3137978…):
  contador por board que avança com mudanças fora do top-N. Regra adotada: aceitar salto para a
  frente (contado), ressincronizar em retrocesso/versão parada/mint desconhecido.
- 05:58 HTTP: `/boards/new` 200 (40 878 B, mesma forma do snapshot), `/in-memory-coin` 200 (65
  campos), `swap-api` p1 200 (`x-ratelimit-limit: 1000`, `remaining: 913`), p2 200, `getTransaction`
  200 (`slot 446373814` = 12 primeiros dígitos de `0004463738140009040000`; `blockTime 1789198468`
  = `2026-09-12T07:34:28Z` = `timestamp`), `/coins/{graduado}` 200 (`complete: true`,
  `virtual_token_reserves 279 900 000 000 000`, `real_token_reserves 0`, quote SOL). 06:01 `swap-api`
  do graduado 200 (`remaining: 900`).
- **Causa-raiz dos 0 `complete = true`**: não é o parser (o graduado real passa). É a expulsão do
  tracker por `migrated` antes do primeiro poll (43/49 graduações no slot da criação) mais a exclusão
  de migrados em `_LOAD_TRACKED`. Provado em `test_tracker_priority.py::test_the_root_cause_*` e no
  testcontainer (`completed_at` escrito pelo parser real; mint migrado volta com `final_read_pending`).
- `swap-api`: 0/230 txs com mais de um trade; `quoteAmount == amountSol` exato em lamports só nos
  `pump`; `raydium_cpmm` traz `amountSol` com 28 decimais (conversão) → `quote_is_native_sol = false`.

## Comandos e saídas reais

```
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42c/capture_trenches.py new graduating graduated movers
[new] frames=26 counts={'snapshot': 1, 'delta': 25} ops={'update': 339, 'add': 3, 'remove': 3} elapsed=21.91s bytes=197397
[graduating] idle 8s … counts={'snapshot': 1, 'delta': 0}   (recapturas: 7 em 34,05 s; 2 em 31,67 s; 5 em 32,86 s — mantida a de 7)
[graduated] frames=26 counts={'snapshot': 1, 'delta': 25} ops={'update': 361} elapsed=18.72s bytes=288785
[movers] frames=27 counts={'snapshot': 2, 'delta': 25} ops={'update': 190} elapsed=15.12s bytes=85278
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42c/capture_http.py
indexer_boards_new 200 563ms 40878B · indexer_in_memory_coin 200 156ms 1795B · swap_api_trades_p1 200 453ms 63380B rl={limit 1000, remaining 913}
swap_api_trades_p2 200 266ms 63337B · getTransaction {'rpc_slot': 446373814, 'rpc_blockTime': 1789198468} · frontend_api_v3_coin_graduated 200 219ms 2161B

$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/ -q -p no:cacheprovider -k pumpfun
116 passed, 375 deselected in 2.70s          (21 trenches + 8 swap-api + 5 indexer + os 82 da T4.1/T4.8)
$ timeout 290 uv run pytest services/meme-worker/tests/test_features.py …test_tracker.py …test_paper_engine.py …test_proposals.py …test_tracker_priority.py …test_features_tape.py …test_boards.py …test_trades.py …test_sources.py -q
89 passed in 1.96s                           (30 novos: tracker/causa-raiz 7, features/look-ahead 9, boards 6, trades 4, fontes 4)
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_sources_service.py apps/api/tests/unit/test_meme_service.py apps/api/tests/unit/test_meme_lab_service.py -q
31 passed in 0.44s
$ timeout 290 uv run pytest packages/core/tests/unit -q
1330 passed, 1 failed → test_no_raw_engine_begin: a linha 7 do docstring de repo.py (herdada da T4.2, igual no HEAD) menciona ``engine.begin()`` em prosa; reformulada → 6 passed

$ timeout 590 uv run pytest services/meme-worker/tests/test_boards_trades_persistence.py -q      # testcontainer, head = 0023
8 passed in 19.88s
$ timeout 590 uv run pytest services/meme-worker/tests/test_persistence.py services/meme-worker/tests/test_lab_persistence.py -q
1 failed, 21 passed → o teste da T4.2 afirmava que um mint migrado não volta; agora volta para a leitura final (asserção atualizada)
$ timeout 590 uv run pytest services/meme-worker/tests/test_persistence.py -q      # depois da asserção atualizada
10 passed in 20.02s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q
142 passed in 419.14s (0:06:59)               (a primeira rodada completa deu 140 + 2 falhas: meu teste inseria holders=3 sem motivo esperando recusa — a forma legal do CHECK; corrigido para a forma ilegal, holders NULL sem motivo)
$ timeout 590 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q
57 passed in 177.27s (0:02:57)

$ timeout 290 uv run ruff check <tudo> → All checks passed!
$ timeout 290 uv run ruff format --check <tudo> → already formatted
$ timeout 290 uv run pyright <tudo> → 0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py → scanned 739 files; 0 over budget, 0 grandfathered
```

## Decisões que vale registrar

1. **`meme_trades.commitment` anulável na 0023** (não editei a 0021): o `swap-api` não declara
   finalidade; escrever `confirmed` seria o MUST-FIX 2 ao contrário. `slot` provado por RPC;
   `event_index` = ordinal no lote; `outer/inner_ix_index`, `is_mayhem_agent` = NULL (emenda 2).
2. **Salto de versão para a frente é aceito** no trenches (medido no `graduating`); só retrocesso,
   versão parada ou mint desconhecido ressincronizam. Exigir contiguidade teria ressincronizado 8×
   em 30 s.
3. **`creator_sold` virou coluna da fita** (qualquer venda do criador; ausência `no_trade_feed`) e
   `creator_net_seller` nasceu ao lado (o insumo da EXP-M1). `no_sells` entrou no vocabulário
   (+ `NullReason` da API); `trenches_ws` entrou em `first_seen_source` (+ `MemeSource`).
4. **Leitura final antes da expulsão** (`final_read_pending`) e **descarte de cotação ≠ SOL** na
   primeira recusa — as duas correções do adendo, com teste que reproduz o cenário de produção.
5. **Prioridade única** (poll, fita, risco): aposta aberta > leitura final > `graduating` > `new` >
   jovem > resto; a fita tem intervalos 10/10/20/60 s e gasta 1/6 do orçamento por ciclo de 10 s.
6. **O scratchpad da sessão tem 245 caracteres** e o Python do Windows não abre arquivos nele
   (MAX_PATH); os scripts de captura ficaram em `C:/Users/evert/AppData/Local/Temp/t42c/`.

## Preocupações / pendências

1. **A porta da EXP-M1 ainda não consome as colunas novas**: `lab_repo.load_gate_rows` passa
   `curve_volume_1m_sol=None` e lê `creator_sold` como `creator_net_seller`. São dois ajustes de uma
   linha em `lab_repo.py` (selecionar `f.curve_volume_1m_sol` e `f.creator_net_seller`), fora do
   escopo por regra do brief ("não tocar `lab*.py`"). Até lá `lab_gate_refusals` mostra
   `curve_volume_1m_unknown`.
2. **`trenches_graduating.json` tem 7 deltas, não ≥ 20**: o board não muda 20 vezes em 30 s (três
   capturas de 30 s: 7, 2, 5). A regra de versão que ele revelou vale mais que a contagem.
3. **`meme_trades.price` é `numeric(28,10)`** (0021): um preço de 4,3e-8 SOL fica com 3 dígitos
   significativos; `sol_lamports`/`token_amount` são exatos e recompõem o preço (emenda 2).
4. **`event_index` no lote**: uma tx com dois trades separada entre dois pulls daria dois ordinais
   0 e o segundo cairia no `DO NOTHING`. 0/230 txs capturadas têm mais de um trade; declarado.
5. **`pnpm gen:types` não rodado** (`apps/web` intocado): `GET /meme/sources`, `trenches_ws` e
   `no_sells` ainda não estão em `packages/shared-types`.
6. **Volume de `meme_board_observations`**: ~4 boards × ~50 mints × 1 440 min ≈ 100 M linhas/ano
   antes da retenção de 90 dias (~25 M vivas); partição mensal + `DROP`, mas vale medir na VPS.
7. Astra não consultada (`SendMessage` desabilitado); revisão do diff foi minha.
