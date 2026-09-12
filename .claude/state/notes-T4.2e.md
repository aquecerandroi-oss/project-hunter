# T4.2e — o denominador das curvas Mayhem (`MayhemState`) e a cobertura da fita (migração `0025_meme_mayhem_denominator`)

Execução de 12/09/2026, das ~08:40 às ~09:50 BRT (UTC−3). Papel: exchange-integration.
Sem commit (o orquestrador commita por pathspec). Nada real: nenhuma ordem, nenhuma chave, nenhum
`.env`, nenhum acesso à VPS. Toda captura ao vivo foi pública e anônima: **4 chamadas RPC** de 10
permitidas (`api.mainnet-beta.solana.com`, `finalized`), 9 GETs no `frontend-api-v3` (limite 60/60 s),
6 no `advanced-indexer` (60/60 s), 1 no `swap-api` (1000/60 s) — carimbos em
`packages/exchange-adapters/tests/fixtures/pumpfun/t42e_capture_http_log.json`.

**Antes de mim, na árvore (não são meus, não tocados):** `.claude/launch.json`, `docs/DESIGN.md`,
`.claude/state/exp-drafts/dp19/*`, `.claude/state/astra-*`, `.claude/state/design/**`. As fixtures
`frontend_api_v3_coin_by_mint_response_{raw.json,headers.txt}` (T4.1/T4.2d) continuam **untracked** —
`test_curve_rows.py` e `test_pumpfun_clients.py` dependem delas; o commit por pathspec precisa levá-las.

## Scratchpad

O Python do Windows não abre arquivos no scratchpad da sessão (260 caracteres, MAX_PATH — o mesmo achado
da T4.2c): os scripts de captura e as saídas cruas ficaram em `C:/Users/evert/AppData/Local/Temp/t42e/`
(`capture_mayhem.py`, `analyze_and_extra.py`, `capture_stable.py`, `out/`). O que vale como evidência
foi copiado para as fixtures `t42e_*` do adaptador.

## Arquivos

**Adaptador** — novo `packages/exchange-adapters/hunter_exchanges/pumpfun/mayhem_state.py` (PDAs pelas
seeds da IDL do Pump: `["mayhem-state", mint]`, `["global-params"]`, `["sol-vault"]` no programa
`MAyh…`, cofre = ATA de `sol-vault` sob Token-2022; discriminadores pela convenção Anchor;
`decode_mayhem_state` (106 bytes: u64 início, u64 fim, pubkey mint, i128 SOL líquido, i128 tokens
líquidos vendidos, cauda crua), `decode_token_account_amount`, `decode_mint_supply`,
`mayhem_flow_from_accounts` com a identidade `cofre + líquido = supply_do_mint − supply_da_curva` e
`MayhemRefused` por nome, `NormalizedMayhemFlow`); `rpc.py` (`_call` compartilhado, `get_mayhem_flows`:
`getMultipleAccounts`, 25 mints = 100 contas por chamada, `MayhemFlowBatch` com recusas nomeadas).
Testes `tests/unit/test_pumpfun_mayhem_state.py` (8). Fixtures `tests/fixtures/pumpfun/t42e_*` (17).

**Migração** — `infra/migrations/versions/0025_meme_mayhem_denominator.py`, `ddl/meme_mayhem.py`
(um CHECK alargado com `NOT VALID` + `VALIDATE`; guarda de descida conta linhas `mayhem_state`);
modelo `packages/core/hunter_core/db/models/meme.py`; `packages/core/tests/integration/test_migrations.py`
(HEAD → `0025`, `MEME_GRADUATION_REVISION`, os dois testes da 0024 que usavam `"-1"` restageados,
+3 `test_0025_*`).

**Worker** (`services/meme-worker/hunter_meme_worker/`) — novo `mayhem.py` (laço: uma vez por minuto,
as Mayhem rastreadas sem denominador, 25 por chamada; snapshot `solana_rpc` do mesmo slot via
`collect.persist_reading(count_request=False)`; escreve `initial_real_token_reserves` +
`progress_denominator_source = mayhem_state`; recusas contadas por nome). Modificados: `graduation.py`
(`MAYHEM_STATE`, `is_mayhem`, `denominator_for` — uma fotografia Mayhem não reivindica nada, nem
`observed_virgin`; `mayhem_denominator(flow, params)`; `curve_signals` sem `curve_filled` para Mayhem),
`trades.py` (pulls concorrentes com semáforo atrás do bucket; `not_planned` → `tape_reason = not_polled`;
`coverage_for(mint, end_time)` com frescor de 180 s; `covered_since` = *receive time* da 1.ª página;
`stats`), `fold.py` (`coverage_for`; `record_fold`), `sources.py` (campos de cobertura e do ciclo da
fita, `mayhem_*`), `wiring.py` (concorrência, `clock=utcnow`, estatísticas do ciclo), `main.py` (tarefa
`meme-mayhem`), `config.py` (`trades_concurrency`/`MEME_TRADES_CONCURRENCY`, `tape_stale_s`,
`mayhem_cycle_s`, `mayhem_batch`), `context.py` (`ChainSource.get_mayhem_flows`), `collect.py`
(`persist_reading` público), `features.py` (docstring), **`repo.py` (bug: `_UPSERT_TOKEN` nunca inseria
`mayhem_state`/`mayhem_mode` — corrigido com o `CASE` do CHECK)**. Testes novos: `tests/test_mayhem.py`
(6), `test_mayhem_tape_persistence.py` (testcontainer, 3); ajustados: `test_graduation.py` (+4, 1
invertido com justificativa), `test_curve_rows.py`, `test_trades.py` (+3, 1 asserção ajustada),
`test_sources.py` (+1), `test_lab_persistence.py` (1 linha: o helper violava o CHECK da 0024 desde a
T4.2d — quebra pré-existente, 10/12 falhavam).

**API** — `apps/api/hunter_api/schemas/meme.py` (`ProgressDenominatorSource` + `mayhem_state`),
`schemas/meme_sources.py` (`progress_coverage_pct`, `tape_coverage_pct`, `fold_minute`, `fold_rows`,
`tape_*`, `mayhem_pending`, `mayhem_denominators_60s`, `COVERAGE_EXPLANATION`), `services/meme_sources.py`;
testes `tests/unit/test_meme_sources_service.py` (+1), `test_meme_service.py` (+1).

**SQL do orquestrador** — `infra/scripts/sql/research/2026-09-12-t42e-cobertura.sql` (somente leitura;
§1 cobertura por minuto, §2 motivos, §3 denominador por fonte × Mayhem, §4 progresso negativo, §5 o laço
Mayhem rodou?, §6 lacunas). **Não executado** (sem VPS); sintaxe conferida contra o padrão dp24.

**Docs** — `docs/PUMPFUN-ONCHAIN.md` §3.5 (novo), `docs/PUMPFUN.md` §4.2.1, `docs/plans/T4-MEME-RADAR.md`
§T4.2e, `docs/DATABASE.md` §37, `docs/DEPLOYMENT.md` (`MEME_TRADES_CONCURRENCY`),
`docs/EXCHANGE_INTEGRATION.md` §9, `docs/PIPELINE.md` §1e.

## O que foi medido ao vivo (BRT) e o que prova

- **08:43:50–08:44:0x** `/coins/{2sduGq}`, `/in-memory-coin/{2sduGq}`, `/coins/mayhem-mode?limit=2&
  mayhemState=active` (4BTP…, 8pzW…), `/coins` + `/in-memory-coin` dos dois; RPC #1 `getAccountInfo` da
  conta de IDL Anchor do programa Mayhem (`Acy6P7…` = `create_with_seed(find_program_address([], MAyh),
  "anchor:idl", MAyh)`) → **`value: null`**; RPC #2 `getMultipleAccounts` de 14 contas (`global-params`,
  `sol-vault`, e curva + `mayhem-state` + cofre + mint dos 3 mints), slot 446421000.
- **08:52:24** RPC #3 (668Q…, pausada): slot 446422623. **08:54:19** RPC #4 (Fh42k…, a fixture da T4.1,
  6,5 h depois): slot 446422983; `swap-api` num mint com 4 s de vida → 200 com 1 trade (fita de mint
  recém-criado **não** falha — não é a causa da ausência de fita).
- **Discriminadores:** `sha256("account:MayhemState")[:8] = b1fdbf7dcb16866b` e
  `sha256("account:GlobalParams")[:8] = 79c1f857c3384c0b` — iguais aos bytes lidos (4/4 e 1/1).
- **`sol-vault` = `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`**, a carteira do agente publicada
  (explica o `signer:false` da A4.1b §5.2).
- **Identidade (5/5, até a subunidade):** `cofre + i128@72 = supply_do_mint (2 B) − token_total_supply
  (1 B)`; `mayhem_state[24:56] == mint` (5/5); `fim − início = 86 400 s` (5/5).
- **`2sduGq…`:** `822 644 036,902123 = 793 100 000 + 29 544 036,902123` → humanos líquido 0 (e
  `real_sol` = 1 lamport); **`4BTP…`:** site 3,43 % vs chain 3,4285 % (0,002 pp); `8pzW…` (auto) e
  `668Q…` moveram 108 M / 74 M tokens entre a REST e o RPC → inconclusivos, declarados; **`Fh42k…`:**
  1 713 296 709 tokens na curva (2,16× o inicial), o agente vendeu 999 999 991,75 do bilhão.
- **Não há moeda pausada estável** (0 de 50 sem trade há > 30 min): a lista `paused` é de moedas recentes.

## Decisões

1. **O denominador de uma curva Mayhem é o do registro** (`/global-params`), não um número novo: o
   que a T4.2d viu como "mais tokens que o inicial" é o bilhão do agente vendido líquido. `mayhem_state`
   = "o inicial do registro, escrito só depois de a identidade on-chain fechar naquele slot".
2. **Fotografia REST de Mayhem não reivindica nada** — nem `observed_virgin` (a T4.2d aceitava; a
   fixture estava a 1 lamport com 29,5 M do agente dentro). Inverti esse teste com justificativa.
3. **Layout de `MayhemState` é inferido** (sem IDL em lugar algum) e **validado em toda leitura** pela
   identidade sem constante; uma leitura que não fecha é recusada por nome, nunca um número.
4. **Progresso negativo é guardado** (o site trunca em 0); a fórmula `1 − rt/inicial` não mudou, logo
   `meme_features_v2` continua (o denominador é dado do token). O portão recusa por `progress_below_min`.
5. **`curve_filled_seen_at` não é reivindicado para Mayhem** (`set_mayhem_virtual_params` move o SOL
   virtual: 0,46–27,9 SOL nas cinco curvas contra os 30 do registro).
6. **Fita:** a causa estrutural é o `pull_once` sequencial (250 × ~0,35 s ≈ 90 s por "ciclo de 10 s";
   `used_60s ≈ 170 = 250 ÷ 90 s`), somada ao reinício do deploy 3 min antes da medição (cobertura em
   memória zera por desenho). Correção: concorrência 8 atrás do bucket; `not_polled` para o que o teto
   deixa de fora; frescor de 180 s (uma fita sem leitura recente não é um zero); `covered_since` no
   *receive time* (um pull que cruza o fecho do minuto não cobre esse minuto).
7. **`tape_reason = not_polled` reaproveita a palavra do vocabulário** (mesmo fato, mesma palavra) —
   sem migração nem `NullReason` novo.
8. **Um lote RPC conta uma requisição** em `used_60s` (`persist_reading(count_request=False)`).

## Comandos e saídas reais

```
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42e/capture_mayhem.py      # 08:43:50 BRT
[front_coin_2sduGq] 200 281ms 1990B · [indexer_in_memory_coin_2sduGq] 200 · [front_mayhem_list] 200 · ×2 coins/indexer 200
mayhem idl address Acy6P7eBsmrzz7pxakoGkxhEB9Hcr9XzSJj8RD7yvQS4 · [rpc_mayhem_idl] rpc getAccountInfo 200 → no IDL account on chain
[rpc_mayhem_accounts] rpc getMultipleAccounts 200 6047B · slot 446421000
  global_params 13ec7X… owner=MAyh… len=318 disc=79c1f857c3384c0b · sol_vault BwWK17c… (System, len 0)
  bc:2sduGq… {'vt': 1102544036902123, 'vs': 3082705753, 'rt': 822644036902123, 'rs': 1, 'supply': 1000000000000000, 'is_mayhem': 1}
  ms:2sduGq… owner=MAyh… len=106 disc=b1fdbf7dcb16866b · vault amount 970455963097877 · mint supply 2000000000000000 decimals 6
  bc:4BTP… rt=765908543509630 · vault 1009988703539400 · bc:8pzW… rt=636607348093183 · vault 994329931006619
== 2sduGq… INDEXER progress=0 botSupplied=14.39 state=paused mode=manual
== 4BTP…   INDEXER progress=3.43 state=active mode=manual · == 8pzW… INDEXER progress=24.7 mode=auto
rpc calls: 2
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42e/analyze_and_extra.py   # 08:52:24 BRT
  account:MayhemState -> b1fdbf7dcb16866b · account:GlobalParams -> 79c1f857c3384c0b
== 2sduGq… ms.pubkey == mint? True · I1 1000000000000000 == 1000000000000000 -> True · I2 rt - token_net = 793100000000000 <= 793100000000000 -> True; human_net = 0 · progress on-chain = -3.7251 %
== 4BTP…   sol_net=20081941 token_net=-9988703539400 · I1 True · I2 True; human_net = 17202752950970 · progress on-chain = 3.4285 %
== 8pzW…   sol_net=-1008905453 token_net=5670068993381 · I1 True · I2 True · progress on-chain = 19.7318 %
[rpc_mayhem_accounts_paused] rpc 200 · == 668Q… INDEXER progress=8.82 · progress from REST rt = 3.5582 % · on-chain 12.9650 % · I1 True · I2 True
rpc calls total: 3
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42e/capture_stable.py       # 08:54:19 BRT
[front_mayhem_list_paused50] 200 95915B {'x-ratelimit-limit': '60', 'x-ratelimit-remaining': '59'} · stable candidates: 0
[rpc_mayhem_accounts_stable] rpc 200 · slot 446422983 · == Fh42k… on-chain rt=1713296709488602 token_net=999999991751764 vault=8248236 supply=2000000000000000 progress=-116.0253%
newest mint FUoPtt… age_s 4 · [swap_api_trades_fresh] 200 1326B {'x-ratelimit-limit': '1000', 'x-ratelimit-remaining': '908'} → 1 trade
rpc calls total: 4

$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_mayhem_state.py packages/exchange-adapters/tests/unit/test_pumpfun_clients.py -q
1 failed, 26 passed   (meu bug: decode_bonding_curve_account(*_account_data()) passava owner posicional; corrigido)
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/ -q -k pumpfun
129 passed, 375 deselected in 3.17s
$ timeout 290 uv run pytest services/meme-worker/tests -q --ignore=<5 testcontainer>
1 failed, 131 passed   (used_60s do RPC contava 3 para 1 chamada em lote → persist_reading(count_request=False))
132 passed in 1.98s
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_service.py apps/api/tests/unit/test_meme_sources_service.py apps/api/tests/unit/test_meme_lab_service.py -q
37 passed in 0.42s
$ timeout 290 uv run pytest packages/core/tests/unit -q
1331 passed in 70.94s

$ timeout 590 uv run pytest services/meme-worker/tests/test_mayhem_tape_persistence.py -q      # testcontainer, head = 0025, sozinho
1 failed, 2 passed  → mayhem_state NULL após load_tracked: repo._UPSERT_TOKEN nunca inseria mayhem_state/mayhem_mode (bug pré-existente); corrigido
3 passed in 18.08s
$ timeout 590 uv run pytest services/meme-worker/tests/test_persistence.py -q
10 passed in 20.12s
$ timeout 590 uv run pytest services/meme-worker/tests/test_boards_trades_persistence.py -q
1 failed, 7 passed  → o teste monta TapeCoverage(covered_since=…) sem ok_times; covered_since passou a valer como 1.º ok
8 passed in 19.85s
$ timeout 590 uv run pytest services/meme-worker/tests/test_graduation_persistence.py -q
4 passed in 16.21s
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q
10 failed, 2 passed → ck_meme_tokens_a_denominator_names_its_source: o helper _token do teste insere o denominador sem fonte desde a 0024 (T4.2d); +1 linha
12 passed in 87.85s (0:01:27)
$ timeout 590 uv run pytest apps/api/tests/integration/test_meme_repository.py -q
18 passed in 12.80s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0025 or 0024"
8 passed, 142 deselected in 37.65s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q
150 passed in 450.83s (0:07:30)
$ timeout 590 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q
57 passed in 174.59s (0:02:54)

$ timeout 290 uv run ruff check <tudo que toquei>         → All checks passed!   (1 RUF100 corrigido com --fix)
$ timeout 290 uv run ruff format --check <idem>           → 50 files already formatted   (9 reformatados por `ruff format`)
$ timeout 290 uv run pyright services/meme-worker <adaptador> <api> <migração> <core> → 0 errors, 0 warnings, 0 informations   (antes: 3 — isinstance redundante, variável não usada, Optional em max(); corrigidos)
$ timeout 290 uv run python infra/scripts/check_file_size.py → scanned 744 files; 0 over budget, 0 grandfathered
```

`git status --porcelain` do que toquei: 31 ` M` + 24 `??` (lista completa na saída acima do relatório;
inclui as 17 fixtures `t42e_*`, `mayhem_state.py`, `mayhem.py`, `test_mayhem.py`,
`test_mayhem_tape_persistence.py`, `test_pumpfun_mayhem_state.py`, `ddl/meme_mayhem.py`,
`0025_meme_mayhem_denominator.py`, `2026-09-12-t42e-cobertura.sql`).

## Preocupações / pendências

1. **`apps/web` fora do escopo e `pnpm gen:types` não rodado:** `components/meme/labels.ts` tipa
   `Record<MemeDenominatorSource, string>` exaustivo — gerar os tipos sem acrescentar o rótulo
   `mayhem_state` quebra o typecheck do web; em runtime, o rótulo sai `undefined` (vazio) para
   `mayhem_state` até a tela ganhar o texto. `MemeSourcesOut` também tem 12 campos novos sem tipo gerado.
2. **A prova do "≤ 0,5 pp" tem dois pontos limpos** (`2sduGq…` truncado em 0; `4BTP…` 0,002 pp) e dois
   inconclusivos por leitura não atômica de curvas em movimento (`8pzW…`, `668Q…`) — declarados, não
   suavizados; não achei moeda Mayhem estável com 0 < progresso < 100 dentro do orçamento.
3. **O layout de `MayhemState` é inferido**, não lido de IDL (não existe); a identidade por leitura é o
   que impede um número errado — se o programa mudar o layout, o laço passa a recusar (`malformed`/
   `identity_failed`) e `mayhem_pending` sobe no heartbeat, nunca um denominador falso.
4. **Progresso negativo em `meme_features_1m`**: legal pelo §15.8 (sem CHECK de domínio), o portão recusa
   por `progress_below_min`; qualquer leitor que assuma `[0, 1]` (gráficos do web) verá valores abaixo de 0.
5. **O diagnóstico da fita é por leitura de código + git** (sequencial ≈ 90 s/ciclo; deploy 3 min antes),
   não por medição na VPS (proibida). A prova fica com o orquestrador: SQL antes × depois + heartbeat
   `tape_cycle_s`/`tape_coverage_pct`. Se o `tape_cycle_s` cair para ~10 s e a cobertura não subir, a causa
   é outra e os campos novos (`tape_never_pulled`, `tape_deferred_60s`, `errors_1h`) dizem qual.
6. **`mayhem_state` só é detectado pela palavra REST** (`tracked.mayhem_state`); um mint cujo REST omitir o
   estado do agente não entra no laço — a curva on-chain (`is_mayhem_mode`) diria, mas custaria uma
   leitura por mint. Declarado; o SQL §3 mostra quantas Mayhem ficam sem `mayhem_state`.
7. **Bug pré-existente corrigido de passagem** (`repo._UPSERT_TOKEN` sem `mayhem_state`/`mayhem_mode`):
   linhas antigas de `meme_tokens` continuam com NULL; os snapshots têm o estado. Sem backfill (fora do
   escopo; o SQL §3 separa Mayhem por `mayhem_state` **ou** `mayhem_enabled`).
8. **`test_lab_persistence.py` estava quebrado desde a T4.2d** (10/12) — corrigi o helper (1 linha, arquivo
   de teste, fora da lista proibida); o orquestrador decide se leva no mesmo commit.
9. Astra não consultada (`SendMessage` desabilitado); a revisão do diff foi minha.

## Medição do orquestrador — ANTES × DEPOIS na VPS (12/09/2026)

`infra/scripts/sql/research/2026-09-12-t42e-cobertura.sql` via `docker exec -i hunter-postgres-1 psql`.

**ANTES** (imagem `eeb566c`, leitura 09:50 BRT, minutos 12:43–12:49Z): linhas do portão 122–140/min; **com progresso 12–34 %** (15/122 … 47/140); **com fita 36–54 %**; `progress_denominator_source`: global_params 550, observed_virgin 152 (+9 Mayhem), unknown 1 340 Mayhem; `mayhem_state` escritos: 0; lacunas `curve_poll/budget_exhausted`: 13 em 15 min (780 mints não alcançados).

**DEPOIS** (imagem `8478eef`, deploy 09:50–09:53 BRT, leitura 10:00 BRT, ≥ 5 min após o restart): worker 0 restarts, 0 `meme_loop_failed`, 0 tracebacks; heartbeat `progress_coverage_pct` **43,3**, `tape_coverage_pct` **38,8**, `tape_cycle_s` 4,0 (era ~90 s por ciclo), `swap_api_used_60s` 238; `mayhem_state` escritos: **57** (12:51:52Z → 12:55:56Z, 16–19/min); denominador: global_params 602, observed_virgin 153+9, mayhem_state 57, unknown 1 720 padrão + 1 321 Mayhem (histórico, sem backfill); §4 progresso negativo em 17 linhas Mayhem (mín −41,31 %, mediana −1,21 %) — o portão recusa por `progress_below_min`, não por `unknown`; laço: 262 linhas/tick, `progress_unknown` 113 → **74**, `curve_volume_1m_unknown` 109 → **70**, `creator_is_net_seller` 7 → 23, `curve_volume_1m_zero` 15 → 55 (a fita agora diz "zero" em vez de "desconhecido").

**O que ficou (para a T4.2f):** §2a — a razão dominante de progresso ausente é **`not_polled` 1 267 linhas/15 min** (o poll REST de 60 req/min não alcança 130 mints) e não mais o denominador (213); §2b — a razão dominante de fita ausente é **`rate_limited` 1 069 linhas/15 min** com ~238 req/min usadas: o limite real do `swap-api` é ≈ 240/min por IP (não os 1 000/60 s documentados) e as páginas extras dos mints quentes consomem o resto.
