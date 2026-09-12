# T4.2f — cobertura total: a curva de TODOS os rastreados por `getMultipleAccounts` e o limite real do swap-api

Execução de 12/09/2026, início ~10:30 BRT (13:30 UTC). Papel: exchange-integration. Tentativa anterior cortada
antes de escrever qualquer coisa; esta começa do zero. Sem commit (o orquestrador commita por pathspec). Nada real:
nenhuma ordem, nenhuma chave, nenhum `.env`, nenhum acesso à VPS. Estas notas são escritas **incrementalmente**
(cada comando e saída real logo depois de rodar).

**Antes de mim, na árvore (não são meus, não tocados):** `.claude/launch.json`, `docs/DESIGN.md`,
`apps/web/**` (T4.3b, parcial, 5 ` M` + 2 `??` — não incluir em nada), `.claude/state/astra-*`,
`.claude/state/design/**`, `.claude/state/exp-drafts/**`, `.claude/state/tmp/**`, `.claude/state/t346/`,
`tests/e2e/design-audit.*`. HEAD = `731b24a`.

## Leitura (13:30–13:45 UTC)

Lidos por inteiro: o brief, `notes-T4.2e.md`, `notes-T4.2c.md`, `collect/tracker/trades/fold/sources/config/repo/
mayhem/wiring/main/context/curve_rows/features/graduation/features_tape/repo_tape/repo_rows.py` do worker,
`pumpfun/{rpc,decode,swap_api,rate_shared,rest,normalize,models,mayhem_state,tx(head)}.py` e `rate_limit.py` do
adaptador, `docs/PUMPFUN.md` §1.4/§2/§5, `docs/PUMPFUN-ONCHAIN.md` (todo), `docs/EXCHANGE_INTEGRATION.md`,
`docs/PIPELINE.md` §1e, `docs/plans/T4-MEME-RADAR.md` §T4.2e, `docs/DEPLOYMENT.md` (env meme), o SQL da T4.2e,
`t42e_capture_http_log.json` (o único cabeçalho do swap-api capturado: `x-ratelimit-limit: 1000`, `remaining: 908`,
`reset: 20`).

## Plano (o que vou construir)

1. Adaptador: `SolanaRpcClient.get_curve_states(mints)` — `getMultipleAccounts` de 100 PDAs `["bonding-curve", mint]`
   (`tx.bonding_curve_address`, já usado pelo laço Mayhem) por chamada + `getBlockTime(slot)` por slot distinto;
   `observed_at` = blockTime (senão `received_at`, contado como `block_time_missing`); recusas por nome
   (`curve_not_found`, `unsupported_quote`, `malformed`).
2. Worker: laço `chain.py` (`meme-chain`, 60 s) sobre todos os rastreados → `persist_reading(count_request=False)`
   (mesmo caminho da T4.2d: denominador, sinais de conclusão, tracker, fold); o poll REST vira
   identidade/mayhem/fallback (`tracker.plan(..., chain_covered=True)`: aposta aberta, leitura final, nunca lido
   pela REST, Mayhem `active/paused` sem leitura REST há ≥ 5 min); plano cheio quando o laço da cadeia falhou.
3. swap-api: sonda ao vivo até a 1.ª 429 (cabeçalhos), `MEASURED_LIMIT` = o medido, default de
   `MEME_SWAP_API_BUDGET_60S` = 90 % dele; bucket adaptativo (429 real encolhe o orçamento efetivo para o usado
   observado); 1 página por mint por minuto, paginação só para apostas abertas; `tape_reason` honesto
   (`rate_limited` só com 429 real; `not_polled` quando o teto deixou de fora, mesmo se já coberto antes).
4. Prova: `2026-09-12-t42f-cobertura.sql`, campos novos no heartbeat, testes unit + 1 testcontainer, docs.

## Capturas ao vivo (BRT = UTC − 3)

### RPC em lote (10:07 e 10:36 BRT) — `C:/Users/evert/AppData/Local/Temp/t42f/capture_rpc.py`

A tentativa cortada já tinha gasto **4 chamadas RPC** (2 × 403 — o RPC público recusa o `Origin`/`User-Agent` do site
— e 2 × 200 às 13:07:58/59 UTC) e 2 GETs em `/coins` (140 mints mais novos, 70 por página). O script reaproveita o
que está em disco e só faz os `getBlockTime`. Saída real (13:36 UTC):

```
coins listed: 140 distinct mints: 140
derived bonding-curve PDA == REST bonding_curve: 140/140; mismatches=[]
[rpc_curves_batch1] reused the saved response (200 at 2026-09-12T13:07:58+00:00, 467 ms, 34591 B)
  batch1: slot=446436963 accounts=100 null=0 decoded=100 complete=2 mayhem=35 refused={}
[rpc_curves_batch2] reused the saved response (200 at 2026-09-12T13:07:59+00:00, 187 ms, 14072 B)
  batch2: slot=446436965 accounts=41 null=0 decoded=40 complete=0 mayhem=17 refused={'MalformedMessage: owner=1111…1111 len=0 lamports=1400010000': 1}
[rpc_block_time_batch1] 200 437ms 45B rl={'x-ratelimit-tier': 'free', 'x-ratelimit-method-limit': '10', 'x-ratelimit-method-remaining': '9', 'x-ratelimit-rps-limit': '250', …, 'x-ratelimit-conn-limit': '40', …}
  getBlockTime(446436963) -> 1789218467 = 2026-09-12T13:07:47+00:00
[rpc_block_time_batch2] 200 140ms 45B rl={… 'x-ratelimit-method-limit': '10', 'x-ratelimit-method-remaining': '8' …}
  getBlockTime(446436965) -> 1789218468 = 2026-09-12T13:07:48+00:00
chain == REST reserves (exact, non-atomic): 113; differ: 27
rpc calls: 2
```

Total RPC desta tarefa: **6 de 10** (4 da tentativa cortada + 2 minhas). O que prova: (a) a PDA
`["bonding-curve", mint]` derivada bate com o `bonding_curve` da REST em 140/140 — o laço pode ler **qualquer**
rastreado sem depender do frame do PumpPortal; (b) 100 contas numa chamada, 467 ms, 34,6 KB; (c) a conta-sonda
inexistente vem como `owner = System, len 0` (não `null`) → o decodificador recusa por owner; (d) o RPC público
devolve **cabeçalhos próprios**: `x-ratelimit-method-limit: 10`/10 s (não 40) e `x-ratelimit-rps-limit: 250`
— o teto por método é mais apertado do que a doc de `solana.com/docs/references/clusters` dizia (40); (e) o
blockTime do slot finalizado fica **~11 s atrás** do `received_at` (13:07:47 vs 13:07:58): `observed_at` =
blockTime é o instante honesto do estado; (f) REST e cadeia coincidem exatamente em 113/140 (leituras não atômicas,
30 s de distância).

### swap-api — a primeira 429 (10:36–10:41 BRT) — `probe_swap_api.py`

Primeira rodada (script antigo, 4 workers): `requests 33 ok 30 in 2.6s (12.9/s)` → 429 na 33.ª (o script quebrou
antes de gravar; refeito em fases). Rodada em fases, saída real:

```
[A_burst] requests 28 ok 27 in 1.7s (16.09/s) workers 4
  x-ratelimit-limit values: ['1000', 'None']; remaining first/last: ['931', '948', '951'] … ['929', '940', None]
  FIRST 429 at #28 t=1.74s; ok before: 27
  429 headers: {"retry-after": "60", "cf-ray": "a39f4f1d3c7c501a-GRU", "server": "cloudflare", "content-type": "application/json; charset=utf-8"}
  429 body: {"type":"https://developers.cloudflare.com/…/error-1015/","title":"Error 1015: You are being rate limited","status":429,"detail":"You are being rate-limited by the website owner's configuration.",…}
  recovery (60 s depois): 200, x-ratelimit-limit 1000, remaining 891, reset 35
[B_paced_4ps] requests 20 ok 19 in 5.8s (3.47/s) workers 2 → FIRST 429 at #20 t=5.5s (19 ok + 1 GET de recuperação = 20 na janela)
[C_paced_8ps] requests 20 ok 19 in 3.3s (6.01/s) workers 4 → FIRST 429 at #20 t=3.0s (idem: 20 na janela)
saved; total requests 68
```

**Leitura:** o limitador da aplicação (`x-ratelimit-limit: 1000`, janela de 60 s, `remaining` ~900) **não é** o que
recusa; quem recusa é uma **regra de rate limiting do Cloudflare (erro 1015)** por IP: ~**20 requisições por
janela curta**, bloqueio de **60 s** (`retry-after: 60`), sem cabeçalho `x-ratelimit-*` na 429 (a rajada de 16/s
passou 27 antes do corte — contadores distribuídos do CF). É isso que produz os `rate_limited` 1 069/15 min da
T4.2e: o puller dispara 8 em paralelo, o CF corta na ~20.ª, o bucket entra em cooldown de 60 s → ~20 OK/min.
Falta o período da janela (10 s ou 60 s?) → sonda 2.

### swap-api — sondas 2 e 3 (10:43–10:48 BRT): o período e o escopo da regra

```
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42f/probe_swap_api2.py 30     # 13:43 UTC, janela limpa
[D_paced_0.7ps] requests 23 ok 22 in 27.1s (0.85/s) workers 1
  FIRST 429 at #23 t=27.1s; ok before: 22; ok in the 10 s before: 8; in the 60 s before: 22
  429 headers: {"retry-after": "60", "cf-ray": "a39f583b98d01446-GRU", "server": "cloudflare", …}   (erro 1015)
  recovery (60 s): 200, x-ratelimit-limit 1000, remaining 922, reset 59
$ timeout 290 uv run python C:/Users/evert/AppData/Local/Temp/t42f/probe_swap_api3.py 40     # 13:46 UTC, 40 mints DISTINTOS
[F_distinct_mints] requests 24 ok 23 in 20.3s (1.18/s)
  FIRST 429 at #24 t=20.3s mint=G1X3cZ… -> the rule is per IP
  recovery (60 s): 200, remaining 930, reset 5
```

**Conclusão medida (4 sondas, 115 requisições, 5 × 429, todas Cloudflare 1015 com `retry-after: 60`):** a regra
conta **por IP, ~20 requisições por 60 s** (cortes na 20.ª, 20.ª, 23.ª, 24.ª e — na rajada de 16/s — 28.ª;
a 0,85/s só 8 caíram nos 10 s anteriores, logo a janela não é de 10 s), independentemente do mint/rota;
bloqueio de 60 s. O `x-ratelimit-limit: 1000/60 s` do backend nunca é o gargalo. **Consequência aritmética:**
com 130 rastreados e frescor de 180 s (T4.2e), o teto de cobertura da fita por este endpoint e um IP é
≈ 18 × 3 ÷ 130 ≈ **41 %** (a T4.2e mediu 38,8 %); a meta de ≥ 80 % exigiria ≥ 35 leituras/min — impossível
neste IP. O que dá para entregar: ritmo que **nunca** dispara o 1015 (cada 429 custa 60 s de apagão total,
pior do que o ritmo), `not_polled` honesto para o resto, e a opção seguinte nomeada
(`POST /v1/coins/market-activity/batch`: N mints em 1 requisição, janelas 5m/1h — feature diferente, USD).

## Arquivos (o que é meu)

**Adaptador** (`packages/exchange-adapters/hunter_exchanges/pumpfun/`): novo `rpc_curves.py` (`CurveBatch`,
`curve_addresses`, `decode_curve_batch`; recusas `curve_not_found` | `unsupported_quote` | `curve_emptied` |
`malformed`); `rpc.py` (`get_curve_states`: 100 PDAs por `getMultipleAccounts` + `getBlockTime` por slot;
`get_block_time`; `METHOD_SPACING_S = 1.0` pelos cabeçalhos do RPC); `rate_shared.py` (`HttpRateLimited` com
`status_code`/`headers`/`edge`, `retry_after_s`); `swap_api.py` (`HEADER_LIMIT 1000`, `MEASURED_LIMIT 20`,
`MEASURED_BLOCK_S 60`, `REQUEST_CAPACITY 16`). Testes: novo `tests/unit/test_pumpfun_rpc_curves.py` (7);
`test_pumpfun_swap_api.py` (+1, 2 ajustados). Fixtures novas (`tests/fixtures/pumpfun/t42f_*`, 7 arquivos):
`rpc_curves_batch{1,2}_{raw,addresses}`, `rpc_block_time_raw`, `swap_api_ratelimit_probes` (5 fases, 138
requisições com cabeçalhos), `capture_http_log`.

**Worker** (`services/meme-worker/hunter_meme_worker/`): novos `chain.py` (laço `meme-chain`), `tape_budget.py`
(`TapeBudget`: cota exata por ciclo com `Fraction`, `record_refusal` mede/encolhe/bloqueia, `TapeCoverage`/
`PullReport`/`TapeStats`); reescrito `trades.py` (1 página por mint, `max_pages` só para aposta aberta, todo tier
a cada 60 s, `HttpRateLimited` ≠ `RateLimited` do bucket, `absence_reason(mint, at=)`); `tracker.py`
(`last_rest_polled_at`, `mark_polled(source=)`, `needs_rest`, `plan(chain_covered=, mayhem_refresh=)`);
`collect.py` (`chain_covered`, plano restrito, `mark_polled` com a fonte, `chain_covered` no detail da lacuna);
`context.py` (`ChainSource.get_curve_states`, `RadarState.chain_ok_at`/`chain_covers`); `config.py`
(`swap_api_budget_60s` 900 → 16, `trades_concurrency` 8 → 2, `chain_curves_enabled`, `chain_cycle_s`,
`chain_batch`, `rest_mayhem_refresh_s`); `sources.py` (`record_chain_cycle`, `record_tape_budget`, 10 campos
novos no heartbeat); `wiring.py` (`MEASURED_LIMIT`, `tape_tiers` com tier jovem, `record_tape_budget`);
`main.py` (`meme-chain` ou `meme-reconcile`, nunca os dois); `fold.py` (1 linha: `absence_reason(..., at=boundary)`).
Testes: novos `tests/test_chain.py` (4), `tests/test_chain_curves_persistence.py` (testcontainer, 2);
`test_trades.py` (+5, 2 ajustados, fake com `HttpRateLimited`), `test_tracker_priority.py` (+1),
`test_sources.py` (+1), `test_mayhem.py` (stub `get_curve_states` no fake, exigido pelo protocolo).

**API**: `apps/api/hunter_api/schemas/meme_sources.py` (9 campos `chain_*`/`swap_api_*`, `COVERAGE_EXPLANATION`),
`services/meme_sources.py`, `tests/unit/test_meme_sources_service.py` (+1).

**SQL**: `infra/scripts/sql/research/2026-09-12-t42f-cobertura.sql` (§1–§6 da T4.2e + §7 fotografias por fonte,
§7b agregado, §8 origem da fotografia dobrada, §9 lacunas com `chain_covered`, §10 fita por minuto). Não executado
(sem VPS); sintaxe no padrão da T4.2e.

**Docs**: `docs/PUMPFUN-ONCHAIN.md` §5.5 (novo), `docs/PUMPFUN.md` §2 (limite real medido), `docs/plans/T4-MEME-RADAR.md`
§T4.2f, `docs/DEPLOYMENT.md` (4 linhas de env), `docs/EXCHANGE_INTEGRATION.md` §9 (2 linhas da tabela),
`docs/PIPELINE.md` §1 (parágrafo T4.2f).

**NÃO são meus (agente concorrente T4.10 — linhas/hype, `meme_features_v3`, `0026` — editando a mesma árvore
durante esta sessão):** `features.py`, `lab.py`, `lab_bets.py`, `lab_models.py`, `lab_repo.py`, `lab_repo_bets.py`,
`paper_engine.py`, `proposals.py`, `repo.py`, e os novos `features_lines.py`, `lab_repo_lines.py`, `lab_values.py`,
`lines_exit.py`, `paper_fill.py`, `proposals_scale.py`, `repo_lines.py`, `tests/test_features_lines.py`,
`tests/test_lines_exit.py`, `tests/test_proposals_scale.py`. `fold.py` e `main.py` têm hunks dos dois (os meus:
`absence_reason(..., at=boundary)`; `meme-chain`/`meme-reconcile` e o log de partida). O commit por pathspec
tem de separar.

## Decisões

1. **`observed_at` = blockTime do slot** (uma chamada `getBlockTime` por slot distinto, ~2/min): a leitura
   `finalized` chega ~11 s depois do estado; carimbar a chegada poria a curva no futuro. Sem blockTime →
   `received_at` e `chain_block_time_missing_60s` no heartbeat (a linha guarda `slot` para recuperar depois).
2. **A PDA é derivada para todo mint** (`tx.bonding_curve_address`, 140/140 contra a REST), não o
   `bonding_curve` do frame — mints vindos dos boards não têm frame.
3. **`curve_emptied` é sinal de conclusão da própria cadeia** (reservas zero + `complete`): marca o tracker
   como concluído com leitura final REST pendente; o adaptador não inventa um `market_cap` de 0/0.
4. **`unsupported_quote` na cadeia expulsa o mint como na REST** — 16 % das moedas novas; sem eles no conjunto,
   o teto de 120/130 sobra para curvas em SOL.
5. **O poll REST não é mais o orçamento da curva**: `plan(chain_covered=True)` só com o que o espelho ensina
   sozinho; `skipped` (e a lacuna `budget_exhausted`) só conta candidatos. Fallback automático em 2 ciclos sem
   cadeia (`RadarState.chain_covers`), inclusive no arranque (o 1.º poll é cheio).
6. **Reconciliação top-K desligada quando o laço da cadeia está ligado** (subconjunto redundante, gastaria
   `getAccountInfo` 20×/5 min por nada).
7. **Fita: 16/60 s em cota exata por ciclo** (`Fraction`, 2-3-3-2-3-3), 1 página por mint por minuto, todo tier
   a cada 60 s, prioridade decide quem ganha os 16. Uma 429 **real** (`HttpRateLimited`) mede o que passou no
   minuto anterior, encolhe para 80 % por 15 min e bloqueia o `retry-after` (uma requisição dentro do bloqueio
   pode estendê-lo); o `RateLimited` do bucket próprio vira `not_polled`, nunca `rate_limited`.
8. **Meta da fita declarada inatingível por este endpoint/IP** (~40 % de teto) — construí o ritmo honesto e
   nomeei a saída; a decisão (2.º IP/proxy ou `market-activity/batch`) é do Everton/orquestrador.
9. Sem migração, sem mudança de vocabulário de `reason` (`insufficient_coverage` cobre `curve_not_found`/
   `curve_emptied`/`malformed` no minuto; documentado no `chain.py`).

## Comandos e saídas reais (11:00–11:20 BRT)

```
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/ -q -p no:cacheprovider -k pumpfun
3 failed, 44 passed  (1.ª rodada dos 4 arquivos: a fixture fresca tem 23 curvas com quote ≠ SOL e 2 curvas esvaziadas pelo migrate — não são bugs: recusas nomeadas `unsupported_quote`/`curve_emptied`; expectativas corrigidas)
140 passed, 375 deselected in 3.49s        (129 da T4.2e + 7 novos em test_pumpfun_rpc_curves.py + 1 em test_pumpfun_swap_api.py + ajustes)
$ timeout 290 uv run pytest services/meme-worker/tests -q -p no:cacheprovider --ignore=<6 testcontainers>
2 failed, 130 passed  (test_trades: intervalos agora 60 s em todo tier; o fake lançava RateLimited do bucket, não a 429 do servidor → HttpRateLimited)
5 failed, 138 passed  (carry em float 2,667+0,333 = 2,999 → Fraction; open bet anda 3 páginas, não 2; ordem no tier: nunca-lido primeiro; budget=0 conta o final read)
143 passed in 2.67s
159 passed in 3.75s                        (rerodado na árvore compartilhada: inclui os 16 testes novos do T4.10)
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_sources_service.py apps/api/tests/unit/test_meme_service.py apps/api/tests/unit/test_meme_lab_service.py -q
38 passed in 0.48s
$ timeout 590 uv run pytest services/meme-worker/tests/test_chain_curves_persistence.py -q      # testcontainer, head = 0025, sozinho
2 failed in 16.72s   (não há curva virgem na captura — 0 de 79 com real_sol = 0; caso removido e documentado)
1 failed, 1 passed   (chain_tracked_mints = 4 no 2.º ciclo: o mint quote ≠ SOL já saiu do conjunto — asserção corrigida)
2 passed in 18.13s
$ timeout 290 uv run ruff check <26 arquivos>          → Found 1 error (1 fixed) → All checks passed!
$ timeout 290 uv run ruff format <26 arquivos>         → 4 files reformatted → 26 files already formatted
$ timeout 290 uv run pyright <26 arquivos>             → 4 errors (Counter[Unknown], import não usado, FakeChain do test_mayhem sem get_curve_states, Optional em datetime −) → 0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py → scanned 757 files; 0 over budget, 0 grandfathered
   (maiores meus: tracker.py 343, sources.py 334, trades.py 326, main.py 325, collect.py 308)
```

CRLF: 7 arquivos meus (`config.py`, `test_tracker_priority.py`, `test_trades.py`, `PUMPFUN.md`, `T4-MEME-RADAR.md`,
`DEPLOYMENT.md`, `PIPELINE.md`) estavam inteiros em CRLF na árvore de trabalho (o git avisava "CRLF will be
replaced by LF"); normalizei para LF (só EOL, conteúdo igual ao que o git gravaria). `fold.py` também está em
CRLF, mas é compartilhado com o T4.10 — não toquei.

`git status --porcelain` do que toquei (14:20 UTC = 11:20 BRT): 26 ` M` + 15 `??` — lista exata na saída acima
do relatório (adaptador 4 M + 1 novo + 7 fixtures + 1 teste novo; worker 9 M + 2 novos + 4 testes M + 2 testes
novos; API 3 M; docs 6 M; SQL 1 novo; estas notas).

## Preocupações / pendências

1. **Meta da fita (≥ 80 %) não é alcançável por este endpoint a partir de um IP** — medido, não estimado: a
   regra do Cloudflare corta em ~20 requisições/60 s por IP e bloqueia 60 s (5 × 429 em 4 sondas, mesmo com 40
   mints distintos). 16 pulls/min × 180 s ÷ 130 ≈ 40 % (a T4.2e mediu 38,8 %). O que a T4.2f entrega na fita é
   zero apagões de 60 s e `tape_reason` honesto. Decisão para o Everton/orquestrador: 2.º IP/proxy só para o
   swap-api, ou `POST /v1/coins/market-activity/batch` (N mints/requisição, janelas 5m/1h, USD) como feature nova.
2. **Árvore compartilhada com o T4.10 durante a sessão** (`meme_features_v3`, `0026`): `fold.py` e `main.py` têm
   hunks dos dois agentes; `features.py`/`repo.py`/`lab*.py`/`paper_engine.py`/`proposals.py` e os arquivos
   `*_lines.py`/`lab_values.py`/`paper_fill.py`/`proposals_scale.py` **não são meus**. A suíte do worker passou
   inteira na árvore combinada (159), mas o commit por pathspec precisa levar `fold.py`/`main.py` com os dois
   ou negociar a ordem.
3. **Meta do progresso (≥ 90 %) só se prova na VPS.** Aritmética a favor: 115/141 (82 %) da captura fresca são
   curvas SOL legíveis; dos 26 recusados, 23 são quote ≠ SOL (saem do conjunto no 1.º ciclo, liberando vagas) e
   2 são migradas. Entre os lidos, o denominador é `global_params` para toda curva padrão e `unknown` para
   Mayhem até o laço da T4.2e escrever (45/115 eram Mayhem na captura) — logo o `denominator_unknown` Mayhem
   pendente é o que decide se passa de 90; o SQL §8 mostra por origem da fotografia.
4. **`observed_at` = blockTime muda a chave** `(observed_at, mint, source)`: duas leituras no mesmo slot viram uma
   linha (desejado) e o Lab passa a ver a fotografia da cadeia ~11 s "mais cedo" do que a chegada — correto
   (não-antecipação vale para `received_at`, que a tabela guarda), mas é uma mudança de semântica em
   `meme_curve_snapshots` para `solana_rpc`; `pumpfun_rest` continua `observed_at` = chegada.
5. **A reconciliação top-K não roda com o laço ligado** (`MEME_CHAIN_CURVES_ENABLED=true`, default): as
   snapshots `solana_rpc` de `getAccountInfo` (observed_at = chegada) deixam de existir; `reconcile_once` fica
   no código para o modo desligado.
6. **Cabeçalho `x-ratelimit-method-limit: 10` do RPC**: não sei se é por 10 s ou por segundo; o espaçamento de
   1 chamada/s por método é seguro nas duas leituras. O RPC devolve 403 para `Origin`/`User-Agent` do site.
7. **Sonda gastou 138 requisições no swap-api (5 × 429)** a partir do meu IP — bloqueios de 60 s, sem ban
   (recuperação 200 nas 5 vezes). RPC: 6 de 10 chamadas (4 da tentativa cortada).
8. `pnpm gen:types` não rodado (`apps/web` fora do escopo, e em uso pelo T4.3b): os 9 campos novos de
   `MemeSourcesOut` não estão em `packages/shared-types` — mesma pendência da T4.2e.
9. Astra não consultada (`SendMessage` desabilitado); a revisão do diff foi minha.
