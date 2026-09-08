# notes-T3.42 — as duas irmãs com teto de pedágio da única candidata viva (`mean_reversion v1`)

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Owner:** quant-engineer.
**Base do brief:** `main @ 7b0edeb`; VPS rodando `hunter-api:d829546` (api e strategy-worker) do
começo ao fim — **nenhum redeploy no meio desta vez**.
**Nada commitado.** **Nenhum container parado ou recriado.** **Nenhum `.env*` tocado.**
**Nada escrito por mim em `apps/**`, `services/**`, `packages/**`, `obsidian/**`** (ver CONCERN 6:
outras tarefas mexeram nesses diretórios durante a minha janela).
**Escritas na VPS:** apenas `derive_variant.py` (×2), `activate_strategy_version.py` (×2) e os
quatro replays. Todo o resto foi lido em `repeatable read read only`; a passada de estresse é
`READ ONLY` por construção.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Derivar duas variantes de `mean_reversion v1` (`atr_pct_min` 0,008 e 0,010), dry-run e ativar | **OK.** `v2` (0,008) e `v3` (0,010). Digest conferido nos **quatro** dry-runs: `…mean_reversion_v1@sha256:a970c9d9…` — **exatamente o do brief, nunca parei.** Desvio: a espera entre as ativações foi de **9 min 35 s**, não 10 min (CONCERN 1) |
| 2 | Replay 31 d, ETH/SOL/XRP/DOGE, duas fatias por variante, uma coorte cada, `--explain-ledger` | **OK.** Quatro corridas, 0 erros, 11 904 barras por variante; recibos verbatim abaixo |
| 3 | Avaliação pareada contra a coorte do pai `replay:d0f77894…` | **OK, e o resultado é estruturalmente mais simples do que o da T3.40:** as duas variantes são **subconjuntos exatos** do pai (Δ pareado 0,0000 R, `mesmo_risco_inicial` e `mesmo_motivo` 100 %), então o estimando virou "população contra população" e recebeu bootstrap de blocos por dia |
| 4 | Estresse em cada coorte, veredito só se `n ≥ 30` | **OK — e o veredito é `amostra_insuficiente` nas duas** (17 de 30 e 11 de 30). Está dito |
| 5 | `EXP-0014` e `EXP-0015` com portão C1–C8, avaliação REPLAY e carimbos de ativação | **OK** |

**Resposta curta:** o teto de pedágio **funciona como aritmética e não se prova como vantagem**. O
custo médio cai de **0,2263 R → 0,1685 R (piso 0,008) → 0,1452 R (piso 0,010)**, e o cenário
`custos_x2` — que condenava o pai (−0,1213 R) — fica **positivo nas duas** (+0,1297 R e +0,3530 R).
Mas: (a) o IC 95 % por bloco de dia **contém zero** nas duas ([−0,109; +0,728] e [−0,007; +1,783]);
(b) o `n` é 17 e 11, abaixo do mínimo do estresse; (c) **o piso é um filtro de regime disfarçado** —
todas as 11 decisões da `v3` e 13 das 17 da `v2` estão em **2026-08-20…08-23**, quatro dias
consecutivos de trinta e um; (d) a `v3` corta **70,3 %** das decisões do pai e **estoura a régua do
EXP-0006**. Veredito das duas: **`inconclusivo`**, com recomendações diferentes (§VEREDITO).

## FILES

Criados (todos meus, todos fora de código de produção):

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0014-mean-reversion-teto-025.md` | EXP da V1 (`v2`, piso 0,008), portão C1–C8, protocolo congelado, avaliação REPLAY datada |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0015-mean-reversion-teto-020.md` | EXP da V2 (`v3`, piso 0,010), idem, com portão `REVISE` |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t342-sql\*.sql` | as consultas exatas desta nota (`q00`…`q24`) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t342-sql\pai-37.csv` | as 37 decisões do pai, dump para o bootstrap |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t342-blocos\blocos.py` | bootstrap de blocos por dia (NumPy) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t342-blocos\test_blocos.py` | séries sintéticas com valores esperados à mão |
| `C:\dev\project-hunter\.claude\state\notes-T3.42.md` | este arquivo |

---

## COMANDOS E SAÍDA REAL

### 0. Identidade do que rodou (antes de qualquer escrita)

```
$ ssh hunter-vps 'date -u; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Tue Sep  8 21:20:10 UTC 2026
hunter-web-1              hunter-web:d829546   Up 58 minutes (healthy)
hunter-strategy-worker-1  hunter-api:d829546   Up 58 minutes (healthy)
hunter-api-1              hunter-api:d829546   Up 58 minutes (healthy)
hunter-scanner-worker-1   hunter-api:1926e53   Up About an hour (healthy)
hunter-execution-worker-1 hunter-api:1926e53   Up About an hour (healthy)
hunter-market-worker-*    hunter-api:1926e53   Up About an hour (healthy)
hunter-postgres-1 / hunter-redis-1 / hunter-caddy-1  Up 40 hours (healthy)
```

Os dois scripts auditados são **byte a byte** os do commit publicado, nas três árvores:

```
$ ssh hunter-vps 'docker exec hunter-api-1 sha256sum /app/infra/scripts/derive_variant.py /app/infra/scripts/activate_strategy_version.py'
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0  /app/infra/scripts/derive_variant.py
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  /app/infra/scripts/activate_strategy_version.py

$ sha256sum infra/scripts/derive_variant.py infra/scripts/activate_strategy_version.py   # árvore local
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0  infra/scripts/derive_variant.py
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  infra/scripts/activate_strategy_version.py

$ git show d829546:infra/scripts/derive_variant.py | sha256sum            → 830a1f89…  (= imagem)
$ git show d829546:infra/scripts/activate_strategy_version.py | sha256sum → dc6abf95…  (= imagem)
```

Diferente da T3.40: desta vez **não há script modificado em voo**; imagem = árvore = commit.

Pai congelado (`q00-pai.sql`, `read_at = 2026-09-08T21:21:20,089152Z`):

```
| key            | version | status | purpose       | code_ref                                                          | params_format | activated_at                  |
| mean_reversion | v1      | active | research_only | hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d… |             1 | 2026-09-08 16:32:33.947955+00 |

{"fee_bps":"4","atr_bars":"97","stop_atr":"1","horizon_s":"14400","atr_period":"14",
 "target_atr":"1.5","atr_pct_max":"0.05","atr_pct_min":"0.006","target2_atr":"2.5",
 "zscore_bars":"20","slippage_bps":"5","atr_timeframe":"15m","trend_sma_bars":"20",
 "base_confidence":"0.5","trend_timeframe":"1h","zscore_depth_min":"1",
 "max_entry_delay_s":"120","assumed_spread_bps":"2"}
```

**`stop_atr = 1`** — é por isso que a conta do brief (0,25 R e 0,20 R) vale **sem** a correção que a
T3.40 teve de fazer na [[KB-0076]]: aqui a distância do stop **é** o ATR%.

### 1. Dry-runs de derivação (nada escrito)

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py mean_reversion v1 \
    --set atr_pct_min=0.008 --changelog "T3.42: teto de pedagio 0,25 R / 0,20 R (estresse T3.36)" --dry-run'
Tue Sep  8 21:22:48 UTC 2026
2026-09-08 21:22:51 [debug] shadow_version_bound_by_code_ref module=mean_reversion_v1 strategy=mean_reversion_v1
derivaria mean_reversion v2 de v1 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f:
atr_pct_min 0.006 -> 0.008 [params_hash ecd26dfc017a]
exit=0

$ ... --set atr_pct_min=0.010 ... --dry-run
Tue Sep  8 21:23:06 UTC 2026
derivaria mean_reversion v2 de v1 (…) em code_ref …a970c9d9…: atr_pct_min 0.006 -> 0.01 [params_hash a71311773886]
exit=0
```

Digest **exatamente** o do brief (`…a970c9d9…`) nos dois → sigo. Nenhuma recusa de faixa: a tabela
declara para `mean_reversion_v1` o par ordenado `atr_pct_min < atr_pct_max` (0,05) e ambos os pisos
passam — ao contrário do que aconteceu com a V2 da T3.40.

### 2. Derivação (escrita)

```
$ ... derive_variant.py mean_reversion v1 --set atr_pct_min=0.008 --changelog "T3.42: teto de pedagio 0,25 R / 0,20 R (estresse T3.36)"
Tue Sep  8 21:23:43 UTC 2026
derivada mean_reversion v2 de v1 (purpose research_only, draft, nada ativado) em code_ref …a970c9d9…:
atr_pct_min 0.006 -> 0.008 [params_hash ecd26dfc017a]
exit=0

$ ... --set atr_pct_min=0.010 ... (dry-run de novo, agora prevendo v3, e depois a escrita)
Tue Sep  8 21:23:54 UTC 2026
derivaria mean_reversion v3 de v1 … atr_pct_min 0.006 -> 0.01 [params_hash a71311773886]
derivada  mean_reversion v3 de v1 … atr_pct_min 0.006 -> 0.01 [params_hash a71311773886]
exit=0
Tue Sep  8 21:23:57 UTC 2026
```

### 3. Ativação (dry-run e escrita) — **os carimbos do `Registro de Tentativas`**

```
$ ... activate_strategy_version.py mean_reversion v2 --changelog "T3.42 V1: coorte de pesquisa do teto de pedagio 0,25 R (atr_pct_min 0,008) aberta" --dry-run
Tue Sep  8 21:24:08 UTC 2026
would activate mean_reversion v2 (purpose research_only) with code_ref …a970c9d9… (18 parameters)

$ ... (sem --dry-run)
Tue Sep  8 21:24:24 UTC 2026
activated mean_reversion v2 (purpose research_only) at 2026-09-08T21:24:26.306302+00:00 with code_ref …a970c9d9…

$ ... activate_strategy_version.py mean_reversion v3 --changelog "T3.42 V2: coorte de pesquisa do teto de pedagio 0,20 R (atr_pct_min 0,010) aberta" --dry-run
Tue Sep  8 21:33:49 UTC 2026
would activate mean_reversion v3 (purpose research_only) with code_ref …a970c9d9… (18 parameters)

$ ... (sem --dry-run)
Tue Sep  8 21:33:59 UTC 2026
activated mean_reversion v3 (purpose research_only) at 2026-09-08T21:34:01.491564+00:00 with code_ref …a970c9d9…
```

| variante | versão | `atr_pct_min` | teto prometido | derivada em (UTC) | **ativada em (UTC)** | ativada (Brasília) | `params_hash` |
|---|---|---|---|---|---|---|---|
| V1 teto 0,25 R | `mean_reversion v2` | 0,008 | ≤ 0,25 R | 2026-09-08 21:23:45,449938 | **2026-09-08 21:24:26,306302** | 18:24:26 | `ecd26dfc017a` |
| V2 teto 0,20 R | `mean_reversion v3` | 0,010 | ≤ 0,20 R | 2026-09-08 21:23:57,510664 | **2026-09-08 21:34:01,491564** | 18:34:01 | `a71311773886` |

**A ativação preservou o conteúdo próprio da linha derivada** (`q19-conteudo.sql`):

```
| version | status | purpose       | atr_pct_min | atr_pct_max | stop_atr | target_atr | resto_igual_ao_pai | schema_igual | code_ref_igual |
| v1      | active | research_only | 0.006       | 0.05        | 1        | 1.5        | t                  | t            | t              |
| v2      | active | research_only | 0.008       | 0.05        | 1        | 1.5        | t                  | t            | t              |
| v3      | active | research_only | 0.01        | 0.05        | 1        | 1.5        | t                  | t            | t              |
```

E a linhagem sobreviveu (`q19b-linhagem.sql`):

```
| v2 | variante de v1 | derived_from=v1 | overrides=atr_pct_min=0.008 | params_hash=ecd26dfc017a | T3.42 V1: coorte de pesquisa do teto de pedagio 0,25 R (atr_pct_min 0,008) aberta |
| v3 | variante de v1 | derived_from=v1 | overrides=atr_pct_min=0.01  | params_hash=a71311773886 | T3.42 V2: coorte de pesquisa do teto de pedagio 0,20 R (atr_pct_min 0,010) aberta |
```

Observação de comportamento (não é defeito, é bom saber): **o changelog da ativação substitui a
cauda legível do changelog da derivação**. A frase que o brief mandava usar na derivação
("T3.42: teto de pedágio 0,25 R / 0,20 R (estresse T3.36)") **não** ficou visível na linha final;
ela está em `system_events.strategy_version_variant_derived`. O prefixo analisável
(`derived_from`, `overrides`, `params_hash`) sobrevive nos dois casos.

### 4. Replay da V1 — `mean_reversion v2`, coorte `replay:d570b19a-f6e2-4312-86ed-9394b16ac81a`

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
    --version mean_reversion:v2 --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT \
    --workers 3 --cohort replay:d570b19a-f6e2-4312-86ed-9394b16ac81a --explain-ledger /tmp/replay-mr-v2-a.jsonl'
Tue Sep  8 21:24:58 UTC 2026
2026-09-08 21:26:31 [info] replay_explain_ledger  bars=5760 lines=5760 path=/tmp/replay-mr-v2-a.jsonl
{'run_id': 'd570b19a-…', 'version_label': 'mean_reversion v2',
 'window_from': '2026-08-08T00:00:00+00:00', 'window_to': '2026-08-23T00:00:00+00:00',
 'markets': ['binance:ETHUSDT','binance:SOLUSDT','binance:XRPUSDT','binance:DOGEUSDT'], 'market_count': 4,
 'bars_evaluated': 5760, 'signals': 12, 'outcomes_resolved': 12, 'outcomes_open': 0,
 'seconds': 90.184, 'bars_per_second': 63.87, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5290, 'triggered': 22}, 'errors': 0}
Tue Sep  8 21:26:31 UTC 2026

$ ... --from 2026-08-23 --to 2026-09-08 ... --explain-ledger /tmp/replay-mr-v2-b.jsonl
Tue Sep  8 21:26:41 UTC 2026
2026-09-08 21:28:24 [info] replay_explain_ledger  bars=6144 lines=6144 path=/tmp/replay-mr-v2-b.jsonl
{'bars_evaluated': 6144, 'signals': 17, 'outcomes_resolved': 17, 'outcomes_open': 0,
 'seconds': 101.358, 'bars_per_second': 60.62,
 'evaluations_by_state': {'not_triggered': 6136, 'triggered': 8}, 'errors': 0}
Tue Sep  8 21:28:25 UTC 2026
```

**Armadilha do denominador (a mesma da T3.33e e da T3.40):** `signals` conta a **coorte inteira**;
`12` e `17` **não somam** — a população final é **17**. `triggered` é por fatia: 22 + 8 = **30**.

### 5. Replay da V2 — `mean_reversion v3`, coorte `replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4`

```
$ ... --version mean_reversion:v3 --from 2026-08-08 --to 2026-08-23 ... --explain-ledger /tmp/replay-mr-v3-a.jsonl
Tue Sep  8 21:34:12 UTC 2026
2026-09-08 21:35:47 [info] replay_explain_ledger  bars=5760 lines=5760
{'version_label': 'mean_reversion v3', 'bars_evaluated': 5760, 'signals': 10, 'outcomes_resolved': 10,
 'outcomes_open': 0, 'seconds': 91.671, 'bars_per_second': 62.83, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5294, 'triggered': 18}, 'errors': 0}

$ ... --from 2026-08-23 --to 2026-09-08 ... --explain-ledger /tmp/replay-mr-v3-b.jsonl
Tue Sep  8 21:35:55 UTC 2026
2026-09-08 21:37:34 [info] replay_explain_ledger  bars=6144 lines=6144
{'bars_evaluated': 6144, 'signals': 11, 'outcomes_resolved': 11, 'outcomes_open': 0,
 'seconds': 96.923, 'bars_per_second': 63.39,
 'evaluations_by_state': {'not_triggered': 6143, 'triggered': 1}, 'errors': 0}
Tue Sep  8 21:37:35 UTC 2026
```

**Uma barra disparada em dezesseis dias** na segunda fatia. Este é o número mais informativo da
tarefa inteira, e volta no §VEREDITO.

### 6. Livros-razão (`--explain-ledger`, 11 904 linhas por variante, uma por barra)

```
V1 (v2): {"linhas": 11904,
          "estados": {"unavailable": 448, "not_triggered": 11426, "triggered": 30},
          "motivos": {"warmup": 140, "atr_warmup": 308, "no_uptrend_1h": 5288,
                      "not_stretched": 5424, "close_below_mid": 525,
                      "atr_out_of_range": 189, "signal": 30}}
         {"barras_com_atr_pct": 189, "min": 0.000629, "p50": 0.003172, "p90": 0.006738,
          "max": 0.007967, "abaixo_de_0.008": 189, "acima_de_0.05": 0}

V2 (v3): {"linhas": 11904,
          "estados": {"unavailable": 448, "not_triggered": 11437, "triggered": 19},
          "motivos": {"warmup": 140, "atr_warmup": 308, "no_uptrend_1h": 5288,
                      "not_stretched": 5424, "close_below_mid": 525,
                      "atr_out_of_range": 200, "signal": 19}}
         {"barras_com_atr_pct": 200, "min": 0.000629, "p50": 0.003426, "p90": 0.007408,
          "max": 0.009347, "abaixo_de_0.008": 189, "acima_de_0.05": 0}
```

Leitura: **o piso é a única trava que morde** — todas as recusas de ATR estão abaixo dele, nenhuma
acima do teto de 5 %; e as 200 − 189 = **11 recusas novas** da `v3` são exatamente a faixa
[0,008; 0,010). Os quatro porteiros anteriores (`no_uptrend_1h`, `not_stretched`, `close_below_mid`,
`atr_warmup`) têm **contagem idêntica** nas duas variantes, como tem de ser: nada além do piso mudou.

Primeira linha, verbatim (as duas variantes produzem a mesma):

```
{"bar_close":"2026-08-08T00:00:00+00:00","market":"binance:ETHUSDT","state":"unavailable",
 "reason":"warmup","detail":{"window_start":"2026-08-07T19:00:00Z","first_candle":"none"}}
```

### 7. Testes locais

Nenhum código de produção foi escrito. Rodei (a) o que governa a derivação e a ativação, (b) as
provas de não-antecipação que o meu contrato exige, e (c) os testes da ferramenta de bootstrap que
escrevi para esta nota, com séries sintéticas e valores calculados à mão.

```
$ uv run pytest packages/core/tests/unit/strategies/test_no_lookahead.py \
      packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
      packages/core/tests/unit/strategies/test_constraints.py \
      services/strategy-worker/tests/test_replay_lookahead.py -q -p no:cacheprovider
........................................................................ [ 48%]
........................................................................ [ 96%]
.....                                                                    [100%]
149 passed in 79.31s (0:01:19)

$ uv run pytest services/strategy-worker/tests/test_constraints_outside_freeze.py \
      services/strategy-worker/tests/test_derive_variant.py \
      services/strategy-worker/tests/test_activate_derived_guard.py \
      infra/scripts/tests/test_derive_variant_lineage.py -q -p no:cacheprovider
......................................................                   [100%]
54 passed in 66.20s (0:01:06)

$ uv run pytest .claude/state/exp-drafts/t342-blocos/test_blocos.py -q -p no:cacheprovider
......                                                                   [100%]
6 passed in 1.81s
```

Os seis testes novos são sintéticos com resultado conhecido antes de rodar: quatro dias × duas
decisões, +2 R acima do piso e −1 R abaixo ⇒ pai +0,5 R, variante +2,0 R, **Δ = +1,5 R exato** e IC
degenerado [+1,5; +1,5]; piso acima de tudo ⇒ variante vazia, `nan` (nunca 0,0) e zero reamostragens
válidas; bloco = dia (e não decisão) provado por uma série em que o piso não separa nada; e
determinismo pela semente.

---

## RECIBOS

### `replay_runs` (lidos do banco, `q16-recibos.sql`)

```
| coorte            | ver | de         | ate        | mkts | bars | sig | out | open | seg     | wk | lag | estados                                                      | err |
| replay:d0f77894-… | v1  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  17 |  17 |    0 |  93.110 |  3 |   2 | {"triggered":28,"unavailable":448,"not_triggered":5284}      |   0 |
| replay:d0f77894-… | v1  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  37 |  37 |    0 | 104.545 |  3 |   2 | {"triggered":36,"not_triggered":6108}                        |   0 |
| replay:d570b19a-… | v2  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  12 |  12 |    0 |  90.184 |  3 |   2 | {"triggered":22,"unavailable":448,"not_triggered":5290}      |   0 |
| replay:d570b19a-… | v2  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  17 |  17 |    0 | 101.358 |  3 |   2 | {"triggered":8,"not_triggered":6136}                         |   0 |
| replay:f4af4ffe-… | v3  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  10 |  10 |    0 |  91.671 |  3 |   2 | {"triggered":18,"unavailable":448,"not_triggered":5294}      |   0 |
| replay:f4af4ffe-… | v3  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  11 |  11 |    0 |  96.923 |  3 |   2 | {"triggered":1,"not_triggered":6143}                         |   0 |
```

Mesma janela, mesmos quatro mercados (`{binance:ETHUSDT,binance:SOLUSDT,binance:XRPUSDT,binance:DOGEUSDT}`),
mesmo `decision_lag_s = 2`, mesmos `workers = 3` do pai. **Zero erros nas seis corridas.**

### `system_events` da janela

```
| level | component                 | event                            | mensagem (truncada)                                                  | created_at                    |
| info  | activate_strategy_version | strategy_version_variant_derived | mean_reversion v2 derived from v1 (variante, purpose research_only)  | 2026-09-08 21:23:45.449938+00 |
| info  | activate_strategy_version | strategy_version_variant_derived | mean_reversion v3 derived from v1 (variante, purpose research_only)  | 2026-09-08 21:23:57.510664+00 |
| info  | activate_strategy_version | strategy_version_activated       | mean_reversion v2 (purpose research_only) activated with its already-copied code_ref | 2026-09-08 21:24:26.306302+00 |
| info  | replay_engine             | replay_run_finished              | replay mean_reversion v2 4 mercados 08-08…08-23: 5760 barras, 12     | 2026-09-08 21:26:31.568465+00 |
| info  | replay_engine             | replay_run_finished              | replay mean_reversion v2 4 mercados 08-23…09-08: 6144 barras, 17     | 2026-09-08 21:28:24.933752+00 |
| info  | activate_strategy_version | strategy_version_activated       | mean_reversion v3 (purpose research_only) activated with its already-copied code_ref | 2026-09-08 21:34:01.491564+00 |
| info  | replay_engine             | replay_run_finished              | replay mean_reversion v3 4 mercados 08-08…08-23: 5760 barras, 10     | 2026-09-08 21:35:47.101836+00 |
| info  | replay_engine             | replay_run_finished              | replay mean_reversion v3 4 mercados 08-23…09-08: 6144 barras, 11     | 2026-09-08 21:37:34.888819+00 |
```

Nenhum `strategy_version_variant_refused` — nenhuma das duas mudanças saiu da faixa declarada.

### Isolamento — a coorte é a cerca, e ela segurou (`q17-iso.sql`, 21:42:04Z)

```
| outbox_das_coortes | sinais_v2_total | sinais_v3_total | outbox_pendente_total |
|                  0 |              21 |              11 |                     0 |

| versao            | coorte                                      | sinais | primeiro                      |
| mean_reversion v2 | prospective                                 |      4 | 2026-09-08 21:30:14.999909+00 |
| mean_reversion v2 | replay:d570b19a-f6e2-4312-86ed-9394b16ac81a |     17 | 2026-08-20 19:30:02+00        |
| mean_reversion v3 | replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4 |     11 | 2026-08-20 19:30:02+00        |
```

Zero linhas de `shadow_outbox` para as duas coortes de replay (`persist.is_published_cohort` recusa
publicar replay). Os 4 sinais `prospective` da `v2` são o que "entrar no Lab" significa: o primeiro
saiu **5 min 49 s** depois da ativação. A `v3` ainda não tinha decidido nada em prospectiva às
21:42Z — coerente com um piso que só dispara em volatilidade alta.

### Capacidade — vigia (a linha `paper` continua primeiro, `outbox_lag_s` 0 o tempo todo)

| relógio (UTC) | marco | `evaluated_bars` | `last_iteration` | `outbox_lag_s` | `outbox_pending` | `errors` | `open_trackings` |
|---|---|---:|---|---:|---:|---:|---:|
| 21:23:33 | antes de ativar a `v2` | 8 910 | 21:23:04 | 0,0 | 0 | 0 | 42 |
| 21:28:35 | após os dois replays da `v2` | 10 125 | 21:28:03 | 0,0 | 0 | 0 | 42 |
| 21:31:53 | vigia | 11 203 | 21:31:46 | 0,0 | 0 | 0 | 60 |
| 21:33:51 | imediatamente antes de ativar a `v3` | 11 853 | 21:33:04 | 0,0 | 0 | 0 | 61 |
| 21:45:13 | 11 min após ativar a `v3` | 12 356 | 21:45:08 | 0,0 | 0 | 0 | 45 |
| 21:51:24 | fechamento | 14 445 | 21:51:03 | 0,0 | 0 | 0 | 52 |

`hunter-strategy-worker-1` e `hunter-api-1` `healthy` em todas as amostras; `/ready` da API **200**
às 21:45:13 e 21:51:24. Nenhum `errors` em nenhuma leitura.

Ordem do roster (`q18-roster.sql`, ordenação reproduzida de `roster.py:110-129` — chave, depois
`paper` antes de pesquisa, depois versão **numérica**):

```
1 mean_reversion v1 research_only
2 mean_reversion v2 research_only ecd26dfc017a
3 mean_reversion v3 research_only a71311773886
4 momentum       v3 paper           <- paper primeiro dentro da chave, como a A3 da T3.26c exige
5 momentum       v2 research_only
6 momentum       v4 research_only
7 momentum       v6 research_only 8cb1aa497956
8 session_orb    v1 research_only
9 volume_anomaly v2 research_only
```

Nove versões ativas — eram sete depois das aposentadorias da T3.41 (`breakout v1/v2` e
`momentum v5` saíram). Carga nova declarada: CONCERN 5.

---

## TABELAS PAREADAS

`read_at` das leituras: **21:37:59Z** (populações), **21:30:17Z** e **21:38:28Z** (grupos pareados
da V1 e da V2), **21:40:30Z** (motivos de saída), **21:40:39Z** (blocos), **21:45:31Z** (cobertura),
**21:41:37Z** (conteúdo e linhagem), **21:42:04Z** (isolamento). Cada consulta numa transação
`repeatable read read only` própria; o SQL literal está em `.claude/state/exp-drafts/t342-sql/`.

### Populações (o pai e as duas variantes, mesma janela e mesmos quatro mercados)

```
+-------------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
|      versao       |     coorte      | decisoes | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | pf_bruto | dias | atr_pct_min_obs | atr_pct_max_obs |
+-------------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
| mean_reversion v1 | replay:d0f77894 |       37 |         37 |      0.3210 |  0.2263 |        0.0938 |   3.47 |       40.5 |     1.1856 |   1.7999 |   11 |         0.00603 |         0.03565 |
| mean_reversion v2 | replay:d570b19a |       17 |         17 |      0.4686 |  0.1685 |        0.2998 |   5.10 |       41.2 |     1.7483 |   2.4100 |    7 |         0.00815 |         0.03565 |
| mean_reversion v3 | replay:f4af4ffe |       11 |         11 |      0.6587 |  0.1452 |        0.5131 |   5.64 |       36.4 |     2.6919 |   3.5380 |    4 |         0.01044 |         0.03565 |
+-------------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
```

**O eixo do custo se comporta como prometido, e é a única coisa aqui que se comporta:**
0,2263 → 0,1685 → 0,1452 R.

### A população do pai partida pelos dois pisos (`q11-pareado.sql`)

```
+-----------------------+----+-------------+---------+---------------+--------+------------------+------------------+
|         faixa         | n  | exp_bruta_r | custo_r | exp_liquida_r | soma_r | saidas_horizonte | soma_r_horizonte |
+-----------------------+----+-------------+---------+---------------+--------+------------------+------------------+
| pai ABAIXO de 0,008   | 20 |      0.1956 |  0.2753 |       -0.0814 |  -1.63 |                2 |             0.27 |
| pai em [0,008; 0,010) |  6 |      0.1201 |  0.2113 |       -0.0912 |  -0.55 |                0 |                  |
| pai ACIMA de 0,010    | 11 |      0.6587 |  0.1452 |        0.5131 |   5.64 |                4 |             2.79 |
+-----------------------+----+-------------+---------+---------------+--------+------------------+------------------+
```

**Toda a diferença entre as duas variantes são estas 6 decisões e 0,55 R.**

### V1 — os quatro grupos pareados por `(mercado, barra)`

```
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+
|      variante       |           grupo            | n  | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | dias |
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+
| V1 (v2, piso 0,008) | pai SEM par na variante    | 20 |         20 |      0.1956 |  0.2753 |       -0.0814 |  -1.63 |       40.0 |     0.8630 |    8 |
| V1 (v2, piso 0,008) | pai pareado com a variante | 17 |         17 |      0.4686 |  0.1685 |        0.2998 |   5.10 |       41.2 |     1.7483 |    7 |
| V1 (v2, piso 0,008) | variante pareada com o pai | 17 |         17 |      0.4686 |  0.1685 |        0.2998 |   5.10 |       41.2 |     1.7483 |    7 |
| V1 (v2, piso 0,008) | variante SEM par no pai    |  0 |          0 |           — |       — |             — |      — |          — |          — |    — |
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+

| variante            | pares | delta_liq_medio_r | delta_liq_soma_r | delta_bruto_medio_r | mesmo_risco_inicial | mesmo_motivo | dias |
| V1 (v2, piso 0,008) |    17 |            0.0000 |             0.00 |              0.0000 |               17/17 |        17/17 |    7 |
```

### V2 — os quatro grupos pareados

```
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+
|      variante       |           grupo            | n  | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | dias |
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+
| V2 (v3, piso 0,010) | pai SEM par na variante    | 26 |         26 |      0.1782 |  0.2606 |       -0.0836 |  -2.17 |       42.3 |     0.8584 |    9 |
| V2 (v3, piso 0,010) | pai pareado com a variante | 11 |         11 |      0.6587 |  0.1452 |        0.5131 |   5.64 |       36.4 |     2.6919 |    4 |
| V2 (v3, piso 0,010) | variante pareada com o pai | 11 |         11 |      0.6587 |  0.1452 |        0.5131 |   5.64 |       36.4 |     2.6919 |    4 |
| V2 (v3, piso 0,010) | variante SEM par no pai    |  0 |          0 |           — |       — |             — |      — |          — |          — |    — |
+---------------------+----------------------------+----+------------+-------------+---------+---------------+--------+------------+------------+------+

| variante            | pares | delta_liq_medio_r | delta_liq_soma_r | delta_bruto_medio_r | mesmo_risco_inicial | mesmo_motivo | dias |
| V2 (v3, piso 0,010) |    11 |            0.0000 |             0.00 |              0.0000 |               11/11 |        11/11 |    4 |
```

**Diferença estrutural em relação à T3.40 (e a razão de o método mudar):** lá a variante tinha
193 pares com Δ ≠ 0 (o mesmo trade com outro alvo) e 3 decisões sem par. **Aqui o Δ pareado é
exatamente zero e não há decisão sem par**: o piso não altera nenhuma operação, ele **apaga**
operações. Um filtro puro, sem efeito de slot livre — o que é a melhor notícia metodológica do dia e
também o que torna o "Δ pareado" inútil como estimando. Por isso o contraste foi refeito por
população, com bloco de dia:

### O estimando de verdade — bootstrap de blocos por dia

`t342-blocos/blocos.py`, 11 dias, 10 000 reamostragens de dias com reposição, semente 20260908,
Δ = expectancy(variante) − expectancy(pai) medida **na mesma reamostragem**:

```
$ uv run python .claude/state/exp-drafts/t342-blocos/blocos.py .claude/state/exp-drafts/t342-sql/pai-37.csv
piso 0.008 | dias 11 | n_pai 37 | n_var 17 | exp_pai +0.0938 | exp_var +0.2998 | delta +0.2060 | IC95 [-0.1089; +0.7276] | reamostragens 9999
piso 0.010 | dias 11 | n_pai 37 | n_var 11 | exp_pai +0.0938 | exp_var +0.5131 | delta +0.4193 | IC95 [-0.0072; +1.7829] | reamostragens 9925
```

(`exp_pai` e `exp_var` batem casa a casa com o SQL — é a conferência cruzada do dump.)
**Os dois intervalos contêm zero.** E note as reamostragens perdidas: em **75 de 10 000**
reamostragens de dias a `v3` **não decide nada** — não há Δ a medir. Isso não é detalhe numérico, é a
descrição honesta de uma versão que depende de quatro dias existirem.

### Média das médias diárias por coorte (`q13-blocos.sql`)

```
+----------+------------+------------------+--------+-------------+----------------+----------------+------------------+------------------+
|  coorte  | blocos_dia | media_das_medias | desvio | erro_padrao | dias_positivos | dias_negativos | min_decisoes_dia | max_decisoes_dia |
+----------+------------+------------------+--------+-------------+----------------+----------------+------------------+------------------+
| d0f77894 |         11 |          -0.0601 | 0.9672 |      0.2916 |              7 |              4 |                1 |                6 |
| d570b19a |          7 |           0.3387 | 1.1318 |      0.4278 |              5 |              2 |                1 |                6 |
| f4af4ffe |          4 |           0.9303 | 0.6790 |      0.3395 |              4 |              0 |                1 |                6 |
+----------+------------+------------------+--------+-------------+----------------+----------------+------------------+------------------+
```

### **A tabela que decide a tarefa** — R por dia nas três coortes (`q24-dias.sql`)

```
+------------+-------+-------+------+-------+------+------+
|    dia     | n_pai | r_pai | n_v1 | r_v1  | n_v2 | r_v2 |
+------------+-------+-------+------+-------+------+------+
| 2026-08-20 |     5 |  4.98 |    1 |  1.68 |    1 | 1.68 |
| 2026-08-21 |     6 |  6.40 |    5 |  4.27 |    3 | 2.20 |
| 2026-08-22 |     6 |  0.55 |    6 |  0.55 |    6 | 0.55 |
| 2026-08-23 |     1 |  1.22 |    1 |  1.22 |    1 | 1.22 |
| 2026-08-24 |     3 |  0.26 |    0 |       |    0 |      |
| 2026-08-25 |     4 | -4.62 |    2 | -2.29 |    0 |      |
| 2026-08-27 |     3 |  1.02 |    1 |  0.86 |    0 |      |
| 2026-08-28 |     2 | -2.43 |    0 |       |    0 |      |
| 2026-09-03 |     3 | -3.49 |    0 |       |    0 |      |
| 2026-09-05 |     1 | -1.18 |    1 | -1.18 |    0 |      |
| 2026-09-06 |     3 |  0.78 |    0 |       |    0 |      |
+------------+-------+-------+------+-------+------+------+
```

- A **`v3` inteira cabe em 2026-08-20…08-23**: 11 decisões, +5,64 R, e **nada** nos 16 dias
  seguintes. A janela é de 31 dias; a versão existe em 4.
- A **`v2`** tem 13 decisões e +7,72 R nesses mesmos quatro dias e −2,61 R nas quatro decisões que
  sobram nos 16 dias restantes.
- O pai perde **−9,68 R** depois de 08-23. As variantes "melhoram" porque **saem do mercado**
  exatamente na metade que o estresse da T3.36 já tinha marcado como negativa
  (`2a_metade_apos_2026-08-28: −0,5568 R`).

Isto é a mesma coisa que o item 6 do EXP-0009 previa e é o que a [[KB-0010]] chama de decidir pela
janela que inventou a hipótese: **um piso de ATR% não é neutro no tempo**, ele seleciona regime.

### Motivos de saída, população inteira de cada coorte (`q12-motivos.sql`)

```
+----------+---------+----+------+-------------+------------+---------------+
|  coorte  | motivo  | n  | pct  | r_liq_medio | r_liq_soma | r_bruto_medio |
+----------+---------+----+------+-------------+------------+---------------+
| d0f77894 | stop    | 16 | 43.2 |     -1.1682 |     -18.69 |       -0.9281 |
| d0f77894 | target  | 15 | 40.5 |      1.2732 |      19.10 |        1.5199 |
| d0f77894 | expired |  6 | 16.2 |      0.5104 |       3.06 |        0.6548 |
| d570b19a | target  |  7 | 41.2 |      1.3028 |       9.12 |        1.4883 |
| d570b19a | stop    |  6 | 35.3 |     -1.1352 |      -6.81 |       -0.9417 |
| d570b19a | expired |  4 | 23.5 |      0.6970 |       2.79 |        0.7995 |
| f4af4ffe | expired |  4 | 36.4 |      0.6970 |       2.79 |        0.7995 |
| f4af4ffe | target  |  4 | 36.4 |      1.5479 |       6.19 |        1.7257 |
| f4af4ffe | stop    |  3 | 27.3 |     -1.1119 |      -3.34 |       -0.9516 |
+----------+---------+----+------+-------------+------------+---------------+
```

Nenhuma `invalidated` em nenhuma coorte — a `mean_reversion_v1` não invalidou uma única vez em
31 dias.

### **A pergunta do brief: o ganho do pai mora em 6 saídas por horizonte — ele sobrevive ao filtro?**

`q14-horizonte.sql`, as seis, uma a uma:

```
+----------+------------------------+---------+--------+--------------------------+
|  symbol  |         barra          | atr_pct | r_liq  |         destino          |
+----------+------------------------+---------+--------+--------------------------+
| DOGEUSDT | 2026-08-20 03:45:00+00 | 0.00633 | 0.1094 | cortada pelos dois pisos |
| DOGEUSDT | 2026-08-22 05:30:00+00 | 0.03565 | 0.9225 | sobrevive aos dois pisos |
| SOLUSDT  | 2026-08-22 10:30:00+00 | 0.01462 | 0.8969 | sobrevive aos dois pisos |
| XRPUSDT  | 2026-08-22 10:30:00+00 | 0.02829 | 0.1229 | sobrevive aos dois pisos |
| DOGEUSDT | 2026-08-22 10:30:00+00 | 0.02098 | 0.8457 | sobrevive aos dois pisos |
| ETHUSDT  | 2026-08-24 18:00:00+00 | 0.00746 | 0.1650 | cortada pelos dois pisos |
+----------+------------------------+---------+--------+--------------------------+
```

**Resposta: sim, e é a parte pesada que sobrevive.** Das 6 saídas por horizonte do pai (+3,06 R de um
total de +3,47 R — ou seja, **88 % do lucro do pai está em 16 % das operações**), **4 passam pelos
dois pisos** e carregam **+2,79 R**; as 2 cortadas valiam +0,27 R somadas. Consequência a dizer em
voz alta: essas 4 saídas por horizonte respondem por **55 % da soma da `v2`** (+2,79 de +5,10) e
**49 % da soma da `v3`** (+2,79 de +5,64) — e **as quatro acontecem no mesmo dia, 2026-08-22**, três
delas na **mesma barra** (10:30, SOL/XRP/DOGE), isto é, no mesmo choque de mercado. O ganho das duas
variantes não está diversificado por construção: é meia dúzia de operações correlacionadas.

### A identidade do pedágio, conferida decisão a decisão (`q21-identidade.sql`, `q22-risco.sql`)

```
+----------+----+--------------------+------------------+----------------------+--------------------+---------------------+
|  coorte  | n  | custo_medio_medido | custo_max_medido | custo_medio_previsto | custo_max_previsto | maior_erro_absoluto |
+----------+----+--------------------+------------------+----------------------+--------------------+---------------------+
| d0f77894 | 37 |             0.2263 |           0.4435 |               0.2338 |             0.3315 |              0.1470 |
| d570b19a | 17 |             0.1685 |           0.2690 |               0.1660 |             0.2453 |              0.0787 |
| f4af4ffe | 11 |             0.1452 |           0.2690 |               0.1299 |             0.1916 |              0.0787 |
+----------+----+--------------------+------------------+----------------------+--------------------+---------------------+

razao = risco_inicial / (ATR% x preco_de_entrada), que a identidade supõe = stop_atr = 1:
| d0f77894 | min 0.6063 | media 1.0431 | max 1.4163 |
| d570b19a | min 0.6063 | media 0.9766 | max 1.2498 |
| f4af4ffe | min 0.6063 | media 0.9039 | max 1.0775 |
```

**A identidade acerta a média e erra o caso.** O teto prometido (0,25 R e 0,20 R) é **médio**: a pior
decisão das duas coortes pagou **0,269 R**, porque o risco inicial efetivo não é exatamente 1 ATR —
ele varia entre **0,61 e 1,42 ATR** (o stop é o mínimo entre o nível estrutural e o de ATR, e o preço
de entrada anda entre a decisão e a abertura da barra seguinte). Quem citar "teto de 0,25 R" como
garantia estará citando errado; o número honesto é "média 0,17 R, pior caso 0,27 R". CONCERN 3.

### Estresse (`replay.stress`, `READ ONLY`, sem escrita no Lab)

**V1 — `replay:d570b19a…`, `as_of 2026-09-08T21:30:42,486413Z`, 17 entradas congeladas, 4 mercados**

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base` | reprecificacao | 17 | 0.2998 | 1.7483 | — | — |
| `custos_x2` | reprecificacao | 17 | **0.1297** | 1.2932 | -0.1701 | [-0.2197, -0.1292] |
| `stop_x0.75` | reprecificacao | 17 | 0.3645 | 1.7502 | 0.0647 | [-0.0850, +0.2602] |
| `stop_x1.25` | reprecificacao | 17 | 0.3284 | 2.1711 | 0.0286 | [-0.1896, +0.4465] |
| `alvo_x0.75` | reprecificacao | 17 | 0.2398 | 1.5985 | -0.0600 | [-0.2934, +0.1498] |
| `alvo_x1.25` | reprecificacao | 17 | 0.3658 | 1.9129 | 0.0660 | [-0.1016, +0.2082] |
| `entrada_mais_1_barra` | reprecificacao | 17 | 0.2745 | 1.6740 | -0.0253 | [-0.1660, +0.0998] |
| `sem_binance:DOGEUSDT` | recorte | 13 | 0.2237 | 1.5168 | — | — |
| `sem_binance:ETHUSDT` | recorte | 15 | 0.3520 | 1.9389 | — | — |
| `sem_binance:SOLUSDT` | recorte | 13 | 0.4173 | 2.2002 | — | — |
| `sem_binance:XRPUSDT` | recorte | 10 | 0.1677 | 1.3597 | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 16 | 0.3926 | 2.1164 | — | — |
| `2a_metade_apos_2026-08-28` | recorte | **1** | -1.1846 | 0.0000 | — | — |

**Veredito da passada: `amostra_insuficiente` — 17 desfechos avaliáveis de 30.**

**V2 — `replay:f4af4ffe…`, `as_of 2026-09-08T21:40:18,593179Z`, 11 entradas congeladas, 4 mercados**

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base` | reprecificacao | 11 | 0.5131 | 2.6919 | — | — |
| `custos_x2` | reprecificacao | 11 | **0.3530** | 2.0686 | -0.1601 | [-0.2225, -0.1209] |
| `stop_x0.75` | reprecificacao | 11 | 0.7749 | 3.4717 | 0.2618 | **[+0.1635, +0.4830]** |
| `stop_x1.25` | reprecificacao | 11 | 0.4226 | 2.8332 | -0.0905 | [-0.2898, +0.0176] |
| `alvo_x0.75` | reprecificacao | 11 | 0.4962 | 2.6362 | -0.0169 | [-0.3891, +0.2113] |
| `alvo_x1.25` | reprecificacao | 11 | 0.6650 | 3.1929 | 0.1519 | **[+0.0232, +0.3891]** |
| `entrada_mais_1_barra` | reprecificacao | 11 | 0.3869 | 2.2284 | -0.1262 | **[-0.3072, -0.0397]** |
| `sem_binance:DOGEUSDT` | recorte | 8 | 0.2838 | 1.6806 | — | — |
| `sem_binance:ETHUSDT` | recorte | 10 | 0.6832 | 4.1809 | — | — |
| `sem_binance:SOLUSDT` | recorte | 10 | 0.4747 | 2.4230 | — | — |
| `sem_binance:XRPUSDT` | recorte | 5 | 0.6165 | 3.5946 | — | — |
| `1a_metade_ate_2026-08-21` | recorte | 4 | 0.9678 | 4.5263 | — | — |
| `2a_metade_apos_2026-08-21` | recorte | 7 | 0.2532 | 1.7920 | — | — |

**Veredito da passada: `amostra_insuficiente` — 11 desfechos avaliáveis de 30.**

O que **não** posso deixar de dizer, mesmo com o veredito recusado: na `v3`, **três** cenários têm IC
do Δ excluindo zero (`stop_x0.75`, `alvo_x1.25`, `entrada_mais_1_barra`). Com n = 11 isso não é
robustez, é o contrário — a população depende do stop apertado, do alvo largo e de entrar na barra
exata. Na `v1` nenhum cenário de parâmetro se distingue de zero, que é o comportamento saudável.

**A boa notícia, e é real:** o cenário que condenava o pai (`custos_x2`: −0,1213 R, IC do Δ
inteiramente negativo, veredito **frágil a custos**) fica **positivo nas duas variantes** (+0,1297 R
e +0,3530 R, PF 1,29 e 2,07). O eixo que o brief mandou testar responde.

### Cobertura (o quadro do template, `q20-cobertura.sql`)

```
| coorte   | emitidos | pendentes | entradas | nao_entradas | ativos | alvo | stop | expirado | invalidado | censurados | funding_indisponivel | avaliaveis | dias |
| d0f77894 |       37 |         0 |       37 |            0 |      0 |   15 |   16 |        6 |          0 |          0 |                    0 |         37 |   11 |
| d570b19a |       17 |         0 |       17 |            0 |      0 |    7 |    6 |        4 |          0 |          0 |                    0 |         17 |    7 |
| f4af4ffe |       11 |         0 |       11 |            0 |      0 |    4 |    3 |        4 |          0 |          0 |                    0 |         11 |    4 |

| coorte   | taxa_alvo_entre_toques | taxa_lucro_liquido_pct |
| d0f77894 |                   48.4 |                   56.8 |
| d570b19a |                   53.8 |                   64.7 |
| f4af4ffe |                   57.1 |                   72.7 |
```

Cobertura perfeita nas três: **0 pendentes, 0 não-entradas, 0 ativos, 0 censurados, 0 sem funding**;
toda decisão entrou e todo desfecho é avaliável.

### C5 — as decisões que uma linha `paper` recusaria (`q23-c5.sql`)

```
| coorte   | n  | acima_do_teto_paper (ATR% > 3 %) | abaixo_do_piso_paper (< 0,3 %) | soma_r_acima_do_teto |
| d0f77894 | 37 |                                2 |                              0 |                -0.13 |
| d570b19a | 17 |                                2 |                              0 |                -0.13 |
| f4af4ffe | 11 |                                2 |                              0 |                -0.13 |
```

Com `stop_atr = 1`, o piso 0,008 põe o stop a ≥ 0,8 % e o 0,010 a ≥ 1,0 % — **dentro** da banda
`[0,003; 0,03]` do `paper_v1` (`packages/risk-core/hunter_risk/limits.py:151-152`). O problema de C5
que matou o [[EXP-0012]] **não** se repete aqui. O que existe é o outro lado: 2 decisões com ATR%
acima de 3 % seriam recusadas pelo sizing — 12 % da `v2` e **18 %** da `v3`, valendo −0,13 R.

---

## VEREDITO POR VARIANTE

### V1 — `mean_reversion v2`, teto 0,25 R (`atr_pct_min = 0,008`)

**Veredito formal: `inconclusivo`. Recomendação: `manter em pesquisa` — 30 dias prospectivos, não
promover.**

Critérios de descarte, medidos:

| critério | valor | dispara? |
|---|---|---|
| corte > 70 % das decisões (EXP-0006/[[KB-0008]]) | **54,1 %** (20 de 37) | **não** |
| `PF_net ≤ 0,80` | **1,7483** | não |
| `expectancy_net ≤ a do pai` | **+0,2998 R** vs +0,0938 R | não |
| estresse `frágil a custos` | `custos_x2` **+0,1297 R**, PF 1,29 | **não — a fragilidade do pai sumiu** |

O que sustenta: o mecanismo é aritmético e verificável (custo médio 0,2263 → 0,1685 R), o contraste é
o mais limpo possível (subconjunto exato, Δ pareado zero, risco idêntico), o corte fica sob a régua
do EXP-0006 e o cenário que reprovava o pai passa.

O que **não** sustenta, e pesa mais: o IC 95 % por bloco de dia **[−0,109; +0,728] contém zero**;
`n = 17` é metade do mínimo do estresse; 7 dias com decisão em 31; **13 das 17 decisões e +7,72 R
estão em quatro dias consecutivos**, e nos 16 dias seguintes a versão faz 4 operações e perde
2,61 R; **55 % da soma vem de 4 saídas por horizonte do mesmo dia**, três na mesma barra. E, acima de
tudo: **é a mesma janela que gerou a hipótese** — o piso foi escolhido depois de ver esta série.

### V2 — `mean_reversion v3`, teto 0,20 R (`atr_pct_min = 0,010`)

**Veredito formal: `inconclusivo`. Recomendação: `manter em pesquisa com ressalva forte` — e a
régua do EXP-0006 diz que, se um dia isto for promovido, será como estratégia nova, não como
`mean_reversion` com menos custo.**

| critério | valor | dispara? |
|---|---|---|
| corte > 70 % das decisões (EXP-0006/[[KB-0008]]) | **70,3 %** (26 de 37) | **SIM, por 0,3 ponto** |
| `PF_net ≤ 0,80` | **2,6919** | não |
| `expectancy_net ≤ a do pai` | **+0,5131 R** vs +0,0938 R | não |
| estresse `frágil a custos` | `custos_x2` **+0,3530 R**, PF 2,07 | não |

Os números de superfície são os melhores das três populações **e não valem como evidência**:

1. **11 operações em 4 dias consecutivos**, todos entre 08-20 e 08-23; **uma barra disparada em
   dezesseis dias** na segunda fatia. Isto não é "a estratégia com menos custo", é uma aposta num
   episódio.
2. **A diferença real contra a irmã são 6 operações e 0,55 R** — muito abaixo do ruído da janela.
   Escolher 0,010 em vez de 0,008 com base neste replay é decidir por ruído ([[KB-0010]]).
3. O IC por bloco **[−0,0072; +1,7829] contém zero**, e em 75 de 10 000 reamostragens de dias a
   versão simplesmente não existe.
4. Três cenários de estresse com IC excluindo zero (stop, alvo e **atraso de entrada**) — com n = 11,
   sinal de dependência de detalhe de execução.
5. A régua do EXP-0006 é uma regra editorial pré-existente e ela **dispara**. Respeitá-la significa
   dizer: isto precisa do seu próprio desenho, do seu próprio portão e da sua própria coleta.

**O que muda os dois vereditos:** as coortes `prospective` abertas em 21:24:26Z e 21:34:01Z,
reavaliadas em **2026-10-08** contra a `v1` na **mesma** janela e sobre o universo inteiro (200
mercados, onde a frequência de ATR% alto é outra). Se o Δ prospectivo for negativo nas duas, a
recomendação vira `descartar` e o eixo do teto de pedágio fica esgotado nesta estratégia — e a
conclusão do dia volta a ser a da [[KB-0076]] item 10: **falta vantagem na entrada, e nenhum filtro
de custo a fabrica**.

---

## CONCERNS

1. **Esperei 9 min 35 s entre as ativações, não 10 min.** A `v2` foi ativada às 21:24:26,306302Z e a
   `v3` às 21:34:01,491564Z. Erro meu de contagem, declarado em vez de arredondado: a vigia cobriu
   **quatro** amostras nesse intervalo (21:23:33, 21:28:35, 21:31:53, 21:33:51), todas com
   `outbox_lag_s = 0,0`, `outbox_pending = 0`, `errors = 0` e container `healthy`, e mais duas depois
   (21:45:13 e 21:51:24, com `/ready` 200). O propósito da vigia foi cumprido; a letra do brief, por
   25 segundos, não.
2. **A régua do EXP-0006 dispara para a `v3` por 0,3 ponto percentual (70,3 % contra 70 %).** Não
   arredondei para "≈ 70 %": a regra é uma linha e ela foi cruzada. O que fiz com isso está no
   veredito e no portão C3 do EXP-0015 (`REJECT`), não numa nota de rodapé.
3. **O "teto de pedágio" é uma média, não uma garantia — e o brief o chama de teto.** A identidade
   `custo_R = 0,0020 / (stop_atr × ATR%)` supõe risco inicial = `stop_atr × ATR% × preço`; medido, o
   risco efetivo vai de **0,61 a 1,42 ATR**. Resultado: prometido ≤ 0,25 R / ≤ 0,20 R, **medido**
   0,1685 R / 0,1452 R de média e **0,269 R no pior caso das duas**. A ordenação das variantes e a
   direção do efeito não mudam; a palavra "teto" muda.
4. **O ganho das duas variantes está concentrado num dia e numa barra.** 4 das saídas por horizonte
   (+2,79 R) são de 2026-08-22, três delas às 10:30 em SOL, XRP e DOGE — o mesmo choque, contado
   três vezes. Qualquer intervalo que trate essas três como independentes está estreito; o bootstrap
   por dia trata (é por isso que ele é por dia), mas nem ele corrige o fato de a evidência ser um
   punhado de eventos correlacionados.
5. **Oito versões ativas viraram nove.** `mean_reversion` tem agora três (`v1`, `v2`, `v3`). A vigia
   não mostrou degradação (`outbox_lag_s` 0,0 em seis amostras, `errors` 0, `/ready` 200), mas cada
   versão custa uma avaliação por barra por mercado, e continua não existindo via auditada para
   aposentar uma versão substituída por parâmetro (CONCERN aberto desde a T3.33f; a T3.41 aposentou
   três à mão).
6. **A árvore compartilhada mudou embaixo de mim, em `packages/**` e `services/**`, durante a minha
   janela — e não fui eu.** `git status` acusa modificações de outras tarefas em voo (T3.43
   regime-producer, T3.34b trendline-breakout) com mtime **21:36–21:49Z**, dentro do meu trabalho.
   Duas delas são em arquivos que eu leio: `constraints_table.py` e `registry.py`. Conferi o diff
   contra `d829546`: a mudança é **puramente aditiva** (`trendline_breakout_v1`), `mean_reversion_v1`
   não foi tocada, e **a VPS roda a imagem, não a árvore** — nenhuma derivação, ativação ou replay
   meu passou por esse código. O que **fica contaminado** é a minha corrida local de `pytest`
   (21:46–21:49Z), que rodou sobre uma árvore com trabalho alheio em voo; passou (149 e 54), mas não
   é uma árvore limpa e o revisor precisa saber.
7. **`signals` no recibo do replay conta a coorte, não a fatia.** 12 + 17 não são 29: a população é
   17. Mesma armadilha da T3.33e e da T3.40; anotada aqui de novo porque continua sem correção no
   recibo.
8. **O replay herda o universo de hoje**, não o de agosto (`PIPELINE` §6c). Vale igualmente para as
   três coortes — o pareamento não fica enviesado —, mas nenhuma das três descreve o universo real da
   janela.
9. **A hipótese de custo continua declarada, não medida** (2 bps de spread + 5 bps de slippage +
   4 bps de taxa por lado = 20 bps ida e volta). Todo o eixo desta tarefa escala linearmente com ela.
   Medir contra o livro real é a verificação que a [[KB-0076]] já pedia e que ninguém fez.
10. **O changelog da derivação não sobrevive na linha.** A frase que o brief mandou usar
    ("T3.42: teto de pedágio 0,25 R / 0,20 R (estresse T3.36)") foi substituída pela da ativação na
    coluna `changelog`; ela existe em `system_events`. Além disso escrevi as duas **sem acento**
    ("pedagio") de propósito, para não arriscar corrupção de UTF-8 no caminho Windows → ssh → docker
    — decisão minha, declarada.
11. **`EXP-0014` e `EXP-0015` eram as vagas livres às 2026-09-08T21:45Z.** Estão em
    `.claude/state/exp-drafts/`, **não** em `obsidian/**` (fora do meu escopo). Conferido às 21:55Z:
    outra tarefa já rascunhou um `EXP-0017-sweep-reclaim.md`, então os números 0014, 0015 e 0016
    seguem livres — mas se alguém tomar 0014/0015 antes da Sexta-feira arquivar, renumerar.
11b. **O `main` andou durante a tarefa.** O brief nasceu em `7b0edeb` e o `HEAD` da árvore estava em
    `3bd8f3d` quando fechei (seis commits de outras tarefas: T3.44, T3.18d, briefs). **Nenhum é meu,
    nada meu foi commitado** — meus arquivos continuam todos `??` em `git status`. A VPS não foi
    redeployada: `hunter-api:d829546` do início ao fim.
12. **`blocos.py` é ferramenta de nota, não produção.** Bootstrap percentil simples (sem BCa), sobre
    11 dias — com tão poucos blocos o intervalo é grosseiro nas caudas. A leitura que faço dele
    ("contém zero") é robusta a isso; um "IC = [x; y]" citado fora de contexto não seria.

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** os recibos, o CONCERN 1 (25 s a menos de vigia), o CONCERN 3 (o "teto" que é
  média) e o CONCERN 6 (árvore alheia em voo durante meus testes). Nenhum é aritmética; os três são
  julgamento.
- **risk-engine-guardian:** `v2` e `v3` são `research_only`, sem linha em `agents`, coortes de replay
  com `shadow_outbox` zerada. Ponto de atenção novo e **positivo**: ao contrário da `momentum v5` do
  [[EXP-0012]], estas duas ficam **dentro** da banda de stop do `paper_v1`; o que sai da banda são as
  2 decisões com ATR% > 3 % (12 % e 18 % das populações).
- **Sexta-feira:** arquivar `EXP-0014` e `EXP-0015`, ligar do `Strategy Backlog` e do
  `Experiments Index`, e acrescentar duas linhas no `Registro de Tentativas` com os carimbos
  **2026-09-08T21:24:26,306302Z** (18:24:26 Brasília) e **2026-09-08T21:34:01,491564Z** (18:34:01
  Brasília). Multiplicidade sobe: **duas execuções novas, um contraste pré-registrado cada**.
- **Everton:** o número honesto do dia é que **cortar o pedágio funciona e não basta**. As duas
  irmãs viram a `mean_reversion` de perdedora-por-custo em ganhadora-no-papel, mas fazem isso
  **saindo do mercado 4 dias depois de 20 de agosto**. A decisão que este trabalho põe na mesa é
  **esperar 30 dias de prospectiva** antes de mexer em qualquer piso — e desconfiar de qualquer
  número desta janela, inclusive dos bonitos.
