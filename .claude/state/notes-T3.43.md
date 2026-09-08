# notes T3.43 — produtor horário de regime (`regime_hourly_v1`)

**Data:** 2026-09-08. **Base:** `main` @ `7b0edeb`. **Não commitado.**

## 1. O problema, no número

`market_regimes` tinha **uma linha** no stack local (`global`, `UNKNOWN`, aberta desde
2026-09-06 15:36, `regime_v0`). O classificador do §4 grava **por transição**, e um
classificador que está em aquecimento desde que subiu nunca transicionou. Consequência
medida com a própria consulta de pesquisa desta tarefa: **705 de 705** desfechos terminais
do banco local caem em `sem_regime` — nenhuma coorte pode ser cortada por contexto.

## 2. O que foi entregue

**Indicador puro** (`packages/indicators/hunter_indicators/regime/`, quatro módulos novos,
nenhuma linha do `regime_v0` tocada):

- `hourly_model.py` — vocabulário (`HourlyTrend`, `VolRegime`), limiares versionados
  (`HourlyThresholds.identity` → `regime_hourly_v1` ou `regime_hourly_v1+<digest>`),
  projeção sobre `market_regime` **reusando** `REGIME_PROJECTION` do v0;
- `hourly_snapshot.py` — `RegimeSnapshot`, `ScoreComponent`, `SnapshotInputs`,
  `BreadthCount`, `FundingAverage`;
- `hourly.py` — as estatísticas (SMA, retornos absolutos, vol realizada, leituras
  rolantes, percentil mid-rank, tendência, drawdown);
- `hourly_score.py` — as cinco componentes com `raw`/`normalized`/`weight`/`contribution`,
  a redistribuição de peso, `confidence`, `count_breadth` e `build_snapshot`.

**Job do scanner** (`services/scanner-worker/hunter_scanner_worker/`):
`regime_repo.py` (dobra horária em SQL, `is_final` + 60 minutos + último em `bucket+59min`),
`regime_writer.py` (upsert por `(exchange, ts)` com digest, `UPDATE` no lugar),
`regime_job.py` (a passada, backfill por ausência), `regime_hourly.py` (laço horário +
`--once`). Métricas `hunter_regime_rows_total{outcome}` e
`hunter_regime_last_hour_timestamp_seconds`; `regime_last_ts` no heartbeat;
`status_details["regime_hourly"]`.

**Pesquisa:** `infra/scripts/sql/research/2026-09-09-regime-split.sql` (somente leitura).
**Doc:** `docs/PIPELINE.md` §4b, com ponteiro no fim do §2.
**Esquema:** `.claude/state/brief-T3.43-db-market-regimes-hourly.md` (nenhuma migração aqui).

## 3. Decisões que valem registro

1. **`ts` é o corte.** A linha da hora `ts` sai de dados fechados **antes** de `ts` e vale
   em `[ts, ts+1h)`. Um sinal das 12:34 casa com a linha das 12:00. Rotular a hora
   *seguinte* ao dado é o que faz a junção não antecipar nada.
2. **`scope = btc`, não `global`.** O `regime_v0` é dono de `global` com intervalos
   abertos; duas séries no mesmo escopo dariam intervalos sobrepostos e
   `hunter_strategy_worker.repo.regime_at` (ordena por `start_time`) escolheria a que mexeu
   por último. `btc` estava livre e é o que a série mede.
3. **Linha sempre fechada.** `end_time = ts + 1h`. O índice parcial
   `uq_market_regimes_open_per_scope` continua sendo do v0; a série horária é lida por
   contenção de intervalo, não por "a aberta".
4. **`UPDATE`, nunca `DELETE`+`INSERT`.** `agent_signals.regime_id`,
   `trade_proposals.regime_id` e `paper_trades.regime_id` apontam para esses ids com
   `ON DELETE SET NULL`: apagar para reescrever apagaria o regime de toda decisão que
   referenciou a hora.
5. **Idempotência por digest.** SHA-256 do snapshot + exchange + limiares, gravado dentro
   de `supporting_features`. `computed_at` **não** entra no digest (senão toda passada
   reescreveria 31 dias). Rerodar o mesmo corte com as mesmas velas = `unchanged`.
6. **Backfill é "toda hora sem linha".** Primeira passada: 744 horas. Passadas seguintes:
   uma. Depois de um backfill de velas: exatamente as horas cujo digest mudou.
7. **`unknown` é classificação.** Sem 224 horas fechadas (tendência) ou 193 (percentil de
   vol), a resposta é `unknown` com motivo, e o rótulo projetado é `UNKNOWN`.
8. **Peso redistribuído, nunca zero.** Componente sem leitura sai `None`, o peso vai para
   quem respondeu e `confidence` publica quanto respondeu; abaixo de metade não há score.
9. **Percentil mid-rank.** Empates contam meio, então uma fita de volatilidade constante
   ranqueia em 50 (`normal`) em vez de 100 (`high`) — o erro que a versão ingênua comete.

## 4. Números medidos (stack local, 2026-09-08, 217 mercados monitorados)

| medida | valor |
|---|---|
| dobra horária do BTC, 62 dias, em SQL | **0,48 s** (761 horas completas) |
| dobra do universo, 32 dias, lote de 25 mercados | **2,34 s** (~21 s para 217, uma vez) |
| dobra do universo, 25 horas, lote de 25 mercados | **0,12 s** (~1,1 s por passada horária) |
| classificar 745 horas (CPU pura, limiares de produção) | **1,66 s** |
| cobertura de breadth (mercados com as 25 horas completas) | **199 / 217** (91,7 %) |
| histórico de velas disponível | 2026-08-08 04:00Z → 2026-09-08 20:00Z |

**Ensaio a seco sobre as velas reais do BTC** (somente leitura, nada gravado; breadth e
funding vazios de propósito, porque só o BTC foi exportado):

```
horas produzidas: 745  (2026-08-08T21:00Z .. 2026-09-08T21:00Z)
regime: UNKNOWN 207 · SIDEWAYS 151 · HIGH_VOLATILITY 148 · BTC_BULL 150 · LOW_VOLATILITY 35 · BTC_BEAR 54
trend : unknown 207 · flat 229 · up 255 · down 54
vol   : unknown 176 · low 81 · normal 340 · high 148
score : n=538  min=23.56  max=95.78  médio=61.79
```

As 207 horas de `UNKNOWN` são o aquecimento da tendência (224 horas fechadas) sobre um
histórico que começa em 2026-08-08 — não é defeito de cálculo, é a regra funcionando.
Com 60 dias de velas, o backfill inteiro sai classificado.

## 5. O que **não** foi feito, e por quê

- **`replay.stress` com braço de regime:** o cenário `SUBSET` por `trend × vol_regime`
  precisaria do driver em `services/strategy-worker/hunter_strategy_worker/replay/stress.py`,
  que o brief proíbe tocar. O corte por regime está entregue em SQL; o braço de estresse
  fica como pendência com o desenho já decidido (um `StressScenario` `SUBSET` cuja seleção
  é a junção por contenção de intervalo da consulta §2 do arquivo de pesquisa).
- **Migração de `market_regimes`:** fora de escopo; brief entregue.
- **Passada real contra o stack local:** o Postgres do compose **não publica porta** no
  host, e copiar código para dentro do contêiner em execução é invasivo demais para o que
  provaria. A prova de banco é a de testcontainers (6 testes) e a de dado real é o ensaio a
  seco acima.

## 6. Risco declarado

Depois do deploy, `GET /api/v1/regime` passa a devolver **duas** linhas (uma por escopo) e
o tile "Regime atual" do dashboard ganha uma linha `BTC · <rótulo>` **sempre com selo
`stale`**, porque `is_stale` é `end_time is not None or not scanner_alive` e toda linha
horária é fechada. É honesto (a hora passada não é o regime vivo) e pode ser lido como
defeito. As três saídas estão no brief de esquema; nenhuma delas cabia nesta tarefa
(`apps/**` e `infra/migrations/**` proibidos).
