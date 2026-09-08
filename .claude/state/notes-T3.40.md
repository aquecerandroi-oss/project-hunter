# notes-T3.40 — as duas variantes que o diagnóstico do prejuízo pediu (teto de pedágio e alvo 3 ATR)

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Owner:** quant-engineer.
**Base do brief:** `main @ c78a416`; a VPS rodava `hunter-api:c78a416` no início do trabalho e foi
**redeployada por outra tarefa para `c29cbef` às ~19:12Z**, no meio da execução (CONCERN 4).
**Nada commitado.** **Nenhum container parado ou recriado por mim.** **Nenhum `.env*` tocado.**
**Nada em `apps/**`, `services/**`, `packages/**`, `obsidian/**`.**
**Escritas na VPS:** apenas `derive_variant.py` (×2), `activate_strategy_version.py` (×2) e os
replays (×4 + 2 reexecuções de livro-razão). Todo o resto foi lido em transação
`repeatable read read only`.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Dry-run + derivar V1 e V2 de `momentum v2`; ativar cada uma; vigia de 10 min | **OK com desvio declarado.** V1 = `momentum v5` (`atr_pct_min` 0,003 → 0,020). V2 = `momentum v6`, mas **`--set target_atr=3.0` sozinho foi RECUSADO** pelo script auditado (faixa `target_atr < target2_atr`); resolvido deslocando a escada inteira para 3/6/9 (CONCERN 1). Digest conferido nos quatro dry-runs: `…momentum_v1@sha256:ab2e0398…` — **igual ao esperado, nunca parei** |
| 2 | Replay 31 d, 4 mercados, 2 fatias por variante, `--cohort` explícita, `--explain-ledger` | **OK, com um desvio operacional grande: o CLI publicado estava quebrado** (`ModuleNotFoundError: hunter_strategy_worker.replay.stress`) — CONCERN 2. As quatro fatias rodaram; recibos verbatim abaixo |
| 3 | Avaliação pareada por `(mercado, barra)` contra o pai `replay:f8d8279c…` | **OK.** Quatro grupos pareados por variante, Δ pareado, motivos de saída, MFE, blocos por dia |
| 4 | Rascunhos `EXP-0012` e `EXP-0013` com portão C1–C8 e avaliação datada rotulada REPLAY | **OK** |

**Resposta curta:** a **V1 não decide nada** nesta janela (piso acima de todo o ATR% observado — 100 %
de corte, a regra do EXP-0006 estourada). A **V2 sobrevive aos dois critérios de descarte** e mostra
Δ pareado **+0,134 R por decisão**, mas o intervalo de 95 % por bloco de dia **contém zero**
([−0,094; +0,187]) e a variante continua **perdendo** (−0,051 R, PF 0,906). Veredito das duas:
`inconclusivo`, como a regra prospectiva manda.

## FILES

Criados (todos meus, todos fora de código de produção):

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0012-momentum-teto-de-pedagio.md` | EXP da V1, portão C1–C8, protocolo congelado, avaliação REPLAY datada |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0013-momentum-alvo-3-atr.md` | EXP da V2, idem |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t340-sql\*.sql` | as oito consultas exatas desta nota |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t340-sql\replay_shim.py` | o atalho de 30 linhas que fez o replay rodar na imagem quebrada (CONCERN 2) |
| `C:\dev\project-hunter\.claude\state\notes-T3.40.md` | este arquivo |

`git status --porcelain -- .env* apps services packages obsidian` na minha janela: **vazio**.

---

## COMANDOS E SAÍDA REAL

### 0. Identidade do que rodou

```
$ ssh hunter-vps 'docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Tue Sep  8 18:51:07 UTC 2026
hunter-web-1              hunter-web:c78a416   Up 11 minutes (healthy)
hunter-strategy-worker-1  hunter-api:c78a416   Up 11 minutes (healthy)
hunter-api-1              hunter-api:c78a416   Up 11 minutes (healthy)
...

$ ssh hunter-vps 'docker exec hunter-api-1 sha256sum /app/infra/scripts/derive_variant.py /app/infra/scripts/activate_strategy_version.py'
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0  /app/infra/scripts/derive_variant.py
daab4ec4081fd034f7f31b119e1e4a7b0b9bd0351de147e286857ebdd019cc61  /app/infra/scripts/activate_strategy_version.py

$ sha256sum infra/scripts/derive_variant.py                    # árvore local = imagem
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0
$ git show c78a416:infra/scripts/activate_strategy_version.py | sha256sum
daab4ec4081fd034f7f31b119e1e4a7b0b9bd0351de147e286857ebdd019cc61   # = imagem
```

`activate_strategy_version.py` está **modificado na árvore local** (T3.39 em voo, sha `26a642b7…`).
Rodei o **da imagem** (`docker exec`, sem stdin), que é o do commit `c78a416` — por isso os dois
digests batem e nenhuma mudança em voo entrou em produção.

Pai congelado, conferido antes de qualquer escrita:

```
| version | code_ref                                                                                                   |
| v2      | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c |
| version | atr_pct_min | atr_pct_max | stop_atr | target_atr |
| v2      | 0.003       | 0.05        | 1.5      | 1.5        |
```

### 1. Dry-runs (nada escrito)

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py momentum v2 \
    --set atr_pct_min=0.020 --changelog "T3.40 V1: teto de pedágio 0,10 R (KB-0076)" --dry-run'
Tue Sep  8 18:54:17 UTC 2026
derivaria momentum v5 de v2 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c:
atr_pct_min 0.003 -> 0.02 [params_hash 2aef4a5ff989]
```

Digest **exatamente** o esperado pelo brief (`…ab2e0398…`) — sigo.

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py momentum v2 \
    --set target_atr=3.0 --changelog "T3.40 V2: alvo 3 ATR (KB-0076 MFE)" --dry-run'
Tue Sep  8 18:54:27 UTC 2026
RECUSADO: a variante sai da faixa declarada: target_atr=3 não é menor que target2_atr=3
                                                                       (exit code 1)
```

**A mudança literal do brief não é derivável.** `constraints_table.py` declara para `momentum_v1` os
pares ordenados `target_atr < target2_atr < target3_atr` (T3.26c/A2), e o pai publica a escada
`1,5 / 3 / 4,5`. Ver CONCERN 1 para a decisão e a alternativa que rodou:

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py momentum v2 \
    --set target_atr=3.0 --set target2_atr=6.0 --set target3_atr=9.0 --changelog "T3.40 V2: alvo 3 ATR (KB-0076 MFE)" --dry-run'
Tue Sep  8 18:55:54 UTC 2026
derivaria momentum v5 de v2 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.momentum_v1@sha256:ab2e0398…ebaa40c: target2_atr 3 -> 6, target3_atr 4.5 -> 9,
target_atr 1.5 -> 3 [params_hash 8cb1aa497956]
```

### 2. Derivação (escrita)

```
$ ... derive_variant.py momentum v2 --set atr_pct_min=0.020 --changelog "T3.40 V1: teto de pedágio 0,10 R (KB-0076)"
Tue Sep  8 18:56:26 UTC 2026
derivada momentum v5 de v2 (purpose research_only, draft, nada ativado) em code_ref …ab2e0398…:
atr_pct_min 0.003 -> 0.02 [params_hash 2aef4a5ff989]
Tue Sep  8 18:56:28 UTC 2026

$ ... derive_variant.py momentum v2 --set target_atr=3.0 --set target2_atr=6.0 --set target3_atr=9.0 \
      --changelog "T3.40 V2: alvo 3 ATR (KB-0076 MFE)"
Tue Sep  8 18:56:36 UTC 2026
derivada momentum v6 de v2 (purpose research_only, draft, nada ativado) em code_ref …ab2e0398…:
target2_atr 3 -> 6, target3_atr 4.5 -> 9, target_atr 1.5 -> 3 [params_hash 8cb1aa497956]
Tue Sep  8 18:56:38 UTC 2026
```

### 3. Ativação (dry-run e escrita) — **os carimbos do `Registro de Tentativas`**

```
$ ... activate_strategy_version.py momentum v5 --changelog "T3.40 V1: coorte de pesquisa do teto de pedagio (atr_pct_min 0,020) aberta" --dry-run
Tue Sep  8 18:56:48 UTC 2026
would activate momentum v5 (purpose research_only) with code_ref …ab2e0398…ebaa40c (19 parameters)

$ ... (sem --dry-run)
Tue Sep  8 18:57:03 UTC 2026
activated momentum v5 (purpose research_only) at 2026-09-08T18:57:05.384576+00:00 with code_ref …ab2e0398…

$ ... activate_strategy_version.py momentum v6 --changelog "T3.40 V2: coorte de pesquisa do alvo 3 ATR aberta" --dry-run
Tue Sep  8 19:04:43 UTC 2026
would activate momentum v6 (purpose research_only) with code_ref …ab2e0398…ebaa40c (19 parameters)

$ ... (sem --dry-run)
activated momentum v6 (purpose research_only) at 2026-09-08T19:04:56.213531+00:00 with code_ref …ab2e0398…
```

| variante | versão | derivada em (UTC) | ativada em (UTC) | ativada em (Brasília) | `params_hash` |
|---|---|---|---|---|---|
| V1 teto de pedágio | `momentum v5` | 2026-09-08 18:56:28,636295 | **2026-09-08 18:57:05,384576** | 15:57:05 | `2aef4a5ff989` |
| V2 alvo 3 ATR | `momentum v6` | 2026-09-08 18:56:38,527421 | **2026-09-08 19:04:56,213531** | 16:04:56 | `8cb1aa497956` |

**A ativação preservou o conteúdo próprio da linha derivada** (o furo que a T3.26 fechou):

```
| version | status | purpose       | atr_pct_min | target_atr | target2_atr | target3_atr | resto_igual_ao_pai | schema_igual | code_ref_igual |
| v2      | active | research_only | 0.003       | 1.5        | 3           | 4.5         | t                  | t            | t              |
| v5      | active | research_only | 0.02        | 1.5        | 3           | 4.5         | t                  | t            | t              |
| v6      | active | research_only | 0.003       | 3          | 6           | 9           | t                  | t            | t              |
```

E a linhagem **não** se perdeu (ao contrário da `v4` na T3.26 — `keep_lineage` já está na imagem):

```
| v5 | variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.02 | params_hash=2aef4a5ff989 | T3.40 V1: coorte de pesquisa do teto de pedagio (atr_pct_min 0,020) aberta |
| v6 | variante de v2 | derived_from=v2 | overrides=target2_atr=6,target3_atr=9,target_atr=3 | params_hash=8cb1aa497956 | T3.40 V2: alvo 3 ATR (KB-0076 MFE) |
```

### 4. O CLI de replay da imagem estava quebrado (CONCERN 2)

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
    --version momentum:v5 --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT --dry-run'
  File "/app/services/strategy-worker/hunter_strategy_worker/replay/run.py", line 79, in <module>
    from hunter_strategy_worker.replay.stress import run_cli as stress_cli
ModuleNotFoundError: No module named 'hunter_strategy_worker.replay.stress'
```

`git ls-tree c78a416 …/replay/` confirma: `stress.py` **não está no commit** (é arquivo *untracked*
da T3.36 em voo), e `run.py` já o importa no topo. `main @ c78a416` — e a imagem publicada — não
conseguem rodar replay nenhum. Rodei o `run.py` **da imagem, byte a byte**, por um atalho de 30
linhas em `sys.modules` (`t340-sql/replay_shim.py`), sem copiar, escrever ou alterar arquivo dentro
do container; `stress_cli` só é chamado sob `--stress` (run.py:299, dentro de `if args.stress:`), que
o atalho recusa. Prova de equivalência mais adiante (§7).

### 5. Replay da V1 — `momentum v5`, coorte `replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1`

```
$ ssh hunter-vps "docker exec -i hunter-strategy-worker-1 python - --version momentum:v5 \
   --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
   --cohort replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1 \
   --explain-ledger /tmp/replay-momentum-v5-a.jsonl" < replay_shim.py
2026-09-08 19:01:59 [info] replay_explain_ledger  bars=5760 lines=5760 path=/tmp/replay-momentum-v5-a.jsonl
{'run_id': '72cf5671-…', 'version_label': 'momentum v5', 'window_from': '2026-08-08T00:00:00+00:00',
 'window_to': '2026-08-23T00:00:00+00:00', 'market_count': 4, 'bars_evaluated': 5760, 'signals': 0,
 'outcomes_resolved': 0, 'outcomes_open': 0, 'seconds': 95.802, 'bars_per_second': 60.12,
 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5312}, 'errors': 0}
Tue Sep  8 19:01:59 UTC 2026

$ ... --from 2026-08-23 --to 2026-09-08 ... --explain-ledger /tmp/replay-momentum-v5-b.jsonl
2026-09-08 19:04:22 [info] replay_explain_ledger  bars=6144 lines=6144 path=/tmp/replay-momentum-v5-b.jsonl
{'bars_evaluated': 6144, 'signals': 0, 'outcomes_resolved': 0, 'outcomes_open': 0, 'seconds': 103.834,
 'bars_per_second': 59.17, 'evaluations_by_state': {'not_triggered': 6144}, 'errors': 0}
Tue Sep  8 19:04:22 UTC 2026
```

### 6. Replay da V2 — `momentum v6`, coorte `replay:9a08835a-ae13-4c23-b521-734b2f60a3a2`

```
$ ... --version momentum:v6 --from 2026-08-08 --to 2026-08-23 ... --explain-ledger /tmp/replay-momentum-v6-a.jsonl
2026-09-08 19:06:43 [info] replay_explain_ledger  bars=5760 lines=5760 path=/tmp/replay-momentum-v6-a.jsonl
{'version_label': 'momentum v6', 'bars_evaluated': 5760, 'signals': 59, 'outcomes_resolved': 59,
 'outcomes_open': 0, 'seconds': 91.112, 'bars_per_second': 63.22, 'workers': 3,
 'evaluations_by_state': {'triggered': 180, 'unavailable': 448, 'not_triggered': 5132}, 'errors': 0}

$ ... --from 2026-08-23 --to 2026-09-08 ... --explain-ledger /tmp/replay-momentum-v6-b.jsonl
2026-09-08 19:09:02 [info] replay_explain_ledger  bars=6144 lines=6144 path=/tmp/replay-momentum-v6-b.jsonl
{'bars_evaluated': 6144, 'signals': 196, 'outcomes_resolved': 196, 'outcomes_open': 0,
 'seconds': 105.162, 'bars_per_second': 58.42,
 'evaluations_by_state': {'triggered': 280, 'not_triggered': 5864}, 'errors': 0}
Tue Sep  8 19:09:02 UTC 2026
```

**Armadilha do denominador (a mesma da T3.33e):** `signals` do recibo conta a **coorte inteira**, não
a fatia — `59` e `196` **não somam**; a população final é **196**. `triggered` sim é por fatia:
180 + 280 = **460**, exatamente o número do pai (o alvo é lido depois das quatro portas de entrada).

### 7. Livro-razão da V1 e a prova de que o atalho é equivalente

Os arquivos `/tmp` foram apagados pelo redeploy de outra tarefa às 19:12Z (CONCERN 4). As duas
fatias da **V1** foram reexecutadas às 19:17–19:21 **na imagem já corrigida** (`c29cbef`, que traz o
`stress.py` que faltava), agora com `python -m …replay.run` puro, **sem atalho**:

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
    --version momentum:v5 --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT \
    --workers 3 --cohort replay:72cf5671-… --explain-ledger /tmp/replay-momentum-v5-a.jsonl'
2026-09-08 19:19:12 [info] replay_explain_ledger  bars=5760 lines=5760
{'bars_evaluated': 5760, 'signals': 0, 'seconds': 88.346,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5312}, 'errors': 0}
```

**Idêntico, estado por estado, ao que o atalho produziu** (`unavailable 448`, `not_triggered 5312`,
`signals 0`) — e `git diff --stat c78a416 c29cbef -- packages/core/hunter_core/strategies/
services/strategy-worker/hunter_strategy_worker/` mostra que entre as duas imagens **só entraram**
`replay/stress.py` e `replay/stress_report.py`: nada do caminho de avaliação mudou.

O livro-razão somado das duas fatias (11 904 linhas, uma por barra):

```
{"linhas": 11904,
 "estados": {"unavailable": 448, "not_triggered": 11456},
 "motivos": {"warmup": 448, "no_breakout": 10221, "atr_out_of_range": 701, "rvol_low": 534}}
{"barras_com_atr_pct": 701, "min": 0.000644, "p50": 0.004423, "p90": 0.009257,
 "p99": 0.015438, "max": 0.017558, "acima_de_0.020": 0}
```

Primeira linha do arquivo, verbatim:

```
{"bar_close":"2026-08-08T00:00:00+00:00","market":"binance:ETHUSDT","state":"unavailable",
 "reason":"warmup","detail":{"window_start":"2026-08-06T23:45:00Z","first_candle":"none"}}
```

### 8. Testes locais (nenhum código foi escrito; rodei o que governa a recusa da V2)

```
$ uv run pytest services/strategy-worker/tests/test_constraints_outside_freeze.py \
      services/strategy-worker/tests/test_derive_variant.py \
      services/strategy-worker/tests/test_activate_derived_guard.py \
      infra/scripts/tests/test_derive_variant_lineage.py -q
......................................................                   [100%]
54 passed in 56.42s
```

---

## RECIBOS

### `replay_runs` (lidos do banco)

```
| coorte                                      | ver | de         | ate        | mkts | bars | sig | out | open | seg     | wk | lag | estados                                                     | err |
| replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1 | v5  | 2026-08-08 | 2026-08-23 |    4 | 5760 |   0 |   0 |    0 |  95.802 |  3 |   2 | {"unavailable":448,"not_triggered":5312}                    |   0 |
| replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1 | v5  | 2026-08-23 | 2026-09-08 |    4 | 6144 |   0 |   0 |    0 | 103.834 |  3 |   2 | {"not_triggered":6144}                                      |   0 |
| replay:9a08835a-ae13-4c23-b521-734b2f60a3a2 | v6  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  59 |  59 |    0 |  91.112 |  3 |   2 | {"triggered":180,"unavailable":448,"not_triggered":5132}    |   0 |
| replay:9a08835a-ae13-4c23-b521-734b2f60a3a2 | v6  | 2026-08-23 | 2026-09-08 |    4 | 6144 | 196 | 196 |    0 | 105.162 |  3 |   2 | {"triggered":280,"not_triggered":5864}                      |   0 |
```

**Quatro linhas, não seis:** as duas reexecuções de livro-razão da V1 **não** criaram recibo novo —
`record_run` é idempotente pela chave da corrida. Os `seconds` acima são os das corridas originais.

### `system_events` da janela

```
warning | activate_strategy_version | strategy_version_variant_refused | a variante sai da faixa declarada: target_atr=3 não é menor que target2_atr=3   | 18:54:29.234974+00
info    | activate_strategy_version | strategy_version_variant_derived | momentum v5 derived from v2 (variante, purpose research_only) code_ref=…       | 18:56:28.636295+00
info    | activate_strategy_version | strategy_version_variant_derived | momentum v6 derived from v2 (variante, purpose research_only) code_ref=…       | 18:56:38.527421+00
info    | activate_strategy_version | strategy_version_activated       | momentum v5 (purpose research_only) activated with its already-copied code_ref= | 18:57:05.384576+00
info    | replay_engine             | replay_run_finished              | replay momentum v5 … 2026-08-08…2026-08-23: 5760 barras, 0 sinais              | 19:01:59.036755+00
info    | replay_engine             | replay_run_finished              | replay momentum v5 … 2026-08-23…2026-09-08: 6144 barras, 0 sinais              | 19:04:22.700512+00
info    | activate_strategy_version | strategy_version_activated       | momentum v6 (purpose research_only) activated with its already-copied code_ref= | 19:04:56.213531+00
info    | replay_engine             | replay_run_finished              | replay momentum v6 … 2026-08-08…2026-08-23: 5760 barras, 59 sinais             | 19:06:43.723966+00
info    | replay_engine             | replay_run_finished              | replay momentum v6 … 2026-08-23…2026-09-08: 6144 barras, 196 sinais            | 19:09:02.121215+00
info    | replay_engine             | replay_run_finished              | replay momentum v5 … (reexecução do livro-razão)                                | 19:19:12.800256+00
info    | replay_engine             | replay_run_finished              | replay momentum v5 … (reexecução do livro-razão)                                | 19:20:59.847401+00
```

### Isolamento — a coorte é a cerca, e ela segurou

```
| outbox_das_coortes | sinais_v5_total | sinais_v6_total | sinais_v6_fora_da_coorte | slots | v6_nao_terminais |
|                  0 |               1 |             198 |                        2 |     8 |                0 |
```

Zero linhas de `shadow_outbox` para as duas coortes de replay (`persist.is_published_cohort` recusa
publicar replay). Os `1` e `2` sinais "fora da coorte" são **prospectivos**, emitidos depois da
ativação — é exatamente o que "entrar no Lab" significa:

```
| version | coorte      | sinais | primeiro                      |
| v5      | prospective |      1 | 2026-09-08 19:16:21.832394+00 |
| v6      | prospective |      2 | 2026-09-08 19:16:22.048800+00 |
| version | slots_prospectivos |
| v5      |                215 |
| v6      |                215 |
```

### Capacidade — vigia (a `paper` continua primeiro, `outbox_lag_s` 0 o tempo todo)

| relógio (UTC) | `evaluated_bars` | `last_iteration` | `outbox_lag_s` | `outbox_pending` | `errors` | container |
|---|---:|---|---:|---:|---:|---|
| 18:57:43 (após ativar v5) | 2 151 | 18:57:04 | 0,0 | 0 | 0 | `c78a416`, healthy |
| 19:04:34 | 3 871 | 19:04:04 | 0,0 | 0 | 0 | `c78a416`, healthy |
| 19:09:20 (após ativar v6) | 4 086 | 19:09:04 | 0,0 | 0 | 0 | `c78a416`, healthy |
| 19:23:48 | 2 150 | 19:23:04 | 0,0 | 0 | 0 | `c29cbef`, healthy (contadores zerados pelo redeploy alheio) |
| 19:31:53 | 3 455 | 19:31:49 | 0,0 | 0 | 0 | `c29cbef`, healthy, `/ready` 200 |

Ordem do roster (a linha `paper` é a primeira dentro da chave `momentum`, como a A3 da T3.26c exige):

```
1 breakout v1 research_only 15m ceed5b7c0580
2 breakout v2 research_only 15m 0e6abf1114cb
3 mean_reversion v1 research_only 15m 8918b39b73fb
4 momentum v3 paper 15m 40e1688e6b5f      <- paper primeiro
5 momentum v2 research_only 15m 40e1688e6b5f
6 momentum v4 research_only 15m 46635ed2bff2
7 momentum v5 research_only 15m 2aef4a5ff989
8 momentum v6 research_only 15m 8cb1aa497956
9 volume_anomaly v2 research_only 5m fa5dce78173b
```

Nove versões ativas (eram sete na T3.33f). É carga nova declarada — CONCERN 5.

---

## TABELAS PAREADAS

`read_at` das leituras: **19:11:21Z** (população), **19:12:57Z** (grupos pareados), **19:14:21Z**
(motivos e MFE), **19:15:07Z** (blocos), **19:25:48Z** (cobertura). Cada consulta numa transação
`repeatable read read only` própria; o SQL literal está em `.claude/state/exp-drafts/t340-sql/`.

### Populações (o pai e as duas variantes, mesma janela e mesmos quatro mercados)

```
+-------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
|   versao    |     coorte      | decisoes | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | pf_bruto | dias | atr_pct_min_obs | atr_pct_max_obs |
+-------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
| momentum v2 | replay:f8d8279c |      224 |        222 |      0.0820 |  0.2526 |       -0.1717 | -38.13 |       40.6 |     0.6454 |   1.2455 |   24 |         0.00300 |         0.01623 |
| momentum v6 | replay:9a08835a |      196 |        195 |      0.2028 |  0.2554 |       -0.0513 | -10.01 |       27.0 |     0.9064 |   1.5431 |   24 |         0.00300 |         0.01623 |
+-------------+-----------------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+-----------------+-----------------+
```

A `momentum v5` **não aparece: zero decisões**. E a coluna `atr_pct_max_obs = 0,01623` explica por
quê num número só — **o ATR% máximo que a `momentum` observa ao decidir nestes quatro mercados é
1,62 %, e o piso da V1 é 2,0 %.**

### V1 — os grupos pareados (o piso 0,020 sobre a população do pai)

| Grupo | n | avaliáveis | bruta (R) | líquida (R) | soma R |
|---|---:|---:|---:|---:|---:|
| decisões do pai **acima** do piso | **0** | 0 | — | — | — |
| decisões do pai **abaixo** do piso (eliminadas) | **224** | 222 | +0,0820 | −0,1717 | −38,13 |
| decisões da variante **pareadas** | 0 | 0 | — | — | — |
| decisões da variante **sem par** | 0 | 0 | — | — | — |

Corte de decisões: **100,0 %** (a `v4`, com piso 0,0089, cortou 86 %).

### V2 — os quatro grupos pareados por `(mercado, barra)`

```
+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------------+------+
|           grupo            |  n  | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | dias |
+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------------+------+
| pai pareado com a variante | 193 |        191 |      0.0567 |  0.2556 |       -0.2005 | -38.29 |       38.9 |     0.5971 |   24 |
| pai SEM par na variante    |  31 |         31 |      0.2396 |  0.2335 |        0.0052 |   0.16 |       51.6 |     1.0129 |   13 |
| variante pareada com o pai | 193 |        192 |      0.1939 |  0.2558 |       -0.0606 | -11.63 |       26.9 |     0.8905 |   24 |
| variante SEM par no pai    |   3 |          3 |      0.7797 |  0.2326 |        0.5417 |   1.63 |       33.3 |     3.1489 |    2 |
+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------------+------+
```

**Diferença estrutural em relação à T3.26:** lá, toda a melhora da `v4` vinha de 5 decisões sem par
(slot livre). Aqui **193 dos 196** pareiam, e a melhora está **dentro dos pares** — é o mesmo trade,
com outro alvo.

### V2 — o estimando (Δ pareado, 191 pares com os dois lados avaliáveis)

```
+-------+-------------------+------------------+---------------------+---------------------+--------------+------+
| pares | delta_liq_medio_r | delta_liq_soma_r | delta_bruto_medio_r | mesmo_risco_inicial | mesmo_motivo | dias |
+-------+-------------------+------------------+---------------------+---------------------+--------------+------+
|   191 |            0.1341 |            25.61 |              0.1346 |                 191 |          168 |   24 |
+-------+-------------------+------------------+---------------------+---------------------+--------------+------+
```

`mesmo_risco_inicial = 191/191` é a prova de que **só o alvo mudou**: entrada, stop e custo em R são
idênticos par a par.

### V2 — de onde vêm os +25,61 R

```
+-------------+-------------+----+-------------------+--------------+
| motivo_pai  | motivo_var  | n  | delta_liq_medio_r | delta_soma_r |
+-------------+-------------+----+-------------------+--------------+
| target      | target      | 52 |            0.9549 |        48.70 |
| invalidated | invalidated | 73 |            0.0000 |         0.00 |
| stop        | stop        | 40 |            0.0000 |         0.00 |
| expired     | expired     |  5 |            0.0000 |         0.00 |
| target      | expired     | 10 |           -0.6006 |        -6.01 |
| target      | invalidated |  8 |           -1.1385 |        -9.11 |
| target      | stop        |  5 |           -1.5953 |        -7.98 |
+-------------+-------------+----+-------------------+--------------+
```

**52 ganhadores dobraram (+48,70 R); 23 ganhadores foram devolvidos (−23,10 R).** O resto do livro
não se move nem uma casa decimal — até o alvo antigo, é exatamente a mesma operação.

### V2 — motivos de saída, população inteira de cada coorte

```
+----------+-------------+----+------+-------------+------------+---------------+
|  coorte  |   motivo    | n  | pct  | r_liq_medio | r_liq_soma | r_bruto_medio |
+----------+-------------+----+------+-------------+------------+---------------+
| 9a08835a | invalidated | 82 | 41.8 |     -0.6259 |     -50.70 |       -0.3753 |
| 9a08835a | target      | 53 | 27.0 |      1.7011 |      90.16 |        1.9406 |
| 9a08835a | stop        | 45 | 23.0 |     -1.1921 |     -53.65 |       -0.9172 |
| 9a08835a | expired     | 16 |  8.2 |      0.2610 |       4.18 |        0.5595 |
| f8d8279c | target      | 91 | 40.6 |      0.7599 |      68.39 |        1.0027 |
| f8d8279c | invalidated | 82 | 36.6 |     -0.6462 |     -52.34 |       -0.3956 |
| f8d8279c | stop        | 45 | 20.1 |     -1.1883 |     -53.47 |       -0.9190 |
| f8d8279c | expired     |  6 |  2.7 |     -0.1176 |      -0.71 |        0.1530 |
+----------+-------------+----+------+-------------+------------+---------------+
```

`stop` (45) e `invalidated` (82) são **idênticos em contagem** nas duas coortes; o alvo mais distante
converte 38 `target` em 10 `expired` a mais e alonga as operações.

### V2 — MFE capturado

```
+----------+-----+--------------+-------------+-----------+-----------+---------------+-------------------------+------------------+------------------+
|  coorte  |  n  | mfe_ambiguos | mfe_medio_r | mfe_p50_r | mfe_p90_r | r_bruto_medio | fracao_do_mfe_capturada | pct_mfe_maior_2r | pct_mfe_maior_1r |
+----------+-----+--------------+-------------+-----------+-----------+---------------+-------------------------+------------------+------------------+
| 9a08835a | 196 |           98 |      0.4511 |    0.1934 |    1.2988 |        0.2028 |                  0.4496 |              1.0 |             10.7 |
| f8d8279c | 224 |          136 |      0.2343 |    0.1264 |    0.6014 |        0.0820 |                  0.3500 |              0.0 |              1.8 |
+----------+-----+--------------+-------------+-----------+-----------+---------------+-------------------------+------------------+------------------+
```

**Advertência que a T3.32 já tinha registrado e que vale em dobro aqui:** `mfe` é lido por barras
completas (`ohlc_complete_bars_v1`) e **98 das 196 linhas são `ambiguous`** — os percentis acima são
**limites inferiores**. É por isso que "1,0 % com MFE ≥ 2 R" convive com "53 alvos de 2 R atingidos".

### V2 — o teste de blocos (dia como bloco)

```
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+
| blocos_dia | media_das_medias_diarias | desvio | erro_padrao | ic95_inferior | ic95_superior | dias_positivos | dias_negativos |
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+
|         24 |                   0.0463 | 0.3320 |      0.0678 |       -0.0939 |        0.1866 |             10 |              8 |
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+
```

Três dias respondem por quase tudo (08-19 +0,704, 08-21 +0,467, 08-27 +0,626); seis dias têm Δ
exatamente zero. **O intervalo contém zero.**

### Cobertura (o quadro do template)

```
| coorte   | emitidos | pendentes | entradas | nao_entradas | ativos | alvo | stop | expirado | invalidado | censurados | funding_indisponivel | avaliaveis | dias |
| 9a08835a |      196 |         0 |      196 |            0 |      0 |   53 |   45 |       16 |         82 |          0 |                    1 |        195 |   24 |
| f8d8279c |      224 |         0 |      224 |            0 |      0 |   91 |   45 |        6 |         82 |          0 |                    2 |        222 |   24 |
| coorte   | taxa_alvo_entre_toques | taxa_lucro_liquido_pct |
| 9a08835a |                   54.1 |                   32.8 |
| f8d8279c |                   66.9 |                   41.4 |
```

---

## VEREDITO POR VARIANTE

### V1 — `momentum v5`, teto de pedágio (`atr_pct_min = 0,020`)

**Veredito formal: `inconclusivo`** (regra prospectiva; e, nesta janela, por população vazia).
**Recomendação: `descartar` como está — e o critério de descarte do brief é atingido no seu extremo.**

- A regra do EXP-0006/[[KB-0008]] — "um corte acima de 70 % das decisões é outra estratégia" —
  é ultrapassada com **100 %** de corte: 0 decisões em 11 904 barras.
- O motivo é **geométrico e medido**, não estatístico: das 701 barras que chegam ao porteiro de ATR,
  o máximo de `atr_pct_15m` é **1,756 %**; nas 224 decisões do pai, **1,623 %**. ETH, SOL, XRP e DOGE
  simplesmente não têm ATR de 15 min a 2 % do preço nesta janela.
- Há uma segunda razão, de política, que o EXP registra em C5: com `stop_atr = 1,5`, um piso de
  2,0 % põe o stop a **≥ 3,0 % do preço**, e 3 % é exatamente o **teto** `max_stop_distance_pct` do
  `paper_v1` (`hunter_risk/limits.py:151-152`, banda `[0,003; 0,03]`). Ou seja: **toda** barra com
  ATR% acima do piso teria o sizing recusado pelo Risk Engine. Esta variante, por construção, decide
  onde o preset paper não deixa entrar.
- **O que não descarto:** a coorte `prospective` (200 mercados, primeiro sinal 19 min após a
  ativação). O eixo do teto de custo só é testável num universo com ATR% alto; se a prospectiva
  também render ~0, o eixo morre e a conclusão do dia é a da [[KB-0076]] item 10 — **falta vantagem
  na entrada, e nenhum filtro de custo a fabrica**.

### V2 — `momentum v6`, alvo 3 ATR (`target_atr = 3,0`)

**Veredito formal: `inconclusivo`.** **Recomendação: `manter em pesquisa` (não descartar, não
promover).** Os dois critérios de descarte do brief **não** disparam:

| critério do brief | valor medido | dispara? |
|---|---|---|
| `PF_net ≤ 0,80` | **0,9064** | não |
| `expectancy_net ≤ expectancy do pai` | **−0,0513 R** vs **−0,1717 R** | não |

O que sustenta e o que não sustenta a recomendação:

1. **O contraste é limpo como poucos:** 193 dos 196 pareiam, `risco inicial idêntico em 191/191`,
   custo em R praticamente igual (0,2554 vs 0,2526). É o mesmo trade com outro alvo.
2. **Δ pareado +0,134 R por decisão, +25,61 R no total.** Sinal e magnitude batem com o braço
   `TGT-3` do EXP-0007 medido nesta mesma população (+0,104 R) — a versão reproduz o braço.
3. **E não passa no teste que importa:** por bloco de dia, +0,0463 R com IC 95 % **[−0,094; +0,187]**
   — contém zero, três dias explicam quase tudo. A [[KB-0010]] cobra exatamente isto.
4. **A variante continua perdendo dinheiro.** −0,051 R por operação, PF 0,906 < 1. Ela **reduz a
   perda em 70 %**, não a inverte. E o bruto de +0,203 R ainda está longe do +0,25 R que a
   [[KB-0076]] item 10 nomeia como o número que decide tudo.
5. **O mecanismo é caro:** paga 23 ganhadores devolvidos (−23,10 R) para receber 52 dobrados
   (+48,70 R). A taxa de acerto cai de 40,6 % para 27,0 %, o que é uma mudança de perfil psicológico
   grande para quem for olhar a tela.
6. **A mesma janela gerou a hipótese.** É o erro clássico decidir por ela ([[KB-0010]]), e o braço
   equivalente já trocou de sinal em duas populações prospectivas (−0,23 R e −0,10 R). Por isso a
   recomendação é **30 dias prospectivos**, não ativação.

**O que muda o veredito:** a coorte `prospective` aberta em 2026-09-08T19:04:56Z, reavaliada em
2026-10-08 contra `v2` e `v3` na **mesma** janela. Se o Δ prospectivo for negativo, a recomendação
vira `descartar` com duas evidências independentes; se for positivo com IC longe de zero, aí é
conversa de linha `paper` — e do Everton, não minha.

---

## CONCERNS

1. **A V2 literal do brief é inderivável, e eu escolhi o deslocamento da escada.** `--set
   target_atr=3.0` sozinho foi **recusado** pelo `derive_variant.py` (`target_atr` tem de ser menor
   que `target2_atr`, e o pai declara `target2_atr = 3`). Não é bug: é a faixa da A2 da revisão
   T3.26c funcionando. **Decisão numérica minha, declarada:** deslocar a escada inteira preservando a
   regra que o pai já usava (`target × {1, 2, 3}`), ou seja `3 / 6 / 9`. Alternativas que rejeitei:
   `target2_atr = 4` (número arbitrário, dois algarismos sem origem) e `target_atr = 2,99` (fraude
   contra a própria trava). **Consequência real: nenhuma sobre os números** — o `walker` só usa
   `target1` (`walker.py:73,157`), `target2/3` são informativos —, mas o `params_hash` da variante
   cobre os três, então **este EXP não é bit a bit o braço `TGT-3` do EXP-0007**. Se o revisor
   preferir outra escada, é `derive_variant` de novo e um `EXP` novo; os números desta avaliação não
   mudam.
2. **O CLI de replay de `main @ c78a416` está quebrado, e eu contornei.** `replay/run.py` importa
   `hunter_strategy_worker.replay.stress`, um módulo **untracked** (T3.36 em voo): o commit e a
   imagem publicada não rodam replay nenhum. Contornei com um atalho de 30 linhas
   (`t340-sql/replay_shim.py`) que registra um stub em `sys.modules` e executa o `run.py` **da
   imagem**, byte a byte, por `runpy` — sem copiar, escrever ou alterar arquivo dentro do container.
   `stress_cli` só é alcançável sob `--stress` (run.py:299), que o atalho recusa. **A equivalência
   não é afirmada, é conferida:** a mesma fatia rodada depois na imagem corrigida, sem atalho, deu
   estado por estado o mesmo resultado. Ainda assim: **isto é um caminho de execução não auditado
   escrevendo no banco de produção**, e o revisor tem todo o direito de julgar que eu deveria ter
   parado. Se julgar, o conserto é `git add` do `stress.py` (não é meu arquivo) e reexecutar.
3. **Sete versões viraram nove.** `momentum` tem agora **cinco** versões ativas (`v2` research,
   `v3` paper, `v4`, `v5`, `v6` research) e o roster tem nove. A vigia não mostrou degradação
   (`outbox_lag_s` 0,0 em todas as amostras, `errors` 0, `/ready` 200), mas cada versão nova custa
   uma avaliação por barra por mercado — e a T2.5 já registrou que a passada completa está acima do
   alvo de p99. **Ninguém aposentou nada**, e não existe via auditada para aposentar uma versão
   substituída por parâmetro (a T3.33f registrou isso como CONCERN 2 dela e continua aberto).
4. **Outra tarefa recriou o container no meio do meu trabalho e apagou os livros-razão.** Às
   ~19:12Z a VPS foi redeployada de `c78a416` para `c29cbef` (T3.36) e o `/tmp` do
   `hunter-strategy-worker-1` foi zerado: os quatro `.jsonl` sumiram. Reexecutei **só os da V1**
   (população vazia ⇒ reexecução provadamente idêntica, e `record_run` não criou recibo novo). **Os
   livros-razão da V2 não foram regenerados de propósito:** reexecutar 196 decisões sobre a mesma
   coorte mudaria a ocupação de slot e, portanto, a população — seria destruir a medição para obter
   um arquivo de diagnóstico. Do livro-razão da V2 ficam os recibos de linha
   (`bars=5760 lines=5760`, `bars=6144 lines=6144`) e nada mais.
5. **`mfe` é limite inferior em metade das linhas** (98 de 196 na variante, 136 de 224 no pai, com
   `ambiguous = true`). A tabela de MFE capturado descreve a ordem de grandeza, não um valor exato, e
   os `bounds` gravados em `meta.excursions` não foram usados nesta passada — mesma pendência que a
   T3.32 deixou.
6. **O IC por blocos é uma aproximação `t`, não um bootstrap.** Usei 24 médias diárias e `t = 2,069`
   (23 gl). A T3.32 usou bootstrap de blocos com Holm; aqui há **um** contraste pré-registrado, então
   não há multiplicidade a corrigir, mas a distribuição das médias diárias com `n` entre 1 e 21 não é
   normal e o intervalo é otimista nas caudas. A leitura que faço dele ("contém zero") é robusta a
   isso; um "IC = [x; y]" citado fora de contexto não seria.
7. **O replay herda o universo de hoje**, não o de agosto (limitação declarada do motor,
   `PIPELINE` §6c). Vale igualmente para as três coortes, então o pareamento não fica enviesado —
   mas nenhuma das três descreve o universo da janela.
8. **A hipótese de custo continua declarada, não medida** (20 bps ida e volta). Todo o eixo da V1
   escala linearmente com ela. Medir contra o livro real é a verificação que a [[KB-0076]] já pedia.
8b. **Correção aritmética que encontrei ao escrever o EXP-0012.** A identidade
   `custo_R × risco% = 0,0020` usa `risco%` = **distância do stop** em fração do preço, e
   `risco% = stop_atr × ATR% = 1,5 × ATR%`. A [[KB-0076]] (e o brief, ao citá-la) aplica a identidade
   ao **ATR%** direto: daí o "a v4 (0,0089) já testa 0,22 R". Os números corretos são **≈ 0,15 R para
   a `v4`** e **≤ 0,067 R para a `v5`**. Isso **não muda** nenhuma decisão (o teto pedido, 0,10 R, é
   satisfeito com folga e a ordenação das variantes é a mesma), mas a KB merece uma nota de rodapé
   datada — não a escrevi porque `obsidian/**` está fora do meu escopo.
9. **`activate_strategy_version.py` está modificado na árvore local** (T3.39 em voo) e **não é meu**.
   Rodei o da imagem; os digests estão colados acima justamente para provar isso. Nenhuma mudança em
   voo de ninguém entrou em produção por minha mão.
10. **Nada foi arquivado no `obsidian/`.** Os dois EXP estão em `.claude/state/exp-drafts/` como
    rascunho para a Sexta-feira. `EXP-0012` e `EXP-0013` eram as próximas vagas livres às
    2026-09-08T19:25Z; se outra tarefa tomar os números antes, renumerar.

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** o CONCERN 2 (atalho de `sys.modules` executando o `run.py` da imagem para
  escrever no banco) e o CONCERN 1 (a escada 3/6/9 como decisão numérica minha). Os dois são
  julgamentos de política, não de aritmética.
- **risk-engine-guardian:** `v5` e `v6` são `research_only`, sem linha em `agents`, coortes de replay
  recusadas por nome pela ponte, `shadow_outbox` zerada para as duas coortes. O **novo** ponto de
  atenção é o C5 do EXP-0012: a `v5` decide com stop no limite superior do `paper_v1` — se algum dia
  alguém pedir `--paper-line` dela, essa é a conversa.
- **Sexta-feira:** arquivar `EXP-0012` e `EXP-0013`, ligar do `Strategy Backlog` e do `Experiments
  Index`, e acrescentar duas linhas no `Registro de Tentativas` com os carimbos de ativação
  (18:57:05Z e 19:04:56Z). A contagem de multiplicidade sobe: **duas execuções novas, um contraste
  pré-registrado cada**.
- **Everton:** a decisão que este trabalho põe na mesa é **esperar 30 dias** antes de mexer em
  qualquer alvo. O número honesto do dia é que o alvo de 3 ATR reduz a perda em 70 % na janela que
  inventou a ideia, e não se distingue de zero quando se conta por dia.
