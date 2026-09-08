# notes-T3.33g — `session_orb v1` entra no Lab: ativação auditada, replay de 31 dias com o livro de motivos, avaliação por sessão e passada de estresse

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Executor:** quant-engineer.
**Brief:** `.claude/state/brief-T3.33g-session-orb-activate-replay.md`.
**Base local:** `main @ 52f30eb` (o pai é `c86ed19`, a imagem publicada; `52f30eb` só acrescenta o
brief — nenhum arquivo Python muda entre os dois).
**Nada foi commitado.** **Nenhum container parado ou recriado.** **Nenhum `.env*` tocado.** Nenhum
arquivo em `apps/**`, `services/**`, `packages/**` ou `obsidian/**` foi alterado.
**Escritas na VPS:** exatamente três — `activate_strategy_version.py` (uma linha em
`strategy_versions` + `system_events`) e os **dois** replays (coorte `research_only`). Todo o resto
foi lido em transação `REPEATABLE READ, READ ONLY`. Fora do banco, o `--explain-ledger` e o
`--ledger` gravaram JSONL em `/tmp` **dentro** do `hunter-strategy-worker-1`; nenhum arquivo foi
copiado para dentro de container nenhum. **Nada de paper, agents ou flags.**

## STATUS

**DONE_WITH_CONCERNS.** Os cinco passos do brief foram executados; o digest bateu e a corrida seguiu.
As concerns não mudam nenhum número — mudam a leitura de dois deles (K1 por uma decisão; o veredito
da passada de estresse é `amostra_insuficiente`) e registram duas divergências entre o brief e o
estado real da VPS que encontrei antes de começar.

| Passo do brief | Resultado |
|---|---|
| 1. `--dry-run` conferindo `…a4d514ad…` | **OK** — impresso byte a byte; ativação real às **19:42:56,116683Z** |
| 1b. 10 min de vigia de capacidade | **OK** — 19:42→19:57, `errors 0`, `outbox_lag_s 0,0` o tempo todo, `/ready` 200; `versions_active` **6 → 7** (o brief esperava 6 — ver CONCERN 2) |
| 2. Replay 31 d em duas fatias, mesma coorte, `--explain-ledger` | **OK** — 11 904 barras, 0 erros, 20 decisões, livros de motivo com 5 760 + 6 144 linhas |
| 3. Avaliação por sessão, transbordo, motivos, K1–K5 | **OK** — nenhum critério dispara; veredito **`inconclusivo`** |
| 4. Passada de estresse | **OK, mas sem poder de conclusão** — a própria ferramenta devolve `amostra_insuficiente` (20 de 30) |
| 5. Rascunho do EXP-0010 datado + carimbo para o T-037 | **OK** — `.claude/state/exp-drafts/` (o `obsidian/**` **não** foi tocado) |

## PARADA QUE NÃO ACONTECEU (e por que ela quase aconteceu)

O brief manda **PARAR** se o `--dry-run` não imprimir `…session_orb_v1@sha256:a4d514ad…`, citando
`notes-T3.33c.md` como fonte. **`notes-T3.33c.md` não contém esse digest** — a linha 43 daquele
arquivo registra `…session_orb_v1@sha256:aae896ee58bea0382c6e5e27c51a8a133932c143f20f84738f66ef90d7e951e9`.
Antes de tocar na VPS eu calculei o digest nas duas árvores relevantes e o brief está certo, a nota é
que ficou velha: o `code_ref` cobre o fecho `aggregate, base, canonical, envelope, indicators,
numeric, schema, session_orb_v1`, e esses irmãos mudaram entre a T3.33c e hoje.

```
$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref, module_closure; \
    print('closure', sorted(module_closure('session_orb_v1'))); print(version_code_ref('session_orb_v1'))"
closure ['aggregate', 'base', 'canonical', 'envelope', 'indicators', 'numeric', 'schema', 'session_orb_v1']
hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba

$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -c "…version_code_ref(\"session_orb_v1\")…"'
dir /app/packages/core/hunter_core/strategies/__init__.py
closure ['aggregate', 'base', 'canonical', 'envelope', 'indicators', 'numeric', 'schema', 'session_orb_v1']
hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
```

Árvore local, imagem do worker e `--dry-run` do `hunter-api-1` dão **o mesmo digest**. Segui.

## COMANDOS e RECIBOS (saída real, verbatim)

### 0. Estado da VPS antes de qualquer passo

```
$ ssh hunter-vps 'hostname; date -u; cd /opt/project-hunter && git log --oneline -1; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
vmi3483069
Tue Sep  8 19:37:44 UTC 2026
c86ed19 web: totais do Lab reconciliados com os tipos gerados da T3.38a …
hunter-web-1	hunter-web:c86ed19	Up 4 minutes (healthy)
hunter-api-1	hunter-api:c86ed19	Up 4 minutes (healthy)
hunter-strategy-worker-1	hunter-api:c29cbef	Up 25 minutes (healthy)
hunter-execution-worker-1	hunter-api:b5d4f9b	Up 3 hours (healthy)
hunter-scanner-worker-1	hunter-api:b5d4f9b	Up 3 hours (healthy)
hunter-market-worker-*	hunter-api:1ca7cf5	Up 4 hours (healthy)
hunter-caddy-1	caddy:2-alpine	Up 38 hours
hunter-postgres-1	postgres:16-alpine	Up 38 hours (healthy)
hunter-redis-1	redis:7-alpine	Up 38 hours (healthy)
```

**O `strategy-worker` está em `c29cbef`, não em `c86ed19`** (CONCERN 1). `c29cbef` é a T3.36 e é
**posterior** a `2442796` (T3.33f, `--explain-ledger`), então as duas bandeiras que este brief usa
existem na imagem — conferido com `--help`, não suposto:

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run --help'
usage: hunter_strategy_worker.replay.run [-h] [--version VERSION] [--from START] [--to END]
                                         [--markets MARKETS] [--exchange EXCHANGE]
                                         [--cohort COHORT] [--workers WORKERS]
                                         [--lag-s LAG_S] [--ledger LEDGER]
                                         [--explain-ledger EXPLAIN_LEDGER]
                                         [--dry-run] [--drain-queue] [--max-runs MAX_RUNS]
                                         [--stress STRESS] [--as-of AS_OF]
$ … replay.stress --help
usage: hunter_strategy_worker.replay.stress [-h] --cohort COHORT [--as-of AS_OF] [--ledger LEDGER]
                                            [--seed SEED] [--resamples RESAMPLES] [--limit LIMIT] [--json]
```

Roster no banco antes da ativação (SQL somente leitura):

```
key | version | status | purpose | activated_at | code_ref
breakout | v1 | deprecated | research_only | 2026-09-08 16:23:39.791800+00 | hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c
breakout | v2 | deprecated | research_only | 2026-09-08 17:35:22.628018+00 | hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c
derivatives | v1 | draft | research_only |  | hunter_indicators.strategies.derivatives_v1
ensemble | v1 | draft | research_only |  | hunter_indicators.strategies.ensemble_v1
mean_reversion | v1 | active | research_only | 2026-09-08 16:32:33.947955+00 | hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98ffa
momentum | v1 | deprecated | research_only | 2026-09-06 03:36:36.988581+00 | hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e
momentum | v2 | active | research_only | 2026-09-08 04:33:56.865371+00 | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5
momentum | v3 | active | paper | 2026-09-08 05:57:30.922979+00 | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5
momentum | v4 | active | research_only | 2026-09-08 13:05:13.558855+00 | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5
momentum | v5 | deprecated | research_only | 2026-09-08 18:57:05.384576+00 | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5
momentum | v6 | active | research_only | 2026-09-08 19:04:56.213531+00 | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5
narrative | v1 | draft | research_only |  | hunter_indicators.strategies.narrative_v1
order_flow | v1 | draft | research_only |  | hunter_indicators.strategies.order_flow_v1
session_orb | v1 | draft | research_only |  | hunter_indicators.strategies.session_orb_v1
volume_anomaly | v1 | deprecated | research_only | 2026-09-06 03:36:47.845595+00 | hunter_core.strategies.volume_anomaly_v1@sha256:a03d18fece9e
volume_anomaly | v2 | active | research_only | 2026-09-08 04:32:42.178866+00 | hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390
(16 rows)
```

A linha `session_orb v1` existe como `draft` com o `code_ref` **de semente**
(`hunter_indicators.strategies.session_orb_v1`, sem digest) — exatamente o estado que o brief
descreve. **Ativas já eram 6**, não 5 (CONCERN 2).

### 1. `--dry-run`, depois a ativação

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py session_orb v1 --changelog "T3.33g: EXP-0010 entra no Lab como pesquisa" --dry-run'
Tue Sep  8 19:41:02 UTC 2026
would activate session_orb v1 (purpose research_only) with code_ref hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba (22 parameters)

$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py session_orb v1 --changelog "T3.33g: EXP-0010 entra no Lab como pesquisa"'
Tue Sep  8 19:42:54 UTC 2026
activated session_orb v1 (purpose research_only) at 2026-09-08T19:42:56.116683+00:00 with code_ref hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
```

**Carimbo para o `Registro de Tentativas`, linha T-037** (o campo "início" que estava vazio):
**`2026-09-08T19:42:56,116683Z` = 2026-09-08 16:42:56 de Brasília.**
Coorte de replay do dia um: **`replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19`**.

Roster recarregado (a `momentum v3`, `paper`, continua **antes** das irmãs de pesquisa):

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -c "… load_active_versions …"'
… shadow_version_bound_by_code_ref module=session_orb_v1 strategy=session_orb_v1
1 mean_reversion v1 research_only 15m 8918b39b73fb
2 momentum v3 paper 15m 40e1688e6b5f
3 momentum v2 research_only 15m 40e1688e6b5f
4 momentum v4 research_only 15m 46635ed2bff2
5 momentum v6 research_only 15m 8cb1aa497956
6 session_orb v1 research_only 15m cdb9516b2932
7 volume_anomaly v2 research_only 5m fa5dce78173b
```

`params_hash cdb9516b2932…` é o congelado na `notes-T3.33c` — a versão que rodou é a que foi
revisada.

### 1b. Quinze minutos de vigia de capacidade (o brief pede dez)

| relógio (UTC) | `versions_active` | `evaluated_bars` | `outbox_lag_s` | `outbox_pending` | `errors` | `open_trackings` |
|---|---:|---:|---:|---:|---:|---:|
| 19:42:13 (**antes**) | 6 | 4 730 | 0,0 | 0 | 0 | 43 |
| 19:43:19 (**depois**) | **7** | 4 730 | 0,0 | 0 | 0 | 43 |
| 19:46:34 (entre replays) | 7 | 5 564 | 0,0 | 0 | 0 | 45 |
| 19:52:43 | 7 | 6 450 | 0,0 | 0 | 0 | 46 |
| 19:55:29 | 7 | 7 529 | 0,0 | 0 | 0 | 43 |
| 19:57:37 | 7 | 7 529 | 0,0 | 0 | 0 | 42 |

`hunter_shadow_versions_runnable` acompanhou `active` em 7 nas seis amostras e as cinco razões de
`unrunnable` ficaram em **0,0** o tempo todo (`code_ref_mismatch`, `code_ref_not_frozen`, `no_code`,
`no_parameters`, `purpose_live_forbidden`). `/ready` respondeu **200**.

A versão nova **avaliou de fato**, não só entrou no roster:

```
hunter_shadow_evaluations_total{state="not_triggered",strategy="session_orb"} 215.0
hunter_shadow_evaluations_total{state="unavailable",strategy="session_orb"} 96.0
```

215 + 96 = 311 avaliações prospectivas nos primeiros fechamentos de 15 min, e **nenhum
`triggered`** — coerente com uma taxa de disparo de 0,33 % das barras. (Os contadores são cumulativos
desde o start do processo; por isso `breakout` ainda aparece neles apesar de `deprecated`.)

### 2. Os dois replays (uma coorte, duas fatias contíguas)

```
$ ssh hunter-vps 'date -u; docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run --version session_orb:v1 \
    --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
    --cohort replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19 --dry-run'
{'cohort': 'replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19', 'version': 'session_orb v1', 'markets': 4, 'bars_planned': 5760, 'workers': 3}

$ … (sem --dry-run, --ledger /tmp/t33g-replay-session-orb-a-run.jsonl --explain-ledger /tmp/replay-session-orb-a.jsonl)
[info] replay_explain_ledger  bars=5760 lines=5760 path=/tmp/replay-session-orb-a.jsonl
{'run_id': '3fb9dda2-256f-49af-9a1e-7ec5bd001d19', 'cohort': 'replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19',
 'strategy_version_id': '01a08284-6f7b-701d-abf0-bd07ad58d52a', 'version_label': 'session_orb v1',
 'window_from': '2026-08-08T00:00:00+00:00', 'window_to': '2026-08-23T00:00:00+00:00',
 'markets': ['binance:ETHUSDT', 'binance:SOLUSDT', 'binance:XRPUSDT', 'binance:DOGEUSDT'], 'market_count': 4,
 'started_at': '2026-09-08T19:44:42.037570+00:00', 'finished_at': '2026-09-08T19:46:06.830476+00:00',
 'bars_evaluated': 5760, 'signals': 8, 'outcomes_resolved': 8, 'outcomes_open': 0, 'seconds': 84.793,
 'bars_per_second': 67.93, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'not_triggered': 5354, 'unavailable': 236, 'rejected': 153, 'triggered': 17}, 'errors': 0}

$ … --from 2026-08-23 --to 2026-09-08 … --explain-ledger /tmp/replay-session-orb-b.jsonl
[info] replay_explain_ledger  bars=6144 lines=6144 path=/tmp/replay-session-orb-b.jsonl
{'run_id': '3fb9dda2-…', 'version_label': 'session_orb v1', 'window_from': '2026-08-23T00:00:00+00:00',
 'window_to': '2026-09-08T00:00:00+00:00', 'market_count': 4,
 'started_at': '2026-09-08T19:47:07.045308+00:00', 'finished_at': '2026-09-08T19:48:34.957637+00:00',
 'bars_evaluated': 6144, 'signals': 20, 'outcomes_resolved': 20, 'outcomes_open': 0, 'seconds': 87.912,
 'bars_per_second': 69.89, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'not_triggered': 5996, 'rejected': 126, 'triggered': 22}, 'errors': 0}
```

**Atenção ao denominador (a mesma armadilha da T3.33e/f):** `signals`/`outcomes_resolved` do recibo
contam a **coorte inteira**, então `8` na fatia A e `20` na fatia B **não somam**: a população final
é **20 decisões**, confirmada linha a linha no banco.

Recibos em `replay_runs` (lidos do banco, `READ ONLY`):

```
coorte | versao | de | ate | mercados | bars | signals | outcomes | open | seg | workers | lag | estados | erros
replay:3fb9dda2-… | session_orb v1 | 2026-08-08 | 2026-08-23 | 4 | 5760 | 8 | 8 | 0 | 84.793 | 3 | 2 | {"rejected": 153, "triggered": 17, "unavailable": 236, "not_triggered": 5354} | 0
replay:3fb9dda2-… | session_orb v1 | 2026-08-23 | 2026-09-08 | 4 | 6144 | 20 | 20 | 0 | 87.912 | 3 | 2 | {"rejected": 126, "triggered": 22, "not_triggered": 5996} | 0
(2 rows)
```

`system_events` da janela:

```
level | component | event | message | created_at
info | activate_strategy_version | strategy_version_activated | session_orb v1 (purpose research_only) activated with code_ref=hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae2330… | 2026-09-08 19:42:56.116683+00
info | replay_engine | replay_run_finished | replay session_orb v1 4 mercados 2026-08-08T00:00:00+00:00..2026-08-23T00:00:00+00:00: 5760 barras, 8 sinais, 8 desfechos, 84.793 s | 2026-09-08 19:46:06.831694+00
info | replay_engine | replay_run_finished | replay session_orb v1 4 mercados 2026-08-23T00:00:00+00:00..2026-09-08T00:00:00+00:00: 6144 barras, 20 sinais, 20 desfechos, 87.91 s | 2026-09-08 19:48:34.958564+00
(3 rows)
```

**Isolamento — a coorte é a cerca, e ela segurou:**

```
outbox_com_coorte | sinais_coorte | sinais_v1_fora_da_coorte | sinais_v1_total | slots_da_coorte | slots_prospectivos
                0 |            20 |                        0 |              20 |               4 |                215
```

Nenhuma linha de outbox com a coorte (a T3.19b já nem cria), nenhum sinal da `v1` fora dela, quatro
slots de replay (um por mercado) e 215 slots prospectivos armados pelo roster vivo.

### 3. Cobertura por estado (31 dias × 4 mercados = 11 904 barras)

| versão | barras | `unavailable` | `not_triggered` | `triggered` | `rejected` | decisões persistidas |
|---|---:|---:|---:|---:|---:|---:|
| `session_orb v1` | 11 904 | 236 (**1,98 %**) | 11 350 (95,35 %) | 39 (0,328 %) | 279 (2,34 %) | **20** |

Os 236 `unavailable` são **59 por mercado** — o aquecimento de `rvol_window + 1 = 97` barras servido
pelo cache, contra 112 por mercado da `breakout`/`mean_reversion` na T3.33e (janelas diferentes,
mesma janela de dados). 39 barras dispararam e **20** viraram decisão: as outras 19 caíram na
barreira de re-arme (um acompanhamento por versão/mercado/coorte) — não são dado perdido.

### 4. O livro de motivos (`--explain-ledger`, 11 904 linhas = 5 760 + 6 144)

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 sh -c "wc -l /tmp/replay-session-orb-a.jsonl /tmp/replay-session-orb-b.jsonl"'
   5760 /tmp/replay-session-orb-a.jsonl
   6144 /tmp/replay-session-orb-b.jsonl
  11904 total

linhas: 11904
estados: {'not_triggered': 11350, 'unavailable': 236, 'rejected': 279, 'triggered': 39}
```

O histograma do arquivo é **idêntico**, estado por estado, à soma dos dois recibos — a mesma
verificação da T3.33f, aqui reproduzida sobre um livro-razão de verdade (naquele dia a bandeira não
estava na imagem).

| motivo | n | % das barras | asia | europe | us |
|---|---:|---:|---:|---:|---:|
| `outside_session_window` | 4 092 | 34,375 | 868 | 372 | 2 852 |
| `no_range_break` | 4 003 | 33,627 | 1 305 | 1 431 | 1 267 |
| `inside_opening_range` | 1 860 | 15,625 | 620 | 620 | 620 |
| `rvol_low` | 820 | 6,888 | 352 | 255 | 213 |
| `atr_out_of_range` | 575 | 4,830 | 164 | 152 | 259 |
| `range_geometry` | 279 | 2,344 | 44 | 67 | 168 |
| `warmup` | 236 | 1,983 | 108 | 64 | 64 |
| `signal` | 39 | 0,328 | 11 | 15 | 13 |
| **`no_session_open`** | **0** | 0,000 | — | — | — |

Quatro leituras:

1. **`no_session_open` nunca ocorreu.** A CONCERN 3 da `notes-T3.33c` dizia que, com as aberturas
   congeladas, o ramo é **inalcançável** (a asia às 00:00 cobre o dia inteiro). Agora está **medido**
   em 11 904 barras, não argumentado;
2. **`inside_opening_range` é aritmética pura, e fecha exatamente.** São **465 por mercado**
   (1 860 / 4) e **620 por sessão** (1 860 / 3): `bars_since_open <= 4` cobre 5 barras (0..4) por
   sessão, e 5 × 3 sessões × 31 dias = **465**; 5 × 31 × 4 mercados = **620** por sessão. Nenhum
   grau de liberdade, nenhuma surpresa — é o preço fixo de manter a primeira hora fora da regra;
3. **`outside_session_window` é assimétrico por artefato de rótulo, não por mercado.** As 6 horas
   mortas do dia (18:00–24:00 UTC) recebem o rótulo `us` porque `_session_open` devolve a última
   abertura ≤ corte; por isso `us` tem 2 852 e `europe` 372. Isso **não** contamina a decomposição
   das decisões (que é por sessão da barra que decidiu);
4. **A guarda de tamanho é o funil real.** Das 279 recusas de `range_geometry`, **277 são por faixa
   larga demais** e **2** por faixa estreita demais:

```
range_risk_atr nas recusas de geometria: n=279  min 0,921  p25 3,468  mediana 4,438  p75 5,955  max 9,445
   abaixo de 1,0: 2      acima de 2,5: 277
```

Quando o preço rompe a máxima da primeira hora, a **mínima** dessa hora costuma estar a ~4,4 ATR —
um stop enorme. O teto de 2,5 ATR recusa essas operações, e é por isso que o pedágio medido ficou em
0,1428 R (ver adiante) em vez dos 0,6152 R que a `volume_anomaly v2` pagou.

Por mercado (mesma leitura, sem surpresa):

```
binance:DOGEUSDT {'inside_opening_range': 465, 'warmup': 59, 'outside_session_window': 1023, 'no_range_break': 985, 'rvol_low': 220, 'atr_out_of_range': 138, 'range_geometry': 72, 'signal': 14}
binance:ETHUSDT  {'inside_opening_range': 465, 'warmup': 59, 'outside_session_window': 1023, 'no_range_break': 1006, 'atr_out_of_range': 201, 'rvol_low': 191, 'range_geometry': 24, 'signal': 7}
binance:SOLUSDT  {'inside_opening_range': 465, 'warmup': 59, 'outside_session_window': 1023, 'no_range_break': 991, 'rvol_low': 211, 'atr_out_of_range': 143, 'range_geometry': 74, 'signal': 10}
binance:XRPUSDT  {'inside_opening_range': 465, 'warmup': 59, 'outside_session_window': 1023, 'no_range_break': 1021, 'atr_out_of_range': 93, 'rvol_low': 198, 'range_geometry': 109, 'signal': 8}
```

## TABELAS — a avaliação da coorte `replay:3fb9dda2…`

**Rótulo obrigatório (T3.33 §5.1): REPLAY, não coleta prospectiva.** A janela avaliada é a mesma que
gerou a hipótese; nada aqui confirma coisa alguma.

### Nota metodológica sobre "R bruto" (uma correção que eu fiz no meio do caminho)

`signal_outcomes.virtual_entry` e `exit_price` **já são os preços adversos** — `pricing.py` aplica
meio-spread + slippage (6 bps) em cada ponta antes de persistir. Um "bruto" ingênuo
`(exit_price − virtual_entry)/risco` já traria 12 bps de custo embutido e faria o pedágio parecer
metade do que é. O bruto desta tabela desfaz os dois lados
(`raw = virtual_entry/(1+6bps)`, `raw = exit_price/(1−6bps)`) e é, aí sim, **sem custo nenhum**;
`custo_R = R_bruto − r_ex_funding` cobre os 12 bps de preço mais os 8 bps de taxa. A conferência é a
identidade da T3.32 (`custo_R ≈ 0,0020 / risco%`), e ela fecha em três casas por linha: DOGE 20-08
risco 1,259 % → previsto 0,1589, medido **0,1578**; ETH 27-08 risco 0,916 % → previsto 0,2183,
medido **0,2174**.

### Agregados

| recorte | n | avaliáveis | exp. bruta | exp. ex-funding | exp. líquida | custo R | soma `R_net` | PF | acerto | dias | mercados |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **TOTAL** | **20** | 20 | **−0,0501** | **−0,1930** | **−0,1928** | 0,1428 | **−3,86** | **0,662** | 10,0 % | **9** | 4 |
| sessão asia | 6 | 6 | +0,0086 | −0,1454 | −0,1454 | 0,1540 | −0,87 | 0,666 | 0,0 % | 4 | 4 |
| sessão europe | 7 | 7 | −0,1834 | −0,3257 | −0,3257 | 0,1422 | −2,28 | 0,484 | 0,0 % | 4 | 4 |
| sessão us | 7 | 7 | +0,0328 | −0,1010 | −0,1005 | 0,1338 | −0,70 | 0,839 | 28,6 % | 5 | 3 |
| DOGEUSDT | 7 | 7 | +0,1627 | +0,0089 | +0,0089 | 0,1538 | +0,06 | 1,018 | 28,6 % | 6 | 1 |
| ETHUSDT | 3 | 3 | −0,6808 | −0,8335 | −0,8335 | 0,1526 | −2,50 | 0,000 | 0,0 % | 2 | 1 |
| SOLUSDT | 4 | 4 | +0,0913 | −0,0431 | −0,0415 | 0,1344 | −0,17 | 0,924 | 0,0 % | 3 | 1 |
| XRPUSDT | 6 | 6 | −0,0773 | −0,2081 | −0,2085 | 0,1308 | −1,25 | 0,621 | 0,0 % | 5 | 1 |
| saída `expired` | 8 | 8 | +0,6237 | +0,4844 | +0,4841 | 0,1393 | **+3,87** | 11,731 | — | 5 | 4 |
| saída `stop` | 10 | 10 | −0,9551 | −1,1038 | −1,1032 | 0,1487 | **−11,03** | 0,000 | — | 6 | 4 |
| saída `target` | 2 | 2 | +1,7793 | +1,6519 | +1,6519 | 0,1274 | **+3,30** | — | — | 2 | 1 |

Cobertura: `tracking_state` **terminal 20/20**, `no_entry_reason` nulo em todas, `r_net_reason` nulo
em todas → **cobertura de `R_net` = 100,0 %**.

### A regra dos 70 % do EXP-0010

| sessão | decisões | fração | dias distintos |
|---|---:|---:|---:|
| asia | 6 | **30,0 %** | 4 |
| europe | 7 | **35,0 %** | 4 |
| us | 7 | **35,0 %** | 5 |

**Não dispara.** Nenhuma sessão carrega a amostra; a hipótese **não** precisa ser reenunciada como
"uma hora específica". É o achado mais limpo do dia — e é o único achado positivo.

**O outro lado da mesma regra, porém, morde.** O EXP-0010 também congela: *"se a expectancy por
sessão for indistinguível entre as três, o rótulo de sessão não está fazendo trabalho nenhum"*. As
três são negativas (−0,145 / −0,326 / −0,101) e, com n = 6/7/7, **indistinguíveis**. O rótulo de
sessão — que é a hipótese inteira — não fez trabalho nenhum nesta janela.

### Transbordo de sessão (o custo declarado, medido)

| leitura | n | fração |
|---|---:|---:|
| saída **depois do fim da janela de 5 h** da sessão de entrada | 11 / 20 | **55,0 %** |
| saída numa **sessão declarada posterior** | 4 / 20 | **20,0 %** |

```
SOLUSDT  08-21 03:15  asia   -> europe  (expired)
DOGEUSDT 08-27 10:30  europe -> us      (expired)
XRPUSDT  08-27 10:30  europe -> us      (expired)
ETHUSDT  08-27 10:30  europe -> us      (stop)
```

As duas leituras respondem coisas diferentes e por isso publico as duas: a de 55 % diz que **mais da
metade** das operações ainda está aberta quando a janela de cinco horas da própria sessão acaba; a de
20 % diz quantas atravessam para outra **abertura declarada**. O horizonte de 4 h realmente
transborda — está medido, não suposto.

### As 20 decisões

| mercado | decisão (UTC) | sessão | resultado | ATR% | rvol | risco/ATR | risco% | R bruto | R ex-fund | R líquido | custo R | saída (UTC) |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DOGEUSDT | 2026-08-20 02:15 | asia | stop | 0,007020 | 2,738 | 1,728 | 1,259 | −0,9524 | −1,1101 | −1,1101 | 0,1578 | 08-20 03:09 |
| DOGEUSDT | 2026-08-20 14:15 | us | **target** | 0,007003 | 1,978 | 2,160 | 1,382 | +2,3312 | +2,1842 | **+2,1842** | 0,1469 | 08-20 15:55 |
| XRPUSDT | 2026-08-21 01:30 | asia | expired | 0,010098 | 1,426 | 2,336 | 2,265 | +0,7233 | +0,6343 | +0,6343 | 0,0890 | 08-21 05:31 |
| ETHUSDT | 2026-08-21 01:45 | asia | expired | 0,006188 | 2,293 | 2,262 | 1,497 | −0,1405 | −0,2738 | −0,2738 | 0,1334 | 08-21 05:46 |
| SOLUSDT | 2026-08-21 03:15 | asia | expired | 0,007061 | 1,422 | 2,479 | 1,677 | +1,2254 | +1,1050 | +1,1050 | 0,1204 | 08-21 07:16 |
| SOLUSDT | 2026-08-21 08:30 | europe | stop | 0,007137 | 2,739 | 2,224 | 1,689 | −0,9645 | −1,0819 | −1,0819 | 0,1174 | 08-21 11:35 |
| ETHUSDT | 2026-08-21 09:45 | europe | stop | 0,008981 | 1,364 | 1,830 | 1,850 | −0,9676 | −1,0747 | −1,0747 | 0,1071 | 08-21 11:33 |
| DOGEUSDT | 2026-08-22 17:30 | us | **target** | 0,010945 | 1,507 | 1,261 | 1,876 | +1,2273 | +1,1196 | **+1,1196** | 0,1078 | 08-22 20:12 |
| SOLUSDT | 2026-08-23 08:45 | europe | expired | 0,007687 | 1,825 | 1,673 | 1,345 | +1,0589 | +0,9092 | +0,9092 | 0,1497 | 08-23 12:46 |
| XRPUSDT | 2026-08-23 14:30 | us | stop | 0,010558 | 2,218 | 2,060 | 2,394 | −0,9750 | −1,0575 | −1,0575 | 0,0825 | 08-23 14:43 |
| DOGEUSDT | 2026-08-24 11:45 | europe | stop | 0,007340 | 2,705 | 2,043 | 1,303 | −0,9540 | −1,1064 | −1,1064 | 0,1525 | 08-24 12:17 |
| DOGEUSDT | 2026-08-27 10:30 | europe | expired | 0,007292 | 4,281 | 2,039 | 1,490 | +0,3047 | +0,1702 | +0,1702 | 0,1345 | 08-27 14:31 |
| XRPUSDT | 2026-08-27 10:30 | europe | expired | 0,007908 | 2,975 | 2,241 | 1,721 | +1,1729 | +1,0556 | +1,0556 | 0,1173 | 08-27 14:31 |
| ETHUSDT | 2026-08-27 10:30 | europe | stop | 0,006345 | **9,061** | 1,392 | 0,916 | −0,9345 | −1,1519 | −1,1519 | 0,2174 | 08-27 13:39 |
| XRPUSDT | 2026-08-28 01:45 | asia | stop | 0,006201 | 2,186 | 1,540 | 0,987 | −0,9393 | −1,1408 | −1,1408 | 0,2015 | 08-28 02:12 |
| SOLUSDT | 2026-08-28 14:45 | us | stop | 0,008413 | 5,965 | 1,791 | 1,324 | −0,9547 | −1,1047 | −1,0985 | 0,1500 | 08-28 16:03 |
| DOGEUSDT | 2026-08-28 14:45 | us | stop | 0,006897 | 5,283 | 1,871 | 1,282 | −0,9532 | −1,1082 | −1,1082 | 0,1550 | 08-28 15:43 |
| XRPUSDT | 2026-08-28 15:00 | us | stop | 0,008417 | 2,761 | 1,354 | 1,357 | −0,9558 | −1,1021 | −1,1021 | 0,1463 | 08-28 15:42 |
| XRPUSDT | 2026-08-31 15:00 | us | expired | 0,006056 | 1,629 | 2,052 | 1,352 | +0,5100 | +0,3617 | +0,3592 | 0,1483 | 08-31 19:01 |
| DOGEUSDT | 2026-09-06 01:15 | asia | expired | 0,006429 | 1,534 | 1,393 | 0,900 | +0,1351 | −0,0870 | −0,0870 | **0,2221** | 09-06 05:16 |

Três coisas que essa tabela diz e os agregados escondem:

- **`range_risk_atr` das 20 decisões vai de 1,261 a 2,479** — a faixa permitida inteira, concentrada
  na metade de cima. A guarda não está "quase nunca ativa": ela é o que define quem entra;
- **quatro das cinco decisões de 28-08 são stops no mesmo par de horas** (14:45 e 15:00), com rvol
  5,3–6,0. Um evento, quatro operações: a coorte tem menos independência do que n = 20 sugere;
- **os dois alvos são do mesmo mercado** (DOGEUSDT). Com 2 acertos em 20, "10 % de acerto" é uma
  descrição, não uma estimativa.

### O pedágio desta geometria, confrontado com a T3.33c

| leitura | valor |
|---|---:|
| teto aritmético calculado na T3.33c (`0,002 / (1,0 × 0,006)`) | 0,3333 R |
| **pedágio medido, média das 20** | **0,1428 R** |
| pedágio medido, máximo | 0,2221 R |
| pedágio medido, mínimo | 0,0825 R |
| `volume_anomaly v2` (coorte de replay, T3.32) | 0,6152 R |
| `momentum v1` (prospectiva, T3.32) | 0,1506 R |

**O piso `range_risk_atr_min = 1,0` fez o que prometeu:** o pedágio ficou dentro do teto declarado e
na mesma ordem do `momentum`. **E não adiantou** — a expectancy já é negativa **antes** de qualquer
custo (−0,0501 R). Este é o ponto que separa esta versão da `volume_anomaly`: lá o custo era a
doença; aqui o custo está controlado e a regra ainda perde.

## K1–K5 do EXP-0010 (`notes-T3.33.md` §5.1) e veredito

| K | condição | medido | dispara? |
|---|---|---|---|
| K1 | < 20 decisões → deprecar | **exatamente 20** | **não — por uma decisão** |
| K2 | > 1 500 decisões | 20 | não |
| K3 | ≥ 100 avaliáveis **e** ≥ 30 dias **e** expectancy bruta (`r_ex_funding`) < 0 | 20 (< 100), **9 dias** (< 30), `r_ex_funding` **−0,1930** | **não** — falham as duas condições de régua; a de mercado já está cumprida |
| K4 | `unavailable` > 40 % das barras | **1,98 %** | não |
| K5 | cobertura de `R_net` < 70 % | **100 %** | não |
| — | regra dos 70 % (EXP-0010) | máx. **35,0 %** | não |
| — | expectancy indistinguível entre as três sessões (EXP-0010) | **sim**, e as três negativas | não mata, mas **esvazia a hipótese** |

**VEREDITO: `inconclusivo`.** Nenhum critério de descarte dispara. Não escrevo `descartar` porque
nenhum kill criterion disparou — mas registro, sem suavizar, que **K1 falhou por uma decisão** e que
a única condição de K3 que depende do mercado (expectancy bruta negativa) **já está cumprida**: se a
versão chegar a 100 avaliáveis e 30 dias mantendo o sinal desta janela, K3 decide sozinho e a decisão
será `descartar`.

**Next Action:** a versão fica correndo em `prospective` (`research_only`, sem carteira, já no
roster) e é reavaliada quando houver ≥ 100 avaliáveis **e** ≥ 30 dias. **Não** derivar variante por
sessão nem afrouxar `range_risk_atr_max` — as duas estão registradas como variantes **recusadas**, com
o motivo, na tabela de `Variantes tentadas` do EXP-0010.

## PASSADA DE ESTRESSE (T3.36)

```
$ ssh hunter-vps 'date -u; docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.stress \
    --cohort replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19 --ledger /tmp/stress-session-orb.jsonl'
Tue Sep  8 19:53:26 UTC 2026
coorte replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19 · as_of 2026-09-08T19:53:28.833572+00:00 · 20 entradas congeladas · 4 mercados
```

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ | descartes |
|---|---|---:|---:|---:|---:|---|---|
| `base` | reprecificacao | 20 | -0.1928 | 0.6616 | — | — | — |
| `custos_x2` | reprecificacao | 20 | -0.3186 | 0.4966 | -0.1258 | [-0.1522, -0.1107] | — |
| `stop_x0.75` | reprecificacao | 20 | -0.1581 | 0.7565 | 0.0347 | [-0.1077, +0.1749] | — |
| `stop_x1.25` | reprecificacao | 20 | -0.2338 | 0.5632 | -0.0410 | [-0.1187, +0.0058] | — |
| `alvo_x0.75` | reprecificacao | 20 | -0.1439 | 0.7455 | 0.0489 | [-0.0933, +0.2632] | — |
| `alvo_x1.25` | reprecificacao | 20 | -0.1497 | 0.7373 | 0.0431 | [+0.0000, +0.1297] | — |
| `entrada_mais_1_barra` | reprecificacao | 20 | -0.1978 | 0.6572 | -0.0050 | [-0.0674, +0.0659] | — |
| `sem_binance:DOGEUSDT` | recorte | 13 | -0.3014 | 0.5091 | — | — | — |
| `sem_binance:ETHUSDT` | recorte | 17 | -0.0797 | 0.8476 | — | — | — |
| `sem_binance:SOLUSDT` | recorte | 16 | -0.2306 | 0.5995 | — | — | — |
| `sem_binance:XRPUSDT` | recorte | 14 | -0.1860 | 0.6782 | — | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 18 | -0.2293 | 0.6349 | — | — | — |
| `2a_metade_apos_2026-08-28` | recorte | 2 | 0.1361 | 4.1269 | — | — | — |

```
**Veredito:** amostra_insuficiente
- 20 desfechos avaliáveis de 30
```

**Veredito da passada: `amostra_insuficiente`** — e ele é da própria ferramenta, não meu. O brief
pede que eu diga isso explicitamente quando `n < 30`: **digo**. A tabela acima é **descritiva** e
nenhuma linha dela deve ser citada como "frágil a X" ou "robusto a X". Dois exemplos de por quê: a
segunda metade da janela tem **duas** operações (o `+0,1361 R` não é informação), e `alvo_x1.25`
aparece com IC `[+0,0000; +0,1297]` — um limite inferior exatamente em zero é sintoma de reamostragem
por blocos de dia sobre 9 dias, não de significância.

O único número da tabela que eu leria é o `custos_x2`: **−0,3186 R** com IC do Δ inteiro negativo.
Ele não diz "frágil a custos" (a base já perde); diz que dobrar o custo **piora de forma consistente**
uma coorte que já é negativa, e que não há folga nenhuma para deterioração de execução.

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\notes-T3.33g.md` | **novo** — este arquivo |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0010-session-orb-faixa-de-abertura.md` | seção datada **"2026-09-08 — Avaliação (replay, dia um) — T3.33g"** com a tabela de estresse; frontmatter (`status`, `result`, `evaluable`, `days`, `last_eval`); +2 linhas em `Variantes tentadas` (as duas **recusadas**). As seções `Hipótese` e `Protocolo` **não** foram tocadas |

**Não tocados:** `.env*`, `apps/**`, `services/**`, `packages/**`, `infra/**`, `obsidian/**`. Nenhum
commit. Fora do repositório (scratchpad, descartáveis): `roquery.py`/`roq.sh` (SQL somente leitura),
`eval_orb.py` (a avaliação da coorte), `ledger_reasons.py` (histograma do livro-razão), `cap.sh`
(amostra de capacidade).

## O QUE FOI ESCRITO NA VPS (inventário completo)

1. `strategy_versions`: `session_orb v1` → `status active`, `purpose research_only`,
   `activated_at 2026-09-08T19:42:56,116683Z`, `code_ref …a4d514ad…`, `changelog` do brief;
2. `system_events`: 1 linha `strategy_version_activated` + 2 linhas `replay_run_finished`;
3. `replay_runs`: 2 recibos; `agent_signals` + `signal_outcomes`: 20 pares da coorte
   `replay:3fb9dda2…`; `shadow_episodes`: 4 slots de replay;
4. `/tmp` **dentro** do `hunter-strategy-worker-1`: `replay-session-orb-a.jsonl` (5 760 linhas),
   `replay-session-orb-b.jsonl` (6 144), `t33g-replay-session-orb-{a,b}-run.jsonl`,
   `stress-session-orb.jsonl`.

Nada mais. Nenhuma flag, nenhum agent, nenhuma linha de paper, nenhum container reiniciado.

## CONCERNS

1. **O `strategy-worker` não está na imagem que o brief supõe.** O brief diz "a imagem é `c86ed19`";
   `hunter-api-1` e `hunter-web-1` estão em `c86ed19`, mas `hunter-strategy-worker-1` roda
   **`c29cbef`** (T3.36), quatro commits atrás. Verifiquei antes de rodar que isso é **seguro para
   esta tarefa** — `c29cbef` é posterior à T3.33f, então tem `--explain-ledger` e `replay.stress`, e
   calcula **o mesmo digest** `a4d514ad…` do `hunter-api-1` — mas o fato em si é uma deriva de
   deploy: um dia a `api` vai ativar uma versão cujo `code_ref` o worker não reconhece e o Lab
   emudece atrás de um `/ready` verde (é literalmente o modo de falha que o `code_ref` por versão
   existe para evitar). Quem faz deploy precisa atualizar os workers junto, ou o `compose.sh update`
   precisa deixar de ser opcional para eles.
2. **O roster real não era o do brief.** O brief descreve "momentum v2/v3/v4, volume_anomaly v2,
   mean_reversion v1 ativas" e espera `versions_active 6` **depois** da ativação. O estado real às
   19:42Z já era **6 ativas** (a T3.40 ativou `momentum v6` às 19:04 e aposentou a `v5`, e
   `breakout v1`/`v2` já estavam `deprecated`), então o número correto depois de ativar é **7** — que
   é o que as seis amostras mostram. Não é um problema de capacidade (a T3.33f já vigiou 7 versões),
   é o brief que foi escrito contra um retrato de 19:36Z que envelheceu em minutos. **Ativei mesmo
   assim** porque o único critério de parada do brief é o digest.
3. **O digest citado no brief não está na nota citada como fonte.** Ver a seção "PARADA QUE NÃO
   ACONTECEU". A `notes-T3.33c.md` registra `aae896ee…`, que era o digest naquele momento; o fecho
   mudou (`indicators`, `base` etc. são compartilhados) e hoje é `a4d514ad…`. **Nenhum dos dois está
   errado** — o que está errado é tratar um digest de fecho compartilhado como constante entre
   tarefas. Sugestão concreta: notas que citam `code_ref` deveriam citar **também** o commit da
   árvore em que foi calculado, senão a próxima tarefa herda um critério de parada obsoleto que ou
   para uma corrida boa ou (pior) é ignorado por quem "sabe" que mudou.
4. **K1 não disparou por uma decisão.** 20 é exatamente o piso. Se o `--to` fosse um dia mais curto,
   ou se a barreira de re-arme tivesse comido mais uma das 39 barras que dispararam, o veredito seria
   `descartar`. Não arredondei nem estiquei a janela: a janela é a do brief. Mas ninguém deve ler
   "inconclusivo" aqui como "promissor".
5. **A coorte tem menos independência do que n = 20 sugere.** Quatro das 20 decisões são de 28-08
   entre 14:45 e 15:00 (três mercados, mesmo movimento, todas stop) e três são de 27-08 às 10:30
   (mesmo minuto, três mercados). Em blocos de evento, a amostra efetiva está mais para ~14. A
   passada de estresse reamostra por **blocos de dia**, o que trata isso parcialmente — mas com 9
   dias distintos o bootstrap tem pouco com o que trabalhar.
6. **`r_gross` não é uma coluna, é uma reconstrução.** Nada no banco guarda o preço cru: só os
   adversos. O bruto desta nota desfaz 6 bps por ponta a partir de `virtual_entry`/`exit_price`. É
   exato (a operação é uma divisão, não uma estimativa) e está conferido contra a identidade da
   T3.32, mas é **derivado**. Se alguém comparar o "bruto" desta nota com o de uma análise que usou
   `(exit_price − virtual_entry)/risco`, vai encontrar uma diferença de ~0,09 R **de método**, não de
   mercado. Vale padronizar isso num único helper antes que apareçam duas expectancies brutas
   diferentes para a mesma coorte.
7. **`outside_session_window` rotula as horas mortas como `us`.** 2 852 das 4 092 recusas por janela
   caem em `us` só porque `_session_open` devolve a última abertura ≤ corte e não existe abertura
   depois das 13:00. Não afeta nenhuma decisão nem nenhuma métrica desta nota, mas qualquer painel que
   plote "recusas por sessão" a partir do livro-razão vai mentir sobre a sessão americana. O conserto
   honesto seria um rótulo `fora_de_sessao` distinto — **versão nova**, não ajuste.
8. **A hipótese sobreviveu ao teste dos 70 % e morreu no outro critério da mesma página.** As
   decisões se dividiram 30/35/35 %, o que é uma refutação limpa do medo "isto é só uma hora
   específica". Só que as três sessões perderam, com expectancies indistinguíveis: o rótulo de sessão
   não fez trabalho. Registro isso como o achado principal, e registro também que **não** o
   transformei em variante nenhuma.
9. **`hunter-api-1` e `hunter-web-1` foram para `70db58a` no meio da minha janela** (às ~19:56, por
   outra entrega). O `hunter-strategy-worker-1` **não** foi tocado (`Up 45 minutes`, `c29cbef`), então
   ativação e replays não foram afetados; a última amostra de capacidade (19:57:37) já é com a API
   nova e continua `versions_active 7`, `errors 0`, `outbox_lag_s 0,0`. Fica registrado porque a
   árvore e a VPS são compartilhadas e o retrato de "estado final" desta nota vale para o worker, não
   para a API.
10. **Nada disto é evidência prospectiva.** É replay sobre a janela que gerou a hipótese, com quatro
    versões abertas no mesmo dia (multiplicidade declarada no EXP-0010). A única leitura que vale
    para o futuro é: a versão está viva, `research_only`, sem carteira, e a régua de reavaliação é
    ≥ 100 avaliáveis e ≥ 30 dias.

## PRÓXIMO PASSO (não é meu)

- **code-reviewer:** conferir recibos contra o banco (coorte `replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19`);
- **Sexta-feira:** arquivar o EXP-0010 em `obsidian/05-EXPERIMENTS/` a partir de
  `.claude/state/exp-drafts/`, e preencher o **início** da linha **T-037** do
  `Registro de Tentativas` com **2026-09-08T19:42:56,116683Z (16:42:56 de Brasília)** e a coorte
  `replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19`; status da linha: **em curso / inconclusivo**.
