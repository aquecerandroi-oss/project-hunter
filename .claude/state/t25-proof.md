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
