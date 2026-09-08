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

---

# T3.43c — a hora histórica passa a sarar; custo da escrita medido

**Data:** 2026-09-08. **Base:** `main` @ `259d6f6` (T3.43 = `f7aed39`, **não deployada**).
**Não commitado.** Fecha os cinco achados da revisão da T3.43.

## 1. HIGH-1 — a série tinha um buraco permanente, e a documentação dizia o contrário

O `hours_due` da T3.43 produzia **só** o corte atual e as horas **sem linha**. Uma hora
escrita `unknown` porque faltava uma vela **tem** linha: depois que o backfill de velas
enchia o buraco, aquela hora nunca mais era olhada. O docstring, o §7 do PIPELINE e o item
6 destas notas afirmavam o oposto ("conserta exatamente as horas cujo digest mudou") — a
frase descrevia o que o digest faz *quando a hora é recalculada*, e nada recalculava.

**Correção.** Duas regras, unidas e depois recortadas pela janela de backfill
(`regime_window.py`, módulo novo):

| regra | pergunta que responde | alcance |
|---|---|---|
| backfill | "este produtor já rodou para essa hora?" | toda hora da janela sem linha |
| reparo | "as velas daquela hora ainda são as velas do disco?" | últimas **72 h**, com linha ou sem |

`--repair-days N` é o reparo profundo à mão, depois de um backfill grande de velas; ele
sobe `--backfill-days` para pelo menos `N` (pedir reparo de hora fora da janela seria pedir
linha que ninguém produziria).

**Por que 72 h e não "sempre tudo":** recalcular é barato (0,52 s por passada), reescrever é
que custa, e o digest continua sendo quem decide. Um mês inteiro por passada horária pagaria
a dobra do universo de 31 dias a cada hora para, em 99 % das passadas, não escrever nada.

## 2. Provas novas (nenhuma delas passava antes)

- `test_regime_window.py` (8 testes puros): a hora com linha dentro da janela **é** devida;
  com `repair_hours=0` — o comportamento anterior — só o corte volta; o reparo é recortado
  pela janela de backfill.
- `test_a_historical_hour_written_unknown_is_repaired_after_the_candle_arrives`: um minuto
  de `CUT-5h` chega não-final, cinco linhas saem `UNKNOWN`; o minuto vira final; **a regra
  antiga (`repair_hours=0`) conserta só o corte e deixa quatro horas `UNKNOWN` para
  sempre** (asserção explícita, é o teste de regressão); a passada normal devolve
  `{"updated": 4, "unchanged": 21}`, os ids sobrevivem e as 21 horas intocadas mantêm o
  mesmo `xmin`.
- `test_a_rerun_recomputes_the_repair_window_and_writes_nothing`: 25 horas recalculadas,
  **zero** linhas escritas — provado por `xmin` (a transação que escreveu a linha), não por
  igualdade de valores.
- `test_two_producers_of_the_same_cut_write_one_row_per_hour` (LOW-3): dois produtores em
  `asyncio.gather` com a trava real no Redis → um vencedor, 25 linhas, uma por hora. O
  docstring registra o que a revisão pediu que ficasse escrito: **a guarda de verdade é o
  índice único** que o brief de esquema pede; a trava é o que existe hoje.
- `test_a_batch_that_fails_is_retried_hour_by_hour`: com o escritor envenenado duas vezes
  (toda leva falha, e dentro da repetição uma hora específica também), 24 horas são escritas
  e só a hora impossível fica de fora — `{"inserted": 24, "failed": 1}` — e a passada
  seguinte a produz pela regra do backfill, sem operador.
- `test_every_status_detail_the_scanner_registers_is_removed_when_it_stops` (MEDIUM-2): lê
  o fonte do `main.py` com `ast` e compara o conjunto registrado com o conjunto removido no
  `finally` — simetria, não lista, então o quarto detalhe de status que alguém adicionar
  amanhã também falha aqui. Mais `RegimeHealth` como frase, nunca check vermelho.

## 3. LOW-4 — o custo da escrita, medido, e o que ele obrigou a mudar

Uma transação por hora, 745 horas, testcontainer: **186,5 s** (250 ms/hora) — quatro vezes
o teto de 60 s que a revisão fixou. O custo era **ida-e-volta**, não linha: por hora eram
`SET LOCAL` do papel + `SELECT` + `INSERT` + `COMMIT`.

`write_snapshots` passou a escrever **uma leva por dia** (`WRITE_BATCH_HOURS = 24`): um
`SELECT` cobrindo a leva, um `INSERT` multivalor para as horas novas, um `UPDATE` no lugar
para cada hora que mexeu. Uma leva que levanta exceção é repetida **hora a hora**, então a
propriedade que a transação por hora comprava (uma hora impossível custa só a própria hora)
continua de pé.

| medida (testcontainer, 745 horas, 1 mercado) | antes | depois |
|---|---|---|
| backfill de 31 dias, fim a fim | 186,5 s | **11,2 s / 12,2 s** (duas execuções) |
| por hora | 250 ms | **15,0 / 16,4 ms** |
| passada em regime permanente (73 horas recalculadas, 0 escritas) | — | **0,52 s** |
| semeadura das 45 600 velas do teste | — | 8,0 s / 10,2 s |

## 4. Outras mudanças

- `main.py`: `runtime.status_details.pop("regime_hourly", None)` no `finally`, simétrico com
  `baselines`/`beta` (MEDIUM-2).
- `_claim` → `claim_cut` (público): a trava é a invariante e uma invariante que ninguém pode
  chamar é uma invariante que ninguém testa.
- `funding_average` + `FUNDING_WINDOW` migraram de `regime_job.py` para `regime_repo.py`
  (mesmo código, nenhuma mudança de valor) para o `regime_job.py` caber no teto de 350
  linhas; `regime_job` reexporta os dois.
- `run.last_ts` virou o **máximo** das horas tocadas, não a última processada: as horas
  `unchanged` são registradas antes das levas, e "a última processada" nomearia a hora
  errada no dia em que uma hora antiga é reparada e o corte não muda.
- Descrições corrigidas em três lugares: docstring do `regime_job`, `docs/PIPELINE.md` §4b
  (itens 6, 7, 8 e 9) e estas notas.

## 5. O que continua em aberto

- **O índice único de `(scope, start_time, exchange)`** (brief
  `T3.43-db-market-regimes-hourly`) — sem ele, dois produtores simultâneos ainda dependem só
  da trava do Redis. Nada aqui podia criar migração.
- **O risco do §6 da T3.43** (duas linhas em `GET /api/v1/regime`, selo `stale` no tile)
  segue como estava; `apps/**` continua fora de escopo.
- **`regime_job.py` está com 346 linhas** para um teto de 350: a próxima mudança nesse
  arquivo provavelmente terá de tirar algo antes de pôr.
- **Artefato de ambiente, não de código:** rodar `pytest -s` no console do Windows quebra em
  `UnicodeEncodeError` quando o `logger.exception` do teste de falha desenha o traceback do
  structlog (cp1252 não tem os caracteres de moldura). Com captura normal, ou com
  `PYTHONIOENCODING=utf-8`, passa. Nada a corrigir no worker.
