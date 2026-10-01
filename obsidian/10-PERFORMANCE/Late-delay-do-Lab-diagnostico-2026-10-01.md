---
tags: [performance, latencia, shadow-lab, strategy-worker, diagnostico, late-delay]
updated: 2026-10-01
status: parcial
owner: backend-specialist
---

# `late:delay` no Shadow Lab — por que 1.927 sinais não entraram (diagnóstico de 01/10/2026)

> **Só leitura.** Nada foi alterado em código, banco ou VPS; consultas em `BEGIN READ ONLY`, métricas
> por GET, logs por leitura. Origem: a auditoria de dados da Astra
> (`.claude/state/astra-review-astra-auditoria-lab.md` §2, janela 01/09–01/10/2026 UTC): **2.028
> `no_entry`**, 1.927 `late:delay`, 4 `late:missed_open`, 97 `geometry`. Revisão da Astra sobre este
> diagnóstico: [[2026-10-01-late-delay-do-lab]].

## Veredito em quatro linhas

1. **`late:delay` é um incidente fechado de processamento, não lag atual.** Os 1.927 estão **todos** entre
   **06/09 18:17Z e 10/09 19:02Z**; de 11/09 a 30/09 houve **zero** em ~2.225 sinais de perpétuo, com
   atraso decisão-menos-barra de **2–3 s** (p95 4–7 s). A causa (um processo Python de um núcleo,
   despacho serial, replay no mesmo worker) já está em [[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]]
   e [[KB-0089-o-teto-de-cpu-de-um-processo-so]] e foi corrigida.
2. **Não é definição de limiar nem artefato de replay:** `delay_s > 120` equivale, para barras que fecham
   em minuto cheio, a **atraso de decisão ≥ 120 s** (menor lag entre `late:delay`: 120,006 s; maior entre
   quem entrou: 119,970 s). A coorte `replay` tem **0** `late:delay` (lag fixo de 2 s, por construção).
3. **A ausência não é aleatória:** quanto maior a rajada de sinais numa barra, maior a fração recusada
   (7,7 % → 53,5 %). Toda estatística de pesquisa que use 06–10/09 está enviesada para barras calmas.
4. **O que continua aberto é de instrumento, não de latência:** barras recusadas pela válvula
   (`late_delay_backlog`) ou pelo portão de 300 s (`UNAVAILABLE`) **não deixam linha em nenhuma tabela**;
   só contadores Prometheus que zeram a cada deploy. "Zero `late:delay` desde 11/09" **não prova** "zero
   barras tardias". Há também picos residuais de 41–94 s, 22 de 23 no shard 0.

## 1. Onde `late:delay` é decidido (arquivo:linha, relógio comparado)

| Peça | Onde | O que compara |
|---|---|---|
| Decisão | `services/strategy-worker/hunter_strategy_worker/plan.py:95-98` | `delay_s = next_minute_open(decision_at) − source_bar_close`; `late:delay` se `delay_s > costs.max_entry_delay_s` |
| `source_bar_close` | `consumer.py:137` | `close_time` da vela de 1 min vinda do stream — **não** `received_at`, **não** `emitted_at` |
| `decision_at` | `decide.py:214` | relógio de parede do worker; **igual a `emitted_at` em todas as linhas** (diferença 0,0 s) |
| Limite | frozen em cada versão | `max_entry_delay_s = 120` nas 12.857 linhas (1 valor distinto) |
| Válvula (sem linha) | `consumer.py:138-147`, `config.py:313` | `clock() − bar_close > 120 s` ao chegar → `hunter_shadow_bars_skipped_total{reason="late_delay_backlog"}`, antes de qualquer leitura de banco |
| Portão de elegibilidade (sem linha) | `decide.py:131-152`, `config.py:108` | lag > 300 s → `UNAVAILABLE`, não decide nem rearma |

Com `L = decision_at − source_bar_close` e barra fechando em minuto cheio, `delay_s = 60·(⌊L/60⌋+1)`, logo
`delay_s > 120 ⇔ L ≥ 120 s`. Os quatro `late:missed_open` têm lag 59,99 / 59,79 / 119,99 / 119,99 s —
decisões tomadas no último segundo de um minuto (09–10/09); a Astra lembra que `emitted_at` recebe
`decision_at`, então isso mostra decisão perto da fronteira, não necessariamente *commit* naquele instante
(`persist.py:93`, `confirm.py:76`).

## 2. Distribuição (SQL e saída reais, VPS, 01/10/2026 ~03:20Z)

Três consultas, `BEGIN READ ONLY`, `statement_timeout 60s`; o plano é `Seq Scan` de ~20 mil linhas
(`agent_signals`/`signal_outcomes`, `n_live_tup` 19.748 cada) — barato, sem competir com os workers.

```sql
-- por dia (UTC), coorte prospective: sinais, no_entry por motivo, lag decisão-menos-barra
SELECT (a.emitted_at AT TIME ZONE 'UTC')::date AS dia, m.market_type, count(*) AS sinais,
       count(*) FILTER (WHERE o.no_entry_reason = 'late:delay')       AS late_delay,
       count(*) FILTER (WHERE o.no_entry_reason = 'late:missed_open') AS missed_open,
       count(*) FILTER (WHERE o.no_entry_reason = 'geometry')         AS geometry,
       round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY extract(epoch FROM a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz)))::numeric,1) AS lag_p50_s,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz)))::numeric,1) AS lag_p95_s,
       round(max(extract(epoch FROM a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz))::numeric,1) AS lag_max_s
FROM agent_signals a JOIN signal_outcomes o ON o.signal_id = a.id JOIN markets m ON m.id = a.market_id
WHERE a.emitted_at >= '2026-09-01 00:00Z' AND a.emitted_at < '2026-10-01 00:00Z'
  AND split_part(a.supporting_features->>'cohort', ':', 1) = 'prospective'
GROUP BY 1, 2 ORDER BY 1, 2;
```

```text
    dia     | market_type | sinais | late_delay | missed_open | geometry | lag_p50_s | lag_p95_s | lag_max_s
 2026-09-06 | perpetual   |   1237 |         18 |           0 |       31 |      11.5 |      35.2 |     276.4
 2026-09-07 | perpetual   |   1633 |         10 |           0 |        9 |      12.5 |      36.7 |     290.1
 2026-09-08 | spot        |     93 |          0 |           0 |        7 |      44.0 |      81.7 |     104.6
 2026-09-08 | perpetual   |   2025 |        105 |           0 |       17 |      21.4 |     123.2 |     299.6
 2026-09-09 | spot        |    247 |        184 |           0 |       16 |     177.6 |     246.5 |     265.6
 2026-09-09 | perpetual   |   3287 |       1453 |           2 |       14 |     104.0 |     264.1 |     298.8
 2026-09-10 | perpetual   |    715 |        157 |           2 |        1 |      56.8 |     208.2 |     281.9
 2026-09-11 | perpetual   |    113 |          0 |           0 |        0 |       2.6 |       4.4 |      53.3
 2026-09-12 … 2026-09-28 (17 dias, 32–182 sinais/dia, só perpétuo): late_delay 0; lag_p50 2,1–2,7 s; p95 4,0–7,4 s
   (um dia dentro dessa faixa tem máximo alto:)
 2026-09-21 | perpetual   |    179 |          0 |           0 |        0 |       2.7 |       5.2 |      88.8
 2026-09-29 | perpetual   |    112 |          0 |           0 |        0 |       3.1 |      94.4 |      94.7
 2026-09-30 | perpetual   |    100 |          0 |           0 |        0 |       2.3 |       6.1 |      39.0
```

Soma: 18 + 10 + 105 + 1.453 + 157 = **1.743 perpétuo**; + 184 spot (todos em 09/09) = **1.927**; com 4
`missed_open` e 95 + 2 `geometry` fecham os 2.028 da auditoria. (Um rótulo "perp" em 1.637 para 09/09
circulou na primeira versão deste diagnóstico — era perp + spot; a Astra pegou. Em perpétuo 09/09 é
**44,2 %** de 3.287, não 47,2 %.)

```sql
SELECT min(a.emitted_at) primeiro, max(a.emitted_at) ultimo, count(*) n,
       min(extract(epoch FROM a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz))::numeric(10,3) menor_lag_s
FROM agent_signals a JOIN signal_outcomes o ON o.signal_id=a.id
WHERE o.no_entry_reason='late:delay' AND a.emitted_at >= '2026-09-01 00:00Z' AND a.emitted_at < '2026-10-01 00:00Z';
-- primeiro 2026-09-06 18:17:09Z | ultimo 2026-09-10 19:02:01Z | n 1927 | menor_lag_s 120.006
SELECT max(extract(epoch FROM a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz))::numeric(10,3) maior_lag_entrada_s,
       count(DISTINCT o.meta->'entry_plan'->>'max_entry_delay_s') valores_distintos, min(o.meta->'entry_plan'->>'max_entry_delay_s') max_entry_delay_s
FROM agent_signals a JOIN signal_outcomes o ON o.signal_id=a.id WHERE o.tracking_state <> 'no_entry'
  AND a.emitted_at >= '2026-09-01 00:00Z' AND a.emitted_at < '2026-10-01 00:00Z';
-- maior_lag_entrada_s 119.970 | valores_distintos 1 | max_entry_delay_s 120
```

**Fim do incidente, hora a hora (10/09, perpétuo + spot, coorte prospective; agregação local de uma cópia
das 12.857 linhas):** lag mediano 120 s às 16Z (22 de 38 sinais recusados), 56 s às 17Z, 44–48 s às
18–19Z (último `late:delay` às 19:02Z), 40 s às 20Z, **10 s às 21Z**, 8 s às 22Z e 2–3 s de 11/09 em diante.
A virada coincide com o deploy conjunto de sharding/cache/universo de 90 dias da noite de 10/09
([[KB-0089-o-teto-de-cpu-de-um-processo-so]] §5); a atribuição individual de cada correção continua sem
medida, como as duas KB já declaram.

**Por shard e por mercado:** os quatro shards (`STRATEGY_SHARDS=4`) só existem a partir da noite de
10/09, quando `late:delay` já havia acabado; qualquer fatia por `crc32(symbol)%4` de 08–10/09 é
hipotética (era um processo só). Por mercado o problema é difuso: **184 mercados** com ao menos um
`late:delay`, o maior com 65 (3,4 %) — é do universo inteiro, não de um símbolo.

**Por tamanho da rajada (perp, 08–10/09, barras agrupadas por `observation_ts`):**

| Sinais na barra | Barras | Sinais | `late:delay` | % |
|---|---:|---:|---:|---:|
| < 10 | 380 | 1.414 | 109 | 7,7 |
| 10–29 | 127 | 2.097 | 515 | 24,6 |
| 30–99 | 47 | 2.262 | 955 | 42,2 |
| ≥ 100 | 2 | 254 | 136 | 53,5 |

A barra de 09/09 21:00Z (a hora de −34 R de [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]]) teve 36
sinais perp+spot, **23 recusados (64 %)**, mediana de 133,6 s. Cuidado (Astra): "sinais emitidos na
barra" é aproximação da carga — depende também do roster e dos gatilhos.

## 3. Lag real, definição ou artefato?

- **Lag real de processamento (histórico):** sim, e já com causa medida (KB-0087/0089): despacho serial
  de ~200 velas por minuto num processo `asyncio` de um núcleo (GIL), replay no mesmo worker, flush de 1,0 s.
  Correções no ar: `BarDispatcher`, `STRATEGY_SHARDS=4`, `bar_context`, universo de pesquisa de ~200 para
  15 mercados (T3.82), `replay-worker` em serviço próprio.
- **Hoje, medido ao vivo (01/10 ~03:20–03:30Z):** o grupo consumidor de cada um dos 4 shards está em
  `lag 0`, `pending 0` (`XINFO GROUPS market.candles.closed`); `hb:strategy:shadow:{0..3}of4`:
  `decision_lag_p50_s` 1,9 / 3,8 / 2,4 s (shard 0 sem sinal desde o restart), `outbox_lag_s 0.0`,
  `errors 0`, `universe_size` 5 / 2 / 3 / 5 (= 15 mercados). Amostra de `docker stats` a cada ~4 s sobre o
  fechamento de 30 min das 03:30Z: **pico de 47 % de um núcleo** por shard, repouso < 1 %. Nada que
  lembre os 97–100 % da T3.74f. **A VPS tem 12 núcleos (`nproc`), não 1**; load average 5–6, e o
  processo que está a ~99 % de um núcleo é o `scanner-worker`, não o `strategy-worker`.
- **Replay/backfill:** descartado — a coorte `replay` tem 0 `late:delay` e 2 `geometry` (lag fixo de 2 s,
  `replay/environment.py:57`). Os **184 spot** são o mesmo atraso do dia 09/09 numa linha que o Lab nem
  deveria decidir (T3.73: o consumidor passou a recusar tudo que não seja `perpetual`).

### A janela de 30/09 (deploy errado, `STRATEGY_SHARDS=1` ao lado dos shards antigos)

Pergunta do Everton: houve pico entre 05:15Z e 14:48Z? **Nos 56 sinais persistidos da janela: não** (lag
mediano 2,4 s, máximo 39,0 s, nenhum ≥ 60 s; antes da janela: 9 sinais, máximo 2,6 s; depois: 35, máximo 4,2 s).
Evidências do que ocorreu: o grupo órfão `strategy-worker.shadow` tem `last-delivered` **14:47:14Z** (o
processo `SHARDS=1` consumia o fluxo inteiro até o deploy certo) e hoje `lag 50.004`; às **14:48:01–14:48:54Z**
o shard 0 (log `strategy_shard 0/4`) emitiu **980** `shadow_bar_skipped_late_backlog` com `backlog_s` de 174
a 11.822 s — o grupo `0of4` ficou sem consumidor desde ~05:15 e o stream retém ~3,3 h; a válvula fez o que
foi desenhada para fazer. **Limite (Astra):** o que está demonstrado é "sem pico nos sinais persistidos", não
"todas as barras foram avaliadas pelo processo `SHARDS=1`": o consumidor lê antes de concluir o handler e há
recusas com ACK sem avaliação (`consume.py:219`, `consumer.py:260`, `pre_dispatch.py:76`), e os shards antigos
também gravavam. Nada disso mostra um pico escondido; limita a força da frase.

## 4. Resíduo desde 11/09 e lacuna de cobertura

- **23 sinais com lag ≥ 20 s desde 11/09**, 22 no shard 0 (`crc32(symbol)%4`, que bate com os
  `universe_size` dos heartbeats: shard 0 = ETH, LINK, SOL, XRP, ZEC…). Picos: **29/09 15:45Z** (14 sinais, 93,9–94,7 s),
  **21/09 16:00Z** (76,4 e 88,8 s), 29/09 12:00Z (41 s). Todos abaixo de 120 s; **a causa não está
  estabelecida** — os logs de 29/09 já não existem (contêineres reiniciados em 30/09). Hipótese **não provada**:
  o shard 0 é o único líder do `outcome_sweep` (`outcome_sweep.py:102-108`; só o shard 0 o executa), no mesmo
  loop de eventos do consumidor e disputando os mesmos `lock_slot` — o shard 3, com os mesmos 5 mercados e mais
  sinais, tem máximo de 9,4 s. Plausível, não estabelecido.
- **Lacuna estrutural:** a válvula (`consumer.py:138-147`) e o portão de 300 s (`decide.py:134`) devolvem
  antes de existir linha; o `decision_lag` só é observado para sinais escritos (`decide.py:254-255`). Os
  contadores que cobrem isso hoje (`/metrics` dos 4 shards, 12,5 h desde 14:48Z de 30/09): `late_delay_backlog`
  = 980, todos no arranque do shard 0; **zero** avaliações `unavailable`; `queue_wait` em regime 99,1 % < 1 s
  (esse histograma é observado **antes** do `dispatcher.submit`, então não cobre a espera interna do
  despachante — Astra). Antes de 30/09 14:48Z não há contador sobrevivente.
- **O número que a auditoria diz não ter medido ("30 dias de `unavailable` que impediram a emissão") continua
  não medido**, e nenhuma consulta de hoje o recupera.

## 5. Impacto na pesquisa (denominadores)

Janela analítica recomendada pela Astra: **`06/09/2026 00:00Z ≤ source_bar_close < 11/09/2026 00:00Z`**
(recorte operacional por dias completos, não afirmação de que todas as horas estavam degradadas); a janela
**08/09 12:00Z–10/09 21:00Z** (33,4 % de 5.135 sinais perp recusados) entra só como sensibilidade. O dia
11/09 não ganha certificado: teve `RedisTimeoutError` na madrugada e o Redis reiniciou sozinho às 06:25 BRT
([[Diario/2026-09-11]]). Fora da janela larga restam 28 `late:delay` (06–07/09). `delay_s` como covariável **não
basta**: não recupera as barras que a válvula e o portão de 300 s descartaram nem os resultados das entradas que
não aconteceram.

Coorte **prospectiva, perpétuo** por versão (`late:delay` / sinais — recalculado só com perpétuo):

| EXP | Versões | `late:delay` / sinais |
|---|---|---|
| [[EXP-0001-momentum-v1]] | momentum v1, v2 | 15 / 963 (1,6 %); 148 / 631 (23,5 %) |
| [[EXP-0002-volume-anomaly-v1]] | volume_anomaly v1, v2 | 13 / 2.152 (0,6 %); 74 / 1.322 (5,6 %) |
| [[EXP-0005-momentum-paper]] | momentum v3 (**paper**) | 224 / 1.787 (12,5 %) |
| [[EXP-0006-momentum-piso-de-custo]] | momentum v4 | 92 / 302 (30,5 %) |
| [[EXP-0013-momentum-alvo-3-atr]] | momentum v6 | 145 / 309 (46,9 %) |
| [[EXP-0018-stop-largo]] | momentum v7/v8; mean_reversion v4–v7 | v7 4/11; v8 166/332 (50,0 %); mr v4 3/6, v5 3/6, v6 78/325 (24,0 %), v7 76/315 (24,1 %) |
| [[EXP-0019-piso-atr]] | mean_reversion v8, v1 | 82 / 375 (21,9 %); 103 / 461 (22,3 %) |
| [[EXP-0020-regime-gate]] | mean_reversion v11 | 13 / 23 (56,5 %) |
| [[EXP-0021-timeframe]] | mean_reversion v10; momentum v10; mean_reversion_h1 v1 | 64 / 377 (17,0 %); 121 / 215 (56,3 %); 21 / 118 (17,8 %) |
| [[EXP-0016-trendline-breakout]] | trendline_breakout v1 | 78 / 148 (52,7 %) |
| [[EXP-0010-session-orb-faixa-de-abertura]] | session_orb v1 | 29 / 67 (43,3 %) |
| linha paper `mean_reversion v14` | — | 33 / 235 (14,0 %) |

[[EXP-0007-momentum-invalidacao-bracos-INV]] herda os números de momentum/volume v1–v2. Páginas cujo veredito
nasceu só da coorte `replay` (por exemplo [[EXP-0025-mean-reversion-90-dias]], [[EXP-0026-regime-como-estrategia]],
[[EXP-0027-amplitude]], [[EXP-0028-mean-reversion-5-min]]) **não têm este denominador afetado**, exceto onde
usam a coorte prospectiva do pai como comparação. **Não reli o veredito de cada página para saber qual coorte
sustenta cada frase** — isso fica como tarefa de quem for reavaliar. O efeito mais sensível é nas pistas
dependentes de regime/amplitude: a recusa é maior justamente nas barras de maior rajada, ou seja, nos
momentos de movimento amplo do universo.

## 6. Correção proposta (não implementada)

Conclusão de engenharia: **não há defeito do mecanismo `late:delay` a corrigir** — o limiar faz o que o
contrato diz. O que falta é medir o que o mecanismo não vê.

1. **`hunter_shadow_bar_lag_seconds`** — histograma do atraso de **toda barra admitida no handler**
   (filtros de shard/universo já aplicados, `pre_dispatch.py:62`), observado depois de validar a vela final e
   **antes** da válvula, com ou sem sinal. Arquivo: `hunter_strategy_worker/consumer.py` (+ `metrics.py`).
   Teste que falha primeiro: `services/strategy-worker/tests/test_late_delay_backlog.py`, caso novo — uma vela
   final com `clock = bar_close + 7 s` e sem versão devida **observa** 7 s no histograma
   (`registry.get_sample_value("hunter_shadow_bar_lag_seconds_count")` = 1), e a mesma vela com
   `clock = bar_close + 500 s` (barra recusada pela válvula) também observa; hoje `handle_candle` só conta
   `shadow_bars_skipped_total` e o histograma não existe → falha por `None`.
2. **Registro durável das barras que nunca viraram linha** — Postgres (decisão da Astra: Redis não é
   durável sem política de persistência verificada), com granularidade distinta: recusa **por barra**
   (válvula) e indisponibilidade **por barra × versão com o motivo** (`eligibility_unprovable:lag|universe_changed`,
   hoje contada só por estratégia/estado em `metrics.py:50`). Precisa definir idempotência na reentrega
   (incremento + falha antes do ACK conta duas vezes) → **exige `database-architect` e migração**: é
   arquitetural, não entra sem desenho em `docs/`. Teste que falha primeiro: o mesmo arquivo — a válvula
   disparando deixa 1 linha (e reentregar a mesma `message_id` não deixa 2).
3. **Medir antes de mexer no líder do `outcome_sweep`:** métrica de duração da passagem, trackings visitados
   e atraso do event loop no shard 0, correlacionada no tempo com o lag. A cadência é *duração da passagem +
   10 s*, não "a cada 10 s". Só depois decidir entre mover o sweep para processo próprio ou outro shard.
4. **Higiene operacional (orquestrador/Everton, não agente):** o grupo órfão `strategy-worker.shadow` (lag
   50.004, `pending 0`) e os consumidores acumulados (74 por grupo de shard; 110 no do scanner) merecem
   `XGROUP DESTROY`/`DELCONSUMER` conscientes; o `replay-worker` já ignora o órfão (T3.87).

## Achado lateral, fora do escopo

O grupo do **`scanner-worker`** em `market.candles.closed` está **~2 h atrás**: às 03:19Z `lag 32.149`,
`pending 17.541`, `last-delivered` 01:08Z; cinco minutos depois `lag 32.557`, `last-delivered` 01:19Z — avança
cerca de 11 min de stream a cada 5 min de relógio, mas o lag em entradas **não encolhe** (o stream recebe ~465
entradas/min e ele lê ~476/min). O processo está a ~99 % de um núcleo. O stream retém ~3,3 h (50.004
entradas), então a margem até o `MAXLEN` é de ~1 h. Não afeta o Lab (o `strategy-worker` tem grupo próprio e
está em `lag 0`), mas afeta o Radar/oportunidades — **não diagnosticado aqui**; vale tarefa própria.

## Relacionadas

[[Performance Overview]] · [[Strategy Performance]] · [[07-BUGS/Open Bugs|Open Bugs]] ·
[[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] · [[KB-0089-o-teto-de-cpu-de-um-processo-so]] ·
[[KB-0083-uma-hora-de-34-r-deriva-e-impulso]] · [[2026-10-01-late-delay-do-lab]] ·
`docs/PIPELINE.md` §6b · `docs/DEPLOYMENT.md` §3.1b

## Fontes

`.claude/state/astra-review-astra-auditoria-lab.md` §2 · `.claude/state/astra-review-lab-late-delay.md` ·
`infra/scripts/sql/research/2026-09-10-t373-q03-late-delay.sql` (a consulta original de T3.73) · logs
`strategy-worker` de 30/09 14:48Z a 01/10 03:20Z · `/metrics` e `hb:strategy:shadow:*` dos 4 shards ·
`docker stats` de 01/10 ~03:20–03:30Z
