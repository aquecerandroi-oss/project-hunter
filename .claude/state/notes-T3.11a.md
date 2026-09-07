# Notas da T3.11a — coletor de câmbio `USDTBRL` no market-worker

**Autor:** exchange-integration-specialist, 2026-09-07. **Para:** quem mexer em `hunter_core.portfolio.opening`/`ledger` (consumo da FX), quem operar o market-worker em produção, e a T3.11b (já entregue em `8a6a69f`/`9a0ac45`).

Não editei `.env*`, `packages/**`, `infra/migrations/**`, `services/scanner-worker/**`, `services/strategy-worker/**` nem `apps/**`.

## 1. O que entrega

`services/market-worker/hunter_market_worker/fx.py` (316 linhas): a tarefa `fx_collector` do TaskGroup do market-worker (`main.py`), registrada como `"fx"` ao lado de `funding`/`heartbeat`/`watchdog` etc.

- **Cadência:** ~60 s ± 5 s de jitter (`POLL_INTERVAL_S=60.0`, `POLL_JITTER_S=5.0`), só no **shard 0** (`runtime.settings.shard_index == 0`, lido direto de `hunter_core.settings.Settings` — nenhum setting novo foi declarado) **e** só quando `exchange_code == "binance"` (guarda extra para quando um segundo venue existir: a fonte é sempre Binance spot, então só o shard 0 do market-worker de Binance pode coletar). Todo outro shard/venue idla a tarefa para sempre (`asyncio.Event().wait()`), o que satisfaz `supervision.forever` (a tarefa nunca "retorna").
- **Endpoint:** `GET /api/v3/ticker/24hr?symbol=USDTBRL`, peso 2, através de `hunter_exchanges.binance_spot.http.SpotHttp` diretamente (não do `BinanceSpotRestClient`, que descarta o corpo cru) — `build_spot_http` monta o mesmo bucket Redis oficial (`rl:binance:spot_request_weight`, T2.9 fail-closed: `redis=` é sempre passado, nunca um orçamento local por processo) e deixa o `IpRateGate` default da `SpotHttp` se ligar sozinho ao mesmo cliente/exchange.
- **Campos gravados em `fx_observations`:** `pair="USDTBRL"` (`hunter_core.portfolio.attribution.FX_PAIR`, importado, nunca digitado de novo), `source="binance.spot.ticker"` (`hunter_core.portfolio.fx_policy.PAPER_FX_POLICY.source`, idem), `rate=lastPrice`, `observed_at=closeTime` (relógio da Binance), `available_at=utcnow()` no instante do INSERT, `raw=` corpo cru. Mesma escolha de campo que `infra/scripts/open_paper_wallet.py` já documenta (`ticker/24hr` em vez de `ticker/price` porque só o primeiro carrega `closeTime`).
- **Idempotência:** `INSERT ... ON CONFLICT (pair, source, observed_at) DO NOTHING` sobre `uq_fx_observations_observation` (confirmado em `docs/DATABASE.md` §18.2 — é exatamente essa a unique). Duas coletas do mesmo segundo fechado (retry, corrida entre um restart e o próximo tick) produzem no máximo uma linha; a segunda reporta `outcome="duplicate"`, não erro.
- **Banda de plausibilidade:** uma cotação fora de `[1, 100]` (`PAPER_FX_POLICY.plausible_rate_min/max`, a mesma banda que a revisão adversarial de `8a6a69f` bloqueante 3 criou) é **gravada do mesmo jeito** — warning + `hunter_fx_implausible_total` — porque quem recusa é o *consumo* (`validate_fx_observation`), não o coletor. Implementei isso lendo a policy existente em vez de duplicar os números `1`/`100` em `fx.py`.
- **429/418:** `SpotHttp` já levanta `RateLimited` sem retentativa silenciosa (contrato de `EXCHANGE_INTEGRATION.md` §5); `collect_once` grava um `system_event` (`fx_collector_rate_limited`, `warning`, via `heartbeat.safe_record_system_event` — a mesma função que já protege o watchdog de uma falha de Postgres) e devolve o outcome, sem escrever linha nenhuma.
- **Falha de rede/5xx:** depois das retentativas internas do `SpotHttp` (backoff exponencial + jitter, já existente), `ExchangeUnavailable` vira `outcome="network_error"`; o laço externo (`run_fx_collector`) aplica seu próprio backoff (5 s → 60 s, jitter) antes do próximo poll — nunca fabrica cotação, nunca tenta em loop apertado.
- **Observabilidade:** `hunter_fx_observations_total{outcome}` (`ok`, `duplicate`, `malformed`, `rate_limited`, `network_error`, `error`), `hunter_fx_implausible_total`, `hunter_fx_age_seconds` (idade da última coleta bem-sucedida, via `Gauge.set_function` sobre `FxCollectorHealth.age_seconds`, sem I/O). `WorkerRuntime.status_details["fx"]` expõe `"ok"`/`"stale"`/`"unknown"` (limiar = `FxPolicy.availability_max_age_s`, 300 s) — **status detail, nunca readiness check**: registrado fora de `runtime.readiness_checks`, então uma cotação velha nunca derruba `/ready` (a carteira pode não abrir; a coleta de mercado continua).
- **Nunca sob lock de carteira, nunca em transação alheia:** `collect_once` abre sua própria `role_session(factory, db_role="hunter_worker")` só para o INSERT; nada aqui lê ou trava `portfolio_risk_state`, nada participa da ordem de lock que `build_portfolio_state`/`open_paper_wallet` documentam.

`main.py`: duas linhas — import de `run_fx_collector` e uma entrada `"fx": run_fx_collector(factory, runtime.redis, adapter.code, runtime)` no dict de tasks do `TaskGroup`.

`docs/PIPELINE.md`: nova seção curta `## 1c. Câmbio USDTBRL — fx_observations (T3.11a)`, entre o backfill (§1b) e o Feature Engine (§2) — é o único ponto do documento que falava de `market.*` sem cobrir o câmbio, que não é market data de um símbolo e não passa por nenhum stream `market.*`.

## 2. Desvio de instrução: onde ficou a fixture

A instrução cita `hunter_exchanges/testing/fixtures/` (o padrão do resto do pacote de adapters) para fixtures gravadas, mas essa pasta vive dentro de `packages/exchange-adapters/`, que está na lista de "não toque". Gravei a fixture do ticker `USDTBRL` em `services/market-worker/tests/fixtures/fx_usdtbrl_ticker_24hr.json` (formato idêntico ao `spot_ticker_24hr.json` existente, símbolo e preços trocados para um par plausível de USDTBRL) em vez de estender a pasta compartilhada. Nenhum arquivo dentro de `packages/**` foi criado, movido ou editado.

## 3. Testes — `services/market-worker/tests/test_fx.py` (9 casos, testcontainers Postgres real)

| Caso | O que prova |
|---|---|
| `test_collect_once_persists_the_declared_pair_and_source` | pair/source exatamente os que `PAPER_FX_POLICY` exige; `raw` gravado igual ao corpo; `observed_at <= available_at` |
| `test_collect_once_is_idempotent_for_the_same_observed_at` | duas coletas do mesmo `closeTime` → uma linha, outcomes `ok`/`duplicate` |
| `test_collect_once_writes_nothing_on_a_malformed_body` | campo obrigatório ausente (`bidPrice`) → `MalformedMessage` → nenhuma linha |
| `test_collect_once_persists_an_implausible_rate_but_flags_it` | cotação fora de `[1,100]` é gravada, `hunter_fx_implausible_total` incrementa |
| `test_collect_once_reports_rate_limited_and_writes_no_row` | 429 com `Retry-After` → `RateLimited`, `system_events` ganha uma linha `fx_collector_rate_limited`, zero linhas em `fx_observations` |
| `test_collect_once_reports_network_error_and_writes_no_row` | 503 persistente (retentativas do `SpotHttp` esgotadas) → `network_error`, zero linhas |
| `test_fx_collector_health_is_unknown_then_ok_then_stale` | `FxCollectorHealth` pura, relógio injetado: `unknown` → `ok` → `stale` aos 301 s |
| `test_run_fx_collector_idles_forever_off_shard_zero` | shard `1/2` nunca registra `status_details["fx"]`, tarefa nunca retorna |
| `test_run_fx_collector_idles_forever_off_the_declared_venue` | `exchange_code="bybit"` idem, mesmo em shard 0 |

Mandatórias de `docs/EXCHANGE_INTEGRATION.md` §6 que se aplicam a um poller de um endpoint só: mensagem malformada (coberto) e as duas formas de "a coleta não produz linha" (rate limit, falha de transporte) — cobertas. Símbolo delistado/book fora de sequência/reconexão com gap não se aplicam: `ticker/24hr` não tem sequência nem WS, e `USDTBRL` não é um símbolo que a Binance delista silenciosamente da forma que os perpétuos fazem.

## 4. Comandos e saída real

```
$ uv run pytest services/market-worker/tests/test_fx.py -q
.........
9 passed in 53.89s

$ uv run pytest services/market-worker/tests/test_supervision.py services/market-worker/tests/test_readiness_naming.py -q
..............
14 passed in 9.51s

$ uv run ruff check services/market-worker
All checks passed!

$ uv run ruff format --check services/market-worker
80 files already formatted

$ uv run pyright services/market-worker
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 411 files; 0 over budget, 0 grandfathered
```

Sanidade adicional (não pedida explicitamente, rodada por precaução já que `fx.py` entra no `TaskGroup` do `main.py`): `test_rest_gate.py` e `test_role_registration.py` (que importam `main`) — 7 passed.

## 5. Astra — indisponível

`bash infra/scripts/astra.sh ask T3.11a-fx "..."` (pergunta cobrindo as seis decisões: cadência/shard, `observed_at`/`available_at`, idempotência, banda de plausibilidade, 429/418, status detail) falhou: `.claude/state/astra-stderr.log` mostra `ERROR: You've hit your usage limit ... try again at Sep 12th, 2026`. Não há como consultar a Astra (antes ou depois) até essa data com a cota atual. Registrado honestamente em vez de simular uma resposta ou pular a menção. As seis decisões de design estão documentadas na íntegra no §1 acima e na docstring de `fx.py`, com a rastreabilidade para `notes-T3.3.md` e `review-T3.3-T3.4.md` (bloqueante 3) que já as fixam para o lado consumidor — este coletor só as respeita, não as reabre.

## 6. Prova de 10 minutos no stack local

O stack já estava de pé (`docker compose --profile shards up -d`, 4 shards de `market-worker` na imagem antiga `hunter-api:dev`). Como só uma imagem nova traz `fx.py`, subi uma tag isolada (`hunter-api:t311afx`, `docker build -f infra/docker/Dockerfile.api-workers --build-arg GIT_SHA=t311afx`, mesmo padrão que `hunter-api:t25e-proof` já deixado por outra tarefa) e rodei um container **avulso, à parte dos quatro `market-worker` reais** — nunca substituí nem reiniciei os containers da stack em produção local, para não arriscar o trabalho concorrente de outros agentes. O container avulso chama exatamente `hunter_market_worker.fx.run_fx_collector` (o mesmo código do `TaskGroup` de `main.py`), com `MARKET_SHARD=0/1`, contra o Postgres/Redis reais da rede `docker_default` (script `.claude/state/tmp/fx_proof.py`, apagado ao final, nunca commitado).

**Achado operacional durante a montagem:** minha primeira tentativa (pipe para `head`, no shell) matou o cliente `docker run` mas não o container — ele ficou órfão (`bold_mendeleev`) rodando um segundo coletor `shard 0` em paralelo por ~4 min antes de eu notar e removê-lo (`docker rm -f`). Sem dano: a idempotência por `(pair, source, observed_at)` absorveu os dois coletores concorrentes sem duplicar linha nenhuma — o que é, involuntariamente, mais uma prova em produção real de que o `ON CONFLICT DO NOTHING` funciona sob concorrência de processos de verdade, não só na suíte. Removido antes da janela oficial de 10 minutos abaixo.

**Janela oficial (`fx-proof-t311a`, 2026-09-07 04:12:20–04:22:20 UTC, 600,3 s):**

```
shard_index=0 shard_total=1
[04:12:50] t+  30.0s fx_status=ok outcome_ok=1.0  outcome_duplicate=0.0 errors=0
[04:13:20] t+  60.0s fx_status=ok outcome_ok=2.0  outcome_duplicate=0.0 errors=0
[04:13:50] t+  90.1s fx_status=ok outcome_ok=2.0  outcome_duplicate=0.0 errors=0
[04:14:20] t+ 120.1s fx_status=ok outcome_ok=3.0  outcome_duplicate=0.0 errors=0
[04:14:50] t+ 150.1s fx_status=ok outcome_ok=3.0  outcome_duplicate=0.0 errors=0
[04:15:20] t+ 180.1s fx_status=ok outcome_ok=4.0  outcome_duplicate=0.0 errors=0
[04:15:50] t+ 210.1s fx_status=ok outcome_ok=4.0  outcome_duplicate=0.0 errors=0
[04:16:20] t+ 240.1s fx_status=ok outcome_ok=5.0  outcome_duplicate=0.0 errors=0
[04:16:50] t+ 270.2s fx_status=ok outcome_ok=5.0  outcome_duplicate=0.0 errors=0
[04:17:20] t+ 300.2s fx_status=ok outcome_ok=6.0  outcome_duplicate=0.0 errors=0
[04:17:50] t+ 330.2s fx_status=ok outcome_ok=6.0  outcome_duplicate=0.0 errors=0
[04:18:20] t+ 360.2s fx_status=ok outcome_ok=7.0  outcome_duplicate=0.0 errors=0
[04:18:50] t+ 390.2s fx_status=ok outcome_ok=7.0  outcome_duplicate=0.0 errors=0
[04:19:20] t+ 420.2s fx_status=ok outcome_ok=8.0  outcome_duplicate=0.0 errors=0
[04:19:50] t+ 450.2s fx_status=ok outcome_ok=8.0  outcome_duplicate=0.0 errors=0
[04:20:20] t+ 480.2s fx_status=ok outcome_ok=9.0  outcome_duplicate=0.0 errors=0
[04:20:50] t+ 510.3s fx_status=ok outcome_ok=9.0  outcome_duplicate=0.0 errors=0
[04:21:20] t+ 540.3s fx_status=ok outcome_ok=10.0 outcome_duplicate=0.0 errors=0
[04:21:50] t+ 570.3s fx_status=ok outcome_ok=10.0 outcome_duplicate=0.0 errors=0
[04:22:20] t+ 600.3s fx_status=ok outcome_ok=11.0 outcome_duplicate=0.0 errors=0
DONE errors=0
```

`docker wait fx-proof-t311a` → `0` (saída limpa). **11 coletas bem-sucedidas em 10 minutos** (~1 a cada 55 s, dentro de 60 s ± 5 s de jitter), `fx_status` (o mesmo `WorkerRuntime.status_details["fx"]` de produção) em `"ok"` do primeiro ao último tick — nunca `"stale"` nem `"unknown"` depois da primeira coleta —, `errors=0` do início ao fim.

Conferência direta em `fx_observations` (via `docker exec docker-postgres-1 psql`), incluindo as linhas do container órfão:

```
 rows_this_source |       first_observed       |       last_observed       |        last_available         |     age_now
------------------+----------------------------+---------------------------+-------------------------------+-----------------
               16 | 2026-09-07 04:09:45.917+00 | 2026-09-07 04:22:07.97+00 | 2026-09-07 04:22:10.648378+00 | 00:00:27.412567
```

Idade da observação mais recente no fim da janela: 27 s — muito abaixo dos 90 s pedidos e dos 300 s de `FxPolicy.availability_max_age_s`. `system_events` com `event LIKE 'fx_%'` — zero linhas: nenhum 429/418 real ocorreu contra a Binance nesses 10 minutos, e nenhuma cotação implausível veio da exchange (todas em torno de R$5,17–5,17/USDT, dentro de `[1,100]`).

Container avulso e imagem `hunter-api:t311afx` removidos ao final (`docker rm -f`, `docker rmi`); nenhum dos quatro `market-worker` da stack real foi tocado, parado ou reiniciado.
