# notes-T3.47 — o stop largo: o pedágio cai como a identidade promete, e o bruto cai junto

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Owner:** quant-engineer.
**Base do brief:** `main @ 2e39774`; VPS rodando `hunter-api:2e39774` (api, web e strategy-worker)
do começo ao fim — **nenhum redeploy dos meus containers no meio** (o `scanner-worker` foi
redeployado por outra tarefa às ~23:01Z; ver CONCERN 6).
**Nada commitado.** **Nenhum container parado ou recriado.** **Nenhum `.env*` tocado.**
**Nada escrito por mim em `apps/**`, `services/**`, `packages/**`, `obsidian/**`.**
**Escritas na VPS:** apenas `derive_variant.py` (×6), `activate_strategy_version.py` (×6), os
12 replays e as 7 passadas de estresse (as 6 variantes e o pai `momentum v6`; `READ ONLY` por construção). Todo o resto foi lido em
transação `repeatable read read only`.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Ler T3.40/T3.42/T3.45 e colar a geometria atual de `mean_reversion v2`/`v3`, `momentum v6`, `session_orb v1` | **OK.** §1. Achado de contrato: **`session_orb v1` não tem `stop_atr` nem `target_atr`** — ela declara `range_risk_atr_min/max` e alvos em R; a alavanca "stop largo" nela é outro parâmetro (CONCERN 5) |
| 2 | Tabela de pedágio **antes** (ATR% mediano, `custo_R` p25/p50/p75, bruto × líquido, quanto da perda é pedágio) | **OK.** §2, todas as coortes fechadas das três estratégias |
| 3 | Derivar duas variantes por pai (stop ×1,5 e ×2 com a escada de alvos na mesma escala), `--dry-run` antes, ativar como `research_only` | **OK, sem nenhuma recusa da tabela de faixas** (ao contrário da T3.40). Seis variantes: `momentum v7`/`v8`, `mean_reversion v4`/`v5` (de `v3`) e `v6`/`v7` (de `v2`). Digests conferidos nos **doze** dry-runs/derivações: `…momentum_v1@sha256:ab2e0398…` e `…mean_reversion_v1@sha256:a970c9d9…`, **exatamente os do brief** |
| 4 | Replay 31 d, 4 mercados, `--explain-ledger`, `--cohort` explícita + estresse + pareamento + IC por bloco de dia | **OK.** 12 fatias, 0 erros, 6 passadas de estresse, 6 contrastes pareados, IC por bootstrap de blocos de dia |
| 5 | Veredito por variante + resposta ao Everton + registrar o achado do piso de ATR% | **OK.** §VEREDITO, §RESPOSTA e §PROPOSTA |
| 6 | Rascunho EXP-0018 | **OK.** `.claude/state/exp-drafts/EXP-0018-stop-largo.md` |

**Resposta curta.** O stop largo **faz exatamente o que a identidade promete e quase nada do que se
esperava dele**. O pedágio cai pelo fator pedido, decisão a decisão: `momentum v6` **0,2554 R →
0,1731 R** (÷1,48) com stop ×1,5 e **→ 0,1305 R** (÷1,96) com stop ×2; `mean_reversion v2`
**0,1685 → 0,1075 → 0,0838 R**. Só que **o bruto em R cai junto**, porque R é a distância até o stop:
no `momentum`, dos **0,1315 R** de pedágio economizados pelo stop ×2, **0,1155 R** somem no bruto e
sobram **+0,0161 R** por operação — **12 %**. O Δ pareado das seis variantes tem IC 95 % por bloco de
dia **contendo zero nas seis**. Nenhuma inverte o sinal: `momentum v8` continua em **−0,0299 R**
(PF 0,906), e as quatro `mean_reversion` continuam positivas porque **já eram** — e com **9 a 15
decisões**, o que **dispara o K1** (< 20 decisões) nas quatro.

---

## FILES

Criados (todos meus, todos fora de código de produção):

| arquivo | o quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t347-q00-catalogo.sql` | roster + geometria declarada dos pais |
| `infra/scripts/sql/research/2026-09-09-t347-q01-pedagio-antes.sql` | a tabela de pedágio **antes** |
| `infra/scripts/sql/research/2026-09-09-t347-q02-session-orb.sql` | parâmetros completos da `session_orb v1` |
| `infra/scripts/sql/research/2026-09-09-t347-q10-populacoes.sql` | populações dos três pais e das seis variantes |
| `infra/scripts/sql/research/2026-09-09-t347-q11-pareado.sql` | os quatro grupos pareados e o Δ pareado por par |
| `infra/scripts/sql/research/2026-09-09-t347-q12-dump-pareado.sql` | dump dos Δ pareados para o bootstrap |
| `infra/scripts/sql/research/2026-09-09-t347-q13-motivos.sql` | motivos de saída + matriz de transição pai → variante |
| `infra/scripts/sql/research/2026-09-09-t347-q14-recibos-iso.sql` | `replay_runs`, `system_events`, `shadow_outbox` |
| `infra/scripts/sql/research/2026-09-09-t347-q15-iso-roster.sql` | isolamento, linhagem, conteúdo próprio, roster |
| `infra/scripts/sql/research/2026-09-09-t347-q16-cobertura-c5.sql` | cobertura, identidade do pedágio, C5 da banda `paper_v1`, `code_ref` |
| `infra/scripts/sql/research/2026-09-09-t347-q17-dias.sql` | R por dia nas nove coortes |
| `.claude/state/exp-drafts/t347-blocos/blocos_pareado.py` | bootstrap de blocos por dia **pareado** (NumPy) — CONCERN 1 |
| `.claude/state/exp-drafts/t347-blocos/test_blocos_pareado.py` | seis séries sintéticas com valor esperado calculado à mão |
| `.claude/state/exp-drafts/t347-blocos/pares.csv` | os 407 Δ pareados exportados pelo `q12` |
| `.claude/state/exp-drafts/EXP-0018-stop-largo.md` | o EXP com portão C1–C8, protocolo congelado e avaliação REPLAY datada |
| `.claude/state/notes-T3.47.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O QUE JÁ ESTAVA VIVO (antes de qualquer escrita)

```
$ ssh hunter-vps 'date -u; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Tue Sep  8 22:23:56 UTC 2026
hunter-web-1              hunter-web:2e39774   Up 7 minutes (healthy)
hunter-api-1              hunter-api:2e39774   Up 7 minutes (healthy)
hunter-strategy-worker-1  hunter-api:2e39774   Up 7 minutes (healthy)
hunter-scanner-worker-1   hunter-api:1926e53   Up 2 hours (healthy)
hunter-execution-worker-1 hunter-api:1926e53   Up 2 hours (healthy)
hunter-market-worker-*    hunter-api:1926e53   Up 2 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1                Up 41 hours (healthy)
```

Os dois scripts auditados são **byte a byte** os do commit publicado, nas três árvores:

```
$ ssh hunter-vps 'docker exec hunter-api-1 sha256sum /app/infra/scripts/derive_variant.py /app/infra/scripts/activate_strategy_version.py'
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0  /app/infra/scripts/derive_variant.py
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  /app/infra/scripts/activate_strategy_version.py

$ sha256sum infra/scripts/derive_variant.py infra/scripts/activate_strategy_version.py    # árvore local
830a1f89…   dc6abf95…
$ git show 2e39774:infra/scripts/derive_variant.py | sha256sum            -> 830a1f89…
$ git show 2e39774:infra/scripts/activate_strategy_version.py | sha256sum -> dc6abf95…
```

Ao contrário da T3.40, **o CLI de replay do commit publicado está inteiro**: `git ls-tree 2e39774
services/strategy-worker/hunter_strategy_worker/replay/` lista `stress.py` e `stress_report.py`.
Nenhum atalho foi necessário nesta tarefa.

### Geometria declarada dos pais (`q00`, `read_at = 2026-09-08T22:25:38,688643Z` = 19:25:38 Brasília)

```
+-------------------+-------------+-------------+----------+------------+-------------+-------------+-----------+---------------+
|      versao       | atr_pct_min | atr_pct_max | stop_atr | target_atr | target2_atr | target3_atr | horizon_s | entry_delay_s |
+-------------------+-------------+-------------+----------+------------+-------------+-------------+-----------+---------------+
| mean_reversion v1 | 0.006       | 0.05        | 1        | 1.5        | 2.5         |             | 14400     | 120           |
| mean_reversion v2 | 0.008       | 0.05        | 1        | 1.5        | 2.5         |             | 14400     | 120           |
| mean_reversion v3 | 0.01        | 0.05        | 1        | 1.5        | 2.5         |             | 14400     | 120           |
| momentum v2       | 0.003       | 0.05        | 1.5      | 1.5        | 3           | 4.5         | 14400     | 120           |
| momentum v6       | 0.003       | 0.05        | 1.5      | 3          | 6           | 9           | 14400     | 120           |
| session_orb v1    | 0.006       | 0.05        |          |            |             |             | 14400     | 120           |
+-------------------+-------------+-------------+----------+------------+-------------+-------------+-----------+---------------+
```

**A `session_orb v1` não declara `stop_atr` nem `target_atr`** (`q02`): a geometria dela é
`range_risk_atr_min = 1` / `range_risk_atr_max = 2.5` com alvos **em R** (`target_r = 2`,
`target2_r = 4`). O pedido do brief (colar o `stop_atr`/`target_atr` dela) não tem resposta porque o
parâmetro não existe — a alavanca equivalente ali seria **subir `range_risk_atr_min`**, e isso é
outro experimento (CONCERN 5).

Digests dos pais que derivei, conferidos antes de escrever:

```
| mean_reversion v2 | hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f |
| mean_reversion v3 | hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f |
| momentum v6       | hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c       |
```

---

## 2. A TABELA DE PEDÁGIO **ANTES** (`q01`, `read_at = 2026-09-08T22:26:45,090832Z` = 19:26:45)

Todas as coortes fechadas das três estratégias com `n >= 5`. `risco%` é a **distância do stop em
fração do preço** (a grandeza da identidade, [[KB-0076]] com a correção da T3.40 §8b), não o ATR%.

```
+-------------------+-----------------+-----+-------------+---------------+-----------+-----------+-----------+-------------+-------------+---------------+---------+------------+----------+------+----------------+-------------------------+
|      versao       |     coorte      |  n  | atr_pct_p50 | risco_pct_p50 | custo_p25 | custo_p50 | custo_p75 | custo_medio | exp_bruta_r | exp_liquida_r | soma_r  | pf_liquido | pf_bruto | dias | perda_por_op_r | pedagio_sobre_bruto_pct |
+-------------------+-----------------+-----+-------------+---------------+-----------+-----------+-----------+-------------+-------------+---------------+---------+------------+----------+------+----------------+-------------------------+
| mean_reversion v1 | prospective     |  24 |     0.01053 |       0.01241 |    0.1445 |    0.1613 |    0.2114 |      0.1755 |      0.2250 |        0.0480 |    1.15 |     1.0851 |   1.4763 |    1 |        -0.0495 |                    78.0 |
| mean_reversion v1 | replay:d0f77894 |  37 |     0.00760 |       0.00869 |    0.1894 |    0.2290 |    0.2657 |      0.2263 |      0.3210 |        0.0938 |    3.47 |     1.1856 |   1.7999 |   11 |        -0.0948 |                    70.5 |
| mean_reversion v2 | replay:d570b19a |  17 |     0.01051 |       0.01066 |    0.1285 |    0.1871 |    0.1988 |      0.1685 |      0.4686 |        0.2998 |    5.10 |     1.7483 |   2.4100 |    7 |        -0.3001 |                    36.0 |
| mean_reversion v3 | replay:f4af4ffe |  11 |     0.01462 |       0.01511 |    0.0985 |    0.1333 |    0.1855 |      0.1452 |      0.6587 |        0.5131 |    5.64 |     2.6919 |   3.5380 |    4 |        -0.5135 |                    22.0 |
| momentum v1       | prospective     | 929 |     0.00898 |       0.01400 |    0.0946 |    0.1425 |    0.1956 |      0.1506 |     -0.0399 |       -0.1905 | -176.94 |     0.6131 |   0.8995 |    3 |         0.1904 |                   377.7 |
| momentum v2       | prospective     | 332 |     0.00967 |       0.01442 |    0.1016 |    0.1387 |    0.1843 |      0.1477 |     -0.0518 |       -0.2006 |  -66.59 |     0.6043 |   0.8730 |    1 |         0.1996 |                   285.0 |
| momentum v2       | replay:7598d6c4 |  23 |     0.00399 |       0.00659 |    0.2550 |    0.3030 |    0.3418 |      0.3248 |     -0.2816 |       -0.6064 |  -13.95 |     0.1967 |   0.4555 |    3 |         0.6064 |                   115.3 |
| momentum v2       | replay:f8d8279c | 222 |     0.00528 |       0.00788 |    0.1873 |    0.2539 |    0.3034 |      0.2524 |      0.0811 |       -0.1717 |  -38.13 |     0.6454 |   1.2413 |   24 |         0.1714 |                   311.4 |
| momentum v3       | prospective     | 313 |     0.00961 |       0.01439 |    0.1017 |    0.1390 |    0.1843 |      0.1481 |     -0.0667 |       -0.2158 |  -67.56 |     0.5785 |   0.8380 |    1 |         0.2148 |                   221.9 |
| momentum v6       | prospective     |  17 |     0.01106 |       0.01236 |    0.1059 |    0.1611 |    0.2363 |      0.1784 |     -0.2039 |       -0.3823 |   -6.50 |     0.4265 |   0.5965 |    1 |         0.3823 |                    87.5 |
| momentum v6       | replay:9a08835a | 195 |     0.00525 |       0.00778 |    0.1870 |    0.2568 |    0.3107 |      0.2557 |      0.2052 |       -0.0513 |  -10.01 |     0.9064 |   1.5485 |   24 |         0.0505 |                   124.6 |
| session_orb v1    | replay:3fb9dda2 |  20 |     0.00721 |       0.01370 |    0.1174 |    0.1466 |    0.1531 |      0.1428 |     -0.0501 |       -0.1928 |   -3.86 |     0.6616 |   0.8965 |    9 |         0.1930 |                   284.9 |
+-------------------+-----------------+-----+-------------+---------------+-----------+-----------+-----------+-------------+-------------+---------------+---------+------------+----------+------+----------------+-------------------------+
```

Leitura (é a razão de a tarefa existir):

- **A `momentum v6` no replay é o caso perfeito da hipótese**: bruto **+0,2052 R**, pedágio
  **0,2557 R**, líquido **−0,0513 R**. O pedágio vale **125 % do bruto** — a perda inteira é o
  pedágio, e um pedágio 1,5× ou 2× menor deveria, no papel, virar o sinal.
- **As `mean_reversion v2`/`v3` já estão positivas** (+0,2998 e +0,5131 R) e com pedágio pequeno
  (0,1685 e 0,1452 R): a T3.42 já cobrou pedágio delas por outro caminho (piso de ATR%).
- A `momentum v3` (a linha **`paper`**) prospectiva perde **−0,2158 R** com pedágio de 0,1481 R e
  bruto de **−0,0667 R**. Cortar pedágio ali não conserta nada, e isso está no §RESPOSTA.

---

## 3. DERIVAÇÃO E ATIVAÇÃO — os carimbos do `Registro de Tentativas`

### 3.1 Dry-runs (nada escrito) — **nenhuma recusa da tabela de faixas**

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py momentum v6 \
    --set stop_atr=2.25 --set target_atr=4.5 --set target2_atr=9 --set target3_atr=13.5 \
    --changelog "T3.47: stop largo x1,5 (pedagio dividido por 1,5)" --dry-run'
Tue Sep  8 22:27:41 UTC 2026
derivaria momentum v7 de v6 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c:
stop_atr 1.5 -> 2.25, target2_atr 6 -> 9, target3_atr 9 -> 13.5, target_atr 3 -> 4.5 [params_hash 5e456ae9eb5b]
exit=0

$ ... --set stop_atr=3 --set target_atr=6 --set target2_atr=12 --set target3_atr=18 ... --dry-run
Tue Sep  8 22:27:43 UTC 2026
derivaria momentum v7 de v6 (...) em code_ref ...ab2e0398...:
stop_atr 1.5 -> 3, target2_atr 6 -> 12, target3_atr 9 -> 18, target_atr 3 -> 6 [params_hash 69152dbc9173]
exit=0

$ ... mean_reversion v3 --set stop_atr=1.5 --set target_atr=2.25 --set target2_atr=3.75 ... --dry-run
Tue Sep  8 22:27:57 UTC 2026
derivaria mean_reversion v4 de v3 (...) em code_ref ...a970c9d9...:
stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash 1b868c55ebed]
exit=0
$ ... mean_reversion v3 --set stop_atr=2 --set target_atr=3 --set target2_atr=5 ... --dry-run
derivaria mean_reversion v4 de v3 (...): stop_atr 1 -> 2, target2_atr 2.5 -> 5, target_atr 1.5 -> 3 [params_hash dd8b22cd30a0]
$ ... mean_reversion v2 --set stop_atr=1.5 --set target_atr=2.25 --set target2_atr=3.75 ... --dry-run
derivaria mean_reversion v4 de v2 (...): stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash 11ce73ed48b5]
$ ... mean_reversion v2 --set stop_atr=2 --set target_atr=3 --set target2_atr=5 ... --dry-run
Tue Sep  8 22:28:04 UTC 2026
derivaria mean_reversion v4 de v2 (...): stop_atr 1 -> 2, target2_atr 2.5 -> 5, target_atr 1.5 -> 3 [params_hash 6b6168718cf2]
exit=0
```

**Por que a escada inteira e não só o stop:** manter os múltiplos de R do pai (o `momentum v6`
publica `alvo = target x {1, 2, 3}` e a `mean_reversion` `1,5 / 2,5`) é o que torna o contraste
"só a largura mudou". Multiplicar tudo pelo mesmo fator preserva a ordem estrita
`target_atr < target2_atr < target3_atr` que a `constraints_table.py` exige, e por isso **nenhum dos
seis dry-runs foi recusado** — o oposto do que aconteceu na T3.40, quando `--set target_atr=3.0`
sozinho quebrou a faixa. (`system_events` da minha janela não tem **nenhum**
`strategy_version_variant_refused`.)

### 3.2 Derivação e ativação (escrita)

```
Tue Sep  8 22:29:10 UTC 2026
derivada momentum v7 de v6 (purpose research_only, draft, nada ativado) em code_ref ...ab2e0398...:
stop_atr 1.5 -> 2.25, target2_atr 6 -> 9, target3_atr 9 -> 13.5, target_atr 3 -> 4.5 [params_hash 5e456ae9eb5b]
derivada momentum v8 de v6 (...): stop_atr 1.5 -> 3, target2_atr 6 -> 12, target3_atr 9 -> 18, target_atr 3 -> 6 [params_hash 69152dbc9173]
Tue Sep  8 22:29:14 UTC 2026

$ docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py momentum v7 --changelog "..." --dry-run
would activate momentum v7 (purpose research_only) with code_ref ...ab2e0398...ebaa40c (19 parameters)
$ ... (sem --dry-run)
activated momentum v7 (purpose research_only) at 2026-09-08T22:29:28.783999+00:00 with code_ref ...ab2e0398...
$ ... momentum v8 ...
activated momentum v8 (purpose research_only) at 2026-09-08T22:29:33.049734+00:00 with code_ref ...ab2e0398...

Tue Sep  8 22:38:13 UTC 2026
derivada mean_reversion v4 de v3 ...: stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash 1b868c55ebed]
derivada mean_reversion v5 de v3 ...: stop_atr 1 -> 2,   target2_atr 2.5 -> 5,    target_atr 1.5 -> 3    [params_hash dd8b22cd30a0]
derivada mean_reversion v6 de v2 ...: stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash 11ce73ed48b5]
derivada mean_reversion v7 de v2 ...: stop_atr 1 -> 2,   target2_atr 2.5 -> 5,    target_atr 1.5 -> 3    [params_hash 6b6168718cf2]
Tue Sep  8 22:38:21 UTC 2026

activated mean_reversion v4 (purpose research_only) at 2026-09-08T22:38:37.842745+00:00 with code_ref ...a970c9d9...
activated mean_reversion v5 (purpose research_only) at 2026-09-08T22:38:41.887854+00:00 with code_ref ...a970c9d9...
activated mean_reversion v6 (purpose research_only) at 2026-09-08T22:38:46.022557+00:00 with code_ref ...a970c9d9...
activated mean_reversion v7 (purpose research_only) at 2026-09-08T22:38:49.950926+00:00 with code_ref ...a970c9d9...
Tue Sep  8 22:38:50 UTC 2026
```

| variante | versão | pai | stop_atr | escada de alvos | **ativada (UTC)** | Brasília | `params_hash` | coorte de replay |
|---|---|---|---|---|---|---|---|---|
| C1 stop ×1,5 | `momentum v7` | `momentum v6` | 1,5 → **2,25** | 3/6/9 → **4,5/9/13,5** | 2026-09-08T22:29:28,783999Z | **19:29:28** | `5e456ae9eb5b` | `replay:293d98b7-90e1-4dfe-a604-60556f3b175e` |
| C2 stop ×2 | `momentum v8` | `momentum v6` | 1,5 → **3** | 3/6/9 → **6/12/18** | 2026-09-08T22:29:33,049734Z | **19:29:33** | `69152dbc9173` | `replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd` |
| A1 stop ×1,5 | `mean_reversion v4` | `mean_reversion v3` | 1 → **1,5** | 1,5/2,5 → **2,25/3,75** | 2026-09-08T22:38:37,842745Z | **19:38:37** | `1b868c55ebed` | `replay:af24ee08-01cf-41ba-9b7a-1b43172bea28` |
| A2 stop ×2 | `mean_reversion v5` | `mean_reversion v3` | 1 → **2** | 1,5/2,5 → **3/5** | 2026-09-08T22:38:41,887854Z | **19:38:41** | `dd8b22cd30a0` | `replay:66fa85cb-1d51-4330-a00b-00964b430ab4` |
| B1 stop ×1,5 | `mean_reversion v6` | `mean_reversion v2` | 1 → **1,5** | 1,5/2,5 → **2,25/3,75** | 2026-09-08T22:38:46,022557Z | **19:38:46** | `11ce73ed48b5` | `replay:9d99748b-21b9-44a7-8980-32c37b931e6e` |
| B2 stop ×2 | `mean_reversion v7` | `mean_reversion v2` | 1 → **2** | 1,5/2,5 → **3/5** | 2026-09-08T22:38:49,950926Z | **19:38:49** | `6b6168718cf2` | `replay:264b227f-5bc0-4930-8c5b-2e883c0a858e` |

**A ativação preservou o conteúdo próprio e a linhagem** (`q15`):

```
| mean_reversion v4 | active | research_only | 0.01  | 1.5  | 2.25 | 3.75 |      | variante de v3 | derived_from=v3 | overrides=stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=1b868c55ebed |
| mean_reversion v5 | active | research_only | 0.01  | 2    | 3    | 5    |      | variante de v3 | derived_from=v3 | overrides=stop_atr=2,target2_atr=5,target_atr=3 | params_hash=dd8b22cd30a0 |
| mean_reversion v6 | active | research_only | 0.008 | 1.5  | 2.25 | 3.75 |      | variante de v2 | derived_from=v2 | overrides=stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=11ce73ed48b5 |
| mean_reversion v7 | active | research_only | 0.008 | 2    | 3    | 5    |      | variante de v2 | derived_from=v2 | overrides=stop_atr=2,target2_atr=5,target_atr=3 | params_hash=6b6168718cf2 |
| momentum v7       | active | research_only | 0.003 | 2.25 | 4.5  | 9    | 13.5 | variante de v6 | derived_from=v6 | overrides=stop_atr=2.25,... | params_hash=5e456ae9eb5b |
| momentum v8       | active | research_only | 0.003 | 3    | 6    | 12   | 18   | variante de v6 | derived_from=v6 | overrides=stop_atr=3,...    | params_hash=69152dbc9173 |
```

E o `code_ref` de cada variante é **idêntico ao do seu pai** (`q16` §4):

```
| mean_reversion v4/v5/v6/v7 | code_ref_igual_ao_pai = t | sufixo 239dadc3f0bd395f |
| momentum v7/v8             | code_ref_igual_ao_pai = t | sufixo 391bdb238ebaa40c |
```

---

## 4. OS DOZE REPLAYS (recibos verbatim, `q14`)

Todos com `--markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 --explain-ledger` e `--cohort`
explícita, em duas fatias contíguas (2026-08-08→08-23 e 08-23→09-08).

```
+-----------------+-----+------------+------------+------+------+-----+-----+--------+---------+----+-----+---------------------------------------------------------------+-----+
|     coorte      | ver |     de     |    ate     | mkts | bars | sig | out | aberto |   seg   | wk | lag |                            estados                            | err |
+-----------------+-----+------------+------------+------+------+-----+-----+--------+---------+----+-----+---------------------------------------------------------------+-----+
| replay:af24ee08 | v4  | 2026-08-08 | 2026-08-23 |    4 | 5760 |   9 |   9 |      0 |  90.639 |  3 |   2 | {"triggered": 18, "unavailable": 448, "not_triggered": 5294}  |   0 |
| replay:af24ee08 | v4  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  10 |  10 |      0 |  99.280 |  3 |   2 | {"triggered": 1, "not_triggered": 6143}                       |   0 |
| replay:66fa85cb | v5  | 2026-08-08 | 2026-08-23 |    4 | 5760 |   8 |   8 |      0 |  86.558 |  3 |   2 | {"triggered": 18, "unavailable": 448, "not_triggered": 5294}  |   0 |
| replay:66fa85cb | v5  | 2026-08-23 | 2026-09-08 |    4 | 6144 |   9 |   9 |      0 | 100.380 |  3 |   2 | {"triggered": 1, "not_triggered": 6143}                       |   0 |
| replay:9d99748b | v6  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  11 |  11 |      0 |  95.509 |  3 |   2 | {"triggered": 22, "unavailable": 448, "not_triggered": 5290}  |   0 |
| replay:9d99748b | v6  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  15 |  15 |      0 | 103.494 |  3 |   2 | {"triggered": 8, "not_triggered": 6136}                       |   0 |
| replay:293d98b7 | v7  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  50 |  50 |      0 |  99.186 |  3 |   2 | {"triggered": 180, "unavailable": 448, "not_triggered": 5132} |   0 |
| replay:264b227f | v7  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  10 |  10 |      0 |  93.142 |  3 |   2 | {"triggered": 22, "unavailable": 448, "not_triggered": 5290}  |   0 |
| replay:293d98b7 | v7  | 2026-08-23 | 2026-09-08 |    4 | 6144 | 184 | 184 |      0 | 117.772 |  3 |   2 | {"triggered": 280, "not_triggered": 5864}                     |   0 |
| replay:264b227f | v7  | 2026-08-23 | 2026-09-08 |    4 | 6144 |  14 |  14 |      0 | 101.290 |  3 |   2 | {"triggered": 8, "not_triggered": 6136}                       |   0 |
| replay:ee11d60b | v8  | 2026-08-08 | 2026-08-23 |    4 | 5760 |  50 |  50 |      0 | 106.530 |  3 |   2 | {"triggered": 180, "unavailable": 448, "not_triggered": 5132} |   0 |
| replay:ee11d60b | v8  | 2026-08-23 | 2026-09-08 |    4 | 6144 | 181 | 181 |      0 | 104.138 |  3 |   2 | {"triggered": 280, "not_triggered": 5864}                     |   0 |
```

**Armadilha do denominador (a mesma da T3.33e, T3.40 e T3.42):** `sig` conta a **coorte inteira**;
50 + 184 não são 234 — a população da `momentum v7` é **184**. `triggered` é por fatia, e é a prova
de que **as portas de entrada não se mexeram**: 180 + 280 = **460** nas duas variantes de `momentum`,
exatamente o número do pai `v6`; 22 + 8 = **30** nas duas de `mean_reversion v2` e 18 + 1 = **19** nas
duas de `mean_reversion v3`, exatamente os números dos pais na T3.42. **Um stop mais largo não muda
quem entra, só o que acontece depois.**

A diferença entre `triggered` e a população (460 → 184/181; 30 → 15/14) é **ocupação de slot**: com
stop e alvo mais longe, a operação dura mais e o segundo sinal do mesmo mercado é recusado. É a
única porta que o stop largo mexe, e ela **reduz** a frequência.

**Livros-razão:** 12 arquivos `/tmp/t347-*.jsonl`, `bars=lines` em todos (5760 e 6144 por fatia,
11 904 linhas por variante). Os recibos de linha estão nas saídas verbatim acima.

### `system_events` da janela (`q14`, trecho)

```
| info | activate_strategy_version | strategy_version_variant_derived | momentum v7 derived from v6 (variante, purpose research_only) | 2026-09-08 22:29:12.060311+00 |
| info | activate_strategy_version | strategy_version_variant_derived | momentum v8 derived from v6 (variante, purpose research_only) | 2026-09-08 22:29:14.025607+00 |
| info | activate_strategy_version | strategy_version_activated       | momentum v7 (purpose research_only) activated with its already-copied code_ref | 2026-09-08 22:29:28.783999+00 |
| info | activate_strategy_version | strategy_version_activated       | momentum v8 (purpose research_only) activated with its already-copied code_ref | 2026-09-08 22:29:33.049734+00 |
| info | activate_strategy_version | strategy_version_activated       | trendline_breakout v1 (purpose research_only) activated ...    | 2026-09-08 22:29:52.701952+00 |   <- NÃO É MINHA (T3.34b)
| info | replay_engine             | replay_run_finished              | replay momentum v7 4 mercados 08-08..08-23: 5760 barras        | 2026-09-08 22:31:43.112201+00 |
| info | replay_engine             | replay_run_finished              | replay momentum v7 4 mercados 08-23..09-08: 6144 barras        | 2026-09-08 22:33:55.582127+00 |
| info | replay_engine             | replay_run_finished              | replay momentum v8 4 mercados 08-08..08-23: 5760 barras        | 2026-09-08 22:36:00.470512+00 |
| info | replay_engine             | replay_run_finished              | replay momentum v8 4 mercados 08-23..09-08: 6144 barras        | 2026-09-08 22:37:58.583624+00 |
| info | activate_strategy_version | strategy_version_variant_derived | mean_reversion v4 derived from v3                              | 2026-09-08 22:38:15.279787+00 |
| info | activate_strategy_version | strategy_version_variant_derived | mean_reversion v5 derived from v3                              | 2026-09-08 22:38:17.241534+00 |
| info | activate_strategy_version | strategy_version_variant_derived | mean_reversion v6 derived from v2                              | 2026-09-08 22:38:19.644613+00 |
| info | activate_strategy_version | strategy_version_variant_derived | mean_reversion v7 derived from v2                              | 2026-09-08 22:38:21.6033+00   |
| info | activate_strategy_version | strategy_version_activated       | mean_reversion v4 ... | 2026-09-08 22:38:37.842745+00 |
| info | activate_strategy_version | strategy_version_activated       | mean_reversion v5 ... | 2026-09-08 22:38:41.887854+00 |
| info | activate_strategy_version | strategy_version_activated       | mean_reversion v6 ... | 2026-09-08 22:38:46.022557+00 |
| info | activate_strategy_version | strategy_version_activated       | mean_reversion v7 ... | 2026-09-08 22:38:49.950926+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v4 ... 08-08..08-23 | 2026-09-08 22:40:42.255489+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v4 ... 08-23..09-08 | 2026-09-08 22:42:34.020103+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v5 ... 08-08..08-23 | 2026-09-08 22:44:12.693583+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v5 ... 08-23..09-08 | 2026-09-08 22:46:04.777619+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v6 ... 08-08..08-23 | 2026-09-08 22:47:52.625569+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v6 ... 08-23..09-08 | 2026-09-08 22:49:49.431886+00 |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v7 ... 08-08..08-23 | 2026-09-08 22:51:35.79656+00  |
| info | replay_engine             | replay_run_finished              | replay mean_reversion v7 ... 08-23..09-08 | 2026-09-08 22:53:31.147413+00 |
```

Três linhas de `replay_run_finished` de `trendline_breakout v1` (22:31:08, 22:33:27, 22:36:05) sao de
**outra tarefa rodando no mesmo container ao mesmo tempo** — CONCERN 6.

### Isolamento — a coorte é a cerca, e ela segurou (`q15`, `read_at = 2026-09-08T22:57Z`)

```
| outbox_das_coortes | outbox_pendente_total |
|                  0 |                     0 |

| mean_reversion v4 | prospective                                 |   3 | 2026-09-08 22:46:40.900209+00 |
| mean_reversion v4 | replay:af24ee08-01cf-41ba-9b7a-1b43172bea28 |  10 | 2026-08-20 19:30:02+00        |
| mean_reversion v5 | prospective                                 |   3 | 2026-09-08 22:46:41.046463+00 |
| mean_reversion v5 | replay:66fa85cb-1d51-4330-a00b-00964b430ab4 |   9 | 2026-08-20 19:30:02+00        |
| mean_reversion v6 | prospective                                 |   4 | 2026-09-08 22:45:51.754385+00 |
| mean_reversion v6 | replay:9d99748b-21b9-44a7-8980-32c37b931e6e |  15 | 2026-08-20 19:30:02+00        |
| mean_reversion v7 | prospective                                 |   4 | 2026-09-08 22:45:52.237354+00 |
| mean_reversion v7 | replay:264b227f-5bc0-4930-8c5b-2e883c0a858e |  14 | 2026-08-20 19:30:02+00        |
| momentum v7       | prospective                                 |   7 | 2026-09-08 22:30:19.991609+00 |
| momentum v7       | replay:293d98b7-90e1-4dfe-a604-60556f3b175e | 184 | 2026-08-11 14:15:02+00        |
| momentum v8       | prospective                                 |   7 | 2026-09-08 22:30:20.137493+00 |
| momentum v8       | replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd | 181 | 2026-08-11 14:15:02+00        |
```

**Zero linhas de `shadow_outbox` para as seis coortes de replay** e zero pendentes na fila inteira.
Os sinais `prospective` são o que "entrar no Lab" significa: o primeiro da `momentum v7` saiu
**46 s** depois da ativação; o da `mean_reversion v6`, **7 min 5 s** depois.

### Capacidade — vigia (a linha `paper` continua primeira, `outbox_lag_s` 0,0 o tempo todo)

| relógio (UTC) | marco | `evaluated_bars` | `outbox_lag_s` | `outbox_pending` | `errors` | `open_trackings` |
|---|---|---:|---:|---:|---:|---:|
| 22:28:41 | antes de qualquer ativação | 1 381 | 0,0 | 0 | 0 | 55 |
| 22:29:33 | logo após ativar `momentum v7`/`v8` | 1 381 | 0,0 | 0 | 0 | 55 |
| 22:37:58 | após os quatro replays de `momentum` | 4 212 | 0,0 | 0 | 0 | 61 |
| 22:38:50 | logo após ativar as quatro `mean_reversion` | 4 212 | 0,0 | 0 | 0 | 61 |
| 22:53:31 | após os oito replays de `mean_reversion` | 9 126 | 0,0 | 0 | 0 | 74 |
| 23:07:30 | fechamento (`/ready` **200**) | 13 050 | 0,0 | 0 | 0 | 71 |

`hunter-strategy-worker-1`, `hunter-api-1` e `hunter-web-1` `healthy` em todas as amostras, sempre em
`2e39774`. **Nenhum `errors` em nenhuma leitura.**

Roster final (`q15`, ordenação reproduzida de `roster.py:110-129`):

```
 1 mean_reversion     v1 research_only
 2 mean_reversion     v2 research_only ecd26dfc017a
 3 mean_reversion     v3 research_only a71311773886
 4 mean_reversion     v4 research_only 1b868c55ebed   <- minha
 5 mean_reversion     v5 research_only dd8b22cd30a0   <- minha
 6 mean_reversion     v6 research_only 11ce73ed48b5   <- minha
 7 mean_reversion     v7 research_only 6b6168718cf2   <- minha
 8 momentum           v3 paper                        <- paper primeiro dentro da chave (A3 da T3.26c)
 9 momentum           v2 research_only
10 momentum           v4 research_only
11 momentum           v6 research_only 8cb1aa497956
12 momentum           v7 research_only 5e456ae9eb5b   <- minha
13 momentum           v8 research_only 69152dbc9173   <- minha
14 session_orb        v1 research_only
15 trendline_breakout v1 research_only                <- de outra tarefa (T3.34b)
16 volume_anomaly     v2 research_only
```

**Nove versões viraram dezesseis** (seis minhas e uma da T3.34b). Carga nova declarada: CONCERN 4.

---

## 5. POPULAÇÕES (`q10`, `read_at = 2026-09-08T22:54:05,204105Z` = 19:54:05)

Mesma janela, mesmos quatro mercados, mesmo `decision_lag_s = 2`, mesmos `workers = 3`.

```
+-------------------+----------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+---------------+
|      versao       |  coorte  | decisoes | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | pf_bruto | dias | risco_pct_p50 |
+-------------------+----------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+---------------+
| mean_reversion v1 | d0f77894 |       37 |         37 |      0.3210 |  0.2263 |        0.0938 |   3.47 |       40.5 |     1.1856 |   1.7999 |   11 |       0.00869 |
| mean_reversion v2 | d570b19a |       17 |         17 |      0.4686 |  0.1685 |        0.2998 |   5.10 |       41.2 |     1.7483 |   2.4100 |    7 |       0.01066 |
| mean_reversion v3 | f4af4ffe |       11 |         11 |      0.6587 |  0.1452 |        0.5131 |   5.64 |       36.4 |     2.6919 |   3.5380 |    4 |       0.01511 |
| mean_reversion v4 | af24ee08 |       10 |         10 |      0.4251 |  0.0897 |        0.3337 |   3.34 |       10.0 |     2.4787 |   3.1259 |    4 |       0.02346 |
| mean_reversion v5 | 66fa85cb |        9 |          9 |      0.5541 |  0.0697 |        0.4830 |   4.35 |       11.1 |    21.1793 |  51.5892 |    4 |       0.02973 |
| mean_reversion v6 | 9d99748b |       15 |         15 |      0.3953 |  0.1075 |        0.2861 |   4.29 |        6.7 |     2.2820 |   3.0027 |    7 |       0.01631 |
| mean_reversion v7 | 264b227f |       14 |         14 |      0.4301 |  0.0838 |        0.3450 |   4.83 |        7.1 |     4.7605 |   6.6357 |    7 |       0.02077 |
| momentum v6       | 9a08835a |      196 |        195 |      0.2028 |  0.2554 |       -0.0513 | -10.01 |       27.0 |     0.9064 |   1.5431 |   24 |       0.00779 |
| momentum v7       | 293d98b7 |      184 |        183 |      0.1159 |  0.1731 |       -0.0568 | -10.39 |       14.7 |     0.8590 |   1.4131 |   24 |       0.01136 |
| momentum v8       | ee11d60b |      181 |        181 |      0.1013 |  0.1305 |       -0.0299 |  -5.42 |       11.6 |     0.9056 |   1.4519 |   24 |       0.01496 |
+-------------------+----------+----------+------------+-------------+---------+---------------+--------+------------+------------+----------+------+---------------+
```

**Três leituras que decidem a tarefa inteira:**

1. **O pedágio obedece.** `momentum` 0,2554 → 0,1731 → 0,1305 (÷1,48 e ÷1,96); `mean_reversion v2`
   0,1685 → 0,1075 → 0,0838 (÷1,57 e ÷2,01); `v3` 0,1452 → 0,0897 → 0,0697 (÷1,62 e ÷2,08). A
   identidade `custo_R = 0,0020 / risco%` está certa até a terceira casa (§7).
2. **O bruto obedece na mesma proporção.** `momentum` 0,2028 → 0,1159 → 0,1013. Multiplicando cada
   um pelo seu fator de stop para trazer tudo à régua do pai: **0,2028 / 0,1739 / 0,2026** de bruto
   e **0,2554 / 0,2597 / 0,2610** de pedágio. Em preço, **nada mudou**: nem a vantagem, nem a
   despesa. O stop largo é uma **mudança de unidade**, e por isso `−0,0513 → −0,0568 → −0,0299` não
   troca de sinal.
3. **A taxa de acerto desaba** (`momentum` 27,0 % → 14,7 % → 11,6 %; `mean_reversion` 41,2 % →
   6,7 % → 7,1 %), porque o alvo se afasta junto com o stop e o horizonte de 4 h continua onde
   estava. Em `mean_reversion v6`/`v7`, **80 % e 86 % das saídas são por horizonte**.

---

## 6. AVALIAÇÃO PAREADA (`q11`, `read_at = 2026-09-08T22:55:29,145996Z` = 19:55:29)

### 6.1 Os quatro grupos por par

```
+-----------------------------+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------+
|           rotulo            |           grupo            |  n  | avaliaveis | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | dias |
+-----------------------------+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------+
| A1 mr v3 -> v4 (stop x1,5)  | pai pareado com a variante |   9 |          9 |      0.5745 |  0.1481 |        0.4258 |   3.83 |       33.3 |    4 |
| A1 mr v3 -> v4 (stop x1,5)  | variante pareada com o pai |   9 |          9 |      0.5695 |  0.0946 |        0.4730 |   4.26 |       11.1 |    4 |
| A1 mr v3 -> v4 (stop x1,5)  | pai SEM par na variante    |   2 |          2 |      1.0378 |  0.1322 |        0.9056 |   1.81 |       50.0 |    2 |
| A1 mr v3 -> v4 (stop x1,5)  | variante SEM par no pai    |   1 |          1 |     -0.8741 |  0.0461 |       -0.9201 |  -0.92 |        0.0 |    1 |
| A2 mr v3 -> v5 (stop x2)    | pai pareado com a variante |   9 |          9 |      0.5745 |  0.1481 |        0.4258 |   3.83 |       33.3 |    4 |
| A2 mr v3 -> v5 (stop x2)    | variante pareada com o pai |   9 |          9 |      0.5541 |  0.0697 |        0.4830 |   4.35 |       11.1 |    4 |
| A2 mr v3 -> v5 (stop x2)    | pai SEM par na variante    |   2 |          2 |      1.0378 |  0.1322 |        0.9056 |   1.81 |       50.0 |    2 |
| B1 mr v2 -> v6 (stop x1,5)  | pai pareado com a variante |  14 |         14 |      0.4873 |  0.1694 |        0.3175 |   4.45 |       42.9 |    7 |
| B1 mr v2 -> v6 (stop x1,5)  | variante pareada com o pai |  14 |         14 |      0.4859 |  0.1119 |        0.3722 |   5.21 |        7.1 |    7 |
| B1 mr v2 -> v6 (stop x1,5)  | pai SEM par na variante    |   3 |          3 |      0.3815 |  0.1645 |        0.2171 |   0.65 |       33.3 |    3 |
| B1 mr v2 -> v6 (stop x1,5)  | variante SEM par no pai    |   1 |          1 |     -0.8741 |  0.0461 |       -0.9201 |  -0.92 |        0.0 |    1 |
| B2 mr v2 -> v7 (stop x2)    | pai pareado com a variante |  14 |         14 |      0.4873 |  0.1694 |        0.3175 |   4.45 |       42.9 |    7 |
| B2 mr v2 -> v7 (stop x2)    | variante pareada com o pai |  14 |         14 |      0.4301 |  0.0838 |        0.3450 |   4.83 |        7.1 |    7 |
| B2 mr v2 -> v7 (stop x2)    | pai SEM par na variante    |   3 |          3 |      0.3815 |  0.1645 |        0.2171 |   0.65 |       33.3 |    3 |
| C1 mom v6 -> v7 (stop x1,5) | pai pareado com a variante | 182 |        181 |      0.2007 |  0.2622 |       -0.0603 | -10.91 |       26.9 |   24 |
| C1 mom v6 -> v7 (stop x1,5) | variante pareada com o pai | 182 |        181 |      0.1095 |  0.1741 |       -0.0643 | -11.63 |       14.3 |   24 |
| C1 mom v6 -> v7 (stop x1,5) | pai SEM par na variante    |  14 |         14 |      0.2310 |  0.1665 |        0.0645 |   0.90 |       28.6 |    6 |
| C1 mom v6 -> v7 (stop x1,5) | variante SEM par no pai    |   2 |          2 |      0.7062 |  0.0862 |        0.6200 |   1.24 |       50.0 |    2 |
| C2 mom v6 -> v8 (stop x2)   | pai pareado com a variante | 180 |        180 |      0.2188 |  0.2623 |       -0.0444 |  -7.99 |       27.8 |   24 |
| C2 mom v6 -> v8 (stop x2)   | variante pareada com o pai | 180 |        180 |      0.1033 |  0.1308 |       -0.0282 |  -5.08 |       11.7 |   24 |
| C2 mom v6 -> v8 (stop x2)   | pai SEM par na variante    |  16 |         15 |      0.0234 |  0.1782 |       -0.1346 |  -2.02 |       18.8 |    8 |
| C2 mom v6 -> v8 (stop x2)   | variante SEM par no pai    |   1 |          1 |     -0.2433 |  0.0886 |       -0.3318 |  -0.33 |        0.0 |    1 |
+-----------------------------+----------------------------+-----+------------+-------------+---------+---------------+--------+------------+------+
```

O contraste é limpo: **182 de 184** (`momentum v7`), **180 de 181** (`v8`), **14 de 15** e **9 de 10**
pareiam. Os poucos sem par são o efeito de slot descrito em §4.

### 6.2 O estimando — Δ pareado decisão a decisão

```
+-----------------------------+-------+-------------------+------------------+---------------------+---------------------+-------------------+--------------+------+
|           rotulo            | pares | delta_liq_medio_r | delta_liq_soma_r | delta_bruto_medio_r | delta_custo_medio_r | razao_risco_medio | mesmo_motivo | dias |
+-----------------------------+-------+-------------------+------------------+---------------------+---------------------+-------------------+--------------+------+
| A1 mr v3 -> v4 (stop x1,5)  |     9 |            0.0472 |             0.42 |             -0.0050 |             -0.0535 |            1.5753 |            5 |    4 |
| A2 mr v3 -> v5 (stop x2)    |     9 |            0.0572 |             0.51 |             -0.0203 |             -0.0784 |            2.1506 |            4 |    4 |
| B1 mr v2 -> v6 (stop x1,5)  |    14 |            0.0547 |             0.77 |             -0.0013 |             -0.0575 |            1.5304 |            6 |    7 |
| B2 mr v2 -> v7 (stop x2)    |    14 |            0.0275 |             0.39 |             -0.0571 |             -0.0856 |            2.0609 |            5 |    7 |
| C1 mom v6 -> v7 (stop x1,5) |   181 |           -0.0040 |            -0.72 |             -0.0922 |             -0.0882 |            1.5017 |          131 |   24 |
| C2 mom v6 -> v8 (stop x2)   |   180 |            0.0161 |             2.90 |             -0.1155 |             -0.1315 |            2.0030 |          114 |   24 |
+-----------------------------+-------+-------------------+------------------+---------------------+---------------------+-------------------+--------------+------+
```

`razao_risco_medio` = **1,50 / 2,15 / 1,53 / 2,06 / 1,50 / 2,00**: a prova, par a par, de que o stop
realmente alargou pelo fator pedido (e de que a variação em torno dele é o desvio entre o fechamento
da decisão e o preço de entrada, o mesmo efeito que a T3.42 mediu como "0,61 a 1,42 ATR").

**A conta que resume a tarefa** (economia de pedágio contra perda no bruto, par a par):

| contraste | economia de pedágio | perda no bruto | **Δ líquido** | % da economia que sobra | Δ USDT/op |
|---|---:|---:|---:|---:|---:|
| A1 `mr v3 → v4` ×1,5 | 0,0535 | 0,0050 | **+0,0472** | **88,2 %** | +2,28 |
| A2 `mr v3 → v5` ×2 | 0,0784 | 0,0203 | **+0,0572** | **73,0 %** | +2,76 |
| B1 `mr v2 → v6` ×1,5 | 0,0575 | 0,0013 | **+0,0547** | **95,1 %** | +2,64 |
| B2 `mr v2 → v7` ×2 | 0,0856 | 0,0571 | **+0,0275** | 32,1 % | +1,33 |
| C1 `mom v6 → v7` ×1,5 | 0,0882 | 0,0922 | **−0,0040** | **−4,5 %** | −0,19 |
| C2 `mom v6 → v8` ×2 | 0,1315 | 0,1155 | **+0,0161** | 12,2 % | +0,78 |

(1 R = 48,33 USDT, a conversão declarada do Lab na [[KB-0076]]: 0,25 % de risco sobre 19 333 USDT.)

**No `momentum`, 88 % a 105 % da economia de pedágio é devolvida no bruto. Na `mean_reversion`,
73 % a 95 % dela sobrevive** — e a diferença tem causa medida, não retórica: veja a matriz de
transição em §6.4.

### 6.3 O IC 95 % por bloco de dia (bootstrap pareado, 10 000 reamostragens, semente 20260908)

```
$ uv run python .claude/state/exp-drafts/t347-blocos/blocos_pareado.py .claude/state/exp-drafts/t347-blocos/pares.csv
A1 | pares   9 | dias  4 | delta +0.0472 | IC95 [-0.1338; +0.2843] | reamostragens 10000
A2 | pares   9 | dias  4 | delta +0.0572 | IC95 [-0.3176; +0.1919] | reamostragens 10000
B1 | pares  14 | dias  7 | delta +0.0547 | IC95 [-0.2122; +0.5274] | reamostragens 10000
B2 | pares  14 | dias  7 | delta +0.0275 | IC95 [-0.3137; +0.4616] | reamostragens 10000
C1 | pares 181 | dias 24 | delta -0.0040 | IC95 [-0.1556; +0.1276] | reamostragens 10000
C2 | pares 180 | dias 24 | delta +0.0161 | IC95 [-0.1761; +0.1851] | reamostragens 10000
```

Os seis Δ batem casa a casa com o SQL (conferência cruzada do dump). **Os seis intervalos contêm
zero** — nenhuma das variantes se distingue do próprio pai quando o dia é o bloco.

### 6.4 De onde vem (e para onde vai) cada R — matriz de transição (`q13`)

`momentum v6 → v8` (stop ×2), os 180 pares:

```
| motivo_pai  | motivo_var  | n  | delta_liq_medio_r | delta_soma_r |
| invalidated | invalidated | 72 |            0.3168 |        22.81 |   <- a invalidação não escala: em R ela encolhe
| stop        | invalidated | 31 |            0.5812 |        18.02 |   <- stops que viraram invalidação (mais barata)
| stop        | expired     |  6 |            1.0947 |         6.57 |
| target      | target      | 21 |            0.1774 |         3.72 |
| stop        | stop        |  5 |            0.0896 |         0.45 |
| expired     | expired     | 16 |           -0.1428 |        -2.28 |
| target      | invalidated |  4 |           -2.1150 |        -8.46 |   <- ganhadores devolvidos
| target      | stop        |  4 |           -2.7536 |       -11.01 |
| target      | expired     | 21 |           -1.2811 |       -26.90 |
```

**+51,57 R de um lado, −48,65 R do outro, saldo +2,90 R em 180 operações.** O mecanismo é exatamente
este: o stop largo **salva 41 stops** (31 viram invalidação, 6 viram horizonte, 5 continuam stop mais
barato) e **encolhe em R o preço das 72 invalidações** — e paga por isso com **29 ganhadores** que
não alcançam mais o alvo (que também se afastou). Não é um efeito de custo; é uma troca de
distribuição.

`mean_reversion v2 → v6` (stop ×1,5), os 14 pares:

```
| stop    | expired |  3 |  1.4452 |  4.34 |
| target  | target  |  1 |  0.0883 |  0.09 |
| stop    | stop    |  2 |  0.0293 |  0.06 |
| expired | expired |  3 | -0.3363 | -1.01 |
| target  | expired |  5 | -0.5415 | -2.71 |
```

**Aqui o saldo é +0,77 R em 14 operações** e vem de **3 stops que viraram saída por horizonte
lucrativa**. É o mesmo mecanismo, com uma diferença crucial de contexto: a `mean_reversion_v1`
**não tem invalidação** (0 em todas as coortes) e o alvo dela era perto (1,5 ATR), então afastá-lo
custa menos ganhadores. E `n = 14`.

### 6.5 Motivos de saída, população inteira (`q13`)

```
| coorte (versao)          | motivo      |   n | pct  | r_liq_medio | r_liq_soma |
| 9a08835a (mom v6, pai)   | invalidated |  82 | 41.8 |     -0.6259 |     -50.70 |
| 9a08835a                 | target      |  53 | 27.0 |      1.7011 |      90.16 |
| 9a08835a                 | stop        |  45 | 23.0 |     -1.1921 |     -53.65 |
| 9a08835a                 | expired     |  16 |  8.2 |      0.2610 |       4.18 |
| 293d98b7 (mom v7, x1,5)  | invalidated |  99 | 53.8 |     -0.5044 |     -49.43 |
| 293d98b7                 | expired     |  39 | 21.2 |      0.3423 |      13.35 |
| 293d98b7                 | target      |  27 | 14.7 |      1.7418 |      47.03 |
| 293d98b7                 | stop        |  19 | 10.3 |     -1.1229 |     -21.34 |
| ee11d60b (mom v8, x2)    | invalidated | 108 | 59.7 |     -0.4192 |     -45.27 |
| ee11d60b                 | expired     |  43 | 23.8 |      0.2970 |      12.77 |
| ee11d60b                 | target      |  21 | 11.6 |      1.7527 |      36.81 |
| ee11d60b                 | stop        |   9 |  5.0 |     -1.0803 |      -9.72 |
```

**O stop deixa de ser o modo de morrer** (45 → 19 → 9 saídas por stop) e a invalidação vira quase
60 % do livro. A soma perdida na invalidação cai pouco (−50,70 → −45,27 R) porque o **número** de
invalidações sobe junto: a `momentum_v1` invalida em `close_below prior_max`, um nível **estrutural
que não escala com o stop** — quanto mais largo o stop, mais operações morrem pela invalidação antes
de o stop ser tocado. É a resposta à pergunta "o stop largo dá mais espaço?": **dá, e a invalidação
toma o espaço de volta.**

### 6.6 R por dia (`q17`) — `momentum`, 24 dias

```
|    dia     | n_v6 |  r_v6  | n_v7 | r_v7  | n_v8 | r_v8  |
| 2026-08-19 |   10 |  10.46 |   10 | 12.03 |   10 | 11.86 |
| 2026-08-20 |   15 |   7.40 |   11 |  8.03 |   11 |  5.63 |
| 2026-08-21 |   16 |  13.09 |   14 |  5.93 |   14 |  5.82 |   <- o melhor dia do pai perde 7,3 R
| 2026-08-24 |   17 | -14.52 |   17 | -9.94 |   15 | -5.83 |   <- o pior dia do pai melhora 8,7 R
| 2026-08-27 |   10 |   9.47 |   10 |  2.93 |   10 | -0.70 |   <- e este vira negativo
| 2026-08-28 |    7 |  -5.76 |    7 | -4.36 |    7 | -3.22 |
| 2026-09-02 |    7 |  -5.69 |    7 | -4.43 |    7 | -3.57 |
| 2026-09-07 |    7 |  -5.30 |    6 | -5.32 |    6 | -3.86 |
```

(a tabela completa das 24 linhas está na saída do `q17`.) O padrão é limpo e é o de **compressão de
variância**: em **todos** os dias ruins o stop largo perde menos, em **todos** os dias muito bons
ganha menos. Isso é o que uma redução de exposição faz — e é por isso que o §RESPOSTA diz que
alargar o stop com `risk_per_trade_pct` fixo é, em dinheiro, quase indistinguível de **reduzir o
tamanho**.

---

## 7. A IDENTIDADE DO PEDÁGIO, CONFERIDA DECISÃO A DECISÃO (`q16`)

`custo_R previsto = 0,0020 / risco%`, com `risco%` **medido** (não suposto).

```
+----------+-----+--------------------+------------------+----------------------+---------------------+----------------------+------------------------+----------------------+
|  coorte  |  n  | custo_medio_medido | custo_max_medido | custo_medio_previsto | maior_erro_absoluto | stop_atr_efetivo_min | stop_atr_efetivo_medio | stop_atr_efetivo_max |
+----------+-----+--------------------+------------------+----------------------+---------------------+----------------------+------------------------+----------------------+
| 9a08835a |  196|             0.2554 |           0.6879 |               0.2553 |             0.00338 |               0.7630 |                 1.5409 |               2.4898 |
| 293d98b7 |  184|             0.1731 |           0.3828 |               0.1731 |             0.00278 |               1.5183 |                 2.2961 |               3.2375 |
| ee11d60b |  181|             0.1305 |           0.2652 |               0.1305 |             0.00255 |               2.2735 |                 3.0466 |               3.9853 |
| d570b19a |   17|             0.1685 |           0.2690 |               0.1682 |             0.00176 |               0.6063 |                 0.9766 |               1.2498 |
| 9d99748b |   15|             0.1075 |           0.1728 |               0.1072 |             0.00139 |               1.1136 |                 1.4903 |               1.7488 |
| 264b227f |   14|             0.0838 |           0.1279 |               0.0834 |             0.00139 |               1.6208 |                 1.9813 |               2.2477 |
| f4af4ffe |   11|             0.1452 |           0.2690 |               0.1446 |             0.00176 |               0.6063 |                 0.9039 |               1.0775 |
| af24ee08 |   10|             0.0897 |           0.1575 |               0.0894 |             0.00139 |               1.1136 |                 1.4247 |               1.6251 |
| 66fa85cb |    9|             0.0697 |           0.1113 |               0.0692 |             0.00139 |               1.6208 |                 1.9037 |               2.0764 |
+----------+-----+--------------------+------------------+----------------------+---------------------+----------------------+------------------------+----------------------+
```

**A identidade acerta com erro máximo de 0,0034 R** em 637 decisões. E `stop_atr_efetivo` (o risco
inicial dividido por `ATR% × preço`) mostra a dispersão real: a `momentum v8` declara `stop_atr = 3`
e entrega **2,27 a 3,99** — o mesmo desvio entre o fechamento da decisão e o preço de entrada que a
T3.42 registrou (CONCERN 3 dela). **"Pedágio ÷2" é média, não garantia**, e continua sendo.

## 8. C5 — o que uma linha `paper` recusaria (`q16` §3)

Banda de stop do `paper_v1`: `[0,003; 0,03]` do preço (`packages/risk-core/hunter_risk/limits.py:151-152`).

```
+----------+-----+---------------------+----------------------+--------------+----------------------+
|  coorte  |  n  | acima_do_teto_paper | abaixo_do_piso_paper | pct_recusado | soma_r_acima_do_teto |
+----------+-----+---------------------+----------------------+--------------+----------------------+
| 9a08835a | 196 |                   0 |                    1 |          0.0 |                      |
| 293d98b7 | 184 |                   2 |                    0 |          1.1 |                 1.32 |
| ee11d60b | 181 |                  13 |                    0 |          7.2 |                -2.74 |
| d570b19a |  17 |                   0 |                    0 |          0.0 |                      |
| 9d99748b |  15 |                   3 |                    0 |         20.0 |                -1.45 |
| 264b227f |  14 |                   4 |                    0 |         28.6 |                 1.80 |
| f4af4ffe |  11 |                   0 |                    0 |          0.0 |                      |
| af24ee08 |  10 |                   3 |                    0 |         30.0 |                -1.45 |
| 66fa85cb |   9 |                   4 |                    0 |         44.4 |                 1.80 |
+----------+-----+---------------------+----------------------+--------------+----------------------+
```

**Este é o custo escondido do stop largo e ninguém tinha medido:** as quatro variantes de
`mean_reversion` põem **20 % a 44 %** das decisões **fora** da banda que o `paper_v1` aceita (stop
> 3 % do preço). Numa linha `paper`, o Risk Engine recusaria o sizing dessas operações — a versão
que aparece com PF 21 no papel decidiria **metade do que decidiu aqui**. A `momentum v8` recusa
7,2 %; a `v7`, 1,1 %; os pais, nada. É o mesmo C5 que matou o [[EXP-0012]], agora pelo outro lado.

## 9. COBERTURA (`q16` §1)

```
|  coorte  | emitidos | pendentes | entradas | ativos | alvo | stop | expirado | invalidado | sem_r | avaliaveis | dias |
| 9a08835a |      196 |         0 |      196 |      0 |   53 |   45 |       16 |         82 |     1 |        195 |   24 |
| 293d98b7 |      184 |         0 |      184 |      0 |   27 |   19 |       39 |         99 |     1 |        183 |   24 |
| ee11d60b |      181 |         0 |      181 |      0 |   21 |    9 |       43 |        108 |     0 |        181 |   24 |
| d570b19a |       17 |         0 |       17 |      0 |    7 |    6 |        4 |          0 |     0 |         17 |    7 |
| 9d99748b |       15 |         0 |       15 |      0 |    1 |    2 |       12 |          0 |     0 |         15 |    7 |
| 264b227f |       14 |         0 |       14 |      0 |    1 |    1 |       12 |          0 |     0 |         14 |    7 |
| f4af4ffe |       11 |         0 |       11 |      0 |    4 |    3 |        4 |          0 |     0 |         11 |    4 |
| af24ee08 |       10 |         0 |       10 |      0 |    1 |    1 |        8 |          0 |     0 |         10 |    4 |
| 66fa85cb |        9 |         0 |        9 |      0 |    1 |    0 |        8 |          0 |     0 |          9 |    4 |
```

Cobertura perfeita nas nove: **0 pendentes, 0 ativos, 0 não-entradas**; a única linha sem `R_net` é
uma decisão com funding indeterminado em cada coorte de `momentum` (99,5 % de cobertura, K5 passa).

---

## 10. A PASSADA DE ESTRESSE (`replay.stress`, `READ ONLY`, sem escrita no Lab)

### `momentum v7` (stop ×1,5) — `as_of 2026-09-08T22:58:03,270566Z`, 184 entradas congeladas

```
| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ | descartes |
|---|---|---:|---:|---:|---:|---|---|
| `base` | reprecificacao | 183 | -0.0568 | 0.8590 | — | — | funding_indeterminado=1 |
| `custos_x2` | reprecificacao | 183 | -0.2163 | 0.5660 | -0.1595 | [-0.1770, -0.1428] | ... |
| `stop_x0.75` | reprecificacao | 183 | -0.0860 | 0.8381 | -0.0292 | [-0.1018, +0.0403] | ... |
| `stop_x1.25` | reprecificacao | 183 | -0.0341 | 0.8914 | 0.0227 | [-0.0313, +0.0805] | ... |
| `alvo_x0.75` | reprecificacao | 183 | -0.0376 | 0.9023 | 0.0192 | [-0.0441, +0.0959] | ... |
| `alvo_x1.25` | reprecificacao | 183 | -0.0399 | 0.9037 | 0.0168 | [-0.0396, +0.0607] | ... |
| `entrada_mais_1_barra` | reprecificacao | 183 | -0.0572 | 0.8571 | -0.0004 | [-0.0274, +0.0342] | ... |
| `sem_binance:DOGEUSDT` | recorte | 137 | -0.0935 | 0.7799 | — | — | — |
| `sem_binance:ETHUSDT` | recorte | 142 | -0.0107 | 0.9721 | — | — | — |
| `sem_binance:SOLUSDT` | recorte | 129 | -0.0509 | 0.8726 | — | — | — |
| `sem_binance:XRPUSDT` | recorte | 141 | -0.0728 | 0.8185 | — | — | — |
| `1a_metade_ate_2026-08-24` | recorte | 77 | 0.1985 | 1.5836 | — | — | — |
| `2a_metade_apos_2026-08-24` | recorte | 106 | -0.2422 | 0.4595 | — | — | — |

**Veredito:** sem_vantagem_na_base
- expectancy da base = -0.05677281375546440159415346585
```

### `momentum v8` (stop ×2) — `as_of 2026-09-08T22:58:30,817903Z`, 181 entradas congeladas

```
| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
| `base` | reprecificacao | 181 | -0.0299 | 0.9056 | — | — |
| `custos_x2` | reprecificacao | 181 | -0.1531 | 0.6123 | -0.1232 | [-0.1366, -0.1107] |
| `stop_x0.75` | reprecificacao | 181 | -0.0420 | 0.9001 | -0.0121 | [-0.0831, +0.0553] |
| `stop_x1.25` | reprecificacao | 181 | -0.0245 | 0.9038 | 0.0055 | [-0.0338, +0.0459] |
| `alvo_x0.75` | reprecificacao | 181 | -0.0276 | 0.9064 | 0.0023 | [-0.0495, +0.0666] |
| `alvo_x1.25` | reprecificacao | 181 | -0.0063 | 0.9801 | 0.0236 | [-0.0083, +0.0511] |
| `entrada_mais_1_barra` | reprecificacao | 181 | -0.0309 | 0.9015 | -0.0009 | [-0.0196, +0.0198] |
| `sem_binance:DOGEUSDT` | recorte | 135 | -0.0651 | 0.8067 | — | — |
| `sem_binance:ETHUSDT` | recorte | 142 | 0.0267 | 1.0902 | — | — |
| `sem_binance:SOLUSDT` | recorte | 127 | -0.0602 | 0.8179 | — | — |
| `sem_binance:XRPUSDT` | recorte | 139 | -0.0259 | 0.9156 | — | — |
| `1a_metade_ate_2026-08-24` | recorte | 75 | 0.1913 | 1.7105 | — | — |
| `2a_metade_apos_2026-08-24` | recorte | 106 | -0.1864 | 0.4688 | — | — |

**Veredito:** sem_vantagem_na_base
- expectancy da base = -0.02991994202052675047784249599
```

### O pai `momentum v6` na mesma passada — `as_of 2026-09-08T23:24:34,299331Z`, 196 entradas

```
| `base`                    | reprecificacao | 195 | -0.0513 | 0.9064 | —       | —                    |
| `custos_x2`               | reprecificacao | 195 | -0.2798 | 0.5825 | -0.2285 | [-0.2549, -0.2033]   |
| `stop_x0.75`              | reprecificacao | 195 | -0.0417 | 0.9394 |  0.0096 | [-0.0526, +0.0735]   |
| `stop_x1.25`              | reprecificacao | 195 | -0.0256 | 0.9418 |  0.0257 | [-0.0326, +0.0811]   |
| `alvo_x0.75`              | reprecificacao | 195 | -0.0871 | 0.8337 | -0.0358 | [-0.1014, +0.0435]   |
| `alvo_x1.25`              | reprecificacao | 195 | -0.0400 | 0.9287 |  0.0113 | [-0.0439, +0.0623]   |
| `entrada_mais_1_barra`    | reprecificacao | 195 | -0.0764 | 0.8620 | -0.0251 | [-0.0529, +0.0049]   |
| `1a_metade_ate_2026-08-24`| recorte        |  86 |  0.1763 | 1.3815 | —       | —                    |
| `2a_metade_apos_2026-08-24`| recorte       | 109 | -0.2309 | 0.6257 | —       | —                    |

**Veredito:** sem_vantagem_na_base
```

(rodada nesta tarefa para ter a base do contraste; a T3.40 não tinha rodado estresse na `v6`.)

Duas leituras que valem por si:

- **`entrada_mais_1_barra` é praticamente nulo nas duas** (−0,0004 e −0,0009 R, IC contendo zero).
  O stop largo comprou **robustez de execução**: no pai `momentum v6` a mesma perturbação vale
  **−0,0251 R** (medido na passada de estresse do pai, acima). Isso é real e é o único ganho
  estrutural claro do eixo.
- **A metade de agosto salva as duas e a metade de setembro afunda as duas** (+0,199/−0,242 e
  +0,191/−0,186). O corte por metades da coorte é o mesmo do pai: **o stop largo não muda o regime**.

### As quatro `mean_reversion` — as quatro deram **`amostra_insuficiente`**

`mean_reversion v4` (`as_of 22:58:45,578983Z`, 10 entradas) e `v5` (`22:58:59,359340Z`, 9):

```
v4 | base 0.3337 PF 2.4787 | custos_x2 0.2350 PF 1.9568 (Δ -0.0986 [-0.1529,-0.0778])
   | stop_x0.75 0.3209 | stop_x1.25 0.2470 (Δ -0.0867 [-0.2665,-0.0264])
   | alvo_x0.75 0.3209 | alvo_x1.25 0.3686 (Δ +0.0349 [+0.0000,+0.2095])
   | entrada_mais_1_barra 0.2393 (Δ -0.0944 [-0.2646,-0.0263])
   | sem DOGE 0.2163 (7) | sem ETH 0.4046 (9) | sem SOL 0.3036 (9) | sem XRP 0.4245 (5)
   | 1a metade ate 08-21: 0.8755 (3) | 2a metade: 0.1015 (7)
   **Veredito:** amostra_insuficiente — 10 desfechos avaliáveis de 30

v5 | base 0.4830 PF 21.1793 | custos_x2 0.4048 PF 12.5230 (Δ -0.0783 [-0.1158,-0.0636])
   | stop_x0.75 0.5220 | stop_x1.25 0.3864 (Δ -0.0966 [-0.2355,-0.0516])
   | alvo_x0.75 0.4435 | alvo_x1.25 0.3572 (Δ -0.1258 [-0.6792,+0.0000])
   | entrada_mais_1_barra 0.3992 (Δ -0.0838 [-0.1742,-0.0387])
   | sem DOGE 0.5044 (6) | sem ETH 0.5703 (8, no_losses) | sem SOL 0.4864 (8) | sem XRP 0.3123 (5)
   | 1a metade ate 08-21: 0.6494 (3) | 2a metade: 0.3998 (6)
   **Veredito:** amostra_insuficiente — 9 desfechos avaliáveis de 30
```

`mean_reversion v6` (`as_of 22:59:02,403788Z`, 15 entradas) e `v7` (`22:59:06,645006Z`, 14):

```
v6 | base 0.2861 PF 2.2820 | custos_x2 0.1716 PF 1.7089 (Δ -0.1145 [-0.1565,-0.0857])
   | stop_x0.75 0.1842 | stop_x1.25 0.2022 (Δ -0.0839 [-0.1741,-0.0293])
   | alvo_x0.75 0.2917 | alvo_x1.25 0.3093 (Δ +0.0233 [+0.0000,+0.1047])
   | entrada_mais_1_barra 0.2626 (Δ -0.0235 [-0.0978,+0.0255])
   | sem DOGE 0.1635 (11) | sem ETH 0.3096 (13) | sem SOL 0.3428 (12) | sem XRP 0.3262 (9)
   | 1a metade ate 08-28: 0.2587 (14) | 2a metade: 0.6692 (1)
   **Veredito:** amostra_insuficiente — 15 desfechos avaliáveis de 30

v7 | base 0.3450 PF 4.7605 | custos_x2 0.2557 PF 3.4679 (Δ -0.0894 [-0.1167,-0.0696])
   | stop_x0.75 0.4054 | stop_x1.25 0.2618 (Δ -0.0833 [-0.1514,-0.0438])
   | alvo_x0.75 0.3197 | alvo_x1.25 0.2642 (Δ -0.0809 [-0.3396,+0.0000])
   | entrada_mais_1_barra 0.3200 (Δ -0.0251 [-0.0757,+0.0151])
   | sem DOGE 0.3014 (10) | sem ETH 0.3839 (12) | sem SOL 0.4487 (11) | sem XRP 0.2150 (9)
   | 1a metade ate 08-28: 0.3335 (13) | 2a metade: 0.4953 (1)
   **Veredito:** amostra_insuficiente — 14 desfechos avaliáveis de 30
```

**A boa notícia real:** `custos_x2` continua **positivo nas quatro** (+0,2350, +0,4048, +0,1716,
+0,2557) e a sensibilidade a custo das duas de `momentum` cai muito: o Δ de `custos_x2` vale
**−0,2285 R no pai `v6`**, **−0,1595 R na `v7`** (÷1,43) e **−0,1232 R na `v8`** (÷1,85) — quase
exatamente o 1/k que a identidade prevê. Era isso que o eixo prometia entregar, e ele entrega.

**A má notícia real:** `1a_metade / 2a_metade` de `v6` e `v7` são **14 e 1** e **13 e 1** decisões —
as duas irmãs herdaram do pai o vício da T3.42: **a versão existe em quatro dias de agosto**.

---

## 11. K1–K5 (régua do EXP-0017, aplicada a cada variante)

| variante | K1 (< 20 decisões) | K2 (> 1 500) | K3 (>=100 aval. e >=30 dias e bruto < 0) | K4 (`unavailable` > 40 %) | K5 (cobertura `R_net` < 70 %) |
|---|---|---|---|---|---|
| `momentum v7` | não (184) | não | **não avaliável** (24 dias < 30; bruto +0,116) | não (3,8 %) | não (99,5 %) |
| `momentum v8` | não (181) | não | **não avaliável** (24 dias; bruto +0,101) | não (3,8 %) | não (100 %) |
| `mean_reversion v4` | **SIM (10)** | não | não avaliável | não | não |
| `mean_reversion v5` | **SIM (9)** | não | não avaliável | não | não |
| `mean_reversion v6` | **SIM (15)** | não | não avaliável | não | não |
| `mean_reversion v7` | **SIM (14)** | não | não avaliável | não | não |

K6 (>= 60 % num único mercado) **não dispara em nenhuma**: pelos recortes do estresse, o maior
mercado da `momentum v8` responde por 54/181 = **29,8 %** e o da `mean_reversion v6` por 6/15 =
**40 %**.

**K1 dispara nas quatro `mean_reversion`.** Pela régua, isso não é "aguardar mais 30 dias": é
**ausência de população nesta janela** — e a origem é o pai, não a variante (o piso de ATR% da T3.42
já tinha deixado 11 e 17 decisões).

---

## 12. TESTES LOCAIS

Nenhum código de produção foi escrito. Rodei (a) as provas de não-antecipação que o meu contrato
exige, (b) o que governa derivação/ativação e a tabela de faixas, e (c) os testes da ferramenta de
bootstrap que escrevi para esta nota, com séries sintéticas e valores calculados à mão **antes** de
o módulo existir.

```
$ uv run pytest packages/core/tests/unit/strategies/test_no_lookahead.py \
      packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
      packages/core/tests/unit/strategies/test_constraints.py \
      services/strategy-worker/tests/test_replay_lookahead.py -q -p no:cacheprovider
........................................................................ [ 36%]
........................................................................ [ 73%]
....................................................                     [100%]
196 passed in 146.21s (0:02:26)

$ uv run pytest services/strategy-worker/tests/test_constraints_outside_freeze.py \
      services/strategy-worker/tests/test_derive_variant.py \
      services/strategy-worker/tests/test_activate_derived_guard.py \
      infra/scripts/tests/test_derive_variant_lineage.py -q -p no:cacheprovider
......................................................                   [100%]
54 passed in 81.37s (0:01:21)

$ cd .claude/state/exp-drafts/t347-blocos && uv run --project C:/dev/project-hunter pytest test_blocos_pareado.py -q -p no:cacheprovider
......                                                                   [100%]
6 passed in 1.87s
```

Os seis testes sintéticos, com o valor esperado escrito antes de rodar: Δ constante ⇒ intervalo
degenerado [+1,5; +1,5]; **um único dia com Δ = {+3, −1} ⇒ Δ = +1,0 e IC degenerado** (a prova de
que o bloco é o dia e não a decisão); dia com 3 decisões de +1 contra dia com 1 de −3 ⇒ Δ = 0,0
(concatenação, não média de médias); suporte da reamostragem = {+2,0; +1,0; −1,0} exatamente, com
IC [−1,0; +2,0]; semente fixa a sequência inteira; população vazia devolve `nan`, nunca 0,0.

**Um teste meu falhou na primeira execução e a expectativa errada era minha, não do módulo:** eu
tinha afirmado que sementes diferentes dariam IC diferentes; com **três dias** o IC percentil satura
nos extremos das oito combinações possíveis e é **igual** para qualquer semente. Corrigi o teste
para afirmar o que é verdade (a semente fixa a **sequência** de reamostragens) e deixei o comentário
no arquivo. Está declarado aqui porque um teste reescrito depois de falhar merece ser dito em voz
alta.

---

## 13. VEREDITO POR VARIANTE

Régua: `descartar` / `manter em pesquisa` / `candidata a prospectivo`.

### C1 — `momentum v7` (stop ×1,5): **descartar**

- Δ pareado **−0,0040 R** em 181 pares: a variante é **pior** que o pai. Dos 0,0882 R de pedágio
  economizados, **0,0922 R** somem no bruto — **105 % devolvidos**.
- Estresse: `sem_vantagem_na_base` (−0,0568 R, PF 0,859), pior que o pai (−0,0513, PF 0,906).
- IC 95 % por bloco de dia [−0,156; +0,128] contém zero, como tem de conter para um Δ de −0,004.
- **Não há hipótese sobrevivente aqui:** o fator 1,5 é dominado pelo fator 2 em toda métrica.
  Recomendo **aposentar** a versão quando existir via auditada para isso (não existe: CONCERN 4).

### C2 — `momentum v8` (stop ×2): **manter em pesquisa** (não promover)

| critério | valor | dispara? |
|---|---|---|
| Δ pareado <= 0 | **+0,0161 R** (181 pares) | não |
| IC 95 % por bloco de dia exclui zero | **[−0,176; +0,185]** | **não exclui** |
| `PF_net <= 0,80` | 0,9056 | não |
| `expectancy_net <= a do pai` | −0,0299 vs −0,0513 | não |
| estresse `frágil a custos` | `custos_x2` −0,1531 (**ainda negativo**) | **sim, herdado do pai** |
| K1–K5 | nenhum dispara | não |

O que sustenta: é o único contraste com `n` de verdade (181 pares, 24 dias, 180 com o mesmo par),
o Δ é positivo, a sensibilidade a custo cai 46 % (Δ de `custos_x2` −0,2285 → −0,1232),
`entrada_mais_1_barra` vira ruído (−0,0251 no pai → −0,0009) e o pior dia da
janela melhora 8,7 R. O que **não** sustenta, e pesa mais: **ela continua perdendo** (−0,0299 R,
PF 0,906 < 1), o IC contém zero, o ganho vem de **comprimir variância** (perde menos nos dias ruins,
ganha menos nos bons) e **7,2 % das decisões ficam fora da banda de stop do `paper_v1`**. E o
mecanismo medido — 41 stops salvos contra 29 ganhadores devolvidos — é uma troca de distribuição,
não vantagem nova.

### A1/A2 — `mean_reversion v4` (×1,5) e `v5` (×2), filhas da `v3`: **descartar como candidatas**

**K1 dispara** (10 e 9 decisões). A `v5` é o caso didático do que **não** se deve citar: PF 21,18
com **nenhuma** operação perdedora além de uma, **8 das 9 saídas por horizonte**, tudo em **quatro
dias consecutivos** de 2026-08-20 a 08-23, e **44 % das decisões fora da banda do `paper_v1`**. Δ
pareado +0,0572 R com IC [−0,318; +0,192]. **Isso não é uma estratégia, é um episódio reprecificado.**
A `v4` é pior que a irmã em tudo e não tem nem esse argumento.

### B1 — `mean_reversion v6` (×1,5), filha da `v2`: **manter em pesquisa — é a melhor candidata das seis**

- **95,1 % da economia de pedágio sobrevive** (0,0575 R economizados, 0,0013 R perdidos no bruto):
  o melhor aproveitamento medido em toda a tarefa.
- Δ pareado **+0,0547 R** (14 pares, 7 dias), líquido **+0,2861 R**, PF 2,28, `custos_x2` **+0,1716**.
- **Mas K1 dispara (15 decisões)**, o IC é [−0,212; +0,527], 12 das 15 saídas são por horizonte,
  a segunda metade da janela tem **uma** decisão e **20 % das decisões ficam fora da banda do
  `paper_v1`**.

### B2 — `mean_reversion v7` (×2), filha da `v2`: **manter em pesquisa com ressalva**

Δ pareado +0,0275 R, líquido +0,3450 R, PF 4,76 — números maiores e evidência menor: **só 32 % da
economia sobrevive** (o bruto já começa a ceder, −0,0571 R) e **28,6 % das decisões saem da banda
do `paper_v1`**. Entre as duas irmãs, **a diferença são 0,027 R e uma decisão** — escolher entre elas
por este replay seria decidir por ruído ([[KB-0010]]), exatamente o que a T3.42 já disse sobre os
pais delas.

---

## 14. RESPOSTA AO EVERTON (dez linhas)

1. **Alargar o stop funciona no pedágio e não positiva a entrada.** Com stop ×2 na `momentum v6`, o
   pedágio caiu de 0,2554 R para 0,1305 R por operação — exatamente a metade prometida.
2. Só que **R é a distância até o stop**: alargando o stop, o mesmo movimento de preço vale menos R.
   O bruto caiu junto (0,2028 → 0,1013) e **sobrou +0,0161 R por operação — 12 % da economia**.
3. Em dinheiro, isso é **+0,78 USDT por operação**: a `momentum` sai de −2,48 para −1,45 USDT.
   **Menos prejuízo, ainda prejuízo.**
4. E há uma equivalência incômoda que precisa ser dita: com o risco por operação fixo em 0,25 %,
   dobrar o stop **corta o tamanho da posição pela metade**. Em dinheiro, o efeito é quase o mesmo
   que operar metade do tamanho. **Isso é menos risco, não mais.**
5. A melhor candidata das seis é a **`mean_reversion v6`** (piso 0,008 com stop 1,5 ATR): ela guarda
   **95 % da economia de pedágio**, dá +0,2861 R por operação e continua positiva com o custo
   dobrado. **Mas tem 15 decisões em 31 dias** — a régua manda chamar isso de ausência de população.
6. As duas filhas da `mean_reversion v3` (9 e 10 decisões, PF 21) são **um episódio de quatro dias de
   agosto reprecificado**, não uma estratégia. Descarto as duas como candidatas.
7. **O que o stop largo conserta de verdade:** ele torna a versão quase imune ao atraso de entrada e
   reduz quase pela metade a sensibilidade a custos (Δ de `custos_x2` −0,2285 R no pai contra
   −0,1232 R nela). Isso é robustez, e é bem-vinda.
8. **O que ele não conserta:** a vantagem na entrada. A `momentum v3`, que é a linha `paper`, tem
   bruto **−0,0667 R** — perde **antes** de pagar qualquer pedágio. Nenhuma geometria salva isso.
9. **Minha recomendação para rodar prospectivamente agora:** `momentum v8` (stop ×2), porque é a
   única com população para ser julgada em 30 dias; e `mean_reversion v6` como segunda, sabendo que
   ela vai gerar ~15 decisões por mês. As duas já estão no Lab desde as 19:29 e 19:38 de hoje.
10. **A próxima alavanca não é o stop, é o piso de ATR%**: hoje `atr_pct_min = 0,006` recusa 67 % a
    89 % das barras desses mercados (T3.45). É lá que estão as decisões que faltam — e é a proposta
    do §15.

## 15. PROPOSTA (não executada — só se houver tempo, como o brief pede)

**A descoberta que atravessa a T3.45 e esta tarefa:** o piso de ATR% da `mean_reversion_v1`
(`0,006`) recusa **67 % a 89 %** das barras destes quatro mercados (ETHUSDT: só 10,68 % chegam ao
porteiro), e os pais `v2`/`v3` **subiram** esse piso para 0,008 e 0,010. O resultado é aritmético e
está medido nesta nota: **9 a 17 decisões em 31 dias**, K1 disparando em todas as variantes.

O stop largo já entrega o teto de pedágio que o piso de ATR% comprava — `mean_reversion v6` paga
**0,1075 R** com piso 0,008, contra **0,1452 R** da `v3` com piso 0,010. Então a variante que falta
testar é a inversa das anteriores:

> **`mean_reversion` com `atr_pct_min` de volta a 0,006 (ou 0,004) e `stop_atr = 1,5`** — comprar
> população de volta com o piso e pagar o pedágio com a largura do stop. Teto previsto:
> `0,0020 / (1,5 × 0,006) = 0,222 R`, melhor que os **0,2263 R** que a `v1` paga hoje com piso 0,006
> e stop 1 ATR, **com três vezes mais decisões** que a `v6`.

Não derivei: seriam mais duas versões num roster que já tem dezesseis (CONCERN 4), e a decisão de
gastar mais uma execução é do dono do backlog, não minha. O contraste está desenhado e pré-declarado
aqui, o que é o suficiente para não ser garimpo depois.

---

## CONCERNS

1. **Escrevi uma ferramenta nova em vez de usar a que o brief indicou, e ela está fora do escrito de
   escrita do brief.** O `t342-blocos/blocos.py` faz contraste **população contra população**
   (variante = subconjunto do pai por um piso), e aqui a variante decide **as mesmas barras** com
   outra geometria — o estimando é o Δ **pareado**, que aquele arquivo não calcula. Escrevi
   `t347-blocos/blocos_pareado.py` (106 linhas, NumPy, sem `Decimal` porque nada ali é dinheiro
   persistido) com seis testes sintéticos escritos antes. O brief listava três caminhos de escrita e
   este não é um deles; é `.claude/state/exp-drafts/`, fora de código de produção, mas **é um desvio
   e está declarado**.
2. **Seis variantes num roster que já tinha nove versões — e agora tem dezesseis.** Cada versão
   ativa custa uma avaliação por barra por mercado. A vigia não mostrou degradação em nenhuma das
   seis amostras (`outbox_lag_s` 0,0, `outbox_pending` 0, `errors` 0, `/ready` 200, `paper` primeira
   na ordem do roster), mas eu **dobrei** a carga de estratégia da VPS numa tarefa de pesquisa. Se
   alguém tiver de escolher o que aposentar, minha lista é: `momentum v7` (descartada acima),
   `mean_reversion v4` e `v5` (K1, episódio de quatro dias).
3. **Não existe via auditada para aposentar uma versão substituída por parâmetro.** CONCERN aberto
   desde a T3.33f; a T3.41 aposentou três à mão. Eu recomendo descartar três das minhas seis e
   **não tenho como fazê-lo**.
4. **O "pedágio ÷2" é média, não garantia — de novo.** `stop_atr_efetivo` medido na `momentum v8`
   vai de **2,27 a 3,99** para um `stop_atr` declarado de 3,0, porque o risco inicial é
   `entrada − stop` e a entrada anda entre a decisão e a abertura da barra seguinte. O pior caso de
   pedágio da `v8` foi **0,2652 R**, não 0,1277. Mesma ressalva que a T3.42 registrou (CONCERN 3
   dela); repito porque a frase "pedágio dividido por dois" está no changelog das versões.
5. **A `session_orb v1` ficou de fora e o brief pedia o número dela.** Ela não tem `stop_atr` nem
   `target_atr`: usa `range_risk_atr_min = 1` / `range_risk_atr_max = 2.5` e alvos em R (2 e 4).
   O equivalente ao "stop largo" ali é subir `range_risk_atr_min`, o que **muda a população de
   entrada** (a faixa de risco é porteiro, não geometria) — é outro experimento, com outro contraste,
   e eu não o inventei por conta própria. A geometria dela está colada em §1.
6. **Outra tarefa (T3.34b, `trendline_breakout`) ativou uma versão e rodou três replays no mesmo
   container, dentro da minha janela** (22:29:52 a 22:36:05Z). Isso **não contamina** os meus
   números — replay é determinístico por coorte e as populações batem barra a barra com os pais —,
   mas divide CPU com as minhas corridas (`bars_per_second` caiu de 63,2 para 52,2 na fatia que
   coincidiu) e **soma uma décima-sexta versão ativa** ao roster. O `scanner-worker` também foi
   redeployado por outra tarefa (`hunter-api:14c4b54`) às ~23:01Z. Nada disso é meu.
7. **Um teste meu falhou e eu reescrevi o teste.** Detalhado em §12. A expectativa errada era minha;
   o módulo não mudou por causa disso.
8. **O replay herda o universo de hoje**, não o de agosto (`PIPELINE` §6c). Vale igualmente para as
   nove coortes — o pareamento não fica enviesado —, mas nenhuma descreve o universo real da janela.
9. **A hipótese de custo continua declarada, não medida** (2 bps de spread + 5 bps de slippage/lado +
   4 bps de taxa/lado = 20 bps ida e volta). **Todo** o eixo desta tarefa é linear nela: se o custo
   real for metade do assumido, o pedágio do pai já seria 0,128 R e a `momentum v6` estaria positiva
   sem variante nenhuma. Medir contra o livro real é a verificação que a [[KB-0076]] pede desde
   ontem e que ninguém fez — e, depois desta tarefa, ela vale mais do que qualquer variante nova.
10. **Escrevi os changelogs sem acento** ("pedagio"), decisão minha para não arriscar corrupção de
    UTF-8 no caminho Windows → ssh → docker, como a T3.42 fez. O texto do brief pedia "×1,5" e
    "÷1,5"; ficou "x1,5" e "dividido por 1,5".
11. **`EXP-0018` era a vaga livre às 2026-09-08T23:10Z.** O rascunho está em
    `.claude/state/exp-drafts/`, **não** em `obsidian/**` (fora do meu escopo). Se outra tarefa tomar
    o número antes da Sexta-feira arquivar, renumerar.
12. **A janela é a mesma que gerou a hipótese.** Os seis contrastes são REPLAY sobre 2026-08-08…09-08,
    e a ideia do stop largo nasceu do diagnóstico desta mesma série ([[KB-0076]]). Nenhum número
    desta nota decide ativação sozinho ([[KB-0010]]); as seis coortes prospectivas abertas hoje são
    o que decide, em 2026-10-08.

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** o CONCERN 1 (ferramenta nova fora do escopo de escrita do brief) e o CONCERN 2
  (dobrei o roster). Os dois são julgamento, não aritmética.
- **risk-engine-guardian:** as seis são `research_only`, sem linha em `agents`, `shadow_outbox`
  zerada para as seis coortes de replay. O ponto de atenção **novo e sério** é o §8: as variantes de
  `mean_reversion` põem **20 % a 44 %** das decisões acima do teto de stop do `paper_v1`
  (`limits.py:151-152`), e a `momentum v8`, 7,2 %. Se alguém pedir `--paper-line` de qualquer uma
  delas, essa é a conversa — e ela é maior do que foi no [[EXP-0012]].
- **Sexta-feira:** arquivar `EXP-0018`, ligar do `Strategy Backlog` e do `Experiments Index`, e
  acrescentar **seis** linhas no `Registro de Tentativas` com os carimbos de ativação
  (22:29:28,783999Z / 22:29:33,049734Z / 22:38:37,842745Z / 22:38:41,887854Z / 22:38:46,022557Z /
  22:38:49,950926Z — 19:29 e 19:38 de Brasília). A multiplicidade sobe muito: **seis execuções
  novas, um contraste pré-registrado cada**.
- **Everton:** a decisão que este trabalho põe na mesa é que **a alavanca da geometria está no fim**.
  Piso de ATR% (T3.42), alvo mais longe (T3.40) e stop mais largo (esta) foram testados: os três
  mexem no pedágio e nenhum fabrica vantagem. O número honesto do dia é **+0,0161 R por operação**,
  com intervalo que contém zero. O que falta medir não é mais uma variante: é **o custo real contra
  o livro da corretora** (CONCERN 9) e **a vantagem na entrada** — e é aí que eu gastaria a próxima
  execução.

---

## ADENDO — o estado da árvore ao fechar (2026-09-08T23:15Z = 20:15 Brasília)

```
$ git -C C:/dev/project-hunter status --porcelain -- .claude/state/notes-T3.47.md \
      .claude/state/exp-drafts/EXP-0018-stop-largo.md .claude/state/exp-drafts/t347-blocos \
      infra/scripts/sql/research
?? .claude/state/exp-drafts/EXP-0018-stop-largo.md
?? .claude/state/exp-drafts/t347-blocos/
?? .claude/state/notes-T3.47.md
?? infra/scripts/sql/research/2026-09-09-t347-q00-catalogo.sql
?? infra/scripts/sql/research/2026-09-09-t347-q01-pedagio-antes.sql
?? infra/scripts/sql/research/2026-09-09-t347-q02-session-orb.sql
?? infra/scripts/sql/research/2026-09-09-t347-q10-populacoes.sql
?? infra/scripts/sql/research/2026-09-09-t347-q11-pareado.sql
?? infra/scripts/sql/research/2026-09-09-t347-q12-dump-pareado.sql
?? infra/scripts/sql/research/2026-09-09-t347-q13-motivos.sql
?? infra/scripts/sql/research/2026-09-09-t347-q14-recibos-iso.sql
?? infra/scripts/sql/research/2026-09-09-t347-q15-iso-roster.sql
?? infra/scripts/sql/research/2026-09-09-t347-q16-cobertura-c5.sql
?? infra/scripts/sql/research/2026-09-09-t347-q17-dias.sql
```

**Tudo meu está `??` — nada foi commitado, nada foi indexado.** `git status --porcelain -- .env*
obsidian` acusa `.env.example` **modificado por outra tarefa** (já estava assim às 22:23Z, antes de
eu começar; não toquei nele).

**O `main` andou durante a tarefa:** o brief nasceu em `2e39774` e o `HEAD` da árvore estava em
`6a8679b` quando fechei (T3.50 e outras). **Nenhum commit é meu.** A VPS **não** foi redeployada
para os meus containers: `hunter-api:2e39774` na api, na web e no strategy-worker do início ao fim —
o que quer dizer que **as seis derivações, as seis ativações, os doze replays e as seis passadas de
estresse rodaram na imagem do commit do brief**, não em código em voo.

**Última amostra da vigia, 2026-09-08T23:26:07Z (20:26 Brasília), 47 min depois da primeira
ativação e com dezesseis versões ativas:** `outbox_lag_s` **0,0**, `outbox_pending` **0**,
`errors` **0**, `evaluations_by_state` `{"not_triggered":13402,"triggered":180,"ineligible":78,
"unavailable":4073}`, `hunter-api-1` e `hunter-web-1` `healthy` em `2e39774`.
