# T3.33e — `breakout v1` e `mean_reversion v1` entram no Lab: ativação auditada + replay de 31 dias (dia um)

**Data:** 2026-09-08 (UTC; horário de Brasília = UTC−3).
**Executor:** quant-engineer. **Base:** `main` em `b5d4f9b`; VPS rodando `hunter-api:b5d4f9b` para
api/web/strategy-worker/scanner/execution. **Nada commitado.** **Nenhum container parado ou recriado.**
**Nenhuma escrita fora do `activate_strategy_version.py` e dos quatro replays.** Nenhum `.env*` tocado.

## STATUS

`DONE_WITH_CONCERNS`.

| Passo do brief | Resultado |
|---|---|
| 1. `seed.py --dry-run` | **NÃO EXECUTADO** — a flag `--dry-run` **não existe** em `infra/scripts/seed.py` (o script não tem `argparse`; o `Usage` do docstring é `uv run python infra/scripts/seed.py`, sem flags). Fiz no lugar a **diferença somente-leitura** que o dry-run responderia (abaixo). O seed continua **pendente do operador**; nada nele é pré-requisito da ativação nem do replay |
| 2. dry-run + ativação `breakout v1` | **OK** — o dry-run imprimiu exatamente `…breakout_v1@sha256:4c920b0c…64ff1`. Ativado às **16:23:39,79 UTC (13:23:39 BRT)** |
| 3. 10 min de vigia (`hb:strategy`, `shadow_evaluations_total`) | **OK** — sem erro, sem `unrunnable`, `momentum v3` (paper) continua sendo avaliado **primeiro** em cada mercado |
| 3b. dry-run + ativação `mean_reversion v1` | **OK** — digest `…mean_reversion_v1@sha256:a970c9d9…395f`. Ativado às **16:32:33,95 UTC (13:32:33 BRT)** |
| 4. quatro replays (2 fatias × 2 versões, mesma coorte por versão) | **OK** — 23 808 barras avaliadas ao todo, 0 erros |
| 5. avaliação do dia um contra K1–K5 congelados | **OK** — `breakout v1` **descartar** (K1 + o critério específico da versão); `mean_reversion v1` **inconclusivo**, nenhum critério de morte disparado |
| 6. seções datadas nos rascunhos EXP-0008/EXP-0009 | **OK** — em `.claude/state/exp-drafts/`; `obsidian/**` **não** foi tocado |

## COMANDOS (saída real, verbatim)

### 0. Estado da VPS antes de qualquer coisa

```
$ ssh hunter-vps 'hostname; date -u; cd /opt/project-hunter && git log --oneline -1; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
vmi3483069
Tue Sep  8 16:17:35 UTC 2026
b5d4f9b T3.29b: corrida de relógios do avgPrice fechada ...
hunter-web-1	hunter-web:b5d4f9b	Up 2 minutes (healthy)
hunter-api-1	hunter-api:b5d4f9b	Up 2 minutes (healthy)
hunter-execution-worker-1	hunter-api:b5d4f9b	Up 2 minutes (healthy)
hunter-strategy-worker-1	hunter-api:b5d4f9b	Up 2 minutes (healthy)
hunter-scanner-worker-1	hunter-api:b5d4f9b	Up 2 minutes (healthy)
hunter-market-worker-spot-1	hunter-api:1ca7cf5	Up 41 minutes (healthy)
... (mais quatro market-worker em 1ca7cf5) ...
hunter-caddy-1	caddy:2-alpine	Up 34 hours
hunter-postgres-1	postgres:16-alpine	Up 35 hours (healthy)
hunter-redis-1	redis:7-alpine	Up 35 hours (healthy)
```

**Os quatro digests da imagem, antes de ativar nada** (somente leitura, dentro do worker):

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -c "
from hunter_strategy_worker.code_ref import version_code_ref
for m in (\"breakout_v1\",\"mean_reversion_v1\",\"momentum_v1\",\"volume_anomaly_v1\"): print(version_code_ref(m))"'
hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

Os dois digests das versões vivas (`momentum_v1 ab2e0398…`, `volume_anomaly_v1 9b8c14ab…`) são
**idênticos** aos congelados na T3.33a/b: a imagem é este código e nada se moveu por baixo delas.

### 1. O seed — o que o dry-run responderia, sem escrever

`infra/scripts/seed.py` não aceita flags. Em vez de rodar um script que escreve em oito tabelas de
referência sem o portão que o brief pediu, li o estado (transação `REPEATABLE READ READ ONLY`):

```
-- key | name | category | description
breakout | Breakout | trend | Range break confirmed by volume and order flow.
mean_reversion | Mean Reversion | reversion | Fade of stretched moves in low volatility.
momentum | Momentum | trend | Continuation with relative volume and breakout strength.
volume_anomaly | Volume Anomaly | anomaly | Entry after a VOLUME_SPIKE with pressure.
```

contra o que a build embarca (`infra/scripts/seed_reference.py::STRATEGIES`):

| key | descrição no banco (hoje) | descrição da build (b5d4f9b) | diverge? |
|---|---|---|---|
| `breakout` | Range break confirmed by volume and order flow. | Breakout of the previous highs after a contraction of true range, confirmed by volume. | **sim** |
| `mean_reversion` | Fade of stretched moves in low volatility. | Pullback bought inside a higher-timeframe uptrend, on a close stretched below its mean. | **sim** |

Ou seja: **a condição do brief ("only if it reports the rows need the new description") está
satisfeita** — as duas descrições estão velhas. **Não rodei o seed assim mesmo**, e a razão está no
CONCERN 1. A descrição é do catálogo (`strategies.description`), não da versão: ela não entra em
`code_ref`, `parameters_schema`, `default_parameters` nem em envelope nenhum, e por isso não muda uma
linha do que foi ativado ou replayado hoje. Comando exato que fica para o operador:
`docker exec hunter-api-1 python infra/scripts/seed.py`.

Estado do catálogo antes da ativação (mesma transação somente-leitura):

```
breakout       | v1 | draft  | research_only | hunter_indicators.strategies.breakout_v1       | (activated_at nulo) | {}
mean_reversion | v1 | draft  | research_only | hunter_indicators.strategies.mean_reversion_v1 | (activated_at nulo) | {}
momentum       | v2 | active | research_only | …momentum_v1@sha256:ab2e0398…       | 2026-09-08 04:33:56
momentum       | v3 | active | paper         | …momentum_v1@sha256:ab2e0398…       | 2026-09-08 05:57:30
momentum       | v4 | active | research_only | …momentum_v1@sha256:ab2e0398…       | 2026-09-08 13:05:13
volume_anomaly | v2 | active | research_only | …volume_anomaly_v1@sha256:9b8c14ab… | 2026-09-08 04:32:42
```

### 2. Ativação de `breakout v1` — dry-run e execução

```
$ ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py breakout v1 --changelog "T3.33e: EXP-0008 entra no Lab como pesquisa" --dry-run'
would activate breakout v1 (purpose research_only) with code_ref hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1 (20 parameters)
```

Digest **igual** ao exigido pelo brief e 20 parâmetros — a contagem congelada no `brief-T3.33a` §6.
Só então:

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py breakout v1 --changelog "T3.33e: EXP-0008 entra no Lab como pesquisa"'
Tue Sep  8 16:23:38 UTC 2026
activated breakout v1 (purpose research_only) at 2026-09-08T16:23:39.791800+00:00 with code_ref hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
```

### 3. Dez minutos de vigia antes de ativar a segunda

Linha de base (16:23:08 UTC, **antes** da ativação): `hunter_shadow_versions_active 4`,
`evaluations_by_state={"not_triggered":963,"triggered":37,"unavailable":108}`, `evaluated_bars=1108`,
`errors=0`, `outbox_lag_s=0.0`, `open_trackings=95`.

```
Tue Sep  8 16:24:08 UTC 2026
… evaluations_by_state={"not_triggered":963,"triggered":37,"unavailable":108} evaluated_bars=1108 errors=0 outbox_pending=0
hunter_shadow_versions_active 5.0 hunter_shadow_versions_runnable 5.0

Tue Sep  8 16:25:48 UTC 2026
… evaluations_by_state={"not_triggered":1165,"triggered":51,"unavailable":108,"ineligible":1} evaluated_bars=1325 errors=0
hunter_shadow_versions_active 5.0 hunter_shadow_versions_runnable 5.0

Tue Sep  8 16:31:38 UTC 2026
… evaluations_by_state={"not_triggered":2003,"triggered":98,"unavailable":108,"ineligible":6} evaluated_bars=2215 errors=0 outbox_lag_s=0.0
hunter_shadow_evaluations_total{state="not_triggered",strategy="momentum"} 1099.0
hunter_shadow_evaluations_total{state="triggered",strategy="momentum"} 62.0
hunter_shadow_evaluations_total{state="not_triggered",strategy="volume_anomaly"} 782.0
hunter_shadow_evaluations_total{state="triggered",strategy="volume_anomaly"} 36.0
hunter_shadow_evaluations_total{state="not_triggered",strategy="breakout"} 191.0
hunter_shadow_evaluations_total{state="ineligible",strategy="breakout"} 1.0
hunter_shadow_versions_active 5.0 hunter_shadow_versions_runnable 5.0
hunter_shadow_versions_unrunnable{…} 0.0   (as cinco razões, todas zero)
```

Leitura: a versão nova entrou no roster em segundos (`active` 4 → 5) e **avaliou de fato** no primeiro
fechamento alinhado de 15 min (16:30): 191 `not_triggered` + 1 `ineligible` = 192 mercados. O
`momentum` continuou avaliando no mesmo corte (566 → 1099 `not_triggered`, 22 → 62 `triggered`), o
que responde à concern 6 da T3.33: acrescentar uma versão **não** deslocou a faixa viva.

**Ordem T3.26c — a linha `paper` primeiro, provada por linha do banco.** Os `signal_id` que o log
emitiu no ciclo das 16:30, resolvidos para versão e `purpose`:

| `emitted_at` | versão | purpose | mercado |
|---|---|---|---|
| 16:30:35,717959 | `momentum v3` | **paper** | DOGSUSDT |
| 16:30:35,828161 | `momentum v2` | research_only | DOGSUSDT |
| 16:30:35,932469 | `momentum v4` | research_only | DOGSUSDT |
| 16:30:49,955385 | `momentum v3` | **paper** | ARXUSDT |
| 16:30:50,067822 | `momentum v2` | research_only | ARXUSDT |
| 16:30:50,191945 | `momentum v4` | research_only | ARXUSDT |
| 16:30:50,323771 | `volume_anomaly v2` | research_only | ARXUSDT |

Em cada mercado a linha `paper` decide antes de qualquer versão de pesquisa (`roster.roster_order`).

### 3b. Ativação de `mean_reversion v1`

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py mean_reversion v1 --changelog "T3.33e: EXP-0009 entra no Lab como pesquisa" --dry-run'
Tue Sep  8 16:32:22 UTC 2026
would activate mean_reversion v1 (purpose research_only) with code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f (18 parameters)

$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py mean_reversion v1 --changelog "T3.33e: EXP-0009 entra no Lab como pesquisa"'
Tue Sep  8 16:32:32 UTC 2026
activated mean_reversion v1 (purpose research_only) at 2026-09-08T16:32:33.947955+00:00 with code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
```

Digest **igual** ao exigido pelo brief e 18 parâmetros — a contagem congelada no `brief-T3.33b` §6.

Vigia com as **seis** versões (ciclo das 16:45; amostras 16:48 / 16:50 / 16:52 UTC):

```
hunter_shadow_versions_active 6.0 hunter_shadow_versions_runnable 6.0
hunter_shadow_versions_unrunnable{reason="code_ref_mismatch"} 0.0   (e as outras quatro razões, zero)
hunter_shadow_evaluations_total{state="not_triggered",strategy="mean_reversion"} 216.0
hunter_shadow_evaluations_total{state="not_triggered",strategy="breakout"} 432.0
… errors=0 outbox_pending=0 outbox_lag_s=0.0 open_trackings=88..100
```

`evaluated_bars` foi de 2843 (16:41) para 4139 (16:48) — exatamente 1296 = 216 mercados × 6 versões,
a passada inteira. O primeiro sinal do ciclo das 16:45 saiu às 16:45:04,58 (4,6 s depois do corte) e a
passada terminou antes do heartbeat das 16:48:04 — folga confortável dentro dos 15 min do timeframe.

### 4. Replays — duas fatias contíguas por versão, mesma coorte

Coortes (uma por versão, `uuid4` gerada uma vez):
`replay:2059ea0c-12d5-46ec-ae4a-1d8944da678e` (breakout) e
`replay:d0f77894-1e04-454e-a49f-d9a98d894968` (mean_reversion).

Dry-run de plano (escreve nada): `{'cohort': 'replay:2059ea0c-…', 'version': 'breakout v1',
'markets': 4, 'bars_planned': 5760, 'workers': 3}`.

```
$ docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
    --version breakout:v1 --from 2026-08-08 --to 2026-08-23 \
    --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
    --cohort replay:2059ea0c-12d5-46ec-ae4a-1d8944da678e --ledger /tmp/replay-breakout-v1-a.jsonl
{'run_id': '2059ea0c-…', 'version_label': 'breakout v1', 'window_from': '2026-08-08T00:00:00+00:00',
 'window_to': '2026-08-23T00:00:00+00:00', 'market_count': 4, 'bars_evaluated': 5760, 'signals': 0,
 'outcomes_resolved': 0, 'outcomes_open': 0, 'seconds': 90.742, 'bars_per_second': 63.48,
 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5310, 'rejected': 2}, 'errors': 0}

$ … --from 2026-08-23 --to 2026-09-08 … --ledger /tmp/replay-breakout-v1-b.jsonl
{'bars_evaluated': 6144, 'signals': 0, 'outcomes_resolved': 0, 'seconds': 98.808,
 'bars_per_second': 62.18, 'evaluations_by_state': {'not_triggered': 6132, 'rejected': 12}, 'errors': 0}

$ … --version mean_reversion:v1 --from 2026-08-08 --to 2026-08-23 … --cohort replay:d0f77894-… \
    --ledger /tmp/replay-mean_reversion-v1-a.jsonl
{'bars_evaluated': 5760, 'signals': 17, 'outcomes_resolved': 17, 'outcomes_open': 0,
 'seconds': 93.11, 'bars_per_second': 61.86,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5284, 'triggered': 28}, 'errors': 0}

$ … --from 2026-08-23 --to 2026-09-08 … --ledger /tmp/replay-mean_reversion-v1-b.jsonl
{'bars_evaluated': 6144, 'signals': 37, 'outcomes_resolved': 37, 'outcomes_open': 0,
 'seconds': 104.545, 'bars_per_second': 58.77,
 'evaluations_by_state': {'not_triggered': 6108, 'triggered': 36}, 'errors': 0}
```

**Atenção ao denominador:** `signals`/`outcomes_resolved` do recibo são contados **da coorte inteira**
(`simulate._population` lê as linhas, não a fatia), então `17` na fatia A e `37` na fatia B **não
somam**: a população final da coorte `mean_reversion` é **37 decisões**, confirmada por
`select count(*) from agent_signals where strategy_version_id='01a074c5-8f3b-7346-a483-15c2d2b93764'`
→ **37**, uma única coorte, primeira em `2026-08-20 03:45:02+00`, última em `2026-09-06 15:15:02+00`.
Para `breakout v1` o mesmo `count(*)` é **0**.

## RECIBOS

### `replay_runs` (quatro linhas, lidas do banco)

| coorte | versão | de | até | mercados | barras | sinais* | desfechos* | seg | barras/s | workers | lag_s | estados | erros |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `replay:2059ea0c…` | breakout v1 | 2026-08-08 | 2026-08-23 | 4 | 5 760 | 0 | 0 | 90,7 | 63,48 | 3 | 2 | `{"rejected":2,"unavailable":448,"not_triggered":5310}` | 0 |
| `replay:2059ea0c…` | breakout v1 | 2026-08-23 | 2026-09-08 | 4 | 6 144 | 0 | 0 | 98,8 | 62,18 | 3 | 2 | `{"rejected":12,"not_triggered":6132}` | 0 |
| `replay:d0f77894…` | mean_reversion v1 | 2026-08-08 | 2026-08-23 | 4 | 5 760 | 17 | 17 | 93,1 | 61,86 | 3 | 2 | `{"triggered":28,"unavailable":448,"not_triggered":5284}` | 0 |
| `replay:d0f77894…` | mean_reversion v1 | 2026-08-23 | 2026-09-08 | 4 | 6 144 | 37 | 37 | 104,5 | 58,77 | 3 | 2 | `{"triggered":36,"not_triggered":6108}` | 0 |

\* acumulado da coorte, não da fatia (ver acima). Custo medido: **61,5 barras/s** com 3 workers, contra
os ~65 projetados na T3.33 §5.1 — a projeção de "≈ 3 min por fatia" se confirmou (90,7 s e 98,8 s).
Os quatro JSONL (`/tmp/replay-{breakout,mean_reversion}-v1-{a,b}.jsonl`, dentro de
`hunter-strategy-worker-1`) carregam o mesmo objeto, linha a linha.

### `system_events` (componentes `replay_engine` e `activate_strategy_version`)

```
info | activate_strategy_version | strategy_version_activated | breakout v1 (purpose research_only) activated with code_ref=hunter_core.strategies.breakout_v1@sha256:4c920b0c… params_format=1: T3.33e: EXP-0008 entra no Lab como p… | 2026-09-08 16:23:39.791800+00
info | activate_strategy_version | strategy_version_activated | mean_reversion v1 (purpose research_only) activated with code_ref=hunter_core.strategies.mean_reversion_v1@sha256:a970c9d9… params_format=1: T3.33e: EXP-0009 entra n… | 2026-09-08 16:32:33.947955+00
info | replay_engine | replay_run_finished | replay breakout v1 4 mercados 2026-08-08…2026-08-23: 5760 barras, 0 sinais, 0 desfechos, 90.742 s | 2026-09-08 16:34:50.525324+00
info | replay_engine | replay_run_finished | replay breakout v1 4 mercados 2026-08-23…2026-09-08: 6144 barras, 0 sinais, 0 desfechos, 98.808 s | 2026-09-08 16:36:58.394997+00
info | replay_engine | replay_run_finished | replay mean_reversion v1 4 mercados 2026-08-08…2026-08-23: 5760 barras, 17 sinais, 17 desfechos, 93.11 s | 2026-09-08 16:39:11.317519+00
info | replay_engine | replay_run_finished | replay mean_reversion v1 4 mercados 2026-08-23…2026-09-08: 6144 barras, 37 sinais, 37 desfechos, 104.545 s | 2026-09-08 16:41:07.940421+00
```

### Isolamento (a coorte é a cerca, e ela segurou)

```
-- linhas_outbox_com_replay        (shadow_outbox cujo payload cita qualquer das duas coortes)
0
-- propostas_das_coortes           (trade_proposals ligadas a sinais destas coortes)
0
```

Nenhuma linha de outbox (`persist.is_published_cohort` recusa publicar coorte de replay) e nenhuma
proposta — nada chegou perto de carteira. `open_trackings` da faixa viva oscilou 88–100 durante os
replays e `errors` ficou em 0 o tempo todo.

### Integridade do custo (identidade da T3.32)

`custo_R × (risco/preço)` linha a linha, nos 37 desfechos de `mean_reversion v1`:

```
 n | identidade_custo_med | identidade_min | identidade_max
37 |           0.00200332 |     0.00197308 |     0.00202846
```

A identidade `0,0020` se reproduz com desvio ≤ 2,9×10⁻⁵ — a decomposição de R desta coorte é a mesma
das dez populações da T3.32, e portanto as expectancies abaixo são comparáveis com as de lá.

## TABELAS DE AVALIAÇÃO — **REPLAY, não coleta prospectiva**

Rótulo obrigatório (T3.33 §5.1): tudo abaixo é a **mesma janela que gerou as hipóteses**; não
confirma nada.

### Cobertura por estado (31 dias × 4 mercados = 11 904 barras por versão)

| versão | barras | `unavailable` | `not_triggered` | `triggered` | `rejected` | `ineligible` | decisões persistidas |
|---|---:|---:|---:|---:|---:|---:|---:|
| `breakout v1` | 11 904 | 448 (**3,76 %**) | 11 442 (96,12 %) | **0 (0,00 %)** | **14 (0,118 %)** | 0 | **0** |
| `mean_reversion v1` | 11 904 | 448 (**3,76 %**) | 11 392 (95,70 %) | 64 (0,538 %) | 0 | 0 | **37** |

Duas leituras que só existem porque as duas versões rodaram sobre **as mesmas barras**:

- **`unavailable` é idêntico (448 = 448)**, e as duas versões têm janelas de disponibilidade
  diferentes: a `mean_reversion` exige, além de tudo o que a `breakout` exige, 1 260 minutos
  contíguos para a porta de 1 h. Como o total não subiu **nem uma barra**, a porta de tendência
  **não perdeu nenhuma barra por gap** nesta janela: os 448 são o aquecimento comum do início
  (112 barras por mercado ≈ 28 h; o cache leu desde 2026-08-06T22:00). Isto responde, por diferença,
  à pergunta "`trend_gap` é a maioria dos `unavailable`?" do EXP-0009: **não é; é zero**;
- 64 barras dispararam na `mean_reversion` e **37** viraram decisão: as outras 27 caíram na barreira
  de re-arme / regra "um acompanhamento por (versão, mercado, coorte)" — não são perda de dado.

### `mean_reversion v1` — população e métricas (coorte `replay:d0f77894…`)

| métrica | valor | denominador |
|---|---:|---|
| decisões | **37** | 11 904 barras (0,298 por mercado-dia) |
| desfechos terminais | 37 | 37 decisões |
| avaliáveis (`r_multiple` não nulo) | **37** | cobertura de `R_net` = **100,0 %** |
| dias distintos | **11** | janela de 31 dias |
| mercados distintos | 4 | 4 pedidos |
| expectancy **bruta** (`r_gross`, sem custo) | **+0,3210 R** | 37 |
| expectancy ex-funding (`r_ex_funding`) | +0,0948 R | 37 |
| expectancy **líquida** (`R_net`) | **+0,0938 R** | 37 |
| pedágio médio (`custo_R`) | 0,2263 R | 37 |
| soma de `R_net` | +3,47 R | 37 |
| taxa de acerto (`result='target'`) | **40,5 %** | 37 |
| profit factor líquido | **1,186** | 37 |
| profit factor bruto | 1,800 | 37 |
| risco/preço médio | 1,050 % | 37 |
| funding médio | +0,001002 R | 37 |

**Por motivo de saída:**

| motivo | n | % | `R_net` médio | soma `R_net` | `R_bruto` médio |
|---|---:|---:|---:|---:|---:|
| `stop` | 16 | 43,2 | −1,1682 | −18,69 | −0,9281 |
| `target` | 15 | 40,5 | +1,2732 | +19,10 | +1,5199 |
| `expired` (horizonte 4 h) | 6 | 16,2 | +0,5104 | +3,06 | +0,6548 |

**O resultado inteiro está no balde do horizonte.** Alvo e stop quase se anulam
(+19,10 − 18,69 = **+0,41 R em 31 decisões**, +0,013 R cada); os +3,47 R da coorte são, dentro do
arredondamento, os +3,06 R das seis saídas por tempo. A tabela de geometria congelada no EXP-0009
(equilíbrio 53,35 % em ATR% 0,006) supõe população binária stop/alvo; com 16,2 % saindo por horizonte,
40,5 % de acerto e expectancy positiva **não** se contradizem — mas a margem depende de **seis**
observações.

**Profundidade do z-score (a decomposição que o EXP-0009 exige):**

| faixa de z | n | z mín | z máx | exp. bruta R | exp. líquida R | soma R | acerto |
|---|---:|---:|---:|---:|---:|---:|---:|
| −1,25 < z ≤ −1,00 | 11 | −1,198 | −1,019 | +0,8808 | **+0,6879** | +7,57 | 63,6 % |
| −1,50 < z ≤ −1,25 | 5 | −1,439 | −1,307 | −0,2655 | −0,5027 | −2,51 | 20,0 % |
| −2,00 < z ≤ −1,50 | 11 | −1,926 | −1,576 | +0,3917 | +0,1379 | +1,52 | 45,5 % |
| z ≤ −2,00 | 10 | −3,080 | −2,049 | −0,0792 | −0,3101 | −3,10 | 20,0 % |

**A profundidade não paga — ela parece pagar ao contrário.** O balde mais raso (o que passa raspando
no `zscore_depth_min = 1`) responde por +7,57 R dos +3,47 R totais, e o mais fundo perde. Com n = 10–11
por balde isto é ruído do tamanho do efeito; o que fica registrado é que **não há monotonicidade** que
justifique tratar "mais esticado" como "melhor", e que `zscore_depth_min` continua sendo convenção
declarada, não medida.

**Por faixa de ATR% (piso congelado 0,006):**

| faixa | n | ATR% mín | ATR% máx | exp. bruta R | exp. líquida R | soma R |
|---|---:|---:|---:|---:|---:|---:|
| 0,006 ≤ ATR% < 0,008 | 20 | 0,00603 | 0,00775 | +0,1956 | **−0,0814** | −1,63 |
| 0,008 ≤ ATR% < 0,010 | 6 | 0,00815 | 0,00935 | +0,1201 | **−0,0912** | −0,55 |
| 0,010 ≤ ATR% < 0,015 | 6 | 0,01044 | 0,01462 | +0,7087 | +0,5212 | +3,13 |
| ATR% ≥ 0,015 | 5 | 0,01742 | 0,03565 | +0,5987 | +0,5033 | +2,52 |

**26 das 37 decisões (70,3 %) estão abaixo de ATR% 0,010 e são líquidas negativas**, com a bruta
positiva nos dois baldes: é o pedágio comendo a vantagem, o mecanismo da KB-0008/T3.32
(`custo_R = 0,0020 / (risco/preço)`). Subir o piso é **versão nova**, não ajuste — fica registrado
como candidato a `v2`, não como conserto.

**Por mercado** (mistura de slot declarada: seis versões dividem o mesmo mercado):

| símbolo | n | ATR% médio | exp. bruta R | exp. líquida R | soma R | acerto |
|---|---:|---:|---:|---:|---:|---:|
| DOGEUSDT | 12 | 0,01083 | +0,1313 | −0,0927 | −1,11 | 25,0 % |
| ETHUSDT | 6 | 0,00792 | +0,4986 | +0,2132 | +1,28 | 50,0 % |
| SOLUSDT | 8 | 0,00849 | +0,6080 | +0,3490 | +2,79 | 50,0 % |
| XRPUSDT | 11 | 0,01356 | +0,2224 | +0,0465 | +0,51 | 45,5 % |

**Por dia** (11 dias com decisão em 31): 08-20 (5, +4,98 R) · 08-21 (6, +6,40) · 08-22 (6, +0,55) ·
08-23 (1, +1,22) · 08-24 (3, +0,26) · 08-25 (4, −4,62) · 08-27 (3, +1,02) · 08-28 (2, −2,43) ·
09-03 (3, −3,49) · 09-05 (1, −1,18) · 09-06 (3, +0,78). Dois dias (08-20/08-21) valem +11,4 R
enquanto os outros nove somam −7,9 R.

### `breakout v1` — a população que não existiu

| métrica | valor |
|---|---|
| decisões | **0** em 11 904 barras |
| barras que passaram compressão + rompimento + volume + faixa de ATR% | **14** (todas `REJECTED`) |
| avaliáveis, expectancy, PF, acerto, dias, mercados | **— (não há população)** |
| decomposição por balde de `squeeze_ratio` | **vazia** — ver abaixo |
| faixa `0,0050 ≤ ATR% < 0,0059` (condição do revisor) | **0 decisões**; expectancy indefinida |

**As 14 rejeições são todas `geometry_invalidation`, e isso é demonstrável sem dado novo.** O módulo
congelado tem duas portas de geometria, nesta ordem: `0 < stop < close < target1` e
`stop < base_low < close`. A primeira **não pode** falhar depois da porta de ATR%, que já garante
`ATR% ≤ 0,05`: `stop = C − 1,25·ATR = C(1 − 1,25·ATR%) ≥ 0,9375·C > 0` e `target1 = C + 2,5·ATR > C`.
Logo toda `REJECTED` desta versão é a segunda porta — `base_low ≤ stop`, isto é, **a mínima da base de
8 barras cai mais de 1,25 ATR abaixo do fechamento do rompimento**. O critério específico congelado no
EXP-0008 ("`REJECTED / geometry_invalidation` acima de 20 % das barras que disparariam") sai em
**14/14 = 100 %**.

Em uma frase: **o par `(squeeze_window_bars = 8, stop_atr = 1,25)` está errado** — a "base comprimida"
de 8 barras de 15 min é, na prática, mais larga que um stop de 1,25 ATR de 97 barras, então a
invalidação estrutural que o desenho queria ficaria **abaixo** do stop, e a guarda — funcionando
exatamente como escrita — recusou a decisão. Corrigir é **versão nova**.

## VEREDITO POR VERSÃO

### `breakout v1` (EXP-0008) — `inconclusivo` + recomendação **`descartar`**

| critério congelado | leitura | disparou? |
|---|---|---|
| **K1** — < 20 decisões | **0 decisões** em 31 dias × 4 mercados | **SIM** |
| K2 — > 1 500 decisões | 0 | não |
| K3 — ≥ 100 avaliáveis **e** ≥ 30 dias **e** expectancy bruta < 0 | 0 avaliáveis, 0 dias | não (inaplicável) |
| K4 — `unavailable` > 40 % | 3,76 % | não |
| K5 — cobertura de `R_net` < 70 % | inaplicável (nenhum desfecho) | não |
| **específico da versão** — `geometry_invalidation` > 20 % das barras que disparariam | **100 % (14/14)** | **SIM** |

**Result: `inconclusivo`** pela régua de maturidade (0 avaliáveis < 100, 0 dias < 30 — antes de madura
o resultado é sempre `inconclusivo`). **Next Action: `descartar` `breakout v1`** — K1 é explícito:
"não é 'amostra pequena', é ausência de população, e mais 30 dias não a criam". A causa não é a
hipótese da compressão: é a guarda de geometria, que rejeitou **todas** as barras que passaram pelas
quatro portas de entrada, e a hipótese da compressão **não chegou a ser testada**. Uma `v2` que queira
testá-la precisa mexer no par `(squeeze_window_bars, stop_atr)` ou na invalidação — experimento novo,
portão C1–C8 novo, não conserto deste.

O que **não** foi possível medir, e por quê: o EXP-0008 exige a distribuição de `squeeze_ratio` em
barras que disparam e que não disparam (obrigação C2) e o corte por regime de BTC (obrigação C4).
**Nenhuma das duas é obtível deste replay**: barras `not_triggered`/`rejected` não persistem detalhe
algum (o caminho só conta `evaluations_by_state` por estado, `replay/simulate.py`), e `market_regimes`
tem **uma** linha no banco inteiro, começando em 2026-09-06 18:18 — não há regime gravado para agosto.
As duas obrigações continuam abertas e mudam de instrumento (CONCERNS 3 e 4).

### `mean_reversion v1` (EXP-0009) — `inconclusivo`, nenhum critério de morte disparado

| critério congelado | leitura | disparou? |
|---|---|---|
| K1 — < 20 decisões | **37** | não |
| K2 — > 1 500 decisões (o risco real desta versão) | 37 (0,298/mercado-dia) | não |
| K3 — ≥ 100 avaliáveis **e** ≥ 30 dias **e** expectancy bruta < 0 | 37 avaliáveis (< 100), 11 dias (< 30), bruta **+0,3210 R** | não |
| K4 — `unavailable` > 40 % | 3,76 % | não |
| K5 — cobertura de `R_net` < 70 % | **100 %** | não |
| gap da porta de 1 h ("se `trend_gap` for a maioria dos `unavailable`") | `trend_gap` = **0** (por diferença contra `breakout`, mesmas barras) | não |

**Result: `inconclusivo`** (madura = ≥ 100 avaliáveis **e** ≥ 30 dias distintos; temos 37 e 11).
**Next Action: seguir prospectivo** na coorte `prospective`, universo elegível inteiro, e reavaliar
pela régua de 30 dias. Nada aqui promove nada; `research_only` continua sem carteira.

**A obrigação que não pôde ser cumprida:** "a porta de tendência tem de pagar por si", no formato
pareado da EXP-0006 — expectancy **com e sem** `no_uptrend_1h` sobre a mesma população de recuos.
Recuos rejeitados pela porta saem como `not_triggered` e **não persistem**, então o braço "sem porta"
não existe no banco. Medir isso é derivar uma irmã de parâmetro (`derive_variant.py`) com a porta
desligada e replayar a mesma janela — trabalho novo, declarado aqui e não feito.

## REGISTRO DE TENTATIVAS — datas de início (para a Sexta-feira arquivar; `obsidian/**` não tocado)

| versão | EXP | início (UTC) | início (BRT) | coorte de replay do dia um |
|---|---|---|---|---|
| `breakout v1` | EXP-0008 | **2026-09-08T16:23:39,791800Z** | 2026-09-08 13:23:39 | `replay:2059ea0c-12d5-46ec-ae4a-1d8944da678e` |
| `mean_reversion v1` | EXP-0009 | **2026-09-08T16:32:33,947955Z** | 2026-09-08 13:32:33 | `replay:d0f77894-1e04-454e-a49f-d9a98d894968` |

Multiplicidade a declarar junto (KB-0010): estas são a 3ª e a 4ª versão nova aberta em 2026-09-08
(`momentum v4` às 13:05:13 UTC e a linha `paper momentum v3` às 05:57:30 UTC vieram antes), e os dois
vereditos acima devem ser lidos sabendo disso.

## CONCERNS

1. **`seed.py` não tem `--dry-run`, e eu não rodei o seed.** O brief condicionou a execução ao que o
   dry-run reportasse; a flag não existe. Rodar o script sem portão escreveria em oito tabelas de
   referência — inclusive `risk_profiles.limits` (upsert que **reescreve** os limites dos presets do
   sistema com os valores da build) — e as verificações de `opportunity_weights`/`feature_definitions`
   **abortam a transação inteira** em caso de divergência. Nada disso é pré-requisito do que o brief
   pediu, então parei e reportei em vez de escrever. **Consequência viva:** as descrições de
   `breakout` e `mean_reversion` no catálogo (e portanto na tela do Lab) continuam sendo as antigas,
   que descrevem outra coisa. Comando pendente do operador:
   `docker exec hunter-api-1 python infra/scripts/seed.py`.
2. **Ativação é irreversível, e uma delas nasceu morta.** `breakout v1` está `active`/`research_only`
   com `code_ref` congelado e **produz zero decisão**: no prospectivo ela custa 216 avaliações por
   corte de 15 min, para sempre, sem gerar linha nenhuma. Encerrar isso exige `deprecar` a linha —
   fora do escopo autorizado hoje (o brief autorizou ativar, não desativar). Registro a recomendação
   e **não** a executei.
3. **O replay não persiste o *motivo* de cada barra, só o estado.** `evaluations_by_state` conta
   `unavailable/not_triggered/triggered/rejected/ineligible`; as razões (`atr_gap`, `trend_gap`,
   `not_compressed`, `no_breakout`, `rvol_low`, `atr_out_of_range`, `geometry_invalidation`) morrem no
   processo. Foi por isso que a decomposição por balde de `squeeze_ratio` do EXP-0008 e as fatias
   `atr_gap`/`trend_gap` do EXP-0009 não puderam ser medidas **diretamente** — o que consegui foi
   obtê-las por **diferença** entre duas versões sobre as mesmas barras (`trend_gap = 0`) e por
   **construção** (as 14 rejeições). Proposta concreta para o próximo brief: um `--explain-ledger` no
   `replay.run` gravando `(bar_close, market, state, reason, detail)` em JSONL — só arquivo, sem
   tabela nova, sem mudar uma linha da avaliação.
4. **Não existe histórico de regime para a janela.** `market_regimes` tem **1** linha no banco,
   `start_time = 2026-09-06 18:18:05`. A obrigação C4 do portão (quebrar o resultado por regime de
   BTC) é **impossível em replay** hoje e só será cumprível prospectivamente; o SQL
   `2026-09-08-07-regime-btc.sql` existe e não tem o que ler.
5. **Elegibilidade é lida *hoje*, não na barra** (limitação declarada do método, PIPELINE §6c): o
   conjunto ETH/SOL/XRP/DOGE é o de hoje, não o de agosto. Vale para as duas versões e para toda
   comparação com as coortes da T3.32.
6. **A amostra da `mean_reversion` é frágil onde importa.** 37 decisões, 11 dias, e o saldo positivo
   inteiro vem de 6 saídas por horizonte e de 2 dias (08-20/08-21). É `inconclusivo` no sentido forte:
   não é "quase madura", é pequena.
7. **Uma vigia de 10 min ficou em segundo plano por limite da minha ferramenta**, não por escolha: um
   laço de amostragem por `ssh` (somente leitura: `redis-cli HGETALL` e `GET /metrics`) estourou o
   timeout de 120 s do harness e foi movido para segundo plano, terminando sozinho com código 0.
   Nenhum comando que escreve rodou fora do primeiro plano; as duas ativações e os quatro replays
   foram todos em primeiro plano, com a saída completa colada acima.

## Arquivos tocados nesta tarefa (nenhum commit)

- `.claude/state/notes-T3.33e.md` (este arquivo);
- `.claude/state/exp-drafts/EXP-0008-breakout-compressao-de-volatilidade.md` — seção
  "Avaliação de 2026-09-08 — replay de abertura (REPLAY)" **acrescentada**, hipótese e protocolo
  intocados;
- `.claude/state/exp-drafts/EXP-0009-mean-reversion-pullback-em-tendencia.md` — idem.
