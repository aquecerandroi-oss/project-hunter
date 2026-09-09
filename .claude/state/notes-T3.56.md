# notes-T3.56 — a limpeza do roster: sete aposentadorias escritas, duas já estavam feitas, uma recusada

**Data:** 2026-09-09, janela de escrita 14:55:29–15:00:10 UTC = **11:55:29–12:00:10 (Brasília, UTC−3)**.
**Owner:** quant-engineer. **Origem:** autorização de Everton 2026-09-09 11:50 BRT ("as que estão dando
ruim pode matar"). **Continuação de** `.claude/state/notes-T3.47b.md` (higiene de roster) e
`.claude/state/notes-T3.47c.md` (semântica de *append* no `changelog`).

**Árvore local:** `HEAD = 212d1c0`. **Nada commitado, nada indexado, nenhum `.env*` tocado, nenhum
container parado, recriado ou reiniciado.** Nenhum `git pull` na VPS.
**Escritas na VPS:** sete `activate_strategy_version.py --deprecate` (a única ferramenta usada). Todo
o resto foi lido em transação `repeatable read read only` pelo stdin do `psql`. **Nenhum `UPDATE`
manual. Nenhum SQL de escrita.**

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Alvo do brief | Resultado |
|---|---|---|
| 1 | `volume_anomaly v1` | **Nada a fazer** — já estava `deprecated` desde 2026-09-08T04:32:42Z. `--dry-run` recusou: "is 'deprecated', not active". §3.1 |
| 2 | `volume_anomaly v2` | **Aposentada** 14:55:29Z = **11:55:29 BRT** |
| 3 | `momentum v1` | **Nada a fazer** — já `deprecated` desde 2026-09-08T04:33:56Z. Mesma recusa. §3.1 |
| 4 | `momentum v2` | **Aposentada** 14:56:27Z = **11:56:27 BRT** |
| 5 | `momentum v4` | **Aposentada** 14:57:16Z = **11:57:16 BRT** |
| 6 | `momentum v6` (sucessora `v8`) | **Aposentada** 14:58:00Z = **11:58:00 BRT**, `successor=momentum v8` |
| 7 | `momentum v10` | **Aposentada** 14:58:42Z = **11:58:42 BRT** |
| 8 | `session_orb v1` | **Aposentada** 14:59:24Z = **11:59:24 BRT** |
| 9 | `trendline_breakout v1` | **Aposentada** 15:00:10Z = **12:00:10 BRT** |
| 10 | `momentum v3` (linha `paper`) | **RECUSADA pelo script, e eu parei** — `--force-paper` foi aceito, mas o segundo portão (exposição aberta) barrou: "still has skin in the game: 5 shadow slot(s) tracking an open outcome". §4 |
| 11 | Semântica de *append* da T3.47c | **Verificada em produção**, linha a linha: prefixo de linhagem intacto no byte 0 em todas as 7. §6 |
| 12 | Acompanhamentos abertos continuam andando | **Medido**: 57 acompanhamentos das versões aposentadas, todos atualizados 45–51 s antes da leitura, **depois** da aposentadoria. §8 |

**Roster: 16 → 9 versões ativas.** As nove são exatamente as oito que o brief mandou manter vivas
(`mean_reversion v1/v2/v3/v6/v7/v8/v10` + `momentum v8`) **mais** a `momentum v3`, que o script se
recusou a aposentar. Nada novo foi ativado.

**CONCERNs:** três, em §9 — (1) `session_orb v1` foi morta com um número que não reproduz mais;
(2) `momentum v3` tem um impasse estrutural (o portão exige zero *slots* abertos, mas a versão viva
continua abrindo); (3) `trendline_breakout v1` emitiu 2 decisões **23 s depois** de aposentada (cache
de roster de 60 s) — comportamento esperado pelo código, mas não documentado em lugar nenhum.

---

## FILES

Criados (todos meus, todos fora de código de produção; raiz `C:\dev\project-hunter\`):

| arquivo | o quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t356-q00-catalogo-antes.sql` | catálogo por purpose/status **antes**, o que o `--deprecate` encontraria nas dez alvos, a população medida (n e expectância por coorte) e o retrato dos acompanhamentos abertos |
| `infra/scripts/sql/research/2026-09-09-t356-q01-c5-teto-de-stop.sql` | C5: fração das decisões com stop acima do teto do `paper_v1` (risco/entrada > 3 %), por versão e coorte |
| `infra/scripts/sql/research/2026-09-09-t356-q02-catalogo-depois.sql` | catálogo **depois**, prova do prefixo de linhagem, `system_events` da janela, acompanhamentos abertos das aposentadas, exposição da linha `paper` |
| `.claude/state/notes-T3.56.md` | este arquivo |

**Nenhum arquivo de código foi tocado. Nenhuma ferramenta nova escrita:** o instrumento é o
`infra/scripts/activate_strategy_version.py --deprecate`, sem uma linha alterada.

---

## 1. O QUE JÁ ESTAVA VIVO (antes de qualquer escrita)

```
$ ssh hunter-vps 'date -u; date; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Wed Sep  9 14:49:51 UTC 2026                                   <- 11:49:51 Brasília
Wed Sep  9 16:49:51 CEST 2026
hunter-scanner-worker-1      hunter-api:f1475c4   Up 11 hours (healthy)
hunter-market-worker-2-1     hunter-api:f1475c4   Up 11 hours (healthy)
hunter-market-worker-spot-1  hunter-api:f1475c4   Up 11 hours (healthy)
hunter-market-worker-1-1     hunter-api:f1475c4   Up 11 hours (healthy)
hunter-market-worker-1       hunter-api:f1475c4   Up 11 hours (healthy)
hunter-market-worker-3-1     hunter-api:f1475c4   Up 11 hours (healthy)
hunter-web-1                 hunter-web:09b8fa6   Up 14 hours (healthy)
hunter-api-1                 hunter-api:09b8fa6   Up 14 hours (healthy)
hunter-strategy-worker-1     hunter-api:803f648   Up 14 hours (healthy)
hunter-execution-worker-1    hunter-api:7e9d59c   Up 15 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1            Up 2 days (healthy)
```

**O `strategy-worker` roda `hunter-api:803f648` — que é exatamente o commit da T3.47c**, o fix de
*append* no `changelog`. Conferido antes de escrever, não depois.

**A imagem que o `ops` usa é a do `HEAD` da VPS** (`compose.sh` resolve `GIT_SHA` por
`git rev-parse --short HEAD` no diretório da VPS, e `ops` recusa alto se a imagem não existir, em vez
de construir sozinho — achado F2 da revisão de segurança da T3.15e):

```
$ ssh hunter-vps 'cd /opt/project-hunter && git rev-parse --short HEAD; docker images hunter-api --format "{{.Tag}}" | head -3'
f1475c4
f1475c4
188ff72
2b7cef9
```

Os três arquivos auditados são **byte a byte** os do commit `f1475c4`, na imagem e no git:

```
$ ssh hunter-vps 'docker run --rm --entrypoint sha256sum hunter-api:f1475c4 \
    /app/infra/scripts/activate_strategy_version.py \
    /app/services/strategy-worker/hunter_strategy_worker/deprecate.py \
    /app/services/strategy-worker/hunter_strategy_worker/activation_db.py'
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  /app/infra/scripts/activate_strategy_version.py
7b84d4c328d07bb80ae66cdd3a83da75a124c8434b9a15eb03c48ec5e25b9601  /app/services/strategy-worker/hunter_strategy_worker/deprecate.py
0a5f93767ed864fe3d55f9a762fbd59edc8f93fab935a12fba4b19ec92f58cc9  /app/services/strategy-worker/hunter_strategy_worker/activation_db.py

$ git show f1475c4:infra/scripts/activate_strategy_version.py | sha256sum                        -> dc6abf95…
$ git show f1475c4:services/strategy-worker/hunter_strategy_worker/deprecate.py | sha256sum      -> 7b84d4c3…
$ git show f1475c4:services/strategy-worker/hunter_strategy_worker/activation_db.py | sha256sum  -> 0a5f9376…

$ git merge-base --is-ancestor 803f648 f1475c4 && echo ancestral
ancestral        <- a T3.47c está dentro da imagem que vai escrever
```

**Ressalva honesta sobre a árvore local:** `infra/scripts/activate_strategy_version.py` e
`activation_db.py` têm modificações **não commitadas** na árvore local (`_refuse_unbudgeted_context`,
`policy_column_present` — trabalho de outra tarefa, não meu). **Nada disso está na imagem da VPS**, e
nada disso toca o caminho `--deprecate`: as duas mudanças vivem em `activate()` e no que o
`derive_variant.py` lê. O que rodou hoje é o `f1475c4` puro.

Antes de tocar em qualquer coisa li o `__doc__` do script e o `deprecate.py` inteiro. As duas recusas
estruturais são: `purpose = 'live'` nunca; `purpose = 'paper'` só com `--force-paper` **e** sem
`positions`/`shadow_episodes` aberto. **Oito das dez alvos são `research_only`; a `momentum v3` é a
linha `paper` — e é exatamente ela que bateu no segundo portão.**

---

## 2. O CATÁLOGO **ANTES** (`q00`, `read_at = 2026-09-09T14:52:02,587865Z` = **11:52:02 BRT**)

```
== 2. contagem por status x purpose ==
+------------+---------------+---------+
|   status   |    purpose    | versoes |
+------------+---------------+---------+
| draft      | research_only |       4 |
| active     | paper         |       1 |
| active     | research_only |      15 |
| deprecated | research_only |      10 |
+------------+---------------+---------+
```

**16 versões ativas.** As dez alvos e o que o `--deprecate` iria encontrar:

```
== 3. as dez alvos: o que --deprecate iria encontrar ==
+-----------------------+---------------+------------+---------------+------------------+--------+-------------+--------------------------+
|        versao         |    purpose    |   status   | slots_abertos | posicoes_abertas | sinais | derivada_de | params_hash_no_changelog |
+-----------------------+---------------+------------+---------------+------------------+--------+-------------+--------------------------+
| momentum v1           | research_only | deprecated |             0 |                0 |    963 |             |                          |
| momentum v2           | research_only | active     |             5 |                0 |   1127 |             |                          |
| momentum v3           | paper         | active     |             5 |                0 |    654 |             |                          |
| momentum v4           | research_only | active     |             3 |                0 |    350 |             |                          |
| momentum v6           | research_only | active     |             5 |                0 |    523 | v2          | 8cb1aa497956             |
| momentum v10          | research_only | active     |            10 |                0 |    487 | v8          | a9f1cef0fa58             |
| session_orb v1        | research_only | active     |             5 |                0 |     92 |             |                          |
| trendline_breakout v1 | research_only | active     |            11 |                0 |    199 |             |                          |
| volume_anomaly v1     | research_only | deprecated |             0 |                0 |   2152 |             |                          |
| volume_anomaly v2     | research_only | active     |            26 |                0 |   2098 |             |                          |
+-----------------------+---------------+------------+---------------+------------------+--------+-------------+--------------------------+
```

**Duas surpresas, as duas antes de qualquer escrita:**

1. **`momentum v1` e `volume_anomaly v1` já estavam `deprecated`** — desde 2026-09-08T04:33:56Z e
   04:32:42Z, aposentadas pelo `--supersede` que criou as respectivas `v2` (o `changelog` delas diz
   `superseded by v2 (code_ref … -> …)`). O estado que o brief pede **já era o estado do banco**. Rodei
   o `--dry-run` mesmo assim, para ter o recibo da recusa (§3.1).
2. **`momentum v3` (a linha `paper`) tinha 5 `shadow_episodes` com acompanhamento aberto** — a
   condição exata que `open_paper_exposure()` checa. Isso não é detalhe: é o que a recusa de §4 iria
   dizer, e eu já sabia antes de rodar o comando.

`posicoes_abertas = 0` nas dez (nenhuma carteira exposta — `ENABLE_PAPER_AUTONOMY=false`).

---

## 3. A RAZÃO MEDIDA — o número que foi para cada `changelog`

Medi eu mesmo, no mesmo `read_at`, em vez de copiar o número do brief. População: desfecho `terminal`
com `r_multiple` não nulo; coorte pelo `supporting_features->>'cohort'` (`replay:%` → replay, o resto
→ prospective). C5 = fração das decisões com `initial_risk / entry > 3 %`, a mesma fórmula da
T3.47b `q15`.

| versão | coorte | n | expectância líquida | soma R | C5 (stop > teto do `paper_v1`) |
|---|---|---|---|---|---|
| `volume_anomaly v1` | prospective | 2079 | **−0,3301 R** | −686,21 | 4,9 % |
| `volume_anomaly v2` | prospective | 1190 | **−0,2948 R** | −350,87 | 6,0 % |
| `volume_anomaly v2` | replay | 339 | **−0,5954 R** | −201,83 | 0,9 % |
| `momentum v1` | prospective | 929 | **−0,1905 R** | −176,94 | 13,5 % |
| `momentum v2` | prospective | 471 | **−0,2167 R** | −102,07 | 13,2 % |
| `momentum v2` | replay | 248 | **−0,2247 R** | −55,73 | 0,0 % |
| `momentum v3` (paper) | prospective | 453 | **−0,2256 R** | −102,19 | 12,6 % |
| `momentum v4` | prospective | 201 | **−0,1650 R** | −33,17 | 20,9 % |
| `momentum v4` | replay | 30 | **−0,1506 R** | −4,52 | 0,0 % |
| `momentum v6` | prospective | 156 | **−0,2856 R** | −44,56 | 15,4 % |
| `momentum v6` | replay | 195 | **−0,0513 R** | −10,01 | 0,0 % |
| `momentum v10` | replay | 252 | **−0,0357 R** | −8,99 | **37,3 %** |
| `momentum v10` | prospective | 84 | **−0,1534 R** | −12,89 | **94,0 %** |
| `session_orb v1` | replay | 20 | **−0,1928 R** | −3,86 | 0,0 % |
| `session_orb v1` | prospective | 31 | **−0,0266 R** | −0,83 | 25,8 % |
| `trendline_breakout v1` | replay | 47 | **−0,0382 R** | −1,79 | 0,0 % |
| `trendline_breakout v1` | prospective | 57 | **−0,3417 R** | −19,48 | 31,6 % |

**Todas as dez são negativas em toda coorte que têm.** Nenhuma exceção, nenhum sinal trocado.
O `momentum v10` fecha o C5 do brief no ponto: **37,3 %** contra "37 %" (n 252, replay).

### 3.0 Onde o número do brief e o meu divergem (e por quê)

| versão | brief (2026-09-09 11:50 BRT) | medido (`as_of` 14:52Z) | leitura |
|---|---|---|---|
| `volume_anomaly v1` | −0,33 R, n 2079 | −0,3301, n 2079 | idêntico |
| `volume_anomaly v2` | −0,27 prosp. / −0,60 replay | −0,2948 (n 1190) / −0,5954 (n 339) | piorou um pouco na prospectiva; replay idêntico |
| `momentum v1` | −0,19 R, n 929 | −0,1905, n 929 | idêntico |
| `momentum v2` | −0,22 nas duas | −0,2167 (471) / −0,2247 (248) | idêntico |
| `momentum v4` | −0,19 / −0,15 | −0,1650 (201) / −0,1506 (30) | prospectiva melhorou de −0,19 para −0,165 |
| `momentum v6` | −0,31 prosp., n 50 | −0,2856, **n 156** / replay −0,0513, n 195 | **n triplicou** e o número quase não mudou |
| `momentum v10` | −0,036 replay, n 252, 37 % C5 | −0,0357, n 252, **37,3 %** | idêntico |
| `session_orb v1` | −0,19 / −0,51 | replay −0,1928 (n 20) / **prosp. −0,0266** (n 31) | **o −0,51 não reproduz** — CONCERN 1 |
| `trendline_breakout v1` | −0,04 replay / −0,55 prosp., n 21 | −0,0382 (n 47) / **−0,3417 (n 57)** | prospectiva melhorou de −0,55 para −0,34 com n quase triplo |
| `momentum v3` | −0,24 prosp., n 341 | −0,2256, **n 453** | mesma direção, n 33 % maior |

**O que foi para o `changelog` é o número que eu medi**, com `as_of` explícito — nunca o do brief. Um
`changelog` que cita um número que ninguém consegue reproduzir é pior que nenhum.

### 3.1 As duas que já estavam mortas — os recibos das recusas

```
$ ssh hunter-vps 'date -u; cd /opt/project-hunter && export MARKET_SHARDS=4 MARKET_SPOT=1; \
    bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py volume_anomaly v1 \
    --deprecate --changelog "T3.56: …" --dry-run; echo "exit=$?"; date -u'
Wed Sep  9 14:54:23 UTC 2026
 Container hunter-postgres-1 Running
 Container hunter-postgres-1 Waiting
 Container hunter-postgres-1 Healthy
 Container hunter-ops-run-174eb012d6c7 Creating
 Container hunter-ops-run-174eb012d6c7 Created
REFUSED: volume_anomaly v1 is 'deprecated', not active: nothing to deprecate

exit=1
Wed Sep  9 14:54:27 UTC 2026
```

```
Wed Sep  9 14:54:39 UTC 2026
 Container hunter-ops-run-91fd03da982e Created
REFUSED: momentum v1 is 'deprecated', not active: nothing to deprecate

exit=1
Wed Sep  9 14:54:43 UTC 2026
```

**Não tentei forçar nada.** As duas já carregam, no `changelog`, a razão real pela qual saíram
(`superseded by v2 … code_moved_by_funding_slot_fix_d878fd6…`). Sobrescrever isso com o veredito de
expectância de hoje seria **apagar a história dessas linhas** para registrar uma decisão que o banco
já tomou há 34 h. O estado pedido pelo brief é o estado atual: `deprecated`.

---

## 4. `momentum v3` — os dois portões, e onde eu parei

O brief previu um dos dois portões e mandou parar no outro. Os dois apareceram, na ordem.

**Portão 1 — `--force-paper` (previsto pelo brief; eu tinha autorização para passar):**

```
$ … activate_strategy_version.py momentum v3 --deprecate --changelog "T3.56: …" --dry-run
Wed Sep  9 15:00:23 UTC 2026
 Container hunter-ops-run-194b7851dfe9 Created
REFUSED: momentum v3 is the paper line (purpose 'paper'): deprecating it stops the wallet's own coorte. Pass --force-paper to confirm, and only once its positions and shadow slots are clear (checked below).
exit=1
Wed Sep  9 15:00:27 UTC 2026
```

**Portão 2 — a exposição aberta (não previsto pelo brief → PAREI):**

```
$ … activate_strategy_version.py momentum v3 --deprecate --force-paper --changelog "T3.56: …" --dry-run
Wed Sep  9 15:00:44 UTC 2026
 Container hunter-ops-run-15411e799134 Created
REFUSED: momentum v3 still has skin in the game: 5 shadow slot(s) tracking an open outcome. Close or hand them off before deprecating the paper line.

exit=1
Wed Sep  9 15:00:48 UTC 2026
```

**`--force-paper` foi aceito e usado** (o `argparse` o exige junto de `--deprecate`, e o exigiu; a
recusa mudou de texto, prova de que o primeiro portão foi vencido). O que barrou foi
`open_paper_exposure()` — `shadow_episodes` com `open_outcome_signal_id IS NOT NULL`. **`positions`
aberta: zero** (nada executou; `ENABLE_PAPER_AUTONOMY=false`, como o brief diz). É só acompanhamento
de pesquisa em voo.

**Parei aqui, como o brief manda. Nenhum SQL. `momentum v3` continua `active`, `purpose = 'paper'`.**

Estado da exposição na leitura seguinte (`q02` §7, `read_at = 15:01:36Z` = **12:01:36 BRT**):

```
+-------------+---------+--------+---------------+------------------+---------------------+---------------------+
|   versao    | purpose | status | slots_abertos | posicoes_abertas | primeiro_a_expirar  |  ultimo_a_expirar   |
+-------------+---------+--------+---------------+------------------+---------------------+---------------------+
| momentum v3 | paper   | active |             6 |                0 | 2026-09-09 17:16:00 | 2026-09-09 19:02:00 |
+-------------+---------+--------+---------------+------------------+---------------------+---------------------+
```

**Note o 6.** Eram 5 às 14:52 e 5 na recusa das 15:00:47; um minuto depois são 6. Isso é o CONCERN 2.

---

## 5. AS SETE ESCRITAS — `--dry-run` e escrita, recibos verbatim

Comando, idêntico para as sete (só mudam versão, `--successor` e `--changelog`):

```
ssh hunter-vps 'date -u; cd /opt/project-hunter && export MARKET_SHARDS=4 MARKET_SPOT=1; \
  bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py <estrategia> <vN> \
  --deprecate [--successor v8] --changelog "<veredito medido>" [--dry-run]; echo "exit=$?"; date -u'
```

### 5.1 `volume_anomaly v2`

```
Wed Sep  9 14:54:54 UTC 2026
 Container hunter-ops-run-b25b866e214c Created
would deprecate volume_anomaly v2 (purpose research_only), code_ref hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22, params_hash fa5dce78173b, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida prospectiva -0,2948 R em n=1190 desfechos terminais (soma -350,87 R) e replay -0,5954 R em n=339 (soma -201,83 R): perde nas duas coortes. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora: a familia volume_anomaly sai inteira do roster (v1 ja estava deprecated desde 2026-09-08T04:32Z).
exit=0
Wed Sep  9 14:54:58 UTC 2026

Wed Sep  9 14:55:26 UTC 2026
 Container hunter-ops-run-0740d3c6a158 Created
deprecated volume_anomaly v2 (purpose research_only) at 2026-09-09T14:55:29.448514+00:00, successor=none
exit=0
Wed Sep  9 14:55:30 UTC 2026
```

### 5.2 `momentum v2`

```
Wed Sep  9 14:56:10 UTC 2026
would deprecate momentum v2 (purpose research_only), code_ref hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c, params_hash 40e1688e6b5f, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida prospectiva -0,2167 R em n=471 (soma -102,07 R) e replay -0,2247 R em n=248 (soma -55,73 R): negativa nas duas coortes e no mesmo tamanho. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora declarada; a unica momentum que fica viva e a v8.
exit=0
Wed Sep  9 14:56:14 UTC 2026

Wed Sep  9 14:56:24 UTC 2026
deprecated momentum v2 (purpose research_only) at 2026-09-09T14:56:27.659818+00:00, successor=none
exit=0
Wed Sep  9 14:56:28 UTC 2026
```

### 5.3 `momentum v4`

```
Wed Sep  9 14:56:51 UTC 2026
would deprecate momentum v4 (purpose research_only), code_ref hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c, params_hash 46635ed2bff2, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida prospectiva -0,1650 R em n=201 (soma -33,17 R) e replay -0,1506 R em n=30 (soma -4,52 R): negativa nas duas coortes; 20,9 por cento das decisoes prospectivas acima do teto de stop do paper_v1 (risco/entrada > 3 por cento). Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora declarada; a unica momentum que fica viva e a v8.
exit=0
Wed Sep  9 14:56:55 UTC 2026

Wed Sep  9 14:57:13 UTC 2026
deprecated momentum v4 (purpose research_only) at 2026-09-09T14:57:16.601330+00:00, successor=none
exit=0
Wed Sep  9 14:57:17 UTC 2026
```

### 5.4 `momentum v6` — a única com sucessora declarada

```
Wed Sep  9 14:57:36 UTC 2026
would deprecate momentum v6 (purpose research_only), code_ref hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c, params_hash 8cb1aa497956, successor=momentum v8: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida prospectiva -0,2856 R em n=156 (soma -44,56 R) e replay -0,0513 R em n=195 (soma -10,01 R): negativa nas duas coortes. Sucessora declarada: momentum v8 (mesma linhagem, stop 3 ATR), que fica viva no roster. Autorizacao de Everton 2026-09-09 11:50 BRT.
exit=0
Wed Sep  9 14:57:40 UTC 2026

Wed Sep  9 14:57:57 UTC 2026
deprecated momentum v6 (purpose research_only) at 2026-09-09T14:58:00.789121+00:00, successor=momentum v8
exit=0
Wed Sep  9 14:58:01 UTC 2026
```

`--successor v8` **só aqui**, porque só aqui existe de verdade uma sucessora do mesmo experimento (o
brief a nomeia, e a `v8` é `derived_from=v6`). Nas outras seis o campo é `successor=none`: inventar
uma sucessora para preencher a coluna seria mentir no `system_events`. É a mesma regra da T3.47b §2.3.

### 5.5 `momentum v10`

```
Wed Sep  9 14:58:19 UTC 2026
would deprecate momentum v10 (purpose research_only), code_ref hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c, params_hash a9f1cef0fa58, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida replay -0,0357 R em n=252 (soma -8,99 R) e prospectiva -0,1534 R em n=84 (soma -12,89 R). C5: 37,3 por cento das decisoes de replay e 94,0 por cento das prospectivas tem stop acima do teto do paper_v1 (risco/entrada > 3 por cento) - a geometria de ATR 1h nao cabe na carteira. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora; a unica momentum que fica viva e a v8.
exit=0
Wed Sep  9 14:58:23 UTC 2026

Wed Sep  9 14:58:39 UTC 2026
deprecated momentum v10 (purpose research_only) at 2026-09-09T14:58:42.519219+00:00, successor=none
exit=0
Wed Sep  9 14:58:43 UTC 2026
```

### 5.6 `session_orb v1`

```
Wed Sep  9 14:59:00 UTC 2026
would deprecate session_orb v1 (purpose research_only), code_ref hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba, params_hash cdb9516b2932, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida replay -0,1928 R em n=20 (soma -3,86 R) e prospectiva -0,0266 R em n=31 (soma -0,83 R): negativa nas duas coortes, e K1 nas duas (n pequeno). 25,8 por cento das decisoes prospectivas acima do teto de stop do paper_v1. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora.
exit=0
Wed Sep  9 14:59:04 UTC 2026

Wed Sep  9 14:59:21 UTC 2026
deprecated session_orb v1 (purpose research_only) at 2026-09-09T14:59:24.592397+00:00, successor=none
exit=0
Wed Sep  9 14:59:25 UTC 2026
```

**Escrevi "K1 nas duas" no `changelog` de propósito**: n 20 e n 31 é população de brinquedo, e esta é
a única das sete cuja aposentadoria eu não defenderia só com o número. Ver CONCERN 1.

### 5.7 `trendline_breakout v1`

```
Wed Sep  9 14:59:46 UTC 2026
would deprecate trendline_breakout v1 (purpose research_only), code_ref hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648, params_hash f2e8017c7251, successor=none: T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida replay -0,0382 R em n=47 (soma -1,79 R) e prospectiva -0,3417 R em n=57 (soma -19,48 R); 31,6 por cento das decisoes prospectivas acima do teto de stop do paper_v1. O modulo de linhas de tendencia fica no codigo para uma v2 com a hipotese de repique reformulada. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora ainda.
exit=0
Wed Sep  9 14:59:50 UTC 2026

Wed Sep  9 15:00:06 UTC 2026
deprecated trendline_breakout v1 (purpose research_only) at 2026-09-09T15:00:10.132127+00:00, successor=none
exit=0
Wed Sep  9 15:00:10 UTC 2026
```

**Nenhuma recusa nas sete. Nenhum caso que a doc não previsse.**

---

## 6. A SEMÂNTICA DE *APPEND* DA T3.47c — verificada em produção, linha a linha

Esta era a parte do brief que podia quebrar em silêncio. Verifiquei **imediatamente após a primeira
escrita**, e depois nas sete (`q02` §4).

Primeira verificação, na `volume_anomaly v2`, 29 s depois da escrita
(`read_at = 2026-09-09T14:55:58,116592Z` = **11:55:58 BRT**):

```
| versao            | status     | aposentada_utc      | tamanho | prefixo_intacto_no_inicio | tag_datada_presente |
| volume_anomaly v2 | deprecated | 2026-09-09 14:55:29 |     549 | t                         | t                   |

changelog:
succeeds v1: code_moved_by_funding_slot_fix_d878fd6_lab_refused_v1_on_vps_since_2026-09-07_frozen_parameters_carried_over
[deprecated 2026-09-09T14:55:29.512101+00:00] T3.56: aposentada por veredito medido (as_of 2026-09-09T14:52Z). Expectancia liquida prospectiva -0,2948 R em n=1190 desfechos terminais (soma -350,87 R) e replay -0,5954 R em n=339 (soma -201,83 R): perde nas duas coortes. Autorizacao de Everton 2026-09-09 11:50 BRT. Sem sucessora: a familia volume_anomaly sai inteira do roster (v1 ja estava deprecated desde 2026-09-08T04:32Z).
```

**121 (prefixo) + 1 (`\n`) + 427 (tag + veredito) = 549.** A aritmética fecha: o valor anterior
sobreviveu **byte a byte**, e o novo veio **depois**.

As sete, juntas (`q02` §4, `read_at = 15:01:36Z` = **12:01:36 BRT**):

```
+-----------------------+---------+------------------------------------------------+----------+----------------------------+---------------------------+
|        versao         | tamanho |            prefixo_ainda_no_inicio             | tag_t356 | derived_from_ainda_legivel | params_hash_ainda_legivel |
+-----------------------+---------+------------------------------------------------+----------+----------------------------+---------------------------+
| volume_anomaly v2     |     549 | succeeds v1: code_moved_by_funding_slot_fix_d8 | t        |                            |                           |
| momentum v2           |     500 | succeeds v1: code_moved_by_funding_slot_fix_d8 | t        |                            |                           |
| momentum v4           |     554 | T3.26: coorte de pesquisa da variante de piso  | t        |                            |                           |
| momentum v6           |     547 | variante de v2 | derived_from=v2 | overrides=t | t        | v2                         | 8cb1aa497956              |
| momentum v10          |     719 | variante de v8 | derived_from=v8 | overrides=a | t        | v8                         | a9f1cef0fa58              |
| session_orb v1        |     452 | T3.33g: EXP-0010 entra no Lab como pesquisa   +| t        |                            |                           |
|                       |         | [d                                             |          |                            |                           |
| trendline_breakout v1 |     581 | T3.34c: trendline_breakout v1 (research_only)  | t        |                            |                           |
+-----------------------+---------+------------------------------------------------+----------+----------------------------+---------------------------+
```

**As duas linhas que mais importavam são as duas derivadas** — `momentum v6` e `momentum v10`: o
`derived_from=vN` e o `params_hash=` continuam legíveis pela regex de
`infra/scripts/obsidian_strategy_pages.py::parse_parent_version`, exatamente o que a T3.47c existe
para garantir. Na T3.47b o operador teve que **colar a linhagem à mão** dentro do `--changelog` para
não perdê-la; hoje eu **não colei nada** — mandei só o veredito, e o prefixo sobreviveu sozinho.
**A T3.47c está provada em produção, não só em testcontainers.**

---

## 7. O CATÁLOGO **DEPOIS** (`q02`, `read_at = 2026-09-09T15:01:36,184870Z` = **12:01:36 BRT**)

```
== 2. contagem por status x purpose ==
+------------+---------------+---------+
|   status   |    purpose    | versoes |
+------------+---------------+---------+
| draft      | research_only |       4 |
| active     | paper         |       1 |
| active     | research_only |       8 |
| deprecated | research_only |      17 |
+------------+---------------+---------+
```

**Roster: 16 → 9 versões ativas** (−7):

```
== 3. quem continua viva (o roster que o strategy-worker vai carregar) ==
+--------------------+---------------+---------------------+
|       versao       |    purpose    |     ativada_utc     |
+--------------------+---------------+---------------------+
| mean_reversion v1  | research_only | 2026-09-08 16:32:33 |
| mean_reversion v2  | research_only | 2026-09-08 21:24:26 |
| mean_reversion v3  | research_only | 2026-09-08 21:34:01 |
| mean_reversion v6  | research_only | 2026-09-08 22:38:46 |
| mean_reversion v7  | research_only | 2026-09-08 22:38:49 |
| mean_reversion v8  | research_only | 2026-09-08 23:37:33 |
| mean_reversion v10 | research_only | 2026-09-09 03:22:10 |
| momentum v3        | paper         | 2026-09-08 05:57:30 |
| momentum v8        | research_only | 2026-09-08 22:29:33 |
+--------------------+---------------+---------------------+
```

**Conferência contra o brief:** manter vivas `mean_reversion v1/v2/v3/v6/v7/v8/v10` (7) + `momentum
v8` (1) = 8. Estão as 8, e nada além delas, exceto a `momentum v3` que o script se recusou a matar.
**Nenhuma versão nova foi ativada. Nenhuma `mean_reversion` foi tocada.**

As sete aposentadorias desta janela, com as duas réguas:

| versão | `deprecated_at` (UTC) | **Brasília** | `params_hash` congelado | sucessora |
|---|---|---|---|---|
| `volume_anomaly v2` | 2026-09-09T14:55:29,448514Z | **11:55:29** | `fa5dce78173b` | nenhuma |
| `momentum v2` | 2026-09-09T14:56:27,659818Z | **11:56:27** | `40e1688e6b5f` | nenhuma |
| `momentum v4` | 2026-09-09T14:57:16,601330Z | **11:57:16** | `46635ed2bff2` | nenhuma |
| `momentum v6` | 2026-09-09T14:58:00,789121Z | **11:58:00** | `8cb1aa497956` | **`momentum v8`** |
| `momentum v10` | 2026-09-09T14:58:42,519219Z | **11:58:42** | `a9f1cef0fa58` | nenhuma |
| `session_orb v1` | 2026-09-09T14:59:24,592397Z | **11:59:24** | `cdb9516b2932` | nenhuma |
| `trendline_breakout v1` | 2026-09-09T15:00:10,132127Z | **12:00:10** | `f2e8017c7251` | nenhuma |

O rastro auditado inteiro da janela, incluindo as **quatro recusas** (`q02` §5):

```
+---------+-------------------------------------+----------------------------------------------------------------------------------------------+----------+
|  level  |                event                |                                           mensagem                                           |   utc    |
+---------+-------------------------------------+----------------------------------------------------------------------------------------------+----------+
| warning | strategy_version_activation_refused | volume_anomaly v1 is 'deprecated', not active: nothing to deprecate                          | 14:54:26 |
| warning | strategy_version_activation_refused | momentum v1 is 'deprecated', not active: nothing to deprecate                                | 14:54:42 |
| info    | strategy_version_deprecated         | volume_anomaly v2 (purpose research_only) deprecated at 2026-09-09T14:55:29.448514+00:00, co | 14:55:29 |
| info    | strategy_version_deprecated         | momentum v2 (purpose research_only) deprecated at 2026-09-09T14:56:27.659818+00:00, code_ref | 14:56:27 |
| info    | strategy_version_deprecated         | momentum v4 (purpose research_only) deprecated at 2026-09-09T14:57:16.601330+00:00, code_ref | 14:57:16 |
| info    | strategy_version_deprecated         | momentum v6 (purpose research_only) deprecated at 2026-09-09T14:58:00.789121+00:00, code_ref | 14:58:00 |
| info    | strategy_version_deprecated         | momentum v10 (purpose research_only) deprecated at 2026-09-09T14:58:42.519219+00:00, code_re | 14:58:42 |
| info    | strategy_version_deprecated         | session_orb v1 (purpose research_only) deprecated at 2026-09-09T14:59:24.592397+00:00, code_ | 14:59:24 |
| info    | strategy_version_deprecated         | trendline_breakout v1 (purpose research_only) deprecated at 2026-09-09T15:00:10.132127+00:00 | 15:00:10 |
| warning | strategy_version_activation_refused | momentum v3 is the paper line (purpose 'paper'): deprecating it stops the wallet's own coort | 15:00:27 |
| warning | strategy_version_activation_refused | momentum v3 still has skin in the game: 5 shadow slot(s) tracking an open outcome. Close or  | 15:00:47 |
+---------+-------------------------------------+----------------------------------------------------------------------------------------------+----------+
```

**Onze linhas para onze comandos com efeito.** Nada aconteceu fora do rastro — inclusive as recusas
têm data e hora, que é o ponto da T3.15c.

---

## 8. OS ACOMPANHAMENTOS ABERTOS CONTINUAM ANDANDO (medido, não suposto)

A T3.47b mediu isso para três versões (8 acompanhamentos); refiz para as sete, que carregam **57**
(`q02` §6, `read_at = 15:01:36Z`):

```
| momentum v10          | deprecated | APTUSDT      | active        | open | acompanhado_ate 15:01:00 | atualizado_em 15:01:04 | ha 00:00:32 | expira 17:01 |
| momentum v10          | deprecated | COTIUSDT     | active        | open |                 15:01:00 |               15:01:09 |    00:00:26 |        15:47 |
| momentum v2           | deprecated | GRASSUSDT    | active        | open |                 15:01:00 |               15:01:06 |    00:00:49 |        18:46 |
| momentum v4           | deprecated | NEARUSDT     | active        | open |                 15:01:00 |               15:01:04 |    00:00:50 |        18:32 |
| momentum v6           | deprecated | PUMPUSDT     | active        | open |                 15:01:00 |               15:01:06 |    00:00:48 |        16:02 |
| session_orb v1        | deprecated | FILUSDT      | active        | open |                 15:01:00 |               15:01:03 |    00:00:51 |        15:46 |
| trendline_breakout v1 | deprecated | 1000PEPEUSDT | active        | open |                 15:01:00 |               15:01:04 |    00:00:50 |        22:01 |
| trendline_breakout v1 | deprecated | DOGEUSDT     | pending_entry | open |                        - |               15:00:33 |    00:01:21 |        23:01 |
| volume_anomaly v2     | deprecated | ARBUSDT      | active        | open |                 15:01:00 |               15:01:09 |    00:00:45 |        16:32 |
…                                                                                                          (57 linhas)
```

**`acompanhado_ate = 15:01:00` e `atualizado_em = 15:01:0x` — de 45 s a 51 s antes da leitura, e
minutos DEPOIS das aposentadorias das 14:55–15:00.** Os 57 seguem andando minuto a minuto e vão
liquidar sozinhos (stop, alvo ou horizonte, entre 15:26 e 23:01Z).

O motivo é o mesmo que a T3.47b encontrou lendo o código: `consumer.sweep_outcomes` →
`tracking_repo.load_open_trackings` filtra por `tracking_state`, mercado e coorte — **nunca por versão
nem por status de versão** (`tracking_repo.py:151-177`). Aposentar para a **decisão nova**, não o
**acompanhamento em voo**. Confirmado pela segunda vez, agora com 57 linhas em vez de 8.

E as vivas seguem decidindo — o roster novo não ficou mudo:

```
== as versoes vivas seguem decidindo (ultimo sinal) ==
| mean_reversion v1  | research_only | 2026-09-09 15:01:47 | 1 sinal desde 14:55 |
| mean_reversion v10 | research_only | 2026-09-09 15:01:48 | 1                   |
| mean_reversion v8  | research_only | 2026-09-09 15:01:48 | 1                   |
| momentum v3        | paper         | 2026-09-09 15:01:30 | 2                   |
| momentum v8        | research_only | 2026-09-09 15:01:30 | 2                   |
| mean_reversion v2  | research_only | 2026-09-09 14:19:56 | 0                   |
| mean_reversion v3  | research_only | 2026-09-09 14:19:56 | 0                   |
| mean_reversion v6  | research_only | 2026-09-09 14:19:56 | 0                   |
| mean_reversion v7  | research_only | 2026-09-09 14:19:56 | 0                   |
```

(as quatro com 0 desde 14:55 decidiram às 14:19 — cadência normal delas, não silêncio.)

E a decisão **nova** parou onde deveria (sinais emitidos após `deprecated_at`):

```
+-----------------------+----------------+---------------+---------------------+
|        versao         | aposentada_utc | sinais_depois |  ultimo_sinal_utc   |
+-----------------------+----------------+---------------+---------------------+
| volume_anomaly v2     | 14:55:29       |             0 | 2026-09-09 14:55:25 |
| momentum v2           | 14:56:27       |             0 | 2026-09-09 14:48:13 |
| momentum v4           | 14:57:16       |             0 | 2026-09-09 14:48:03 |
| momentum v6           | 14:58:00       |             0 | 2026-09-09 14:48:14 |
| momentum v10          | 14:58:42       |             0 | 2026-09-09 14:48:14 |
| session_orb v1        | 14:59:24       |             0 | 2026-09-09 14:49:38 |
| trendline_breakout v1 | 15:00:10       |             2 | 2026-09-09 15:00:33 |
+-----------------------+----------------+---------------+---------------------+
```

**Seis das sete: zero decisões novas.** A sétima é o CONCERN 3.

---

## 9. CONCERNS

### CONCERN 1 — `session_orb v1` foi morta com um número que não reproduz mais

O brief justifica com "−0,19 / −0,51 R". O `−0,19` é o **replay** (medi −0,1928, n 20). O `−0,51`
seria a prospectiva — e **hoje a prospectiva da `session_orb v1` é −0,0266 R em n 31** (soma −0,83 R).
Não é erro do brief: é o n crescendo (a coorte era menor quando o número foi medido) e a média
voltando para perto de zero.

**O que isso muda:** a direção continua a mesma (negativa nas duas coortes) e a autorização de Everton
é explícita e cobre "as que estão dando ruim". Mas, das sete, **esta é a única cuja aposentadoria eu
não defenderia só pelo número**: −0,027 R sobre 31 desfechos é ruído, não veredito, e o replay tem
n 20. Escrevi "K1 nas duas" no `changelog` para que quem reabrir o caso veja isso de cara. **Se a
`session_orb` voltar, o caminho honesto é uma v2 com protocolo congelado e n mínimo declarado antes de
olhar, não reativar a v1.**

O mesmo efeito, mais fraco, na `trendline_breakout v1` (brief −0,55 prosp. n 21 → medido −0,3417,
n 57): continua claramente negativa, só que menos — e ali o brief já manda manter o módulo para uma
v2. Na `momentum v6` acontece o **oposto** de ruído (brief −0,31 n 50 → medido −0,2856 n 156: o número
quase não mudou com n triplo).

### CONCERN 2 — a linha `paper` tem um impasse estrutural, e ele não se resolve esperando

`open_paper_exposure()` exige **zero** `shadow_episodes` com acompanhamento aberto. Mas `momentum v3`
está **`active`**, então continua decidindo e **continua abrindo slots novos**: eram 5 às 14:52, 5 na
recusa das 15:00:47 e **6** às 15:01:36. Enquanto ela estiver no roster, a janela em que a checagem
passa é uma coincidência, não um estado alcançável de propósito.

**Não inventei saída** (o brief manda parar, e o portão existe por revisão de risco explícita: "a
version being deprecated must never be the paper line with open positions"). Os dois caminhos
honestos, para quem tem autoridade decidir:

1. **Repetir o comando até pegar uma janela limpa.** Barato e seguro — o comando é idempotente e
   recusa sozinho; a checagem e o `UPDATE` estão na mesma transação. O que não é garantido é *quando*
   a janela aparece.
2. **Trocar a ordem**: primeiro mover a linha `paper` para outra versão (`--paper-line` a partir de
   uma `mean_reversion` viva, que é a família que está ganhando), e só depois aposentar a `momentum
   v3` — aí ela para de abrir slots porque deixou de ser a linha da carteira. **Isso é decisão de
   produto/risco, fora do brief.**

**Enquanto isso: `momentum v3` continua `active`, `purpose = 'paper'`, −0,2256 R em n 453, e nada
executa (`ENABLE_PAPER_AUTONOMY=false`, `posicoes_abertas = 0`).** O custo de não tê-la matado hoje é
zero em dinheiro e é ruído no Lab.

### CONCERN 3 — `trendline_breakout v1` decidiu 2 vezes **23 s depois** de aposentada

`deprecated_at = 15:00:10`, dois sinais em `15:00:33` (DOGEUSDT e SOPHUSDT, os dois em
`pending_entry`). Não é falha de isolamento: `SHADOW_VERSION_REFRESH_S = 60,0`
(`services/strategy-worker/hunter_strategy_worker/config.py:136`) — o worker recarrega o roster a cada
60 s, então uma versão aposentada no meio de um ciclo ainda decide até o fim dele. As outras seis não
mostraram isso porque o ciclo delas caiu do outro lado da escrita.

**Consequência real:** até 60 s de decisões novas depois de um `--deprecate`, que entram na coorte
prospectiva da versão morta e ficam sendo acompanhadas normalmente. É pequeno e auto-limitado, mas
**não está documentado em `docs/ACTIVATION.md`**, e quem auditar a coorte de uma versão aposentada vai
encontrar sinais com `emitted_at > deprecated_at` sem explicação. Vale uma linha na doc — **não
escrevi**: o brief é de operação, não de doc, e a árvore é compartilhada.

---

## 10. O QUE **NÃO** FIZ

- **Não commitei nada.** Nenhum `git add`, `stash`, `checkout --`, `restore`, `reset`, `clean`.
- **Não rodei `git pull` na VPS** (o `ops` usou a imagem `hunter-api:f1475c4`, que já existia).
- **Não parei, recriei nem reiniciei container nenhum.** Os `hunter-ops-run-*` são contêineres
  efêmeros de `docker compose run --rm`, criados e removidos pelo próprio `compose.sh ops`.
- **Não toquei em nenhum `.env*`.**
- **Não escrevi uma linha de SQL de escrita.** As sete mudanças passaram pelo script auditado; todas
  as leituras foram `begin transaction isolation level repeatable read read only`.
- **Não usei shell em background.** Tudo em primeiro plano, dentro de `timeout 290`.
- **Não ativei, derivei nem criei versão nenhuma.** O brief diz "nada mais novo", e nada novo entrou.
- **Não forcei a `momentum v3`** por fora do script depois da recusa.

---

## 11. CONFIRMAÇÃO FINAL (`read_at = 2026-09-09T15:10:22,948954Z` = **12:10:22 BRT**)

Releitura ~10 min depois da última escrita, já com o ciclo de 60 s do roster fechado nas sete:

```
== decisao nova depois da aposentadoria (janela ja fechada) ==
+-----------------------+----------------+---------------+---------------+----------+
|        versao         | aposentada_utc | sinais_depois | ultimo_depois |  atraso  |
+-----------------------+----------------+---------------+---------------+----------+
| volume_anomaly v2     | 14:55:29       |             0 |               |          |
| momentum v2           | 14:56:27       |             0 |               |          |
| momentum v4           | 14:57:16       |             0 |               |          |
| momentum v6           | 14:58:00       |             0 |               |          |
| momentum v10          | 14:58:42       |             0 |               |          |
| session_orb v1        | 14:59:24       |             0 |               |          |
| trendline_breakout v1 | 15:00:10       |             2 | 15:00:33      | 00:00:23 |
+-----------------------+----------------+---------------+---------------+----------+

== os acompanhamentos das aposentadas seguem andando ==
+------------+-------------------------+--------------+-------------+--------------------------------+
|   status   | acompanhamentos_abertos | mais_recente | mais_antigo | atualizados_apos_aposentadoria |
+------------+-------------------------+--------------+-------------+--------------------------------+
| deprecated |                      46 | 00:00:12     | 00:00:13    |                             46 |
+------------+-------------------------+--------------+-------------+--------------------------------+

== roster ativo ==
| draft      | research_only |  4 |
| active     | paper         |  1 |
| active     | research_only |  8 |
| deprecated | research_only | 17 |
```

**Três coisas fechadas de uma vez:**

1. **O atraso da `trendline_breakout v1` congelou em 23 s e em 2 sinais** — nenhum sinal novo depois,
   exatamente o que o cache de 60 s prevê (CONCERN 3). Não é vazamento contínuo.
2. **46 acompanhamentos abertos das sete aposentadas, e os 46 atualizados DEPOIS da aposentadoria**,
   os mais velhos há 13 s. (Eram 57 às 15:01; **onze já liquidaram sozinhos nesses 9 min** — que é
   justamente o comportamento que queríamos ver.)
3. **O roster ficou em 9 ativas** e não se mexeu mais.

---

## 12. VERIFICAÇÕES LOCAIS (nada de código meu para testar, mas o helper da T3.47c é o que carregou a tarefa)

```
$ uv run pytest services/strategy-worker/tests/test_append_deprecation_note.py -q
......                                                                   [100%]
6 passed in 1.35s
```

```
$ uv run python infra/scripts/check_file_size.py
error   354 > 350  services/strategy-worker/hunter_strategy_worker/context_budget.py
scanned 584 files; 1 over budget, 0 grandfathered
```

**O arquivo estourado não é meu**: `context_budget.py` é **untracked** (`git status` → `??`, sem
histórico) — trabalho em voo de outra tarefa (a T3.54b, o `_refuse_unbudgeted_context`). **Não toquei
nele.** Registro aqui só para que ninguém atribua o estouro a esta tarefa.

`git status` dos meus arquivos:

```
?? .claude/state/notes-T3.56.md
?? infra/scripts/sql/research/2026-09-09-t356-q00-catalogo-antes.sql
?? infra/scripts/sql/research/2026-09-09-t356-q01-c5-teto-de-stop.sql
?? infra/scripts/sql/research/2026-09-09-t356-q02-catalogo-depois.sql
```

Quatro arquivos, todos novos, todos fora de `apps/**`, `services/**`, `packages/**` e `obsidian/**`.
**Nada commitado, nada indexado.**
