# Prova operacional — T2.5 (`scanner-worker`)

Stack local (`infra/docker/docker-compose.yml`), imagem `hunter-api:dev` construída do commit de
trabalho da T2.5, contra o **market-worker real** coletando a Binance. Tudo abaixo foi lido do
banco, do Redis, do `/metrics` e do `docker stats` — nenhum número aqui é estimado.

## 1. Janela

| | |
|---|---|
| Janela contínua | **2026-09-06T15:48:17Z → 16:18:52Z** (30 min 35 s) |
| Observação adicional | 16:25:37Z → 16:33:16Z (após o correção de readiness da §7) |
| Serviços no ar | `postgres`, `redis`, `market-worker`, `scanner-worker`, `strategy-worker`, `api` |
| Migrações | `0004_outbox_pending_index` (head) |
| Seed | `feature_definitions` 28 linhas, `opportunity_weights` v1+v2 (v2 ativa) |

**Nota de deploy do `components_frozen` (T2.4 §2):** verificado no banco —
`SELECT version, is_active, weights->>'components_frozen'` devolve `v2 | t | false`. O `UPDATE` de
ratificação **não** foi executado: ele só é necessário depois que `infra/scripts/seed_reference.py`
publicar a flag como `true`, e essa é a tarefa coordenada de dois arquivos do notes-T2.4 §2, fora do
escopo desta. Executá-lo agora deixaria banco e seed em desacordo. Registrado, não feito.

## 2. O que o scanner fez

| Métrica | Valor |
|---|---|
| Mercados no universo | **200** (`markets.is_monitored`), 203 distintos com snapshot ao longo do dia |
| Avaliações (vetores) na janela | **27 336** (`hunter_scanner_markets_evaluated_total{outcome="covered"}`) |
| `feature_snapshots` gravadas | **8 142** ao fim da janela (11 137 no total até 16:33), 43 minutos distintos |
| Transações de persistência | 169 lotes, 10,48 s somados → **62 ms por lote** |
| Eventos consumidos | `market.ticks` 75 860 · `market.candles.closed` 41 369 · `market.derivatives` 31 853 · `market.liquidations` 60 · `market.universe.changed` 2 |
| Regimes | 1 linha (`global`, `UNKNOWN`, motivo `trend_input_unavailable`) + 1 evento `regime.changed` publicado pela outbox |
| Anomalias abertas / resolvidas | **0 / 0** |
| Oportunidades por status/estágio | **nenhuma** |
| `outbox` pendente | 0 durante a janela (182 414 eventos totais, quase todos do market-worker); 307 no pico de backlog às 16:33 |
| Exceções no scanner em 30 min | **0** (`grep -icE "traceback\|_failed\|exception"` sobre os logs da janela) |
| CPU / memória | scanner **99 %** de um núcleo, 107 MiB · market-worker 98 %, 271 MiB |
| `/ready` | verde (ver §7 para a correção que isso exigiu) |

## 3. `covered_until` funcionando com dado real — o resultado que destrava o EARLY

Este é o item que a T2.2 (§13) e a T2.3 (§10b) deixaram como pré-requisito: sem a prova de cobertura
do coletor, `trade_velocity_1m`, `buy_pressure_5m` e `sell_pressure_5m` **nunca** publicam e nenhum
EARLY é confirmado. Última minuto fechado da janela, sobre 202 mercados:

| Feature | Mercados com `quality = ok` |
|---|---|
| `trade_velocity_1m` | **179** |
| `buy_pressure_5m` / `sell_pressure_5m` | **178** cada |
| `return_1m` / `return_5m` / `return_15m` / `volume_acceleration` | 179 cada |
| `funding_rate` | 165 |
| `orderbook_imbalance_20` / `spread_pct` | 86 |

Hash publicado pelo coletor (`mkt:binance:coverage`): `session_since` no instante da conexão,
`covered_until` avançando a cada 0,25 s, um campo `sym:<symbol>` por mercado assinado. Heartbeat do
scanner com `coverage=live`.

Distribuição de qualidade no mesmo minuto: **1 588 `ok` / 3 452 `unavailable`**. Os motivos da parte
indisponível são o esperado num arranque frio, e cada um é um motivo, não um zero: `gap` (histórico
de candles ainda curto — o hot state tinha ~40 minutos, e `return_1h`/`return_4h`/`atr_14_pct`/
`distance_from_24h_*` pedem de 60 a 1 440 minutos), `warmup`, `missing_input` (sem `deriv_history`,
que só existe depois de duas amostras de OI a 5 min) e `insufficient_coverage` (mercados assinados
há menos que a janela pedida).

## 4. Latência tick → oportunidade — **fora do orçamento, e este é o achado principal**

Histograma `hunter_scanner_tick_to_opportunity_seconds`, medido do carimbo do **mercado** (o `ts` do
evento que sujou o mercado) até o instante do score:

| | Janela de 30 min | Após restart (8 min) |
|---|---|---|
| Amostras | 27 259 | 7 540 |
| Média | **201 s** | 407 s |
| p50 | ~21 s | > 21 s |
| p95 / p99 | **> 21 s** (acima do último bucket) | > 21 s |
| Amostras ≤ 3 s | 150 de 27 259 (0,55 %) | 34 de 7 540 |

**Alvo da decisão conjunta: p99 ≤ 3 s. Medido: > 21 s. Não cumprido.** `hunter_scanner_dirty_markets`
fica estável em ~117–149, isto é, o scanner opera com backlog permanente: uma passada completa sobre
200 mercados custa ~13 s no contêiner (27 336 avaliações / 31 min ≈ 14,7/s), enquanto os ticks
chegam a ~42/s.

A causa está medida e é herdada, não nova: a revisão cruzada da T2.2 mediu ~50 ms por vetor com 53 %
em `windows._epoch_minutes` (chamado 17× por vetor) e **entregou explicitamente a otimização à T2.5**
(`notes-T2.2.md` §16). O teste sintético desta tarefa
(`services/scanner-worker/tests/test_load.py`, 200 mercados × 1 tick/s) reproduz o teto sem rede:
**p50 31,5 ms e p99 96,5 ms por mercado, 7,2 s por passada** — e está no repositório como
`xfail(strict=True)`, de modo que vira vermelho por *passar* no dia em que a otimização entrar. O
contêiner é pior que o sintético porque acrescenta o round-trip do Redis por mercado.

O remédio prescrito (memo por `(mercado, as_of)` em
`packages/indicators/hunter_indicators/features/windows.py`) é código de motor, e este brief autoriza
`packages/indicators/**` só para adaptadores finos de IO. Fica como o item 1 do NEXT STEP.

## 5. Radar da API — **não demonstrado**, e o motivo exato

`GET /api/v1/radar` exige autenticação Clerk, então a verificação foi feita contra a consulta que o
repositório emite (`FROM opportunities`, `apps/api/hunter_api/repositories/radar.py`):
**0 linhas**. O caminho é determinístico e correto:

1. o arquivo de baselines está **vazio** (`feature_baselines` = 0 linhas);
2. sem baseline utilizável, nenhum componente MAD está disponível e o scorer devolve
   `score = None` com `eligible = False` (`no_eligible_evidence`) — "degradado não é evidência"
   (notes-T2.4 §4);
3. `advance_status` com amostra inelegível **não abre episódio** (notes-T2.4 §5);
4. sem episódio não há linha em `opportunities`, e o Radar seleciona `FROM opportunities` de
   propósito, para não mostrar um mercado com score fabricado.

Ou seja: o worker está correto e o item de aceite **não foi demonstrado**. Nenhuma linha foi
inventada para demonstrá-lo. O que falta é o **bootstrap** das baselines sobre candles persistidas,
que esbarra no mesmo teto da §4 (10 080 cortes por mercado × ~30 ms ≈ 5 min/mercado ≈ 16 h para 200)
— os módulos de leitura estão prontos e testados, o laço que os agenda não foi entregue
(`notes-T2.5.md` §8). Sem bootstrap, a primeira baseline utilizável exige 3 dias distintos e ≥ 120
observações por bucket, ou seja, ~3 dias de operação contínua.

A Astra antecipou exatamente isto na consulta de desenho: *"a API consulta somente `opportunities`;
mercados sem episódio ficam ausentes. Se não surgir episódio, esse item fica não demonstrado, sem
inventar linhas e sem declarar o aceite integral cumprido."*

## 6. Defeitos encontrados **pela prova** (nenhum apareceu nos testes)

1. **`deque[NormalizedCandle](maxlen=…)` num `default_factory`** — o subscrito é avaliado em runtime
   e o tipo é import de `TYPE_CHECKING`: o worker morria na partida com `NameError` enquanto toda a
   suíte passava. Corrigido; teste novo constrói todo componente de longa vida
   (`test_lifecycle.py::test_every_long_lived_component_can_actually_be_constructed`).
2. **Regime "do futuro" derrubando o ciclo inteiro** — o regime era classificado em `utcnow()` e os
   mercados avaliados no corte provado pelo coletor (~10 s atrás); `ScoreContext` recusa evidência
   posterior ao corte (corretamente) e a exceção descartava o lote de **todos** os mercados. Três
   correções: o regime passa a ser classificado no mesmo corte provado, `Scanner.regime_for` retém
   uma decisão mais nova que o corte em vez de passá-la, e o laço trata falha **por mercado**.
   Teste: `test_pipeline.py::test_a_regime_newer_than_the_cut_is_withheld_instead_of_raising`.
3. **Métricas invisíveis** — declaradas no registry global do `prometheus_client` em vez do
   `hunter_core.observability.registry`, que é o que `/metrics` expõe: o endpoint respondia 200 sem
   uma linha `scanner_`. Corrigido; teste
   `test_lifecycle.py::test_every_metric_is_on_the_registry_that_is_actually_scraped`.
4. **`/ready` vermelho num worker saudável** — `market.liquidations` publicou 60 eventos em 30 min e
   o `scanner_consumers` só registrava progresso quando chegava mensagem, então stream quieto lia
   como laço travado. Corrigido com a mesma sonda do strategy-worker (`XREVRANGE`: atrás do stream é
   travado, no mesmo ponto é ocioso). Cinco testes em `test_health.py`.
5. **`SELECT … FOR SHARE` recusado pelo banco** (BUG-1 do relatório) — `hunter_worker` não tem
   `UPDATE` em `feature_baselines` e o PostgreSQL exige `UPDATE` para travar linha. O scanner sonda
   na partida, registra em `error` e degrada para leitura de existência; a amostra cuja baseline
   sumiu continua **não sendo gravada**. Log real da partida:
   `scanner_baseline_lock_denied … "hunter_worker lacks UPDATE on feature_baselines"`.

## 6b. Defeitos encontrados pela **revisão de diff da Astra**, corrigidos e re-provados

6. **O envelope não pode renomear o vetor.** Eu tinha renomeado `vector` -> `features` ao gravar,
   contra o que `apps/api/.../radar_common.py` lia no commit `5bd17db`. A Astra verificou o
   histórico e mostrou que **`98bcfea` já havia corrigido a API** para ler
   `feature_snapshot.vector.values` (com teste de contrato construído do próprio
   `opportunity_envelope()`), publicado depois de eu ler o arquivo. O rename foi removido: o
   envelope é gravado como o motor o produz. O teste passou a afirmar contra a **constante da
   própria API** (`FEATURE_ENVELOPE_PATH`), para não poder divergir de novo em silêncio.
7. **A invalidação por baseline sumida deixava efeitos passarem.** Removia a oportunidade e a
   amostra de history, mas mantinha as anomalias, os eventos e os callbacks pós-commit — publicando
   `opportunities.updated` de uma linha que ninguém gravou e avançando o marcador de history. Agora
   a invalidação derruba **todos** os efeitos do mercado afetado (`event_market` e o dono de cada
   callback tornam isso possível). Teste:
   `test_persistence.py::test_a_vanished_baseline_drops_every_effect_of_that_evaluation`.
8. **Um lote que falha perdia o minuto para sempre.** `last_snapshot_minute` avançava ao montar o
   lote; se a transação falhasse, o lote era descartado e nenhuma avaliação posterior recriava
   aquele minuto. A promoção passou a acontecer **depois do commit**.
9. **E o defeito que essa correção introduziu**, encontrado na prova: com a promoção adiada, várias
   avaliações do mesmo minuto entram no mesmo lote e `ON CONFLICT DO UPDATE` recusa tocar a mesma
   linha duas vezes (`CardinalityViolationError`). Corrigido com de-duplicação por chave de conflito
   dentro do lote, ficando a **última** (a computada do hot state mais fresco). Teste:
   `test_persistence.py::test_one_batch_with_the_same_minute_twice_commits_once`.

Após as quatro correções: **10 minutos contínuos (17:01:53Z → 17:11:53Z) com 0 exceções**,
`/ready` verde nos quatro checks, `outbox` pendente 0, 18 740 snapshots sobre 96 minutos distintos.

## 7. Veredito honesto

| Item do brief | Situação |
|---|---|
| Consumidores dos 5 streams, grupos próprios, idempotência, ACK após efeito | **OK** (75 860 + 41 369 + 31 853 + 60 + 2 mensagens processadas, 0 erro de consumidor) |
| Cadências (features 1 s, score 2 s, regime 1 min, watchdog) | **Implementadas**; a de features não é *atingida* sob 200 mercados (§4) |
| Contexto incremental, mercados sujos, coalescência | **OK** (`dirty` oscila, uma avaliação por mercado por ciclo) |
| `covered_until` preenchido pela saúde da coleta | **OK e provado com dado real** (§3) |
| Persistência em lote numa transação | **OK** (169 lotes, 62 ms cada) |
| Publicação pela outbox genérica | **OK** (`regime.changed` publicado; 0 pendências durante a janela) |
| `radar:scores` / `rt:radar` | **vazios** — consequência da §5, não do transporte |
| Supervisão, `/ready`, heartbeat, métricas, compose | **OK** (após as correções da §6) |
| `feature_snapshots` por minuto | **OK** (8 142 linhas / 43 minutos / 202 mercados) |
| Anomalias, oportunidades, history, baselines gravadas | **0 linhas** — §5 |
| p99 tick→oportunidade ≤ 3 s | **NÃO CUMPRIDO** (> 21 s) — §4 |
| Radar da API com linhas reais | **NÃO DEMONSTRADO** — §5 |

O worker roda 30 minutos contra dado real sem uma exceção, escreve o que tem evidência para
escrever, e diz com motivo estruturado tudo o que não tem. O que falta para o aceite integral do M2
são duas coisas, e ambas são a **mesma** dependência: o custo por vetor da T2.2 precisa cair antes do
bootstrap das baselines ser viável, e sem baselines não há score, nem anomalia, nem linha no Radar.

---

# Prova operacional — T2.5b (bootstrap, refresh horário, backfill, derivativos)

Segunda janela, sobre o mesmo stack local, com a imagem `hunter-api:dev` reconstruída do
commit de trabalho da T2.5b (`docker compose build api`) e o `scanner-worker` recriado. Tudo
abaixo foi lido do banco, do Redis, do `/metrics`, do `/ready` e do `docker stats`.

## 1. Janela e preparação declarada

| | |
|---|---|
| Janela contínua | **2026-09-06T18:20:23Z → 18:51:01Z** (30 min 38 s) |
| Serviços | `postgres`, `redis`, `market-worker`, `scanner-worker`, `strategy-worker`, `api` |
| Migrações | `0005_baseline_lock_grant` (head) — chegou de outra tarefa em voo e **fecha o BUG-1** da §6.5 |
| Universo | 200 mercados monitorados |

**Preparação feita à mão, e por quê (isto não é dado inventado).** O banco local só tinha
candles de `2026-09-04T15:27Z` em diante — 2,1 dias. Com 2 dias não existe bucket utilizável
(o portão pede ≥ 3 dias distintos), então nenhuma baseline do bootstrap passaria e a prova
mediria o vazio de novo. O caminho previsto para isso é o `market.backfill.requested`, e ele
**não tem consumidor** (§4). Então fiz à mão exatamente o que o consumidor faria: inseri 32
linhas em `ingestion_gaps` (8 mercados × 4 janelas de 1 dia, `2026-09-01T00:00Z` →
`2026-09-04T15:26Z`) e deixei o **market-worker** buscá-las por REST, que é o dono do REST.
Resultado: 8 mercados com **5,76 dias de candles reais da Binance** (`8 299` minutos cada);
os outros 192 continuam com 2,1 dias. Nenhuma linha foi escrita por mim em `candles`.

## 2. O bootstrap rodou, e o que ele produziu

| Métrica | Valor |
|---|---|
| Mercados com bootstrap concluído na janela | **28** (`feature_baselines.source='bootstrap'`, 28 `market_id` distintos) |
| Revisões de bootstrap gravadas | **9 909** no banco (`hunter_scanner_baseline_revisions_total{source="bootstrap"}` = 9 549 no instante da leitura) |
| Buckets **utilizáveis** (≥ 3 dias distintos e ≥ 120 observações) | **1 065** |
| Minutos reprocessados | **278 917** cortes (`hunter_scanner_bootstrap_cuts_total`) |
| Custo por mercado | 10 080 cortes; ~65 s de parede neste banco (a maior parte dos cortes cai antes do primeiro candle e é barata) |
| Progresso em `/ready` | `"baselines":"bootstrapping 4USDT (9/200)"` às 18:31, `"bootstrapping BEATUSDT (26/200)"` às 18:51 |
| `scanner_baselines` (readiness) | **verde a janela inteira**, com o progresso ao lado como *status detail* |

Ordem: `BTCUSDT` primeiro por desenho (o regime e o breadth dependem dele), depois a ordem do
universo.

## 3. O refresh horário

Na partida, o bucket da hora fechada (17:00Z) foi recomputado para os 200 mercados a partir das
`feature_snapshots` de 7 dias:

```
scanner_baseline_hour_refreshed hour=2026-09-06T17:00:00+00:00 markets=200 written=3045 withheld=0 cached=3045
```

**Só o bucket daquela hora** (`hour=17`), 3 045 revisões `live`, nenhuma retida — não havia ainda
bootstrap utilizável para nenhuma delas, então não havia maturidade a proteger. A política de
retenção de revisão imatura (`outcome="withheld"`) aparece no `/metrics` em 0, que é o número
correto para esta janela; quem a exercita é o teste
`test_an_immature_live_revision_does_not_supersede_a_usable_bootstrap`.

## 4. Backfill: pedido, e **sem consumidor** — o bloqueio herdado

| | |
|---|---|
| Pedidos publicados | **28** (`hunter_scanner_backfill_requests_total`), 29 mensagens no stream |
| Exemplo real | `scanner_backfill_requested symbol=BTCUSDT gap_start=2026-08-29T17:00:00Z gap_end=2026-09-01T00:00:00Z reason=baseline_bootstrap` |
| Consumidores do stream | **nenhum** — `XINFO GROUPS market.backfill.requested` devolve vazio |
| REST chamado pelo scanner | **zero** (o teste mata `httpx.AsyncClient` e o bootstrap passa) |

O pedido é publicado corretamente e **ninguém o atende**: `services/market-worker` não tem
consumidor de `market.backfill.requested` (a `recovery.py` acha lacunas pela própria janela de
detecção, de 1 439 minutos). É a MF-3 da Astra, confirmada, e está **fora dos arquivos desta
tarefa**. Enquanto não existir, "faltou histórico" é declarado (`markets_under_construction`) e
reparado à mão, como na §1.

## 5. Derivativos

| | |
|---|---|
| Observações de OI carregadas na partida | **7 164** sobre 200 mercados (`scanner_baselines_loaded deriv_observations=7164`) |
| Janela | 9 h (cobre `open_interest_change_4h` e `funding_change_8h` com as tolerâncias) |
| `OPEN_INTEREST_SPIKE` desarmado | **1 mercado** (`deriv_history_unavailable`); nos outros 199 está armado |
| `FUNDING_ANOMALY` desarmado | **81 mercados** (`funding_unavailable`: o hash `deriv` não traz funding para eles) |
| `LIQUIDATION_CLUSTER` / `CROSS_EXCHANGE_DIVERGENCE` | 200 cada, pelos motivos herdados (`feature_not_implemented`, `single_exchange_until_m1b`) |

Antes da T2.5b o `load_deriv_history` nunca era chamado e `OPEN_INTEREST_SPIKE` ficava **armado e
mudo** nos 200. Agora o motivo é uma métrica e um campo do heartbeat
(`detectors_disarmed=...OPEN_INTEREST_SPIKE:deriv_history_unavailable=1`).

## 6. O que o scanner fez na janela

| Métrica | Valor |
|---|---|
| Avaliações (vetores) | **13 725** (`markets_evaluated_total{outcome="covered"}`) |
| `feature_snapshots` gravadas na janela | **6 599** |
| Eventos consumidos | ticks 52 248 · candles 53 746 · derivativos 49 678 · liquidações 105 · universo 1 |
| Transações de persistência | 96 lotes, 17,75 s somados → **185 ms por lote** |
| `outbox` pendente | **0** |
| Anomalias abertas / oportunidades | **0 / 0** |
| Regimes | 1 linha (`UNKNOWN`, warm-up: `regime_seeded samples=137 usable=False`) |
| Exceções em 30 min | **0** (`grep -icE "traceback\|exception\|_failed"` sobre os logs da janela) |
| CPU / memória | scanner **99,8 %** de um núcleo, 166 MiB · market-worker 99,9 %, 275 MiB |
| `/ready` | **200** nos quatro checks, com `baselines: "bootstrapping ... (26/200)"` |

## 7. Latência tick → oportunidade — continua fora do orçamento, com uma causa a mais

| | Janela T2.5 (30 min) | Janela T2.5b (30 min) |
|---|---|---|
| Amostras | 27 259 | **13 645** |
| Média | 201 s | **145 s** |
| ≤ 3 s | 150 (0,55 %) | **0** |
| ≤ 21 s | ~2 000 | **2 066 (15 %)** |
| p95 / p99 | > 21 s | **> 21 s** |

**Alvo p99 ≤ 3 s: não cumprido.** Duas causas somadas, ambas declaradas:

1. a herdada e não resolvida: ~50 ms por vetor (`windows._epoch_minutes`, notes-T2.2 §16). A
   T2.2b, que derruba isso para ≤ 5 ms, **não estava na árvore** durante esta prova
   (`packages/indicators/hunter_indicators/features/windows.py:38` continua sem memo);
2. a nova e intencional: o bootstrap divide o mesmo event loop, com `bootstrap_duty = 0,4`
   (padrão). Perto de metade do relógio do scanner esteve reproduzindo 279 mil minutos de
   histórico. Essa metade desaparece sozinha quando o arquivo estiver construído; a outra é o
   item 1.

O número honesto: com o bootstrap ativo há **menos avaliações** (13 725 contra 27 336) e uma
média **melhor** (145 s contra 201 s), porque o backlog de mercados sujos ficou parecido
(`dirty` 124–162 contra 117–149) sobre menos amostras — a latência não piorou, e também não
chegou perto do alvo.

## 8. Radar da API — **ainda não demonstrado**, com um motivo novo e mais estreito

`GET /api/v1/radar` seleciona `FROM opportunities`: **0 linhas**. `radar:scores` (ZSET): **0
entradas**. Mas o motivo mudou de lugar, e a diferença importa.

Sonda somente-leitura dentro do contêiner, pelo caminho de produção (`build_market_context` →
`evaluate_market`), sobre os 26 mercados já bootstrapados:

```
       ADAUSDT score=0.00 eligible=True  conf=0.0952 status=NORMAL stage=NONE available=['agent_consensus','anomalies','volume']
       BTCUSDT score=0.09 eligible=True  conf=0.0952 status=NORMAL stage=NONE available=['agent_consensus','anomalies','volume']
        (24 outros) score=None eligible=False        available=['agent_consensus','anomalies']
scored: 2/26
```

Isto é **progresso real e verificável** sobre a T2.5, onde `score` era `None` em 200 de 200:

- **o scorer agora produz score elegível** (`eligible=True`) para os mercados com ≥ 3 dias
  distintos de histórico — exatamente os dois da amostra que passaram pelo backfill da §1;
- os outros 24 seguem `no_eligible_evidence` porque só têm 2,1 dias de candles: os buckets
  existem e não passam o portão. É a §4 de novo — o backfill não tem quem o atenda;
- mesmo nos dois que pontuam, **só o componente `volume` está disponível**. `momentum`,
  `liquidity`, `order_flow` e `derivatives` dizem `no_usable_input` e `market_regime` diz
  `regime_unknown` (o regime está em warm-up: `regime_seeded samples=137 usable=False`).
  `liquidity`/`order_flow` são estruturais e estão declarados desde a T2.3: o bootstrap **não
  pode** produzir baseline de livro nem de tape (`historical_source_unavailable`), então elas só
  amadurecem com 7 dias de `feature_snapshots` ao vivo;
- com um componente de oito e peso ~0,10, o score fica ~0, `advance_status` devolve `NORMAL`,
  `NORMAL` não abre episódio, e sem episódio não há linha em `opportunities` nem em
  `radar:scores`. **Comportamento correto**, não falha.

Nenhuma linha foi inventada para preencher o Radar. O que falta para demonstrá-lo, na ordem:
(a) um consumidor de `market.backfill.requested` (fora desta tarefa) para que os 192 mercados
restantes tenham 7 dias; (b) 7 dias de snapshots ao vivo para o livro e o tape, ou uma decisão
explícita sobre pontuar com menos componentes; (c) o memo da T2.2b, para que o bootstrap dos 200
mercados caiba em horas em vez de dias.

## 9. Veredito

| Item da T2.5b | Situação |
|---|---|
| Runner de bootstrap (7 dias, uma passada por minuto, lotes, progresso reidratável) | **OK** — 28 mercados, 9 909 revisões, 1 065 buckets utilizáveis |
| Refresh horário só do bucket da hora fechada | **OK** — `hour=17`, 3 045 revisões, nenhum outro bucket tocado |
| Backfill publicado, nunca REST, "em construção" com motivo | **OK no scanner**; **BLOQUEADO** do lado de quem atende (nenhum consumidor) |
| `load_deriv_history` chamado de verdade, detectores desarmados com motivo | **OK** — 7 164 observações; `OPEN_INTEREST_SPIKE` armado em 199/200 |
| Readiness declara o bootstrap sem ficar vermelho | **OK** — `"bootstrapping BEATUSDT (26/200)"`, quatro checks verdes |
| 0 exceções, outbox 0, snapshots por minuto | **OK** |
| p99 tick→oportunidade ≤ 3 s | **NÃO CUMPRIDO** (> 21 s) — §7 |
| Radar da API com linhas reais | **NÃO DEMONSTRADO** — §8, com o motivo agora medido componente a componente |

## 10. Confirmação após as correções da revisão de diff da Astra

A janela de 30 min da §1 mediu a imagem **anterior** às cinco correções (notes-T2.5 §21). Depois
delas a imagem foi reconstruída (`docker compose build api`) e o `scanner-worker` recriado, com uma
janela curta de confirmação — não é uma segunda prova de 30 min, é a evidência de que o binário
corrigido roda:

| | |
|---|---|
| Janela | **2026-09-06T19:12:48Z → 19:22:25Z** (9 min 37 s) |
| Exceções | **0** |
| `/ready` | `{"database":true,"redis":true,"scanner_consumers":true,"scanner_evaluation":true,"scanner_outbox":true,"scanner_baselines":true,"baselines":"bootstrapping DOGEUSDT (51/200)"}` |
| Bootstrap | **51 mercados** no arquivo (18 077 revisões), ~70 s por mercado, 10 080 cortes cada |
| Recarga imediata | `scanner_baseline_market_reloaded symbol=DEXEUSDT revisions=381` logo após cada mercado — a correção que impede um bootstrap de ficar invisível até a hora virar |
| Refresh horário | o bucket da hora 18 entrou (`live` foi de 3 045 para 6 263 revisões, 201 mercados) |
| `complete=False gaps=1` por mercado | correto: o histórico local começa em `2026-09-01`, então todo mercado tem um buraco declarado no início da janela de 7 dias e um pedido de backfill |

---

# Prova operacional — T2.5-backfill (consumidor de `market.backfill.requested`)

**2026-09-06**, stack local (`infra/docker/docker-compose.yml`), imagem `hunter-api:dev` reconstruída
da árvore de trabalho desta tarefa, `market-worker` recriado às **20:23:52Z** e observado até
**20:39:43Z** (15 min 51 s). `scanner-worker`, `api`, `strategy-worker`, `postgres` e `redis` no ar o
tempo todo, contra a Binance real. Todo número abaixo foi lido do Redis, do `/metrics`, do `/ready`,
do Postgres ou do log do contêiner.

**Ressalva honesta de ambiente:** a árvore de trabalho também contém as alterações **não commitadas de
outra tarefa em voo** (`services/scanner-worker/**`), que entraram na mesma imagem. O que está sendo
provado aqui é o consumidor do market-worker; o scanner é o produtor real, no estado em que está.

## 1. O grupo existe, e o backlog acabou

`XINFO GROUPS market.backfill.requested` — era **vazio** na T2.5b (§4 daquela prova), com 29 mensagens
paradas:

| Campo | Valor |
|---|---|
| `name` | `market-worker.backfill.binance.0of1` |
| `consumers` | 2 (o `instance` anterior e o atual; nomes por processo) |
| `pending` | **0** |
| `entries-read` | **97** |
| `lag` | **0** |
| `XLEN` | 97 |

As 97 mensagens são pedidos reais do scanner acumulados no stream (as 29 da prova da T2.5b mais as
publicadas depois). O grupo é criado em `id=0`, então a primeira partida **drenou o backlog inteiro**.

## 2. O que o consumidor decidiu (log real, dois exemplos)

```
market_backfill_planned  outcome=accepted symbol=ACEUSDT shard=0/1 reason=baseline_bootstrap
  requested_by=scanner-worker@6c6e55dea590:1 requested_minutes=8547 minutes=5247 chunks=22
  gap_start=2026-08-29T17:00:00+00:00 gap_end=2026-09-04T15:26:00+00:00 unstorable_minutes=3300
market_backfill_refused  reason=no_partition symbol=ADAUSDT exchange=binance
```

O segundo é o achado da prova (notes §29): `create_partitions.py` provisiona o mês corrente e os
seguintes, então **agosto não existe** e 3 300 dos 8 547 minutos pedidos não têm onde ser gravados. Em
vez de abortar a transação inteira e queimar as cinco tentativas do gap, o consumidor não planeja
aqueles minutos, diz `unstorable_minutes` no log e — quando a janela inteira é insalvável — recusa com
`no_partition` **sem marcar o `event_id`**, para ser reavaliado quando as partições existirem. Foi
por causa deste log que `accepted` passou a ser `partial` sempre que algo fica de fora.

## 3. Idempotência, medida em produção

Pedido injetado às 20:34:11Z **com o produtor real** (`hunter_scanner_worker.backfill.BackfillRequester`,
executado dentro do contêiner do scanner) para `ETHUSDT`, janela `[2026-09-03T20:34, 2026-09-04T20:34)`:

```
scanner_backfill_requested  symbol=ETHUSDT gap_start=2026-09-03T20:34:00+00:00 gap_end=2026-09-04T20:34:00+00:00
market_backfill_planned     outcome=empty symbol=ETHUSDT requested_minutes=1440 minutes=0 chunks=0
                            gap_start=2026-09-03T20:34:00+00:00 gap_end=2026-09-04T20:33:00+00:00
```

`gap_end` no log é `20:33` porque o intervalo do pedido é semiaberto e a linha de gap é inclusiva —
a tradução do §22 das notas, visível. E `minutes=0` porque a janela **já estava completa**:

```
select count(*) from candles c join markets m on m.id=c.market_id
where m.symbol='ETHUSDT' and c.open_time >= '2026-09-03 20:34' and c.open_time < '2026-09-04 20:34';
-> 1440
```

1 440 de 1 440 minutos persistidos, **nenhuma chamada REST** feita pelo pedido repetido. Um segundo
pedido do scanner (`JTOUSDT`, 8 427 minutos) na mesma janela também saiu `empty`.
`market_backfill_requests_total{outcome="empty"} 2.0`.

## 4. História que antes não existia

| Medida (Postgres, 20:39:43Z) | Valor |
|---|---|
| Velas `source='rest'` com mais de 25 h (fora da janela de detecção) | **411 803**, em **236 mercados** |
| Velas `source='rest'` com mais de 2 dias (inalcançáveis pela detecção, logo do backfill) | **123 857**, em **218 mercados** |
| Minuto mais antigo já preenchido | **2026-09-01T00:00Z** (a fronteira da partição; agosto continua sem partição) |
| `ingestion_gaps` | `recovered` 16 732 · `open` 2 136 · `failed` 2 |
| Velas antigas preenchidas na janela de 6,5 min medida (20:33 → 20:39) | +9 774 minutos |
| Gaps recuperados no mesmo intervalo | +43 (≈ 6,6/min, o teto é 6 por ciclo de 60 s) |

**O que isso destrava, que é o ponto da tarefa:**

| | T2.5b (`t25-proof` §8) | agora |
|---|---|---|
| Mercados com ≥ 3 dias distintos de velas de 1 min | ~0 (192 de 200 tinham 2,1 dias) | **213** |
| Mercados com menos de 3 dias | quase todos | 25 |
| Baselines utilizáveis (buckets) | 1 065 | **3 220** (`hunter_scanner_baselines{state="usable"}`) |

"≥ 3 dias distintos" é exatamente o portão de maturidade da decisão conjunta do M2 (≥ 3 dias distintos
**e** ≥ 120 observações). Ele deixou de ser inalcançável por falta de dado local.

## 5. Saúde do coletor durante o bootstrap

| | |
|---|---|
| `/ready` ao fim | `{"database":true,"redis":true,"ingestion":true,"persistence":true,"partitions":true,"outbox":true,"rest_gate":"ok"}` |
| `outbox_events` pendentes | **0** |
| `market_backfill_cycle_failed` | **0** |
| Tracebacks em 17 min | **1** (`market_persist_flush_failed`, 20:25:20Z, 90 s após o restart) |
| Rate limit | nenhum `429`/`418`; nenhum `exchange_rest_admissions_suspended_total` |

O único traceback é um `TimeoutError` de 10 s no COMMIT de um lote de persistência (`persist.py:203`)
durante a rajada de partida — o lote é **retentado**, não descartado (só é largado se passar de
`queues.max_age`), e a prontidão de `persistence` nunca ficou vermelha. Está registrado como
preocupação: o backfill acrescenta contenção no Postgres (leituras de cobertura de 7 dias e escrita de
lotes de velas antigas) e uma vez em 17 minutos isso empurrou um COMMIT além dos 10 s.

## 6. O que esta prova **não** mostra

- **Nenhum pedido novo do scanner na janela.** O `scanner-worker` deste contêiner não publicou nada
  entre 20:23 e 20:39 (a deduplicação por janela é de 1 h), então os dois pedidos servidos na janela
  foram um injetado com o produtor real e um antigo reentregue. O que a janela mostra de verdade é o
  **dreno** (as 97 mensagens já consumidas, os gaps sendo recuperados a 6/ciclo).
- **Backfill de sete dias completo:** impossível hoje, porque agosto não tem partição (§2). Os 5–6
  dias de setembro são o que existe, e é o que foi preenchido.
- **Concorrência entre shards reais:** o stack local roda `MARKET_SHARD=0/1`. O fan-out por shard está
  provado em teste (`test_a_market_of_another_shard_is_ignored_without_effect`), não em operação.
- **p99 tick→oportunidade** continua fora do orçamento e não é assunto desta tarefa (t25-proof §7).

---

# Prova operacional — T2.5c (contexto incremental) — 2026-09-06

Terceira janela, mesmo stack local, imagem `hunter-api:dev` reconstruída da árvore de trabalho da
T2.5c (`docker compose build api`) e **só o `scanner-worker` recriado** — o `market-worker` seguiu
com o contêiner que já estava de pé, porque há outra tarefa em voo nos arquivos dele. Tudo abaixo
foi lido do `/metrics`, do `/ready`, do Redis, do Postgres e do `docker stats`.

## 1. Janela

| | |
|---|---|
| Processo recriado | **2026-09-06T20:33:24Z** |
| Janela medida | **20:33:24Z → 21:05:29Z** (32 min 5 s) |
| Universo | 200 mercados monitorados |
| Serviços | `postgres`, `redis`, `market-worker`, `scanner-worker`, `strategy-worker`, `api` |
| Exceções no log do scanner | **0** (`grep -ciE "traceback|exception|error"` → 0 em 169 linhas) |
| `/ready` | **200** a janela inteira: `{"database":true,"redis":true,"scanner_consumers":true,"scanner_evaluation":true,"scanner_outbox":true,"scanner_baselines":true,"baselines":"bootstrapping JTOUSDT (91/200)"}` |

## 2. O que o cache fez, medido dentro do contêiner

`docker exec … probe2.py` (só leitura, 5 mercados líquidos, caches quentes):

```
hiredis: False
round 0: read=22.5ms candles=37.3ms trades=25.5ms book+deriv=0.2ms | rows candles=1009 trades=2000
round 1: read=19.2ms candles=0.8ms  trades=0.9ms  book+deriv=0.3ms | rows candles=1009 trades=2000
round 2: read=18.6ms candles=0.8ms  trades=0.7ms  book+deriv=0.3ms | rows candles=1009 trades=2000
round 3: read=19.3ms candles=0.9ms  trades=1.2ms  book+deriv=0.2ms | rows candles=1009 trades=2000
```

**Decodificar 3 000 linhas por tick passou de 62,8 ms para 1,7 ms.** E o contador confirma no
processo real: entre 21:00:32 e 21:03:36 (184 s, ~4 400 avaliações),
`hunter_scanner_hot_rows_decoded_total` subiu **1 262** — sem reaproveitamento seriam ~13 milhões.

| Métrica | Valor no fim da janela |
|---|---|
| `hunter_scanner_hot_rows_resident{kind="candles"}` | 162 050 |
| `hunter_scanner_hot_rows_resident{kind="trades"}` | 385 163 |
| `hunter_scanner_hot_rows_decoded_total` | 714 863 (dos quais ~540 000 na partida fria) |
| RSS do `scanner-worker` (`docker stats`) | **883,5 MiB** com buffers de ~800 velas; CPU 97–145 % |

## 3. Latência tick → oportunidade — **ainda fora do orçamento**, com a causa medida noutro lugar

Histograma completo da janela (o processo nasceu nela, então o acumulado **é** a janela):

| | |
|---|---|
| Amostras | **47 994** (T2.5b: 13 645 — **3,5×** mais avaliações no mesmo tempo) |
| ≤ 2 s | 11 |
| ≤ 3 s | **417 (0,87 %)** — T2.5b: 0 |
| ≤ 5 s | 4 961 (10,3 %) |
| ≤ 8 s | 14 580 (30,4 %) |
| ≤ 13 s | 25 190 (52,5 %) |
| ≤ 21 s | 28 099 (**58,5 %**) — T2.5b: 15 % |
| p50 (interpolado no balde 8–13 s) | **~12,4 s** |
| p95 / p99 | **> 21 s** (último balde) |

**Alvo p99 ≤ 3 s: não cumprido.** E a causa **mudou de dono** — não é mais o custo do contexto:

1. **O consumidor de `market.ticks` está permanentemente ~10 min atrás.** Medido com
   `XINFO STREAM` / `XINFO GROUPS` em 62 s: **151 mensagens/s produzidas, ~71/s consumidas**, lag
   estacionado em **~95 000** (o `MAXLEN` de 100 000 apara o resto). O histograma mede a partir do
   `ts` que o *mercado* carimbou — de propósito, "uma fila tem de aparecer no número". O consumidor
   de `market.candles.closed`, que tem 1/30 do volume, está com **lag 0**.
   **Atribuição limitada, de propósito** (correção da Astra): `last_input_ts` guarda o **maior**
   carimbo entre os gatilhos que sujaram o mercado (`MarketState.touch`), então um fechamento
   recente substitui o de um tick atrasado — nem toda amostra é a idade de um tick. O que está
   medido é o sintoma (a fila) e a correlação; separar "espera no stream", "espera no dirty set",
   "leitura", "cálculo" e "publicação" exige instrumentar as etapas, e isso não foi feito nesta
   janela;
2. **O laço de avaliação está saturado de CPU**: ~25–30 mercados/s contra os ~200/s que o throttle
   de 1 s pede. Por mercado: **~19 ms de leitura do Redis** (parser RESP em Python puro,
   `HIREDIS_AVAILABLE = False`) + ~10 ms de CPU. 97 % de um núcleo no `docker stats`, com o
   `market-worker` levando outros 99 % na mesma máquina.

Nenhuma das duas está em `services/scanner-worker/**`: a primeira é a taxa de consumo de
`hunter_core.events.consume` (uma verificação de `event_id` por mensagem), a segunda é o parser do
`redis-py` e a revalidação por tick em `hunter_indicators.features.context`. O que **estava** neste
serviço — decodificar o hot state inteiro a cada tick — caiu 37×.

## 4. O que o scanner escreveu na janela (o caminho durável acompanhou)

Contado por par **(mercado, minuto)**, não por linhas — a contagem bruta não distingue "um minuto
faltando aqui compensado por outro ali" (achado da Astra na revisão de diff). Nos 31 minutos
fechados de 20:34 a 21:05:

| | |
|---|---|
| Pares (mercado, minuto) distintos | **6 200** |
| Mercados com **os 31 minutos** | **199** |
| Mercados com menos | **2**, e os dois são a troca de universo das 20:38:58 (`scanner_universe_changed added=['VETUSDT'] removed=['ROBOUSDT']`): `VETUSDT` 26 minutos, `ROBOUSDT` 5 |
| Mercados distintos com snapshot | 201 (200 ao mesmo tempo; o 201º é a troca acima) |
| Anomalias ativas | 4 |
| **Oportunidades abertas** | **4** — `ETHUSDT` ANOMALY score 15,00 conf 0,1191; `DOGEUSDT` 0,67; `BTCUSDT` 0,16; `ADAUSDT` 0,00 |
| `radar:scores` (ZSET) | **5 entradas** |
| Revisões de baseline no arquivo | 45 199 |

**O Radar tem linhas reais pela primeira vez** (T2.5 e T2.5b: 0 linhas, 0 entradas). Não é mérito
desta tarefa — é o bootstrap da T2.5b tendo terminado em mercados suficientes —, mas é a primeira
janela em que o pipeline inteiro produz o artefato que ele existe para produzir.

## 5. Bootstrap: suspenso a janela inteira, e isso é a resposta certa

`hunter_scanner_bootstrap_suspended = 1` do primeiro minuto ao último, `bootstrap_cuts_total = 0`,
`/ready` verde com `"bootstrapping JTOUSDT (91/200)"` ao lado. A contrapressão da §27 das notas fez
exatamente o que foi desenhada para fazer: com o mercado sujo mais velho sempre acima de 1 s, o
replay não tomou uma fatia sequer. **A consequência honesta é que o bootstrap não avança neste
stack enquanto o custo por avaliação não cair** — e é melhor que ele diga isso (métrica + `/ready`)
do que roubar 40 % de um laço que já está atrasado.

## 6. Defeito encontrado pela prova, e que não é desta tarefa

`mkt:coverage:binance` está **congelado**: `covered_until == session_since ==
2026-09-06T20:23:56.93Z`, 41 minutos parado, enquanto o tape e as velas estão frescos (trade mais
novo 8 s atrás, vela do minuto fechada no segundo certo). Consequência: **todas** as 48 057
avaliações da janela saíram `outcome="uncovered"`, e toda feature de tape saiu
`insufficient_coverage`. O `CoverageTracker` é do `market-worker`
(`hunter_market_worker/coverage.py`, carimbo a cada 0,25 s), o contêiner dele não foi recriado nesta
janela e há **outra tarefa em voo nesses arquivos** — então fica registrado como observação, não
como diagnóstico: quem estiver no `market-worker` tem aqui o sintoma e a hora.

## 7. Veredito

| Item de aceite | Situação |
|---|---|
| Contexto incremental por mercado | **cumprido** — 62,8 ms → 1,7 ms de decode por tick, com identidade de bytes provada |
| Reprodutibilidade byte-idêntica | **cumprido** — `tests/test_context_identity.py`, 60 minutos com buraco, backfill e vela em formação |
| Memória medida e limitada | **cumprido** — 2 357 B/vela, 674 MiB projetados para 200×1500, 883 MiB de RSS reais |
| Fixture do `test_load.py` corrigida | **cumprido** — cada símbolo sob a própria chave, tape cheio |
| `xfail` removido | **não** — 3,23 s contra 3,0 s no pior caso sintético; `xfail(strict=True)` mantido com o número e a causa |
| Bootstrap não empurra a avaliação | **cumprido** — suspenso enquanto há atraso, com métrica |
| p99 ≤ 3 s com 200 mercados | **não cumprido** — p50 ~12,4 s, p99 > 21 s, com as duas causas medidas e ambas fora deste serviço |
| 0 exceções, `/ready` verde | **cumprido** |

**Ressalva de honestidade sobre esta janela:** ela rodou com a árvore **anterior** à revisão de
diff da Astra (`.claude/state/astra-review-T2.5c-diff.md`). Os quatro ajustes que vieram depois
dela — a linha de trade com verdicto dependente do corte, a amostra do histograma que passou a
exigir que a projeção não tenha falhado, o contador de decode por mercado e os limiares da
contrapressão lidos do `ScannerConfig` — não mudam nenhum dos custos medidos aqui (nenhum toca o
caminho quente), mas a prova **não** foi refeita depois deles e isto está dito em vez de omitido.

## 7. Confirmação depois das correções da revisão de diff da Astra

Imagem reconstruída e `market-worker` recriado às **21:24:03Z**, observado até **21:32:16Z**. O que a
segunda rodada acrescenta à prova:

**A cauda não liquidada é contada (must-fix 1), com dado real.** Pedido injetado às 21:13:16Z com o
produtor real para `BTCUSDT`, `[2026-09-06T15:13, 2026-09-06T21:43)` — deliberadamente 30 minutos no
futuro:

```
market_backfill_planned  outcome=empty->partial symbol=BTCUSDT requested_minutes=390 minutes=0
  chunks=0 gap_start=2026-09-06T15:13:00+00:00 gap_end=2026-09-06T21:11:00+00:00
  not_settled_minutes=31 unstorable_minutes=0
```

`gap_end` recortado para 21:11 (o último minuto liquidado: `align_open_time(21:13) − 2 min`) e
**31 minutos contados como não liquidados**, o que segura a marca do `event_id`. Este log é também o
que motivou o último ajuste: ele saiu `outcome=empty` enquanto a marca era retida — a palavra dizia
"pronto" e o ACK dizia "não". Agora `partial` é exatamente a condição de reter a marca
(`test_a_pass_that_wrote_nothing_and_still_owes_minutes_says_partial`).

**O `report_losses` não pode esperar pelo lock (correção do meu próprio remédio).** Ao pôr o terceiro
escritor sob o mesmo `pg_advisory_xact_lock` (must-fix 3), ele passou a **bloquear** dentro do
`drain_loop`, que roda uma vez por segundo, atrás de um ciclo de detecção que lê a cobertura de 200
mercados. Medido: `market_persist_lag lag_s=14,4` e 4 `market_persist_flush_failed` em 7 min. Trocado
por `pg_try_advisory_xact_lock`: quem não pega o lock **não escreve nada e não drena nada**, e a
iteração seguinte tenta de novo (o relatório de perdas é best-effort; o flush não é). Teste:
`test_the_loss_report_gives_up_the_lock_instead_of_delaying_the_flush`.

**Janela de confirmação (8 min):**

| | |
|---|---|
| `/ready` | verde, `rest_gate: ok` |
| Grupo | `pending 0`, `entries-read 98`, `lag 0` |
| `market_persist_flush_failed` | **2** (eram 4 em 7 min com o lock bloqueante) |
| `market_persist_lag` | 3 ocorrências |
| Outros erros | nenhum |

**Causa do timeout de flush: continua indeterminada, e é assim que fica registrada.** O `wait_for` de
10 s cobre `flush_batch` inteiro e o log não separa fases nem espera de lock (a Astra recusou minha
atribuição a contenção e ela está certa). O que se sabe: acontece durante a rajada de recuperação de
lacunas vivas de um minuto (dezenas de chamadas REST e transações curtas no mesmo event loop), o lote
é **retentado** e a prontidão de `persistence` nunca ficou vermelha. Medir por fase é o próximo passo,
e não é desta tarefa.

**Instantâneo final, 21:49:23Z** (25 min de contêiner no ar, sem reinícios): grupo
`market-worker.backfill.binance.0of1` com `pending 0`, `entries-read 99`, `lag 0`; **210 970** velas
`source='rest'` com mais de 2 dias em **218 mercados** (eram 123 857 às 20:39 — o dreno continua a
~6 lacunas por ciclo); `ingestion_gaps` `recovered` 17 660 · `open` 1 834 · `failed` 2; **213**
mercados com ≥ 3 dias distintos de velas de 1 min. `docker ps`: `market-worker` *healthy*.
