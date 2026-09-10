# T3.79 — orçamento de latência de ponta a ponta

Brief salvo em `.claude/state/brief-T3.79-latencia-ponta-a-ponta.md`. Medição só-leitura na VPS (`hunter-vps`, `hunter-postgres-1`/`hunter-redis-1`), nenhuma escrita, nenhum contêiner tocado. Instrumentação nova ainda **não foi implantada** na VPS por este agente (regra do brief) — os números abaixo são: (a) o que já dava para calcular via SQL sobre colunas que já existiam, e (b) prova de que o código novo funciona, via os testes unitários locais.

## 1. Onde cada trecho já tinha (ou não) um timestamp

| Trecho | Timestamp existente antes desta tarefa | Onde |
|---|---|---|
| `ingest` (evento na exchange → recebimento) | **Nenhum persistido.** `NormalizedTrade.ts`/`NormalizedCandle.event_ts` e `.received_at` são campos Pydantic em memória (`hunter_core.domain.market`); nunca gravados em Postgres — só o OHLCV da vela final é. Essa é a lacuna que esta tarefa fecha (histograma + heartbeat novos, nunca existiu antes). | — |
| `flush` (fechamento da vela → linha durável) | `candles.received_at` (`server_default now()`) já existia. | `candles` |
| `decision` (fechamento → sinal do agente) | `agent_signals.emitted_at` e `supporting_features->>'observation_ts'` já existiam (T3.74c já usa isso). | `agent_signals` |
| `admission` (sinal → decisão de admissão) | `trade_proposals.decided_at` + `trade_proposals.signal_id → agent_signals.id` já existiam. | `trade_proposals` |
| `fill` (decisão → fill de papel) | `orders.completed_at`/`fills.ts` já existiam (via `orders.proposal_id → trade_proposals.id`). | `orders`, `fills` |

## 2. Números medidos hoje (2026-09-10, consulta às ~16:24 UTC / 13:24 BRT, janela de 24 h)

| Trecho | Mediana | p95 | Status vs. alvo | Observação |
|---|---|---|---|---|
| `ingest` | — | — | `unknown` | Sem dado histórico possível (item 1); heartbeat novo ainda não implantado. |
| `flush` (proxy via `candles.received_at`, só `source='ws'`) | **≈ 1,03 s** | **≈ 3,5–4,1 s** | **critical** (alvo p95 < 1 s) | `FLUSH_INTERVAL_S=1.0` já explica o piso de ~1 s (lote uma vez por segundo); a cauda de ~4 s vem do outbox. **30 203 de 343 449 velas da janela eram `source='rest'` (backfill)** — incluí-las inflava o p95 para **dezenas de milhares de segundos** (artefato de backfill, não atraso real; ver q01). |
| `decision` (T3.74c, `agent_signals`) | **≈ 21–208 s por hora, maioria > 60 s** | **≈ 69–294 s** | **critical** (alvo mediana < 5 s / p95 < 20 s) | Confirma a nota da T3.74c: a correção do `BarDispatcher` concorrente ainda não chegou à VPS nesta medição — a fila de dispatch sequencial continua sendo o gargalo. |
| `admission` | — | — | `unknown` | `trade_proposals`: **0 linhas** no banco inteiro. `hb:execution:paper.paper_autonomy = "false"` — a ponte de autonomia está desligada em produção, então este trecho não tem nenhum evento para medir. |
| `fill` | — | — | `unknown` | `orders`/`fills`: **0 linhas** no banco inteiro (mesma causa). |
| `end_to_end` | — | — | `unknown` | Nunca soma parcial — `admission`/`fill` ausentes bastam para não fabricar o total. |

`agent_signals` teve 1021 linhas nas últimas 24 h (dado real para `decision`); `candles` teve 343 449 linhas 1m na janela (312 946 `ws`, 30 203 `rest`).

## 3. Comandos e saídas reais

```
$ timeout 60 ssh hunter-vps "docker ps --format '{{.Names}}' | sort"
hunter-api-1
hunter-execution-worker-1
hunter-market-worker-1
hunter-market-worker-1-1
hunter-market-worker-2-1
hunter-market-worker-3-1
hunter-market-worker-spot-1
hunter-postgres-1
hunter-redis-1
hunter-scanner-worker-1
hunter-strategy-worker-1
hunter-web-1
```
(4 shards do market-worker perpétuo + 1 spot — confirma a simplificação assumida no serviço da API: o hop `ingest`/`flush` lê só o primeiro `hb:market:*` que aparecer no `SCAN`, sem unir os 4 shards como `market_shards.py` já faz para `ws_state`.)

```
$ timeout 120 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1" < infra/scripts/sql/research/2026-09-10-t379-q00-timestamps-inventario.sql
...
 candles_1m_24h |    first_open_time     |     last_open_time
----------------+------------------------+------------------------
         343279 | 2026-09-09 16:23:00+00 | 2026-09-10 16:21:00+00
 agent_signals_24h
-------------------
              1021
 trade_proposals_total | with_signal_id | decided
-----------------------+----------------+---------
                     0 |              0 |       0
 orders_total | completed
--------------+-----------
            0 |         0
 fills_total
-------------
           0
```

```
$ timeout 120 ssh hunter-vps "..." < infra/scripts/sql/research/2026-09-10-t379-q01-flush-lag-24h.sql
        hour_utc        | candles | mediana_s | p95_s | min_s
------------------------+---------+-----------+-------+-------
 2026-09-10 15:00:00+00 |   12985 |     1.049 | 4.138 | 0.258
 2026-09-10 16:00:00+00 |    4968 |     1.102 | 4.090 | 0.306
(25 linhas no total, mediana estável ~1.03s, p95 ~3.5-4.1s a cada hora)
```
Primeira tentativa (sem filtrar `source='ws'`) deu p95 de até **51 673 s** nas horas mais antigas da janela — descoberto ser artefato do backfill (`source='rest'`) durante a própria consulta; corrigido no arquivo e documentado no comentário SQL.

```
$ timeout 120 ssh hunter-vps "..." < infra/scripts/sql/research/2026-09-10-t379-q02-decision-lag-24h.sql
        hour_utc        | sinais | mediana_s | p95_s | max_s
------------------------+--------+-----------+-------+-------
 2026-09-10 15:00:00+00 |     32 |      89.8 | 171.4 | 171.5
 2026-09-10 16:00:00+00 |      4 |      20.2 |  68.9 |  76.5
(mediana entre 20 s e 208 s por hora ao longo do dia, quase sempre > 60 s)
```

```
$ timeout 120 ssh hunter-vps "..." < infra/scripts/sql/research/2026-09-10-t379-q03-admissao-e-fill.sql
 candidate_rows | admission_mediana_s | admission_p95_s
----------------+---------------------+-----------------
              0 |                     |
 candidate_rows | fill_mediana_s | fill_p95_s
----------------+----------------+------------
              0 |                |
```

```
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:market:binance:0of4"
... (sem ingest_lag_p50_s/flush_lag_p50_s -- instrumentação ainda não implantada)
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:strategy:shadow"
... (sem decision_lag_p50_s/p95_s -- T3.74c/T3.74d ainda não implantados nesta imagem)
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:execution:paper"
paper_autonomy
false
(confirma por que admission/fill estão vazios)
```

Testes locais (todos passaram, saída real):
```
$ uv run pytest packages/core/tests/unit/test_latency.py -q
16 passed in 2.89s
$ uv run pytest services/market-worker/tests/test_latency.py -q
7 passed in 2.38s
$ uv run pytest services/execution-worker/tests/test_latency_metrics.py -q
7 passed in 2.26s
$ uv run pytest apps/api/tests/unit/test_system_latency.py -q
7 passed in 0.74s (após ruff format)
$ uv run pytest services/market-worker/tests/test_heartbeat.py test_ingest_coalesce.py test_persist.py test_persist_batch.py -q
32 passed in 65.78s
$ uv run pytest services/execution-worker/tests/test_bridge_refusal_dedupe.py test_risk_profile.py test_scheduling.py test_supervision.py -q
100 passed in 3.04s
$ uv run pytest apps/api/tests/unit/test_system_workers_status.py -q
36 passed in 0.60s
$ uv run python infra/scripts/check_file_size.py
scanned 616 files; 0 over budget, 0 grandfathered
$ uv run ruff check <17 arquivos tocados>
All checks passed!
$ uv run pyright <17 arquivos tocados>
0 errors, 0 warnings, 0 informations
```

## 4. Contrato congelado — `GET /api/v1/system/latency`

```jsonc
{
  "hops": [
    {"hop": "ingest",    "p50_s": 0.09,  "p95_s": 0.31,  "target_p50_s": 0.5, "target_p95_s": 1.0,  "status": "ok"},
    {"hop": "flush",     "p50_s": 1.03,  "p95_s": 3.90,  "target_p50_s": 0.5, "target_p95_s": 1.0,  "status": "critical"},
    {"hop": "decision",  "p50_s": 45.0,  "p95_s": 180.0, "target_p50_s": 5.0, "target_p95_s": 20.0, "status": "critical"},
    {"hop": "admission", "p50_s": null,  "p95_s": null,  "target_p50_s": 1.0, "target_p95_s": 2.0,  "status": "unknown"},
    {"hop": "fill",      "p50_s": null,  "p95_s": null,  "target_p50_s": 1.0, "target_p95_s": 2.0,  "status": "unknown"}
  ],
  "end_to_end": {"hop": "end_to_end", "p50_s": null, "p95_s": null, "target_p50_s": 5.0, "target_p95_s": 10.0, "status": "unknown"},
  "generated_at": "2026-09-10T16:24:00Z"
}
```

`status` é um de `ok`/`warn`/`critical`/`unknown` (`hunter_core.latency.classify_slo`); `unknown` só quando ainda não há leitura (nunca fabrica `ok`). `end_to_end` só soma quando os cinco hops têm p50/p95 — nunca uma soma parcial. RBAC: `CurrentPrincipal` (qualquer membro autenticado, igual a `/workers` e `/market-status`) — não é rota de tenant, é fato do processo inteiro.

## 5. Simplificações assumidas (documentadas, não escondidas)

- **`ingest`/`flush` leem só o primeiro `hb:market:*` que aparecer no `SCAN`** com o campo `ingest_lag_p95_s` presente — não uma união dos 4 shards perpétuos como `hunter_api.services.market_shards` já faz para `ws_state`. Confirmado na VPS: há 4 shards reais (`0of4`..`3of4`) + 1 spot. Pendência registrada para quem tocar `hunter_api/services/latency.py` de novo.
- **Alvos `warn`/`critical` por hop**: o brief deu um teto único para `ingest+flush` (<1s), `admissão` (<2s) e `fill` (<2s); usei metade do teto como `warn` e o teto como `critical` — convenção minha, documentada em `hunter_api/services/latency.py`, não um número do brief. `decision` usa os dois números exatos do brief (mediana<5s, p95<20s).
- **`flush` mede `close_time → candles.received_at`** (proxy de DB) na pesquisa SQL, mas o histograma novo em produção mede `close_time → utcnow() logo após o commit do flush` (`hunter_market_worker.persist.drain_loop`) — mais apertado que reler a coluna depois, documentado no docstring do módulo.
- Uma vela redistribuída (`ON CONFLICT DO NOTHING`) é contada de novo no histograma de `flush` mesmo quando não foi ela quem foi de fato inserida — simplificação aceita para uma métrica diagnóstica (não uma decisão).

## 6. Arquivos (git status --porcelain, só os meus)

```
 M apps/api/hunter_api/routers/system.py
 M docs/ARCHITECTURE.md
 M docs/PIPELINE.md
 M packages/core/hunter_core/observability.py
 M services/execution-worker/hunter_execution_worker/bridge.py
 M services/execution-worker/hunter_execution_worker/entry.py
 M services/execution-worker/hunter_execution_worker/heartbeat.py
 M services/execution-worker/hunter_execution_worker/metrics.py
 M services/market-worker/hunter_market_worker/heartbeat.py
 M services/market-worker/hunter_market_worker/ingest.py
 M services/market-worker/hunter_market_worker/persist.py
?? .claude/state/brief-T3.79-latencia-ponta-a-ponta.md
?? .claude/state/notes-T3.79.md
?? apps/api/hunter_api/schemas/latency.py
?? apps/api/hunter_api/services/latency.py
?? apps/api/tests/unit/test_system_latency.py
?? infra/scripts/sql/research/2026-09-10-t379-q00-timestamps-inventario.sql
?? infra/scripts/sql/research/2026-09-10-t379-q01-flush-lag-24h.sql
?? infra/scripts/sql/research/2026-09-10-t379-q02-decision-lag-24h.sql
?? infra/scripts/sql/research/2026-09-10-t379-q03-admissao-e-fill.sql
?? packages/core/hunter_core/latency.py
?? packages/core/tests/unit/test_latency.py
?? services/execution-worker/tests/test_latency_metrics.py
?? services/market-worker/hunter_market_worker/latency.py
?? services/market-worker/tests/test_latency.py
```

Todo o resto em `git status --porcelain` da árvore (breadth, T3.74d em `services/strategy-worker/**`, `docs/ACTIVATION.md`/`DATABASE.md`/`DESIGN.md`, `.claude/state/tmp/**` etc.) é de outros agentes — não tocado por esta tarefa.

## 7. O que não foi feito (concerns)

- Não implantei nada na VPS (regra do brief) — os números de `ingest`/`flush`/`admission`/`fill` das heartbeats só existirão depois de um deploy; até lá `/api/v1/system/latency` responde `unknown` para `ingest` (sem instrumentação histórica possível) e para `admission`/`fill` (zero linhas em produção, ponte de autonomia desligada).
- Não escrevi um teste HTTP de ponta a ponta da rota (`TestClient` com auth) — cobri `build_latency` diretamente (service-level) com 7 casos, e a rota em si só delega para ele exatamente como as duas irmãs (`/workers`, `/market-status`) já fazem, sem lógica própria a mais que o try/except 503 (mesmo padrão, revisável a olho).
- A união dos 4 shards do market-worker perpétuo para `ingest`/`flush` não existe (item 5) — hoje reporta só o primeiro shard que o `SCAN` devolver.

## 8. web (frontend-specialist, 2026-09-10) — bloco "Latência" em `/system`

Consumiu o contrato congelado em §4 tal como está: `p50_s`/`p95_s`/`target_*_s` são **números JSON** (`float | null`), não strings `Decimal` — `LatencyHopOut` do backend não os tipa como `Decimal`/`NUMERIC` (não é dinheiro); documentado explicitamente no docstring de `lib/api/latency-types.ts` e coberto por um teste que rejeita strings nesses campos.

**Arquivos:**
- `apps/web/lib/api/latency-types.ts` (novo) — zod: `latencyHopSchema`, `latencyOutSchema`, `latencySloStatusSchema`.
- `apps/web/lib/api/latency.ts` (novo) — `getLatency()`, `GET /api/v1/system/latency`, `.parse()` antes de confiar (mesma convenção de `lab-daily-goal.ts`: rota ainda não passou por `pnpm gen:types`).
- `apps/web/components/system/latency-labels.ts` (novo) — rótulos PT-BR por hop (`Evento da Binance → recebido`, `Vela fechada → publicada`, `Vela → decisão`, `Decisão → admissão`, `Admissão → fill`, `Ponta a ponta`), rótulo/variant de badge por status (`ok`→positive, `warn`→warning, `critical`→negative, `unknown`→default), motivo honesto por hop para `unknown` (a API não manda um campo `reason` por hop, só `status` — o motivo aqui nomeia qual heartbeat ainda não reporta, nunca inventa uma causa específica que o frontend não observa) e `formatLatencySeconds`.
- `apps/web/components/system/latency-panel.tsx` (novo) — Server Component, tabela de 6 linhas (5 hops + ponta a ponta). Linha `critical`: fundo `bg-red-soft`, números em vermelho/negrito, ícone `AlertTriangle` ao lado do badge — pedido do Everton ("quero tudo instantâneo") de que um hop vermelho seja impossível de não notar, não só um badge pequeno. Linha `unknown`: célula única (`colSpan`) "sem medição: `<motivo>`", nunca um número. `as_of`/`generated_at` via `SystemAsOf` (Brasília, T3.22), hover mostra o ISO UTC.
- `apps/web/app/(app)/[orgSlug]/system/page.tsx` (modificado) — `loadLatency()` isolado (mesmo padrão de `loadWorkers`/`loadSystemInfo`, T1.5 F3): uma falha em `/system/latency` não derruba o resto da página, e nunca vira um "tudo `unknown`" fabricado. `AutoRefresh` já montado na página cobre o novo bloco (mesmo padrão do `/lab`).
- `apps/web/tests/latency-types.test.ts`, `latency.test.ts`, `latency-labels.test.ts`, `latency-panel.test.tsx` (novos); `apps/web/tests/system-page.test.tsx` (modificado, mock de `getLatency` + 2 testes de isolamento).

**Rótulos por hop:** o brief lista 4 frases PT-BR + "ponta a ponta" para o que a API publica como 5 hops (`ingest`/`flush`/`decision`/`admission`/`fill`) + `end_to_end`. `services/latency.py` já documenta `ingest`+`flush` como uma família só ("evento da exchange → vela no nosso stream"); dei um rótulo a cada um dentro dessa família em vez de fundir dois SLOs com p50/p95/status independentes numa única linha — decisão registrada aqui, não escondida.

**Comandos (todos foreground, `timeout 290`):**
```
$ npx turbo run lint --filter=@hunter/web
✖ 2 problems (0 errors, 2 warnings)   # ambos pré-existentes (lab-page.test.tsx, ws.test.ts), nenhum arquivo meu

$ npx turbo run typecheck --filter=@hunter/web --force
$ tsc --noEmit   # 0 erros

$ npx turbo run test --filter=@hunter/web --force
 Test Files  130 passed (130)
      Tests  1226 passed (1226)
  Duration  98.54s
```

**Playwright:** não executado — o brief já assinalava "provavelmente bloqueado"; nenhum fluxo Playwright nomeado para esta tarefa, e o navegador embutido não abre localhost/Clerk (memória "in-app-browser-limits") nem há servidor dev + sessão Clerk viva neste ambiente foreground. Cobertura ficou 100% Vitest (schema, mapeamento status→rótulo, renderização null/motivo, integração da página).

**`git status --porcelain` (só os meus arquivos web):**
```
 M apps/web/app/(app)/[orgSlug]/system/page.tsx
 M apps/web/tests/system-page.test.tsx
?? apps/web/components/system/latency-labels.ts
?? apps/web/components/system/latency-panel.tsx
?? apps/web/lib/api/latency-types.ts
?? apps/web/lib/api/latency.ts
?? apps/web/tests/latency-labels.test.ts
?? apps/web/tests/latency-panel.test.tsx
?? apps/web/tests/latency-types.test.ts
?? apps/web/tests/latency.test.ts
```

**Concerns:** nenhum arquivo `apps/api/**` tocado; nada commitado; `pnpm gen:types` não foi rodado (fora do escopo desta tarefa e do brief) — `latency-types.ts` continua hand-mirrored até a rota passar pelo OpenAPI generator.
