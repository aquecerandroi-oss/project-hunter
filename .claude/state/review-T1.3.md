# Kit de revisão — T1.3 · `hunter_market_worker` (universo, ingestão, persistência, recovery, heartbeat)

**Owner:** Astra (GPT-6 via Codex CLI, brief em `.claude/state/astra-brief-T1.3.md`) · **Estado:** em voo em 2026-09-05
**Files (do plano):** `services/market-worker/**`, `packages/core/hunter_core/runtime.py`, `packages/core/hunter_core/settings.py`, `.env.example`
**Depends-on:** T1.1 (commitado); T1.2 só para integração — desenvolve contra o Protocol com `fake_adapter`
**Commit esperado:** `feat(market-worker): universe, ingest, persist, recovery, heartbeat`

> Tarefa maior e mais arriscada do M1 (11 dos 18 itens de aceite da decisão conjunta). Executada pela Astra sem sandbox: **antes de qualquer revisão**, rodar `git status --short` e `git diff --stat` e reverter qualquer hunk fora da lista de `Files:` acima. Há um `services/market-worker/pyright-result.json` não rastreado na árvore — artefato de execução, não deve entrar no commit (avaliar `.gitignore`).

---

## (a) Checklist da decisão conjunta Claude ⇄ Astra que se aplica a T1.3
Copiada literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`.

- [ ] T1.3 — Persistir apenas candles finais no Postgres; bootstrap sem watermark nem fechamento WS prévio busca até 1500 candles efetivamente fechados disponíveis, com corte fixado pela hora da exchange, fechamento exclusivo normalizado e paginação quando necessária. REST usa `ON CONFLICT (market_id, timeframe, open_time) DO NOTHING`, sem sobrescrever final existente; validar resposta REST atrasada após avanço WS e conflitos sem abortar lotes.
- [ ] T1.3 — Manter escritor único e serializado para a lista de candles Redis, exclusivamente na ingestão WS; REST não escreve nela. Abertura maior avança a ponta; na mesma abertura, parcial mais novo atualiza parcial, final substitui parcial e parcial nunca substitui final; rejeitar parciais atrasados/duplicados. Testar dois parciais crescentes, parcial atrasado e final de abertura anterior que atualiza a entrada retida sem regredir a ponta nem renovar seu frescor.
- [ ] T1.3 — Detectar buracos internos a cada minuto comparando aberturas esperadas na janela de 24 h com finais persistidos; processar gaps registrados independentemente do watermark máximo. Confirmar candles e transição para `recovered` na mesma transação somente após comprovar todas as aberturas esperadas por mercado/timeframe; resposta incompleta mantém pendência e incrementa tentativas, quinta falha produz `failed` visível como `degraded`.
- [ ] T1.3 — Limitar filas por itens, bytes e idade; permitir substituição de snapshot pendente pelo mais recente, registrar gap recuperável ao descartar candle final e tornar descartes detectados observáveis em métricas/eventos e qualidade. Validar saturação e consumidor atrasado além da retenção do stream; retenção não substitui limites das filas.
- [ ] T1.3 — Persistir snapshots uma vez por minuto por mercado e OI em buckets UTC de cinco minutos, preservando buckets nos retries e usando escrita em lote idempotente. Manter operação de partições/retenção; 200 mercados geram 288.000 snapshots/dia, sem tratar essa estimativa como benchmark de capacidade.
- [ ] T1.3 — Deduplicar liquidações com `id = uuid5(NAMESPACE_HUNTER_LIQ, canonical(exchange, symbol, side, price_normalizada, qty_normalizada, ts_ms))`, campos delimitados e decimais normalizados; preservar `ts` da fonte e usar exatamente `INSERT ... ON CONFLICT (id, ts) DO NOTHING`. Validar linha única em sobreposição WS, retry após commit incerto, reentrega após 3600 s e perda do cache Redis; `SET NX` é apenas otimização e nunca confirmação antecipada que impeça persistência pendente. Contar duplicatas detectadas e documentar que eventos reais com a mesma tupla colapsam.
- [ ] T1.3 — Publicar `market.liquidations` com `EventEnvelope.event_id` igual ao UUID determinístico e validar deduplicação no consumidor. Aceitar explicitamente publicação best-effort após commit no M1: falha de XADD detectada com processo vivo incrementa `market_publish_failures_total` e gera warning em `system_events`; morte entre commit e XADD pode perder a publicação silenciosamente, sem contador nem warning, mantendo a linha no Postgres. O teste dessa morte verifica histórico único e admite publicação ausente sem exigir registro inexistente; nenhum consumidor M1 depende desse stream para persistir o histórico. Claude registra a limitação no plano e o follow-up M2 de outbox transacional e reconciliação Postgres → stream.
- [ ] T1.3 — Supervisionar tarefas permanentes e filhas, incluindo coalescer, leitores por conexão, persistência, universo, recovery e heartbeat, com `TaskGroup` e `forever`; exceção ou retorno inesperado é fatal e resulta em saída não zero, enquanto cancelamento coordenado de shutdown é normal. Validar falhas de tarefa principal e filha.
- [ ] T1.3 — Aplicar watchdog por conexão public/market com assinaturas e tráfego esperado: 30 s sem dado aceito gera warning e reinicia aquela conexão; três reinícios seguidos sem progresso são fatais. ACK, ping e duplicata não contam como progresso; universo vazio expõe `idle` sem loop fatal. Validar public silenciosa enquanto market continua ativa.
- [ ] T1.3 — Acrescentar `readiness_checks` ao runtime com timeout de 2 s por check e exceção convertida em falso; bootstrap sem dado expõe `initializing` e readiness falsa. Exigir progresso da ingestão conforme contrato de evento há menos de 60 s, timeout de conexão de 15 s por tentativa e tolerância de reconexão limitada a 120 s monotônicos desde a última conexão saudável, sem reiniciar a janela a cada tentativa; vencida a tolerância, retornar 503. Fila pendente sem flush concluído há 30 s também reprova readiness; testar tentativa presa e persistência bloqueada.
- [ ] T1.3 — Coalescer preserva timestamps do último evento aceito e só renova dados/TTL com evento novo aceito; ciclos sem eventos deixam o TTL cair. Usar recebimento monotônico para watchdog e UTC coerente com a exchange para idade compartilhada. Em `deriv`, manter `mark_ts`, `oi_ts`, `funding_ts` e `funding_kind=estimated|realized` independentes, TTL de 600 s e frescor calculado pelos timestamps de cada campo; atualização de OI não rejuvenesce mark.
- [ ] T1.3 — Atualizar universo a cada 15 min aplicando apenas entradas/saídas e preservando assinaturas dos mercados mantidos; delisting, status diferente de TRADING e blocklist removem imediatamente. Validar alternância na fronteira do universo sem reassinar todos os mercados; permanência mínima de 30 min fica para M2.

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
- [ ] `universe.py`: lista perpétuos, upsert `assets`/`markets` com tick/step/min_notional, `volume_24h_usd`, `monitor_rank`, `is_monitored` top N, allow/blocklist, publica `market.universe.changed`.
- [ ] `ingest.py`: assina streams dos monitorados, hot state `mkt:*` com TTLs, coalescência 250 ms, publica `market.ticks`, `market.candles.closed`, `market.derivatives`, `market.liquidations`, pub/sub `rt:market:{ex}:{sym}` e `rt:system`.
- [ ] `persist.py`: candles 1m finais, `market_snapshots` por minuto, `funding_rates`, `open_interest_history` a cada 5 min via REST, `liquidations`; escrita em lote com o role `hunter_worker`.
- [ ] `recovery.py`: gap de `open_time` → REST backfill `source=rest`, `ingestion_gaps`, `data_quality=degraded`.
- [ ] `heartbeat.py`: `hb:market:binance` com `last_event_at`; `system_events` em reconexão/erro.
- [ ] `main.py`: registra `market` no `RoleRegistry`, roda com `WorkerRuntime`.
- [ ] `settings.py`: `MARKET_UNIVERSE_ALLOWLIST`/`BLOCKLIST`, `MARKET_STALE_AFTER_S=10`, `MARKET_UNIVERSE_REFRESH_S`, `MARKET_OI_POLL_S` — e `.env.example` atualizado em sincronia (sem valores reais de segredo).
- [ ] `runtime.py`: registro do papel + `readiness_checks` com timeout, **sem quebrar** os 178 testes de `packages/core` já verdes.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] `Decimal` em preço, quantidade, notional, funding, OI — nenhum `float` chegando ao Postgres.
- [ ] UTC em tudo que é gravado; relógio **monotônico** só para watchdog/idade interna, nunca para o `ts` persistido.
- [ ] Nenhum arquivo acima de 350 linhas — o worker tem ~19 módulos, é onde o gate mais bate.
- [ ] `structlog`, nunca `print`.
- [ ] Sem estado local: nada de SQLite, arquivo JSON ou cache em disco; só Postgres + Redis. (`pyright-result.json` é artefato, não estado.)
- [ ] Sem dado falso: preço congelado nunca é republicado como novo; ausência vira `stale`/`degraded`/`unavailable`.
- [ ] Isolamento: as tabelas de mercado são globais e escritas pelo role `hunter_worker` (BYPASSRLS) — verificar que **nenhuma** escrita de mercado tenta usar `hunter_app` e que nenhum dado de tenant é tocado por este worker.
- [ ] Toda mutação relevante observável: `system_events` em reconexão, gap, descarte de fila, falha de publicação.

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
git status --short && git diff --stat          # 1º: nada fora dos Files: da tarefa
uv run pytest services/market-worker -q
uv run pytest packages/core -q                 # não pode regredir (era 178 passed)
uv run pyright
uv run ruff check . && uv run ruff format --check .
uv run python infra/scripts/check_file_size.py
uv run alembic -c infra/migrations/alembic.ini check   # T1.3 não deve gerar drift de schema
```
Prova de dado real (exigida pela linha do plano):
```bash
docker compose -f infra/docker/docker-compose.yml up -d postgres redis
HUNTER_ROLE=market uv run python -m hunter_market_worker    # deixar 60 s, então Ctrl-C
redis-cli HGETALL mkt:binance:BTCUSDT:ticker
redis-cli HGETALL mkt:binance:BTCUSDT:deriv
```
Colar a saída real no relatório — preço vivo, `ts` avançando, `mark_ts`/`oi_ts`/`funding_ts` independentes.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | conformidade com a linha T1.3 e com a checklist acima; bugs; testes faltando; ≤ 350 linhas; dead code |
| `database-architect` | **obrigatório** — escrita em lote, idempotência (`ON CONFLICT (market_id, timeframe, open_time)`, `ON CONFLICT (id, ts)`), partições e retenção, uso do role `hunter_worker`, planos de consulta do recovery, ausência de drift de migração |
| `exchange-integration-specialist` | **revisão cruzada obrigatória** — o worker usa corretamente o Protocol de T1.2? watchdog, resubscribe, rotas, coalescência e ordenação de parciais batem com o adapter real (não só com o `fake_adapter`)? |
| `security-reviewer` | não obrigatório em T1.3 (sem auth, sem entrada de usuário); dispensado salvo se o diff ler credencial ou expor `/metrics` sem token |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
Atenção: a Astra **implementou** T1.3. A opinião dela sobre o próprio diff vale menos; por isso o peso da decisão fica com `code-reviewer` + `database-architect` + `exchange-integration-specialist`, e a pergunta à Astra é deliberadamente adversarial.
```bash
bash infra/scripts/astra.sh ask review-T1.3 "Review services/market-worker/**, packages/core/hunter_core/runtime.py e settings.py against docs/plans/M1.md (linha T1.3) e os 11 itens T1.3 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md. Você mesma implementou esta tarefa: seja adversarial com o próprio código. Confira item a item: só candles finais no Postgres; ON CONFLICT (market_id, timeframe, open_time) e ON CONFLICT (id, ts); escritor único da lista Redis de candles; parcial nunca substitui final; detecção de buracos internos na janela de 24h; gap failed na 5a tentativa; limites de fila por itens/bytes/idade com descarte observável; snapshots por minuto e OI em buckets UTC de 5 min; uuid5 determinístico de liquidação; TaskGroup com retorno normal fatal; watchdog 30s/3 reinícios; readiness_checks com timeout 2s e tolerância de 120s monotônicos; coalescer que não rejuvenesce TTL sem evento novo; universo aplicando só diferenças. Aponte onde o código diverge do contrato. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```

## (g) Commit esperado
```
feat(market-worker): universe, ingest, persist, recovery, heartbeat

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
`git -c commit.gpgsign=false commit` · só `services/market-worker/**`, `packages/core/hunter_core/{runtime,settings}.py`, testes de core afetados e `.env.example` · `git push origin main`.

---

# VEREDITO FINAL — T1.3 fechada em 2026-09-05, commit `b8c4766`

## (a) Checklist da decisão conjunta — 11 itens de T1.3
| # | Item | Veredito |
|---|---|---|
| 1 | Só candles finais no Postgres; bootstrap até 1500 fechados; `ON CONFLICT (market_id, timeframe, open_time) DO NOTHING` | ✔ |
| 2 | Escritor único e serializado da lista Redis de candles; parcial nunca substitui final | ✔ |
| 3 | Buracos internos a cada minuto na janela de 24 h; `recovered` na mesma transação; `failed` na 5ª tentativa | ✔ (mais reabertura após 1 h, D6) |
| 4 | Filas limitadas por itens, bytes e idade; snapshot substituível; descarte observável | ✔ |
| 5 | Snapshots por minuto e OI em buckets UTC de 5 min, em lote idempotente | ✔ (D8 fechado no caminho com fila) |
| 6 | Liquidação `id = uuid5(...)` com `INSERT ... ON CONFLICT (id, ts) DO NOTHING` | ✔ (`ts` truncado ao ms, D11) |
| 7 | `market.liquidations` com `event_id` = UUID determinístico; publicação best-effort após commit | ✔ (só republica ids retornados por `RETURNING`, D7) |
| 8 | `TaskGroup` + `forever`; retorno inesperado é fatal, saída não zero | ✔ |
| 9 | Watchdog por conexão 30 s / 3 reinícios; universo vazio expõe `idle` | ✔ com ressalva: o token de progresso vem do adaptador, que avança em frame duplicado — limitação já registrada em `docs/plans/M1.md` (T1.2), gate de progresso aceito é a readiness do worker |
| 10 | `readiness_checks` com timeout de 2 s; tolerância de reconexão de 120 s monotônicos; fila sem flush há 30 s reprova | ✔ |
| 11 | Coalescer preserva timestamps do último evento aceito; TTL não rejuvenesce sem evento novo; `deriv` com `mark_ts`/`oi_ts`/`funding_ts` independentes | ✔ |
| 12 | Universo a cada 15 min aplicando só entradas/saídas | ✔ |

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
`universe.py` ✔ · `ingest.py` ✔ · `persist.py` ✔ · `recovery.py` ✔ · `heartbeat.py` ✔ · `main.py` ✔ · `settings.py` + `.env.example` ✔ · `runtime.py` com `readiness_checks` sem regredir `packages/core` ✔ (178 → 254 passed).

## (c) Regras do `CLAUDE.md`
`Decimal` ✔ · UTC nos dados persistidos e monotônico só para watchdog/idade ✔ · nenhum arquivo acima de 350 linhas ✔ (maior: `universe.py`, 333) · `structlog` ✔ · sem estado local ✔ · sem dado falso ✔ (preço velho vira `NULL` + contador, nunca republicado) · role `hunter_worker` em todos os entry points, nenhum dado de tenant tocado ✔ · mutação observável em `system_events` ✔.

## (d) Verificação real (2026-09-05, saída colada)
```
uv run pytest services/market-worker -q -p no:cacheprovider   → 139 passed in 169.49s
uv run pytest services/market-worker -q -p no:cacheprovider   → 139 passed in 170.44s   (2ª rodada, sem flakiness)
uv run pytest packages/core -q -p no:cacheprovider            → 254 passed in 274.27s
uv run ruff check services/market-worker packages/core        → All checks passed!
uv run ruff format --check services/market-worker packages/core → 111 files already formatted
uv run pyright services/market-worker packages/core           → 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py                → scanned 127 files; 0 over budget, 0 grandfathered
```
✘ **Prova de dado real ainda não feita.** Subir o worker contra a Binance e mostrar `mkt:binance:BTCUSDT:ticker` vivo com `ts` avançando é da **T1.6**; até lá `obsidian/02-MARKET/Market Collector.md` fica `status: parcial`.

## (e) Revisores
`code-reviewer` ✔ · `database-architect` ✔ (duas passadas, `db-review-T1.3.md` e `db-review-T1.3-part2.md`) · `exchange-integration-specialist` ✔ (revisão cruzada) · `security-reviewer` dispensado (sem auth, sem entrada de usuário, sem credencial no diff) · `risk-engine-guardian` não se aplica no M1.

## (f) Segunda opinião da Astra (adversarial, sobre o próprio código)
`.claude/state/astra-review-review-T1.3-final.md`: 20 itens CRITICAL/HIGH conferidos um a um. **17 FECHADO**, 3 ABERTO — todos os três fora do escopo da T1.3 e já registrados como follow-up em `docs/plans/M1.md`: H2 (token de progresso avança em frame duplicado, `packages/exchange-adapters`, T1.2), D1 (helpers de domínio em ×100, `packages/core/hunter_core/domain/market.py`, T1.1c), D4 (`lock_timeout` em `infra/scripts/create_partitions.py`, T1.6/ops). Nenhum CRITICAL/HIGH aberto dentro dos arquivos da T1.3.

## (g) Commit
`b8c4766` — 58 arquivos, +7857 linhas. Conferido com `git diff --cached --name-only`: zero arquivos de `apps/**`, `packages/exchange-adapters/**` ou `packages/shared-types/**`.
