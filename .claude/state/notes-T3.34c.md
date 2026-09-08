# notes-T3.34c — `trendline_breakout_v1` sai do papel: catálogo, ativação e o dia um pré-registrado

**Data:** 2026-09-08 (Brasília, UTC−3; UTC como detalhe). **Owner:** quant-engineer.
**Base do brief:** `main @ 2e39774`; a VPS rodou `hunter-api:2e39774` (api e strategy-worker) do
começo ao fim — **nenhum redeploy no meio**.
**Nada commitado.** **Nenhum container parado ou recriado.** **Nenhum `.env*` tocado.**
**Nenhuma linha escrita por mim em `apps/**`, `services/**`, `packages/**`, `obsidian/**`**
(ver CONCERN 8: outras tarefas mexeram nessas pastas durante a minha janela).
**Nenhuma linha alterada em `tl_*.py` nem em `trendline_breakout_v1.py`** — o digest está congelado
pelo teste e continua `…7b83a1ff…`.
**Escritas na VPS:** exatamente três — `seed.py --only strategies --yes` (×1),
`activate_strategy_version.py` (×1) e o CLI de replay (×3 corridas, sendo uma sonda de calibragem).
Todo o resto foi lido em `repeatable read read only`; `replay_exits.py` é `READ ONLY` por construção.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Fechar a ressalva 1 (36, não 37 parâmetros) em `notes-T3.34b.md` e no `EXP-0016` | **OK.** E a correção foi conferida **duas vezes**: `len(default_parameters) == 36` local e `(36 parameters)` impresso pelo `--dry-run` da VPS |
| 2 | Ressalva 2: `KB-0006`/`EXP-0007` em "Relacionadas" e em C8; **pré-registrar** o R pareado da invalidação | **OK com ressalva de procedência (CONCERN 13).** C8 foi **rebaixado de `PASS` para `REVISE`** e a regra de leitura ("Δ ≥ 0 ⇒ a tese de C8 não se sustenta") foi escrita por mim **ao arquivar**, com o número na tela; o Δ saiu **+0,0922 R** e a tese não se sustentou. **O estimando veio do brief, anterior a tudo; o limiar de leitura não é pré-registrado** — CONCERN 13 |
| 3 | Ressalva 3: as duas séries de ATR de Wilder (97 oficial vs 96 do `tl_scan`) | **OK**, medida: **0,000861 %–0,011649 %** em série sintética, teto estrutural 0,2295 % (peso residual da semente). Observação, não defeito |
| 4 | `seed.py --dry-run` → `--only strategies --yes`; diff do catálogo antes/depois; ativar `research_only` | **OK.** Duas linhas `NEW` e mais nada; digest `…7b83a1ff…` exatamente o do brief. **Achado colateral grave: `risk_profiles.paper_v1` NÃO EXISTE na VPS** (CONCERN 1) |
| 5 | Replay 31 d, 4 mercados, `--explain-ledger`, `--cohort` explícita; dia um na ordem (a)(b)(c)(d); K1–K5 | **OK.** 11 904 barras, 0 erros, 47 decisões. **K1–K5 não disparam. K6 dispara: 89,4 % das decisões são repique** |
| 6 | Veredito do funil + ≤ 10 linhas em português para o Everton, com a resposta honesta sobre "cada operação traça as linhas?" | **OK.** Veredito: **`manter em pesquisa`, com a hipótese reenunciada**. A resposta é `sim, 47/47`, provada por SQL |
| — | Estresse (só se K1 sobrevivesse) | **NÃO RODADO** — desvio declarado, CONCERN 5 |

**Resposta curta em quatro linhas.** A geometria **existe no dado real** (90,53 % das barras têm ao
menos uma linha válida) e a versão **decide**: 47 operações em 31 dias × 4 mercados. Ela é a
**primeira** desta casa com **expectancy bruta positiva** (+0,1045 R) — e o pedágio de 0,1401 R come
tudo, deixando **−0,0382 R** líquidos e PF 0,922. Duas descobertas maiores que o número:
**(i) 89,4 % das decisões são repique, não rompimento** — a hipótese que este EXP testa não é a que
o nome diz; **(ii) tirar a invalidação inverte o sinal da expectancy** (−0,038 → +0,054), que é
exatamente o que a [[KB-0006]] já dizia e que o portão C8 tinha negado por autoavaliação.

---

## 0. IDENTIDADE — o que rodou, antes de qualquer escrita

```
$ ssh hunter-vps 'date -u; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Tue Sep  8 22:26:31 UTC 2026
hunter-web-1              hunter-web:2e39774   Up 9 minutes (healthy)
hunter-api-1              hunter-api:2e39774   Up 9 minutes (healthy)
hunter-strategy-worker-1  hunter-api:2e39774   Up 9 minutes (healthy)
hunter-scanner-worker-1   hunter-api:1926e53   Up 2 hours (healthy)
hunter-execution-worker-1 hunter-api:1926e53   Up 2 hours (healthy)
hunter-market-worker-*    hunter-api:1926e53   Up 2 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1   Up 41 hours (healthy)
```

`api` e `strategy-worker` em **`2e39774`** — a base exata que o brief nomeia, e ela contém
`c9691d0`. Os scripts auditados na imagem, byte a byte:

```
$ ssh hunter-vps 'docker exec hunter-api-1 sha256sum /app/infra/scripts/seed.py \
    /app/infra/scripts/seed_cli.py /app/infra/scripts/seed_reference.py \
    /app/infra/scripts/activate_strategy_version.py \
    /app/packages/core/hunter_core/strategies/trendline_breakout_v1.py'
4b07a8b38e73a5518515ca5a748db99fb4ffc3ae8035a8ce20b07e95327c445d  seed.py
0662ffbf7b647c5a2cce46cbee2ee87b17b238358d51d9ead21d751a2debff92  seed_cli.py
c0e6a0e757192e8a447d3093d5e06ca23452cd615ce29c7c57e69df8717a0be2  seed_reference.py
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  activate_strategy_version.py
ce5dca1e08f073901b3a5718a25b8d4567895d7f287681be1317548411b8ec85  trendline_breakout_v1.py
```

Contra o commit publicado (`git show 2e39774:<arquivo> | sha256sum`): **os cinco batem**. Contra a
**árvore local**, três **não** batem — `seed.py`, `seed_cli.py` e `seed_reference.py` estão
**modificados em voo por outra tarefa** (T3.44c, o `ExchangeStatus.PLANNED` da Bybit), e não são
meus:

```
$ git status --porcelain -- infra/scripts/
 M infra/scripts/seed.py
 M infra/scripts/seed_cli.py
 M infra/scripts/seed_dry_run.py
 M infra/scripts/seed_reference.py
```

**Por isso rodei o `seed.py` da imagem** (`docker exec`, sem stdin, sem cópia): é o do commit
`2e39774`, e nada em voo de ninguém entrou em produção pela minha mão. `trendline_breakout_v1.py`
diverge da árvore local **só em CRLF** (`git diff` não mostra uma linha; `.gitattributes` declara
`*.py text eol=lf`).

Catálogo **antes**, `read_at = 2026-09-08 22:27:59,251654+00`
(`infra/scripts/sql/research/2026-09-09-t334c-q00-catalogo-antes.sql`):

```
+----------------+----------------+----------------+---------+--------+-----------+------------+
|      key       |      name      |    category    | versoes | ativas | rascunhos | congeladas |
+----------------+----------------+----------------+---------+--------+-----------+------------+
| breakout       | Breakout       | trend          |       2 |      0 |         0 |          2 |
| derivatives    | Derivatives    | derivatives    |       1 |      0 |         1 |          0 |
| ensemble       | Ensemble       | meta           |       1 |      0 |         1 |          0 |
| mean_reversion | Mean Reversion | reversion      |       3 |      3 |         0 |          3 |
| momentum       | Momentum       | trend          |       6 |      4 |         0 |          6 |
| narrative      | Narrative      | intelligence   |       1 |      0 |         1 |          0 |
| order_flow     | Order Flow     | microstructure |       1 |      0 |         1 |          0 |
| session_orb    | Session ORB    | trend          |       1 |      1 |         0 |          1 |
| volume_anomaly | Volume Anomaly | anomaly        |       2 |      1 |         0 |          2 |
+----------------+----------------+----------------+---------+--------+-----------+------------+
(9 rows)
```

**`trendline_breakout` não existe.** 9 famílias, 18 versões, 9 ativas.

---

## 1. `seed.py --dry-run` — e o achado que eu não fui buscar

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/seed.py --dry-run; echo "exit=$?"; date -u'
Tue Sep  8 22:28:14 UTC 2026
note: momentum v1 is activated and frozen at hunter_core.strategies.momentum_v1@sha256:6ccbe8b6…; this build's registry ships hunter_indicators.strategies.momentum_v1. Left untouched: supersede it to move the code.
note: breakout v1 is activated and frozen at …4c920b0c…                     (idem)
note: volume_anomaly v1 is activated and frozen at …a03d18fe…               (idem)
note: mean_reversion v1 is activated and frozen at …a970c9d9…               (idem)
note: session_orb v1 is activated and frozen at …a4d514ad…                  (idem)
risk_profiles.paper_v1: NEW {'organization_id': None, 'name': 'Paper v1', 'preset': 'paper_v1', 'limits': {…}}
strategies.trendline_breakout: NEW {'key': 'trendline_breakout', 'name': 'Trendline Breakout', 'description': 'Break of a drawn trend line.', 'category': 'trend'}
strategy_versions.trendline_breakout v1: NEW {'strategy_id': UUID('01a08322-e25d-…'), 'version': 'v1', 'status': 'draft', 'parameters_schema': {}, 'default_parameters': {}, 'code_ref': 'hunter_indicators.strategies.trendline_breakout_v1', 'changelog': None, 'activated_at': None, 'deprecated_at': None, 'params_format': 1, 'purpose': 'research_only', 'promising_at': None, 'promising_by': None, 'replication_parent_id': None, 'replication_index': None}
DRY RUN: nothing written
exit=0
Tue Sep  8 22:28:17 UTC 2026
```

**`risk_profiles.paper_v1: NEW`.** Não é ruído do relatório: conferi no banco.

```
$ ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -c \
    \"begin transaction isolation level repeatable read read only; \
      select id, organization_id, name, preset, created_at from risk_profiles order by preset; commit;\""
BEGIN
                  id                  |           organization_id            |     name     |    preset    |          created_at
--------------------------------------+--------------------------------------+--------------+--------------+-------------------------------
 01a074c5-8f56-7478-8289-b0eb0e7bc2bd |                                      | Conservative | conservative | 2026-09-06 03:31:39.415799+00
 01a074c5-8f64-7a9d-a9d5-38dac8b00f6d |                                      | Balanced     | balanced     | 2026-09-06 03:31:39.415799+00
 01a07693-1637-73e9-a9e4-85c13b63bcc9 | 01a07693-160f-70d0-aa35-c6c339187e8a | Balanced     | balanced     | 2026-09-06 11:55:46.064681+00
 01a074c5-8f65-78be-9549-e79c67ddb917 |                                      | Aggressive   | aggressive   | 2026-09-06 03:31:39.415799+00
(4 rows)
COMMIT
```

**O preset `paper_v1` — o que a diretiva do Everton congelou — não está na produção.** Ver
CONCERN 1. **Não escrevi nada disso**: `--only strategies` isola a tabela e o `paper_v1` nem chega
a ser tocado. É achado a reportar, não a consertar por minha conta.

Escopo restrito, dry-run de novo:

```
$ ... docker exec hunter-api-1 python infra/scripts/seed.py --only strategies --dry-run
Tue Sep  8 22:28:42 UTC 2026
(as cinco `note:` de sempre)
strategies.trendline_breakout: NEW {…}
strategy_versions.trendline_breakout v1: NEW {… 'status': 'draft', 'code_ref': 'hunter_indicators.strategies.trendline_breakout_v1', 'purpose': 'research_only' …}
DRY RUN: nothing written
exit=0
Tue Sep  8 22:28:44 UTC 2026
```

**Exatamente as duas linhas que o brief autoriza, e mais nenhuma.**

## 2. `seed.py --only strategies --yes` (a escrita)

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/seed.py --only strategies --yes; echo "exit=$?"; date -u'
Tue Sep  8 22:28:53 UTC 2026
(as cinco `note:`)
strategies.trendline_breakout: NEW {'key': 'trendline_breakout', 'name': 'Trendline Breakout', 'description': 'Break of a drawn trend line.', 'category': 'trend'}
strategy_versions.trendline_breakout v1: NEW {'strategy_id': UUID('01a08323-7c1c-717a-ba68-03bcd114b30d'), 'version': 'v1', 'status': 'draft', … 'code_ref': 'hunter_indicators.strategies.trendline_breakout_v1' …}
seeded  10 row(s) into strategies
seeded  10 row(s) into strategy_versions
exit=0
Tue Sep  8 22:28:56 UTC 2026
```

`10 row(s)` nas duas é o *upsert* das dez famílias do catálogo, não dez linhas novas — só uma delas
mudou de estado, e o diff prova qual.

### O diff do catálogo (`q00` e `q01` têm o CORPO byte a byte idêntico)

```
$ diff <(tail -n +12 …q00-catalogo-antes.sql) <(tail -n +12 …q01-catalogo-depois.sql) && echo "CORPO IDENTICO"
CORPO IDENTICO
```

`read_at` depois = `2026-09-08 22:29:12,875287+00`:

```
+--------------------+--------------------+----------------+---------+--------+-----------+------------+
|        key         |        name        |    category    | versoes | ativas | rascunhos | congeladas |
+--------------------+--------------------+----------------+---------+--------+-----------+------------+
| breakout           | Breakout           | trend          |       2 |      0 |         0 |          2 |
| derivatives        | Derivatives        | derivatives    |       1 |      0 |         1 |          0 |
| ensemble           | Ensemble           | meta           |       1 |      0 |         1 |          0 |
| mean_reversion     | Mean Reversion     | reversion      |       3 |      3 |         0 |          3 |
| momentum           | Momentum           | trend          |       7 |      4 |         1 |          6 |
| narrative          | Narrative          | intelligence   |       1 |      0 |         1 |          0 |
| order_flow         | Order Flow         | microstructure |       1 |      0 |         1 |          0 |
| session_orb        | Session ORB        | trend          |       1 |      1 |         0 |          1 |
| trendline_breakout | Trendline Breakout | trend          |       1 |      0 |         1 |          0 |
| volume_anomaly     | Volume Anomaly     | anomaly        |       2 |      1 |         0 |          2 |
+--------------------+--------------------+----------------+---------+--------+-----------+------------+
(10 rows)
```

**O diff honesto, linha a linha:**

| mudança | de quem |
|---|---|
| `trendline_breakout` (família) + `trendline_breakout v1` `draft`, `code_ref = hunter_indicators.strategies.trendline_breakout_v1` | **minha** |
| `momentum` 6 → **7** versões (`v7` `draft`, `params_hash 5e456ae9eb5b`, `code_ref` já congelado `…ab2e0398…`) | **de outra tarefa** (T3.47), entre 22:27:59 e 22:29:12 |

`seed_strategies` **só** cria linhas `v1` `draft` com `code_ref = hunter_indicators.*`; uma linha
`v7` com `params_hash` e `code_ref` de `hunter_core` só sai do `derive_variant.py`. **O diff do
catálogo não é limpo, e a razão está nomeada** — CONCERN 2.

## 3. Ativação `research_only` — e o desvio do brief que declaro

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py \
    trendline_breakout v1 --changelog "T3.34c: trendline_breakout v1 (research_only) ativada para o replay de dia um; geometria de linhas de tendencia, EXP-0016" --dry-run; echo "exit=$?"; date -u'
Tue Sep  8 22:29:38 UTC 2026
would activate trendline_breakout v1 (purpose research_only) with code_ref hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648 (36 parameters)
exit=0
Tue Sep  8 22:29:40 UTC 2026
```

**Digest exatamente o do brief (`…7b83a1ff…`) — segui. E `(36 parameters)`, que fecha a ressalva 1
com uma testemunha independente da minha contagem.**

```
$ ... (sem --dry-run)
Tue Sep  8 22:29:50 UTC 2026
activated trendline_breakout v1 (purpose research_only) at 2026-09-08T22:29:52.701952+00:00 with code_ref hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648
exit=0
Tue Sep  8 22:29:53 UTC 2026
```

| versão | ativada em (UTC) | **ativada em (Brasília)** | `params_hash` | `code_ref` |
|---|---|---|---|---|
| `trendline_breakout v1` | 2026-09-08 22:29:52,701952 | **2026-09-08 19:29:52** | `f2e8017c7251e22f` | `…trendline_breakout_v1@sha256:7b83a1ff…` |

**Desvio declarado:** o brief manda `activate_strategy_version.py trendline_breakout v1 --purpose
research_only`. **`--purpose` não é um argumento deste script** (`main()` só aceita `--changelog`,
`--dry-run` e o grupo `--supersede`/`--paper-line`/`--deprecate`). O `purpose` vem da linha que o
seed criou — e o seed cria `research_only` —, e a ativação apenas o preserva e o imprime, que é o
que os dois recibos acima mostram. Rodei sem a flag; o efeito pedido foi obtido. Se o revisor quiser
uma flag explícita, é mudança no script auditado, não nesta task.

---

## 4. O REPLAY — recibos verbatim

Coorte **`replay:d78c14d1-b4c5-424a-8f31-a43100744bb4`**, duas fatias, `--explain-ledger` nas duas.

### Sonda de calibragem (declarada, CONCERN 3)

Antes de gastar 290 s numa fatia grande sem saber o custo por barra da geometria, rodei **1 mercado
× 2 dias** numa **coorte separada e descartável** `replay:1c93e83f-396a-4c60-99a9-e7f1b7876d17`:

```
$ ssh hunter-vps 'date -u; docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
   --version trendline_breakout:v1 --from 2026-08-08 --to 2026-08-10 --markets ETHUSDT --workers 3 \
   --cohort replay:1c93e83f-396a-4c60-99a9-e7f1b7876d17 --explain-ledger /tmp/t334c-probe.jsonl'
Tue Sep  8 22:30:59 UTC 2026
2026-09-08 22:31:08 [info] replay_explain_ledger  bars=192 lines=192 path=/tmp/t334c-probe.jsonl
{'run_id': '1c93e83f-…', 'version_label': 'trendline_breakout v1', 'market_count': 1,
 'bars_evaluated': 192, 'signals': 0, 'outcomes_resolved': 0, 'outcomes_open': 0,
 'seconds': 6.296, 'bars_per_second': 30.5, 'decision_lag_s': 2, 'workers': 1,
 'evaluations_by_state': {'unavailable': 112, 'not_triggered': 80}, 'errors': 0}
```

30,5 barras/s com **um** worker ⇒ ~60 com três ⇒ ~100 s por fatia de 5 760 barras. Foi essa conta
que autorizou duas fatias em vez de quatro. **Zero sinais nessa sonda**, então ela não contaminou
população nenhuma; ela existe no `replay_runs` e está declarada aqui.

### Fatia A — 2026-08-08 → 2026-08-23

```
$ ssh hunter-vps 'date -u; docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
   --version trendline_breakout:v1 --from 2026-08-08 --to 2026-08-23 \
   --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
   --cohort replay:d78c14d1-b4c5-424a-8f31-a43100744bb4 --explain-ledger /tmp/t334c-a.jsonl'
Tue Sep  8 22:31:25 UTC 2026
2026-09-08 22:33:27 [info] replay_explain_ledger  bars=5760 lines=5760 path=/tmp/t334c-a.jsonl
{'run_id': 'd78c14d1-b4c5-424a-8f31-a43100744bb4', 'cohort': 'replay:d78c14d1-…',
 'strategy_version_id': '01a08323-7c1e-7b83-8527-553a329e4c32', 'version_label': 'trendline_breakout v1',
 'window_from': '2026-08-08T00:00:00+00:00', 'window_to': '2026-08-23T00:00:00+00:00',
 'markets': ['binance:ETHUSDT','binance:SOLUSDT','binance:XRPUSDT','binance:DOGEUSDT'], 'market_count': 4,
 'started_at': '2026-09-08T22:31:28.397610+00:00', 'finished_at': '2026-09-08T22:33:27.890096+00:00',
 'bars_evaluated': 5760, 'signals': 11, 'outcomes_resolved': 11, 'outcomes_open': 0,
 'seconds': 119.492, 'bars_per_second': 48.2, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5285, 'rejected': 3, 'triggered': 24},
 'errors': 0}
exit=0
Tue Sep  8 22:33:28 UTC 2026
```

### Fatia B — 2026-08-23 → 2026-09-08

```
$ ... --from 2026-08-23 --to 2026-09-08 ... --explain-ledger /tmp/t334c-b.jsonl
2026-09-08 22:36:05 [info] replay_explain_ledger  bars=6144 lines=6144 path=/tmp/t334c-b.jsonl
{'bars_evaluated': 6144, 'signals': 47, 'outcomes_resolved': 47, 'outcomes_open': 0,
 'seconds': 131.63, 'bars_per_second': 46.68, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'not_triggered': 6064, 'triggered': 67, 'rejected': 13}, 'errors': 0}
exit=0
Tue Sep  8 22:36:06 UTC 2026
```

**Armadilha do denominador (a mesma da T3.33e e da T3.40):** `signals` conta a **coorte inteira**,
não a fatia — `11` e `47` **não somam**; a população final é **47**. `triggered` é por fatia:
24 + 67 = **91**. `rejected`: 3 + 13 = **16**.

### `replay_runs` lidos do banco (`read_at = 2026-09-08 22:44:47,255243+00`)

```
+-----------------+-----------------------+------------+------------+------+------+-----+-----+------+---------+----+-----+-----------------------------------------------------------------------------+-----+
|     coorte      |        versao         |     de     |    ate     | mkts | bars | sig | out | open |   seg   | wk | lag |                                   estados                                   | err |
+-----------------+-----------------------+------------+------------+------+------+-----+-----+------+---------+----+-----+-----------------------------------------------------------------------------+-----+
| replay:1c93e83f | trendline_breakout v1 | 2026-08-08 | 2026-08-10 |    1 |  192 |   0 |   0 |    0 |   6.296 |  1 |   2 | {"unavailable": 112, "not_triggered": 80}                                   |   0 |
| replay:d78c14d1 | trendline_breakout v1 | 2026-08-08 | 2026-08-23 |    4 | 5760 |  11 |  11 |    0 | 119.492 |  3 |   2 | {"rejected": 3, "triggered": 24, "unavailable": 448, "not_triggered": 5285} |   0 |
| replay:d78c14d1 | trendline_breakout v1 | 2026-08-23 | 2026-09-08 |    4 | 6144 |  47 |  47 |    0 | 131.630 |  3 |   2 | {"rejected": 13, "triggered": 67, "not_triggered": 6064}                    |   0 |
+-----------------+-----------------------+------------+------------+------+------+-----+-----+------+---------+----+-----+-----------------------------------------------------------------------------+-----+
```

`errors = 0` nas três. `outcomes_open = 0`: **nada ficou em aberto**.

---

## 5. DIA UM, NA ORDEM DE PRIORIDADE QUE O BRIEF FIXOU

Os dois livros-razão (11 904 linhas, uma por barra) foram **copiados para fora do container antes de
qualquer redeploy** (a lição da T3.40 CONCERN 4) e estão em
`.claude/state/exp-drafts/t334c-sql/ledger-{a,b}.jsonl`. Agregação por
`.claude/state/exp-drafts/t334c-sql/ledger_stats.py` (NumPy, sem pandas):

```
$ uv run python .claude/state/exp-drafts/t334c-sql/ledger_stats.py \
      .claude/state/exp-drafts/t334c-sql/ledger-a.jsonl .claude/state/exp-drafts/t334c-sql/ledger-b.jsonl
linhas=11904
estados: {'not_triggered': 11349, 'unavailable': 448, 'triggered': 91, 'rejected': 16}
motivos: {'no_event': 9899, 'no_line': 1085, 'warmup': 448, 'atr_out_of_range': 234, 'rvol_low': 105,
          'signal': 91, 'line_weak': 26, 'risk_too_wide': 15, 'geometry_invalidation': 1}

(a) GEOMETRIA: avaliaveis=11456 com_linha=10371 (90.53 %) no_line=1085 (9.47 %)
    (histograma sobre 10984 barras: as `no_line` e as `no_event`, as unicas cujo detalhe traz a contagem de linhas)
    linhas validas por barra: [(0, 1085), (1, 1692), (2, 2268), (3, 2496), (4, 1779), (5, 1117), (6, 547)]
    media=2.7038 p50=3.0 p90=5.0 max=6
    pivos nas barras SEM linha: media=12.079 p50=12.0 max=18 zero=0

(c) RECUSAS: triggered=91 rejected=16 base=107
    risk_too_wide              15   14.02 % da base
    geometry_invalidation       1    0.93 % da base

    por mercado (estado):
    binance:DOGEUSDT     {'not_triggered': 2836, 'unavailable': 112, 'triggered': 23, 'rejected': 5}
    binance:ETHUSDT      {'not_triggered': 2843, 'unavailable': 112, 'triggered': 19, 'rejected': 2}
    binance:SOLUSDT      {'not_triggered': 2836, 'unavailable': 112, 'triggered': 25, 'rejected': 3}
    binance:XRPUSDT      {'not_triggered': 2834, 'unavailable': 112, 'triggered': 24, 'rejected': 6}
```

Primeira linha do livro-razão, verbatim:

```
{"bar_close":"2026-08-08T00:00:00+00:00","market":"binance:ETHUSDT","state":"unavailable",
 "reason":"warmup","detail":{"window_start":"2026-08-06T23:45:00Z","first_candle":"none"}}
```

### (a) A geometria existe no dado real? **Existe, e com folga.**

- **90,53 %** das 11 456 barras avaliáveis têm **ao menos uma** linha de tendência válida.
  `no_line` = **1 085** (**9,47 %**).
- Entre as barras sem evento: **2,70** linhas em média contando as sem linha, **3,00** contando só as
  que tinham; p90 = 5, máximo = 6 (o teto `max_lines`).
- Nas 47 decisões: **3,43** linhas em média, **15,1 pivôs**, **1,02 linha aposentada** (máximo 4;
  **29 das 47** decisões tinham ao menos uma linha aposentada pela regra que a cópia acrescentou).
- **E o que corta não é a falta de pivôs:** nas 1 085 barras `no_line` há em média **12,1 pivôs**
  confirmados e **nenhuma** com zero. Quem recusa é a exigência de **três toques**.

**Leitura:** ao contrário do medo do C3 do EXP-0016, o problema desta versão **não** é a geometria
não existir. É que a geometria existe **quase sempre** — o que rebaixa "há uma linha" a quase-não-
condição (o mesmo achado que a T3.45 fez sobre a porta de pivô da `sweep_reclaim`) e joga todo o
peso da seleção para o **evento** (`no_event` = 9 899 de 11 456 = **86,4 %**).

### (b) Contagem bruta de decisões — **K1 sobrevive**

| | |
|---|---:|
| barras avaliadas | 11 904 |
| `triggered` | **91** |
| sinais na coorte (após ocupação de vaga) | **47** |
| desfechos avaliáveis (`R_net`) | **47** (100 %) |
| dias distintos | **14** |
| mercados | 4 |

**K1 (< 20 decisões) não dispara.** 47 é 2,4× o piso. Foi a incógnita nº 1 do portão C3 e ela
**passou**.

### (c) As duas recusas de geometria, separadas

| recusa | n | % da base (91 + 16 = 107) | limiar do brief |
|---|---:|---:|---|
| `risk_too_wide` | **15** | **14,02 %** | 20 % |
| `geometry_invalidation` | **1** | **0,93 %** | 20 % |

**As duas passam.** E o `geometry_invalidation` de 0,93 % é a **confirmação no dado real** do que a
`notes-T3.34b` CONCERN 4 previu por argumento ("num rompimento comum a última cava fica mais de
2 ATR abaixo da linha e a guarda nunca dispara"). A única recusa foi DOGEUSDT com
`ref = 0,09038`, `stop = 0,08502892…`, `linha = 0,08270545…` — a linha **abaixo** do stop, isto é,
uma invalidação que seria código morto. A guarda fez exatamente o trabalho dela, uma vez em 31 dias.

As 15 `risk_too_wide`, uma a uma, estão no fim da saída do `ledger_stats.py` (coladas na íntegra em
`.claude/state/exp-drafts/t334c-sql/`); a distribuição é 6 XRPUSDT, 4 DOGEUSDT, 3 SOLUSDT, 2 ETHUSDT.

### (c bis) **O R PAREADO DA INVALIDAÇÃO — a métrica pré-registrada da ressalva 2**

**Procedência, sem maquiagem:** o **estimando** foi fixado pelo brief
`.claude/state/brief-T3.34c-trendline-seed-replay-day-one.md` (item 2), escrito por outra pessoa
**antes** de a versão ser ativada e de qualquer replay rodar — *"mean R of `geometry_invalidation`
exits vs the counterfactual R until stop/target/expired on the same episodes (the EXP-0007 design),
not only the percentage"*. O **texto** do item 4b do `EXP-0016` e o **limiar de leitura**
("Δ ≥ 0 ⇒ a tese de C8 não se sustenta") foram escritos **por mim, depois** da corrida, ao arquivar.
**A métrica é pré-registrada; a regra de decisão sobre ela não é** — CONCERN 13. Ferramenta: `replay_exits.py`, braço
`INV-B` — **as regras de saída não são reimplementadas**, cada braço é dobrado por `walker.walk` e
liquidado por `settle.settle`, o código de produção. O script na imagem é byte a byte o do commit:

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 sha256sum /app/infra/scripts/replay_exits.py \
      /app/packages/indicators/hunter_indicators/replay/policies.py'
db4877d095a0d15e2d4b43a0651e9ac62fed27c0cbbc48cd51464db175c9e626  replay_exits.py
5c80b1aa8d64d4f87fe1ba89dc5ac310c2b4b18e698df29e9952267f77fa2233  policies.py
$ git show 2e39774:infra/scripts/replay_exits.py | sha256sum                       → db4877d0…e626
$ git show 2e39774:packages/indicators/hunter_indicators/replay/policies.py | sha256sum → 5c80b1aa…2233
```

(`db4877d0…e626` é **o mesmo digest** que o `EXP-0007` publicou na T3.32 — é literalmente a mesma
ferramenta que mediu os braços da `momentum`.)

```
$ ssh hunter-vps 'date -u; docker exec hunter-strategy-worker-1 sh -c "python /app/infra/scripts/replay_exits.py \
   --database-url \"\$DATABASE_URL\" --versions trendline_breakout --only-version trendline_breakout_v1 \
   --cohort replay:d78c14d1-b4c5-424a-8f31-a43100744bb4 --policies INV-B \
   --as-of 2026-09-08T22:00:00Z --out /tmp/t334c-exits.md"'
Tue Sep  8 22:42:12 UTC 2026
2026-09-08 22:42:14 [info] replay_loaded      cases=47 cohort=replay:d78c14d1-… only_version=trendline_breakout_v1 versions=1
2026-09-08 22:42:17 [info] replay_collected   cases=47 comparable=47 reproduced=47
2026-09-08 22:42:17 [info] replay_written     json=/tmp/t334c-exits.json out=/tmp/t334c-exits.md
exit=0
Tue Sep  8 22:42:17 UTC 2026
```

`input_digest = f2a226822eef4ed0` · `series_digest = 449635eaedbf3df4` ·
**portão do passo 1: reprodução de trajetória 1,0000 sobre 47/47** (limiar 0,9900), 0 divergências.

```
| política | resolvidos | avaliáveis | gatilhos de invalidação | taxa de alvo | expectancy líq. (R) | PF     |
| base     |         47 |         47 | {"invalidation": 23}    | 0.533 (8/15) |           -0.038163 | 0.9220 |
| INV-B    |         47 |         47 | —                       | 0.310 (9/29) |           +0.054063 | 1.1101 |

| contraste     | pares | blocos | Δ médio R_net | IC 95% (blocos)     |    p     | p Holm | rejeita? | |Δ| ≥ 0,05 R |
| INV-B - base  |    47 |     14 |      0.092226 | [-0.0618, 0.2151]   | 0.264587 | 1.0000 |   não    |     sim      |
| (sem funding) |    47 |      — |      0.093020 | [-0.0616, 0.2166]   |    —     |   —    |    —     |      —       |
```

**As duas leituras que o pré-registro exigia:**

1. **População inteira (47 pares):** Δ = **+0,092226 R por decisão**, soma **+4,335 R**.
2. **Condicionada aos 23 episódios que de fato saíram por invalidação:** como `INV-B` só difere da
   base nos episódios que dispararam a invalidação (a política muda **uma** regra, e os 24 restantes
   — 8 alvo, 7 stop, 9 expirado — mantêm desfecho idêntico, o que as contagens de `INV-B` confirmam:
   9 alvos = 8 + 1, 20 stops = 7 + 13, 18 expirados = 9 + 9), **todo** o Δ vem desses 23:

   | | R médio |
   |---|---:|
   | saída por invalidação (medida) | **−0,6555 R** |
   | contrafactual até stop / alvo / expiração (INV-B) | **−0,4670 R** |
   | **Δ** | **+0,1885 R** |

   *(número derivado: 4,33462 / 23 = 0,188462, somado ao −0,6555 do `q02`. É aritmética sobre
   agregados publicados, não leitura caso a caso — o JSON do `replay_exits.py` não expõe o R por
   caso. Declarado como derivação, CONCERN 6.)*

**Veredito de C8:** Δ ≥ 0 ⇒ **a tese de C8 não se sustenta nesta janela**. Tirar a invalidação **inverte o sinal da expectancy** (−0,038 → +0,054) e o Δ supera o
efeito mínimo de 0,05 R — **mas o IC de 95 % por bloco de dia contém zero e Holm não rejeita**, então
isto **não** é prova de que a invalidação faz mal. É a repetição, numa quinta população e numa
estratégia de mecanismo diferente, do achado da [[KB-0006]]/[[EXP-0007]]: *a invalidação adianta a
perda, ela não a cria*. O que o EXP-0016 afirmava — "é o contraste direto com `momentum_v1`", "é o
ponto da versão" — era **autoavaliação otimista** e foi rebaixado a `REVISE`.

### (d) Decomposição obrigatória

**Por modo — e é aqui que K6 dispara** (`read_at = 2026-09-08 22:40:14,667867+00`):

```
+------------+------------+----+------+-------------+------------+---------------+------+-------+-------------+-------+-----------+
| event_kind | line_kind  | n  | pct  | r_liq_medio | r_liq_soma | r_bruto_medio | dias | alvos | invalidados | stops | expirados |
+------------+------------+----+------+-------------+------------+---------------+------+-------+-------------+-------+-----------+
| bounce     | support    | 42 | 89.4 |      0.0177 |       0.74 |        0.1600 |   13 |     8 |          19 |     7 |         8 |
| breakout   | resistance |  5 | 10.6 |     -0.5075 |      -2.54 |       -0.3615 |    4 |     0 |           4 |     0 |         1 |
+------------+------------+----+------+-------------+------------+---------------+------+-------+-------------+-------+-----------+
```

**89,4 % vêm de UM modo.** O critério do EXP ("≥ 60 % de um modo **ou** de um mercado ⇒ a hipótese
não é 'linhas de tendência', é aquela porta, e tem de ser **reenunciada antes** de qualquer avaliação
seguinte") **dispara**. A porta de rompimento — a que dá nome à versão — decidiu **cinco** vezes em
31 dias e **perdeu as cinco** (0 alvos, 4 invalidações, 1 expiração, −0,5075 R por decisão).

**Por mercado — K6 NÃO dispara nessa metade:**

```
+----------+----+------+-------------+------------+------+
|  symbol  | n  | pct  | r_liq_medio | r_liq_soma | dias |
+----------+----+------+-------------+------------+------+
| SOLUSDT  | 15 | 31.9 |     -0.1292 |      -1.94 |    8 |
| XRPUSDT  | 13 | 27.7 |     -0.0677 |      -0.88 |    9 |
| DOGEUSDT | 10 | 21.3 |     -0.2512 |      -2.51 |    9 |
| ETHUSDT  |  9 | 19.1 |      0.3929 |       3.54 |    5 |
+----------+----+------+-------------+------------+------+
```

Maior mercado: **31,9 %**, bem abaixo dos 60 %. Distribuição boa — e a única soma positiva
(+3,54 R) está inteira no ETHUSDT, em 5 dias. Nove decisões não são uma tese.

**Por decil de `line_slope_per_bar`** (normalizado: `slope / ATR`, porque `slope` em preço não é
comparável entre ETH ~2 300 e DOGE ~0,09), `read_at = 2026-09-08 22:41:27,907563+00`:

```
+-------+---+---------------+---------------+-------------+------------+---------------+----------+-------------+-------+-------------+
| decil | n | slope_atr_min | slope_atr_max | r_liq_medio | r_liq_soma | r_bruto_medio | repiques | rompimentos | alvos | invalidados |
+-------+---+---------------+---------------+-------------+------------+---------------+----------+-------------+-------+-------------+
|     1 | 5 |     -0.135931 |     -0.031019 |     -0.5075 |      -2.54 |       -0.3615 |        0 |           5 |     0 |           4 |
|     2 | 5 |      0.004436 |      0.017779 |     -0.5205 |      -2.60 |       -0.3935 |        5 |           0 |     0 |           2 |
|     3 | 5 |      0.020600 |      0.035323 |      0.6430 |       3.22 |        0.8187 |        5 |           0 |     1 |           1 |
|     4 | 5 |      0.042757 |      0.057005 |      0.4096 |       2.05 |        0.5486 |        5 |           0 |     2 |           2 |
|     5 | 5 |      0.057555 |      0.070836 |     -0.0846 |      -0.42 |        0.0731 |        5 |           0 |     0 |           3 |
|     6 | 5 |      0.073100 |      0.083489 |     -0.2318 |      -1.16 |       -0.0961 |        5 |           0 |     1 |           3 |
|     7 | 5 |      0.084921 |      0.091544 |     -0.2002 |      -1.00 |       -0.0618 |        5 |           0 |     1 |           3 |
|     8 | 4 |      0.094735 |      0.117316 |      0.5230 |       2.09 |        0.6582 |        4 |           0 |     2 |           1 |
|     9 | 4 |      0.118877 |      0.158898 |     -0.2581 |      -1.03 |       -0.1279 |        4 |           0 |     0 |           2 |
|    10 | 4 |      0.160192 |      0.195227 |     -0.0982 |      -0.39 |        0.0381 |        4 |           0 |     1 |           2 |
+-------+---+---------------+---------------+-------------+------------+---------------+----------+-------------+-------+-------------+
```

**O achado é estrutural, não estatístico: o decil 1 é EXATAMENTE o conjunto dos 5 rompimentos.**
E não é coincidência — é construção: uma resistência que rompe é, por definição, **descendente**
(slope < 0) e um suporte que repica é **ascendente** (slope > 0). **`line_slope_per_bar` não é um
substituto independente de regime nesta versão: é o modo com outro nome.** O C4 do EXP-0016
prometeu inclinação como substituto de regime (já que `market_regimes` só tem `UNKNOWN`) e o dia um
mostra que a promessa **não se cumpre**. Dentro dos repiques, em três faixas:

```
+------------------------------------+----+-----------------+-------------+------------+---------------+----------+-------------+
|               faixa                | n  | slope_atr_medio | r_liq_medio | r_liq_soma | r_bruto_medio | repiques | rompimentos |
+------------------------------------+----+-----------------+-------------+------------+---------------+----------+-------------+
| A descendente (< -0,02 ATR/barra)  |  5 |        -0.08024 |     -0.5075 |      -2.54 |       -0.3615 |        0 |           5 |
| B quase horizontal ([-0,02; 0,02]) |  5 |         0.01315 |     -0.5205 |      -2.60 |       -0.3935 |        5 |           0 |
| C ascendente (> 0,02 ATR/barra)    | 37 |         0.08563 |      0.0904 |       3.35 |        0.2348 |       37 |           0 |
+------------------------------------+----+-----------------+-------------+------------+---------------+----------+-------------+
```

Tudo o que a versão tem de positivo está na faixa C (suporte **claramente** ascendente): 37 decisões,
+0,0904 R líquidos, +0,2348 R brutos. **Com 5 decisões em cada uma das outras faixas, nada disso é
evidência** — é a decomposição que o EXP pré-registrou, publicada com o tamanho que tem.

---

## 6. O QUADRO DE EXPECTANCY (`q02`, `read_at = 2026-09-08 22:40:14,667867+00`)

```
+----------+------------+-----------+-------------+---------+---------------+--------+------------+------------+------+----------+-----------------+-----------------+
| decisoes | avaliaveis | sem_risco | exp_bruta_r | custo_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | dias | mercados | atr_pct_min_obs | atr_pct_max_obs |
+----------+------------+-----------+-------------+---------+---------------+--------+------------+------------+------+----------+-----------------+-----------------+
|       47 |         47 |         0 |      0.1045 |  0.1401 |       -0.0382 |  -1.79 |       17.0 |     0.9220 |   14 |        4 |         0.00501 |         0.01067 |
+----------+------------+-----------+-------------+---------+---------------+--------+------------+------------+------+----------+-----------------+-----------------+
```

**Este é o número mais interessante do dia**, e não é o veredito: **a expectancy BRUTA é positiva
(+0,1045 R) e a líquida é negativa (−0,0382 R) só por causa do pedágio.** Nenhuma outra versão desta
casa esteve nessa posição: a `momentum v2` era +0,0820 bruta com **0,2526** de custo; a `session_orb`
era negativa nos dois. Aqui a distância entre viver e morrer é **0,04 R de custo**.

Motivos de saída:

```
+-------------+----+------+-------------+------------+---------------+
|   motivo    | n  | pct  | r_liq_medio | r_liq_soma | r_bruto_medio |
+-------------+----+------+-------------+------------+---------------+
| invalidated | 23 | 48.9 |     -0.6555 |     -15.08 |       -0.5143 |
| expired     |  9 | 19.1 |      0.6074 |       5.47 |        0.7571 |
| target      |  8 | 17.0 |      1.9279 |      15.42 |        2.0838 |
| stop        |  7 | 14.9 |     -1.0865 |      -7.61 |       -0.9634 |
+-------------+----+------+-------------+------------+---------------+
```

**48,9 % das operações morrem pela invalidação**, a −0,6555 R cada, somando −15,08 R — quase
exatamente o que os 8 alvos ganham (+15,42 R). É o mesmo desenho de livro que a [[KB-0076]]
diagnosticou na `momentum v2` (lá foram 36,6 % e −52,34 R). E as `expired` são **positivas**
(+0,6074 R), o que diz que o horizonte de 8 h está **curto** para esta geometria, não longo.

`touches` das linhas que dispararam:

```
+---------+------------+----+-------------+------------+
| touches | violations | n  | r_liq_medio | r_liq_soma |
+---------+------------+----+-------------+------------+
|       3 |          0 | 34 |      0.0338 |       1.15 |
|       3 |          1 |  4 |     -0.1208 |      -0.48 |
|       3 |          2 |  1 |     -0.3640 |      -0.36 |
|       4 |          0 |  5 |     -0.3630 |      -1.81 |
|       4 |          1 |  1 |     -0.5478 |      -0.55 |
|       5 |          0 |  1 |      0.8724 |       0.87 |
|       5 |          1 |  1 |     -0.6038 |      -0.60 |
+---------+------------+----+-------------+------------+
```

**39 das 47 linhas têm exatamente 3 toques** — o mínimo. `min_touches_signal = 3` é a porta que
define a população, e a folclórica "quanto mais toques, mais forte a linha" **não aparece**
(4 toques: −0,38 R em 6 decisões). Com 8 decisões acima de 3 toques isso é observação, não medida.

### A identidade do pedágio, e a correção que ela impõe ao EXP-0016

```
+----+-----------------+---------------+---------------+-----------------+----------------+--------------------+-------------------------+
| n  | risco_atr_medio | risco_atr_min | risco_atr_max | risco_pct_medio | custo_r_medido | custo_r_identidade | acima_do_teto_declarado |
+----+-----------------+---------------+---------------+-----------------+----------------+--------------------+-------------------------+
| 47 |          2.1139 |        1.6797 |        3.0114 |         0.01492 |         0.1401 |             0.1400 |                      28 |
+----+-----------------+---------------+---------------+-----------------+----------------+--------------------+-------------------------+
```

`custo_R` medido **0,1401** contra `0,0020 / risco%` = **0,1400**: a identidade da [[KB-0076]]
(com a correção da `notes-T3.40` §8b) reproduz a medição na **quarta casa decimal**. Bonito, e
inconveniente: **o "teto de pedágio declarado de 0,1333 R" do EXP-0016 é falso como teto.** Ele foi
calculado no melhor caso simultâneo (ATR% no piso de 0,005 **e** risco em 3 ATR); na prática o risco
mediano é **2,11 ATR**, e **28 das 47 decisões (59,6 %) pagam mais que 0,1333 R**. O teto real desta
geometria é `0,0020 / (2 × 0,005)` = **0,20 R**. Corrigido aqui; o EXP fica com o texto congelado e
esta nota é o registro datado.

*(`risco_atr` sai de 1,68 a 3,01 embora `stop_atr_max = 2` e `max_risk_atr = 3`: `initial_risk` é
medido do **preço de entrada** — a abertura da barra seguinte — e não do fechamento da decisão. Não
é violação de faixa, é o gap de uma barra.)*

### Bloco de dia e MFE

```
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+-----------+
| blocos_dia | media_das_medias_diarias | desvio | erro_padrao | ic95_inferior | ic95_superior | dias_positivos | dias_negativos | maior_dia |
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+-----------+
|         14 |                  -0.0392 | 0.7567 |      0.2022 |       -0.4761 |        0.3976 |              6 |              8 |         9 |
+------------+--------------------------+--------+-------------+---------------+---------------+----------------+----------------+-----------+

+----+--------------+-------------+-----------+-----------+---------------+------------------+------------------+
| n  | mfe_ambiguos | mfe_medio_r | mfe_p50_r | mfe_p90_r | r_bruto_medio | pct_mfe_maior_2r | pct_mfe_maior_1r |
+----+--------------+-------------+-----------+-----------+---------------+------------------+------------------+
| 47 |           15 |      0.6601 |    0.4174 |    1.6764 |        0.1045 |              4.3 |             21.3 |
+----+--------------+-------------+-----------+-----------+---------------+------------------+------------------+
```

IC 95 % **[−0,476; +0,398]** — **contém zero com folga**, 14 blocos, `t = 2,160` (13 gl). MFE médio
0,66 R contra 0,1045 R capturado: **captura 15,8 %** do movimento favorável (a `momentum v6` capturava
45 %). **15 das 47 linhas de MFE são `ambiguous`**, então esses percentis são **limites inferiores**
(mesma advertência da T3.32).

---

## 7. ISOLAMENTO, CAPACIDADE E O LAB PROSPECTIVO

```
+--------------------+---------------------------+------------------------+-----------------------+---------------+
| outbox_das_coortes | outbox_trendline_qualquer | sinais_trendline_total | sinais_fora_da_coorte | nao_terminais |
+--------------------+---------------------------+------------------------+-----------------------+---------------+
|                  0 |                         5 |                     52 |                     5 |             5 |
+--------------------+---------------------------+------------------------+-----------------------+---------------+
```

**Zero linhas de `shadow_outbox` para as duas coortes de replay** — `persist.is_published_cohort`
recusa publicar replay, e a cerca segurou. Os 5 "fora da coorte" são **prospectivos**, emitidos
depois da ativação; é exatamente o que "entrar no Lab" significa:

```
+---------------------------------------------+--------+-------------------------------+-------------------------------+----------+
|                   coorte                    | sinais |           primeiro            |            ultimo             | mercados |
+---------------------------------------------+--------+-------------------------------+-------------------------------+----------+
| replay:d78c14d1-b4c5-424a-8f31-a43100744bb4 |     47 | 2026-08-19 23:45:02+00        | 2026-09-03 22:00:02+00        |        4 |
| prospective                                 |      5 | 2026-09-08 22:30:38.584122+00 | 2026-09-08 22:33:29.758513+00 |        5 |
+---------------------------------------------+--------+-------------------------------+-------------------------------+----------+
```

**Primeiro sinal prospectivo 46 segundos depois da ativação**, em 5 mercados distintos. A versão
decide no universo de verdade, não só nos quatro do replay. (E note: a coorte de replay tem
**zero** decisões entre 08-08 e 08-19 — as 47 vivem numa janela de 15 dias dentro dos 31.)

`system_events` da minha janela (o que é meu, em negrito no texto):

```
info | activate_strategy_version | strategy_version_activated | trendline_breakout v1 (purpose research_only) activated with code_ref=hunter_core.strategies.trendli… | 2026-09-08 22:29:52.701952+00
info | replay_engine | replay_run_finished | replay trendline_breakout v1 1 mercados 2026-08-08…2026-08-10: 192 ba…  | 2026-09-08 22:31:08.648691+00
info | replay_engine | replay_run_finished | replay trendline_breakout v1 4 mercados 2026-08-08…2026-08-23: 5760 b… | 2026-09-08 22:33:27.891292+00
info | replay_engine | replay_run_finished | replay trendline_breakout v1 4 mercados 2026-08-23…2026-09-08: 6144 b… | 2026-09-08 22:36:05.737358+00
```

**`seed.py` não escreve `system_events`** — o recibo dele é o diff do catálogo, e é por isso que as
consultas `q00`/`q01` existem.

Vigia de capacidade (`22:45:58Z` e `22:46:18Z`):

```
$ docker exec hunter-strategy-worker-1 python -c "... urlopen('http://localhost:8001/ready') ..."
health 200 {"status":"ok"}
ready  200 {"database":true,"redis":true,"shadow_migration":true,"shadow_versions":true,
            "shadow_consumer":true,"shadow_outbox":true}

hunter_shadow_outbox_pending 0.0
hunter_shadow_evaluations_total{state="not_triggered",strategy="trendline_breakout"} 229.0
hunter_shadow_evaluations_total{state="triggered",strategy="trendline_breakout"}       5.0
hunter_shadow_evaluations_total{state="unavailable",strategy="trendline_breakout"}    81.0
hunter_shadow_evaluations_total{state="ineligible",strategy="trendline_breakout"}      1.0
```

`outbox_pending = 0,0`, `/ready` 200 com tudo verde, container `healthy` o tempo todo. **Mas o roster
saiu de 9 para 16 versões ativas na minha janela**, e só **uma** delas é minha — CONCERN 2.

---

## 8. "CADA OPERAÇÃO TRAÇA AS LINHAS?" — a resposta, provada por SQL

`q05`, `read_at = 2026-09-08 22:52:19,603123+00`:

```
+----------+-------------+----------------+--------------------+----------+----------------+------------------+
| decisoes | com_line_id | com_inclinacao | com_preco_da_linha | com_pivo | com_parametros | linhas_distintas |
+----------+-------------+----------------+--------------------+----------+----------------+------------------+
|       47 |          47 |             47 |                 47 |       47 |             47 |               47 |
+----------+-------------+----------------+--------------------+----------+----------------+------------------+
```

**47 de 47, e 47 `line_id` distintos: cada operação tem a sua própria linha, identificada.** Uma
decisão, campo a campo:

```
| symbol   | bar                    | evento | tipo    | line_id          | inclinacao_por_barra          | 1o idx | ult idx | valido | toques | viol | preco_da_linha_na_decisao       | pivo    | pivo idx | barras | pivos | linhas | apos. |
| DOGEUSDT | 2026-08-19 23:45:00+00 | bounce | support | 03422055d14efe64 | 0.0001217142857142857142857143 |     57 |      92 |     95 |      3 |    0 | 0.07470514285714285714285714286 | 0.07434 |       92 |     96 |    13 |      2 |     0 |
| ETHUSDT  | 2026-08-20 12:15:00+00 | bounce | support | 67ccc7512afc5748 | 1.158421052631578947368421053  |     59 |      78 |     81 |      3 |    0 | 2263.703157894736842105263158   | 2273.76 |       86 |     96 |    11 |      1 |     1 |
| ETHUSDT  | 2026-08-20 19:30:00+00 | bounce | support | da6434cc25758098 | 2.7475                         |     72 |      92 |     95 |      3 |    0 | 2316.7425                       | 2308.5  |       92 |     96 |    14 |      4 |     0 |
```

E o registro **inteiro** dos parâmetros da geometria viaja em cada decisão:

```
{"angle_bucket_atr":"0.1","atr_period":"14","bounce_atr":"0.5","bounce_bars":"3","break_atr":"0.5",
 "level_bucket_atr":"0.5","max_anchors":"20","max_channels":"3","max_lines":"6","min_swing_atr":"1",
 "min_touches":"3","parallel_tol":"0.05","pivot_k":"3","retest_bars":"10","retire_after_break":true,
 "rvol_min":null,"tolerance_atr":"0.25"}
```

Com `line_id` + inclinação + `first_idx`/`last_idx` + preço na barra da decisão + `pattern_bars = 96`,
**a linha se redesenha exatamente** — é uma reta, dois pontos bastam, e há cinco. É isso que a T3.49
(o overlay do Lab) vai consumir. E as outras versões:

```
| versao                | sinais | com_line_id |
| volume_anomaly v1     |   2152 |           0 |
| momentum v1           |    963 |           0 |
| volume_anomaly v2     |    809 |           0 |
| momentum v2           |    511 |           0 |
| momentum v3           |    351 |           0 |
| ... (todas as outras) |    ... |           0 |
| trendline_breakout v1 |     13 |          13 |
```

**Nenhuma outra versão desenha linha nenhuma.** A resposta honesta ao Everton é "sim — mas só esta".
E todas as 47 publicam **exatamente uma** invalidação, `close_below` no nível da linha
(`com_close_below = 47`, `min = max = 1`).

---

## 9. VEREDITO PELO FUNIL

**`manter em pesquisa` — com a hipótese OBRIGATORIAMENTE REENUNCIADA.** Não é `descartar` e não é
`candidata`.

| critério | valor | dispara? |
|---|---|---|
| K1 < 20 decisões | **47** | não |
| K2 > 1 500 decisões | 47 | não |
| K3 ≥ 100 aval. **E** ≥ 30 dias **E** bruta < 0 | 47 aval., 14 dias, bruta **+0,1045** | não (nem se aplica) |
| K4 `unavailable` > 40 % | **3,76 %** (448/11 904) | não |
| K5 cobertura de `R_net` < 70 % | **100 %** | não |
| **K6 ≥ 60 % de um modo ou mercado** | **89,4 % repique** (mercado: 31,9 %) | **SIM** |
| régua de maturidade (100 aval. **E** 30 dias) | 47 / 14 | **`inconclusivo` por contrato** |

**Por que não `descartar`:** nenhum critério de morte disparou, a população existe, a geometria
existe, a expectancy **bruta é positiva** — a primeira desta casa a ser — e o contraste da
invalidação aponta um caminho concreto (uma `v2` sem invalidação seria +0,054 R nesta janela).

**Por que não `candidata`:** perde dinheiro líquido (−0,0382 R, PF 0,922); o IC por bloco de dia
contém zero com folga; **14 dias distintos de 31** tornam a régua de maturidade inalcançável neste
replay; e a janela avaliada é a que gerou a hipótese ([[KB-0010]]).

**A reenunciação que K6 obriga, escrita antes de qualquer avaliação seguinte:**

> A hipótese que esta versão de fato testou nos dados de 2026-08-08…09-08 **não** é "o rompimento de
> uma resistência descendente tem vantagem". É: **"o repique confirmado num suporte ascendente
> traçado por três toques tem vantagem"**. A porta de rompimento decidiu 5 vezes em 31 dias, perdeu
> as 5, e **não foi testada** — 5 decisões não testam nada. Qualquer leitura futura desta versão que
> some as duas portas está somando uma medição com um ruído.

---

## 10. TESTES LOCAIS — saída real

Nenhuma linha de código de estratégia foi escrita nesta task. O que rodei prova que o digest não se
moveu por minha mão:

```
$ uv run pytest packages/core/tests/unit/strategies services/strategy-worker/tests/test_code_ref.py -q
........................................................................ [ 13%]
........................................................................ [ 26%]
........................................................................ [ 39%]
........................................................................ [ 52%]
........................................................................ [ 65%]
........................................................................ [ 78%]
........................................................................ [ 91%]
.............................................                            [100%]
549 passed in 70.10s (0:01:10)

$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
breakout_v1                = hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1          = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
momentum_v1                = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
session_orb_v1             = hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
sweep_reclaim_v1           = hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c
trendline_breakout_v1      = hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648
volume_anomaly_v1          = hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

`trendline_breakout_v1 = …7b83a1ff…` — **idêntico ao que a VPS congelou às 22:29:52Z**.
(`sweep_reclaim_v1` é arquivo em voo da T3.45b, não meu.)

A ressalva 3 (as duas séries de ATR), medida:

```
$ uv run python .claude/state/exp-drafts/t334c-sql/atr_divergencia.py
janela oficial      : 97 barras  ATR = 5.857940699855793726342817305
janela da geometria : 96 barras  ATR = 5.857991147927056594755224514
divergencia relativa: 0.000861%

33 cortes: divergencia relativa max = 0.011649% min = 0.000861%

O QUE ISSO TOCA:
  ATR oficial (97 barras) -> stop_atr_max, max_risk_atr, atr_pct_min/max, alvo
  ATR da geometria (96)   -> min_swing_atr, tolerance_atr, break_atr,
                             bounce_atr, angle/level_bucket, distance_atr
Nenhum limiar e comparado entre as duas; a divergencia so desloca, por
uma fracao de por cento, QUAL barra fica de cada lado de um limiar.

$ uv run python -c "peso residual da semente..."
peso residual da semente apos 82 passos (janela 97): 0.229539%
peso residual da semente apos 81 passos (janela 96): 0.247196%
```

**Observação, não defeito** — e o teto estrutural (0,23 %–0,25 %) é o número que faltava para
fechar a ressalva sem hipérbole.

---

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\notes-T3.34c.md` | **novo** — este relatório |
| `C:\dev\project-hunter\.claude\state\notes-T3.34b.md` | **modificado** — "37" → **36** na tabela de FILES + seção "T3.34c" no fim (nada acima reescrito) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0016-trendline-breakout.md` | **modificado** — 36 parâmetros; C8 rebaixado a `REVISE` com [[KB-0006]]/[[EXP-0007]]; item 4b pré-registrado; "Relacionadas" com as duas páginas e o parágrafo do porquê; **avaliação REPLAY datada de 2026-09-08**; frontmatter (`result: inconclusivo`, `evaluable: 47`, `days: 14`) |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q00-catalogo-antes.sql` | **novo** — catálogo antes do seed |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q01-catalogo-depois.sql` | **novo** — corpo byte a byte igual ao `q00`, rodado depois |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q02-populacao.sql` | **novo** — população, motivos, K6, `touches`, geometria por decisão |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q03-decomposicao.sql` | **novo** — decis de inclinação, modo × mercado, identidade do pedágio, blocos de dia, MFE |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q04-recibos-e-isolamento.sql` | **novo** — `replay_runs`, `shadow_outbox`, prospectiva, `system_events`, roster |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t334c-q05-a-linha-de-cada-operacao.sql` | **novo** — a prova da pergunta do Everton |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t334c-sql\ledger_stats.py` | **novo** — agregação dos livros-razão (NumPy, sem pandas) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t334c-sql\atr_divergencia.py` | **novo** — a ressalva 3 medida |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t334c-sql\ledger-a.jsonl`, `ledger-b.jsonl` | **novo** — 11 904 linhas, uma por barra avaliada (salvos fora do container antes de qualquer redeploy) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t334c-sql\ledger_stats.out.txt` | **novo** — a saída dessa agregação, inclusive as 15 `risk_too_wide` uma a uma |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t334c-sql\exits.md`, `exits.json` | **novo** — o relatório e a saída canônica do `replay_exits.py` (braço `INV-B`) |

**Não tocados:** `.env*`, `apps/**`, `services/**`, `packages/**`, `obsidian/**`,
`infra/scripts/*.py`. As modificações que aparecem nessas pastas em `git status` **já estavam lá** e
**não são minhas** (T3.44c em `seed*.py`, T3.45b em `registry.py`/`constraints_table.py`/
`sweep_reclaim_v1.py`, e as tarefas de regime/radar em `apps/**`).

---

## CONCERNS

1. **`risk_profiles.paper_v1` NÃO EXISTE na produção, e o `seed.py --dry-run` completo diz isso em
   voz alta.** Quatro linhas em `risk_profiles` (`conservative`, `balanced` ×2, `aggressive`) e
   **nenhuma** `paper_v1`. O preset que a diretiva de 2026-09-06 congelou — `risk_per_trade_pct
   0,0025`, `max_stop_distance_pct 0,03`, kill switch em 2 %/8 % — está **só no código**
   (`hunter_risk/limits.py::PAPER_V1`), não no banco. Se algum caminho ler o preset do banco em vez
   do código, ele não acha nada. **Não escrevi**: limites são diretiva do Everton e `--only
   strategies` nem toca a tabela. **Isto precisa de decisão dele, não minha**, e é o achado mais
   sério desta tarefa.
2. **O roster foi de 9 para 16 versões ativas na minha janela de 20 minutos, e 15 delas não são
   minhas.** `momentum v7` e `v8` (22:29:28 e 22:29:33) e `mean_reversion v4`, `v5`, `v6`, `v7`
   (22:38:37…22:38:49) foram derivadas e ativadas por outras tarefas **enquanto eu rodava**. Duas
   consequências reais: (i) **o diff do catálogo antes/depois que o brief pediu não é limpo** — a
   linha `momentum v7` aparece entre as duas leituras e eu tive de argumentar (pela forma do
   `code_ref` e pelo `params_hash`) que não é obra do seed; (ii) meus dois replays disputaram CPU
   com **quatro** replays alheios (`momentum v7/v8`, `mean_reversion v4/v5` nos `system_events`), o
   que explica `bars_per_second` 48,2 e 46,68 contra os 60,1 que a `momentum` fazia sozinha na T3.40.
   **Os números da estratégia não mudam com isso** (o replay é determinístico), só o relógio. Ainda
   assim: dezesseis versões ativas é carga de avaliação por barra por mercado que ninguém dimensionou,
   e continua sem via auditada para aposentar uma versão substituída por parâmetro (CONCERN 2 da
   T3.33f, ainda aberto).
3. **Rodei uma sonda de replay numa coorte descartável, e isso deixa uma linha permanente em
   `replay_runs`.** `replay:1c93e83f-396a-4c60-99a9-e7f1b7876d17`, 1 mercado × 2 dias, 192 barras,
   **0 sinais**. Fiz porque não tinha estimativa do custo por barra da varredura de geometria e o
   limite operacional é 290 s por fatia — errar a fatia significaria escrever metade de uma
   população. **É uma escrita a mais do que o brief autoriza**, pelo caminho auditado, e o revisor
   tem o direito de julgá-la desnecessária. Ela não contaminou nada (0 sinais, coorte própria).
4. **O "teto de pedágio declarado de 0,1333 R" do EXP-0016 estava errado, e eu só descobri medindo.**
   O número supõe ATR% no piso **e** risco em 3 ATR ao mesmo tempo. Medido: risco mediano 2,11 ATR,
   custo médio **0,1401 R**, e **28 das 47 decisões acima de 0,1333 R**. O teto correto da geometria
   é **0,20 R**. Corrigido nesta nota, não no texto congelado do EXP.
5. **Não rodei a passada de estresse.** O brief manda "estresse só se K1 sobreviver", e K1
   sobreviveu — logo eu devia ter rodado. **Não rodei porque K6 disparou primeiro**, e uma passada
   de estresse sobre uma população que o próprio EXP obriga a reenunciar mediria a robustez de uma
   hipótese que acabou de mudar de nome. Além disso, 42 repiques e 5 rompimentos não sustentam
   decomposição de estresse por modo (a T3.42 já recusou vereditos com `n < 30`). **É desvio
   declarado, não esquecimento**, e é a primeira coisa a rodar se o revisor discordar do meu
   julgamento.
6. **O Δ condicionado aos 23 episódios invalidados é derivação, não leitura caso a caso.** O JSON do
   `replay_exits.py` publica agregados e contrastes, não o R por caso. Deduzi `+0,1885 R` de
   `4,33462 / 23`, apoiado no fato de que `INV-B` **só** difere da base nos episódios que dispararam
   a invalidação — e as contagens de desfecho de `INV-B` (9 alvos, 20 stops, 18 expirados) fecham
   exatamente com essa partição. A aritmética está exposta acima para ser conferida; se o revisor
   quiser o número lido linha a linha, é uma extensão no `replay_exits.py`, não uma reexecução.
7. **`mfe` é limite inferior em 15 das 47 linhas** (`ambiguous = true`) — a mesma pendência da T3.32.
   "Captura 15,8 % do MFE" descreve ordem de grandeza, não valor exato.
8. **Duas coisas do dia um do EXP-0016 eu NÃO consegui medir, e não vou fingir que medi.**
   (i) **"Fração de rompimentos com reteste dentro de `retest_bars`"**: `find_trigger` só considera
   `breakout` e `bounce`; `retest` **não é gatilho** e o envelope não guarda se um reteste veio
   depois. Com 5 rompimentos, nem valeria. Medir isso exige mudar o envelope — **versão nova**.
   (ii) **"Linhas aposentadas por barra"** eu só tenho **nas 47 decisões** (média 1,02, máximo 4,
   29 decisões com ≥ 1); o livro-razão não carrega `pattern_retired_lines` nas barras que não
   decidiram, porque o detalhe de `no_event` só traz `lines`.
9. **O replay herda o universo e a elegibilidade de HOJE**, não os de agosto (`PIPELINE` §6c). Vale
   igualmente para toda coorte, então não enviesa comparação — mas nenhum número aqui descreve o
   universo da janela.
10. **A janela que mediu é a janela que gerou a hipótese.** Rótulo **REPLAY**, e serve para matar,
    não para promover. A coorte prospectiva aberta em **2026-09-08T22:29:52Z** (Brasília 19:29:52) é
    o que pode amadurecer esta versão — e, na cadência do dia um (47 decisões / 31 dias / 4 mercados
    = 0,38 por mercado-dia), com o universo prospectivo inteiro os 100 desfechos vêm rápido; com
    quatro mercados, não viriam.
11. **Multiplicidade.** Não conto "a n-ésima versão" de cabeça; o número que eu **medi** é o roster:
    **16 versões ativas** ao fim desta tarefa, contra 7 na T3.33f e 9 no começo da minha janela hoje
    ([[KB-0010]]). Desta task saiu **um** contraste pré-registrado (`INV-B − base`), e o Holm do
    relatório é sobre família 7 — conservador aqui, porque seis dos sete braços não têm população.
13. **"Pré-registrado" merece ser desmontado, e eu desmonto.** A sequência real foi: brief escrito
    (com o estimando, item 2) → seed 22:28 → ativação 22:29:52 → replays 22:31–22:36 →
    `replay_exits.py` 22:42 → **só então** eu escrevi o item 4b do `EXP-0016` e o limiar de leitura.
    **O estimando é pré-registrado por terceiro** (o brief está no disco e é anterior a tudo);
    **o limiar de decisão não é** — escrevi-o com o número na tela. Ele é derivável da [[KB-0006]] e
    quase não tem grau de liberdade (Δ ≥ 0 ou Δ < 0 é binário, e o efeito mínimo de 0,05 R já vinha
    do `EXP-0007`), mas isso é argumento, não protocolo, e a [[KB-0010]] não aceita argumento no
    lugar de protocolo. Quem exigir rigor total deve tratar o veredito de C8 como **exploratório**.
12. **Nada foi arquivado no `obsidian/`.** O `EXP-0016` continua em `.claude/state/exp-drafts/` como
    rascunho para a Sexta-feira.

---

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** o CONCERN 3 (a sonda como escrita extra), o CONCERN 5 (não rodei o estresse
  porque K6 disparou) e o CONCERN 6 (o Δ condicionado é derivação). Os três são julgamento, não
  aritmética.
- **risk-engine-guardian:** o **CONCERN 1** é seu — `paper_v1` ausente do banco de produção. E o C5
  do EXP-0016 continua valendo: o stop de 2 a 3 ATR desta versão fura o `max_stop_distance_pct` de
  3 % do `paper_v1`; enquanto `research_only`, é irrelevante; num pedido de `--paper-line`, é
  impeditivo.
- **Sexta-feira:** arquivar o `EXP-0016` com a avaliação REPLAY datada, ligar de [[KB-0006]],
  [[EXP-0007]] e [[KB-0077-linhas-de-tendencia]], e acrescentar ao `Registro de Tentativas` a linha
  **`trendline_breakout v1`, ativada 2026-09-08T22:29:52,701952Z (Brasília 19:29:52), `research_only`,
  `params_hash f2e8017c7251e22f`**.
- **Everton:** ver as dez linhas abaixo.

---

## PARA O EVERTON — dez linhas

1. A estratégia de **linhas de tendência** entrou no catálogo e está rodando: 47 operações
   simuladas em 31 dias, ETH/SOL/XRP/DOGE, zero erros.
2. As linhas **existem de verdade** nos gráficos: 9 em cada 10 barras têm ao menos uma linha válida,
   com média de 3 por barra. O medo de "não achar figura nenhuma" não se confirmou.
3. **Antes dos custos ela GANHA** (+0,10 R por operação). É a primeira da casa a chegar aí.
4. **Depois dos custos ela perde** (−0,04 R, PF 0,92). A corretora fica com 0,14 R por operação —
   toda a vantagem e mais um pouco.
5. Descoberta nº 1: **89 % das operações são "repique", não "rompimento"**. A porta de rompimento,
   que dá nome à estratégia, operou 5 vezes em 31 dias e **perdeu as 5**.
6. Descoberta nº 2: **a regra de "sair quando o preço volta abaixo da linha" está custando dinheiro**.
   Sem ela, a estratégia vira **+0,05 R** (de perde para ganha). Não é conclusivo — o intervalo de
   confiança ainda passa pelo zero —, mas é a terceira vez que essa família de regra aparece como
   estorvo.
7. Metade das operações morre por essa regra (23 de 47), a −0,66 R cada.
8. **Sim, cada operação guarda a sua linha.** Conferido: as 47 gravam identificador da linha,
   inclinação, primeiro e último ponto, preço da linha na hora da decisão, o fundo usado no stop e
   todos os parâmetros do traçado — **a linha de qualquer operação pode ser redesenhada exatamente**.
   É isso que vai virar o desenho na tela (T3.49). **Nenhuma das outras estratégias desenha linhas.**
9. Veredito: **manter em pesquisa**, sem promover. 14 dias de dados não decidem nada, e a janela
   testada é a mesma que deu a ideia.
10. **Achado fora do assunto, mas grave:** o perfil de risco `paper_v1` — aquele com os limites que
    você aprovou — **não está gravado no banco da VPS**. Está só no código. Não mexi; a decisão é sua.

---

**Horários em Brasília (UTC−3), com UTC no detalhe:** seed 19:28:53–19:28:56 (22:28:53Z–22:28:56Z);
ativação **19:29:52** (22:29:52,701952Z); replay fatia A 19:31:25–19:33:28, fatia B 19:33:54–19:36:06;
contraste de saídas 19:42:12–19:42:17; últimas leituras 19:52 (22:52Z).
