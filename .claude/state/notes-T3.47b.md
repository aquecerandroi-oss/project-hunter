# notes-T3.47b — o piso de ATR% compra decisões, e todas as que ele compra são perdedoras

**Data:** 2026-09-08 (UTC; **Brasília = UTC−3** — todo horário desta nota aparece nas duas réguas).
**Owner:** quant-engineer. **Continuação da T3.47** (`.claude/state/notes-T3.47.md` §15 e
`exp-drafts/EXP-0018-stop-largo.md`).

**Base do brief:** `main @ HEAD = 1c72134` (o commit da própria T3.47) — a árvore andou para
`95bc2f0` por outras tarefas antes de eu fechar, e **nenhum commit é meu** (linha do tempo completa
no ADENDO). VPS rodando `hunter-api:2e39774` na `api`, na `web` e no `strategy-worker` **em todos os
atos desta tarefa**; a `api` e a `web` foram redeployadas por outra tarefa **depois** do meu último
ato (~00:05 e ~00:09Z, contra 23:47Z), e o `strategy-worker` — que rodou os replays — **nunca foi
tocado**. Nenhum container parado ou recriado por mim.
**Nada commitado. Nada indexado. Nenhum `.env*` tocado. Nada escrito por mim em `apps/**`,
`services/**`, `packages/**`, `obsidian/**`.**
**Escritas na VPS:** três `activate_strategy_version.py --deprecate`, uma `derive_variant.py`, uma
`activate_strategy_version.py`, dois replays. Duas passadas de estresse (`READ ONLY` por
construção). Todo o resto foi lido em transação `repeatable read read only`.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Aposentar `momentum v7`, `mean_reversion v4`, `mean_reversion v5` com o veredito da T3.47 no changelog | **OK.** §2. Três `--dry-run` limpos, três escritas, catálogo antes/depois colado. **Nenhuma recusa.** Roster **16 → 13** ativas |
| 2 | Derivar **v8** (piso 0,006 + stop 1,5) e **v9** (piso 0,006, só o piso) de `mean_reversion v2`; ativar `research_only` | **v8: OK** (`params_hash b64c4d0e4d4c`, digest `…a970c9d9…` inalterado). **v9: RECUSADA pelo script — e a recusa é a resposta**: "piso 0,006 e nada mais" **é a `mean_reversion v1`**, que já existe e já foi replayada no mesmo protocolo. §3 |
| 3 | Replay 31 d × 4 mercados, `--explain-ledger`, coorte explícita; barras admitidas/recusadas pelo piso; bootstrap de blocos de dia; estresse se K1 sobreviver | **OK.** 2 fatias, 0 erros; o porteiro de ATR% medido barra a barra no livro-razão (§4); `t342-blocos/blocos.py` nas duas populações (§7); **estresse nas duas** (K1 sobrevive nas duas pela primeira vez na família) §8 |
| 4 | Veredito por variante + ≤ 10 linhas para o Everton | **OK.** §10 e §11 |
| 5 | Rascunho EXP-0019 (portão C1–C8, K1–K6, protocolo congelado) | **OK.** `.claude/state/exp-drafts/EXP-0019-piso-atr.md` |

**Resposta curta.** Baixar o piso de ATR% de **0,008 para 0,006** faz exatamente o que a T3.45
prometia em número de decisões e exatamente o contrário do que se esperava em resultado: a população
**dobra** (15 → 33 decisões com stop 1,5; 17 → 37 com stop 1,0) e **a expectância cai 70 %**
(+0,2861 → **+0,0855 R**; +0,2998 → **+0,0938 R**). O motivo está medido decisão a decisão, e não é
o pedágio: **as decisões que o piso 0,006 admite e o 0,008 recusava — a faixa `[0,006; 0,008)` —
rendem −0,0817 R cada uma com stop 1,5 e −0,0814 R com stop 1,0.** As duas colunas de stop dão o
mesmo número até a terceira casa; o stop largo cortou o pedágio da faixa nova de 0,2753 para
0,1873 R (÷1,47, como a identidade manda) e devolveu **0,0882 R** no bruto contra **0,0880 R**
economizados. **O piso de ATR% não escondia decisões boas: escondia dias ruins.** Dos quatro dias
que só existem com o piso baixo, **quatro são negativos**.

---

## FILES

Criados (todos meus, todos fora de código de produção; raiz `C:\dev\project-hunter\`):

| arquivo | o quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t347b-q00-catalogo-antes.sql` | roster/geometria **antes** de qualquer escrita + o que o `--deprecate` checaria |
| `infra/scripts/sql/research/2026-09-09-t347b-q01-slots-abertos.sql` | os oito acompanhamentos abertos das versões a aposentar (o custo declarado) |
| `infra/scripts/sql/research/2026-09-09-t347b-q02-v9-e-v1.sql` | a prova de que a "v9" do brief é a `mean_reversion v1`, e o recibo do replay dela |
| `infra/scripts/sql/research/2026-09-09-t347b-q10-populacoes.sql` | o fatorial 2×2 piso × stop: populações, cobertura, identidade do pedágio, C5, motivos |
| `infra/scripts/sql/research/2026-09-09-t347b-q11-faixa-nova.sql` | a faixa nova `[0,006; 0,008)` contra a que já existia + o pareamento por (mercado, barra) |
| `infra/scripts/sql/research/2026-09-09-t347b-q12-dump-blocos.sql` | dump CSV (dia, ATR%, R líquido) para o `blocos.py` da T3.42 |
| `infra/scripts/sql/research/2026-09-09-t347b-q13-recibos-iso-roster.sql` | `replay_runs`, `system_events`, `shadow_outbox`, roster **depois**, acompanhamentos, linhagem da v8 |
| `infra/scripts/sql/research/2026-09-09-t347b-q14-dias-e-mercados.sql` | R por dia nas quatro coortes e concentração por mercado (K6) |
| `infra/scripts/sql/research/2026-09-09-t347b-q15-teto-de-pedagio.sql` | o teto de 0,222 R do brief contra o pedágio medido; C5 por faixa de ATR% |
| `.claude/state/exp-drafts/t347b-dumps/v8-piso0006-stop15.csv` | as 33 decisões da v8 (CONCERN 1 — fora do escrito de escrita do brief) |
| `.claude/state/exp-drafts/t347b-dumps/v1-piso0006-stop10.csv` | as 37 decisões da v1 |
| `.claude/state/exp-drafts/EXP-0019-piso-atr.md` | o EXP com portão C1–C8, K1–K6 e protocolo congelado |
| `.claude/state/notes-T3.47b.md` | este arquivo |

**Nenhuma ferramenta nova foi escrita.** O bootstrap de blocos de dia é o `t342-blocos/blocos.py`
**sem uma linha alterada** — e desta vez ele é literalmente o instrumento certo, porque a variante é
**superconjunto exato** do pai (§6.1), que é o caso para o qual ele foi escrito (contraste
população-contra-população por piso), ao contrário da T3.47 (CONCERN 1 dela).

---

## 1. O QUE JÁ ESTAVA VIVO (antes de qualquer escrita)

```
$ ssh hunter-vps 'date -u; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Tue Sep  8 23:29:43 UTC 2026                                   <- 20:29:43 Brasília
hunter-scanner-worker-1   hunter-api:14c4b54   Up 28 minutes (healthy)
hunter-web-1              hunter-web:2e39774   Up About an hour (healthy)
hunter-api-1              hunter-api:2e39774   Up About an hour (healthy)
hunter-strategy-worker-1  hunter-api:2e39774   Up About an hour (healthy)
hunter-execution-worker-1 hunter-api:1926e53   Up 3 hours (healthy)
hunter-market-worker-*    hunter-api:1926e53   Up 3 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1            Up 42 hours (healthy)
```

Os dois scripts auditados são **byte a byte** os do `HEAD`, nas três árvores:

```
$ ssh hunter-vps 'docker exec hunter-api-1 sha256sum /app/infra/scripts/derive_variant.py /app/infra/scripts/activate_strategy_version.py'
830a1f896befde5a91092957443310a52839bab3f98da238950c77a9008f9bf0  /app/infra/scripts/derive_variant.py
dc6abf957718707e471aac1757dcf47f17241b59e632df3923a0b8632fd7e22e  /app/infra/scripts/activate_strategy_version.py

$ sha256sum infra/scripts/derive_variant.py infra/scripts/activate_strategy_version.py     # árvore local
830a1f89…  dc6abf95…
$ git show HEAD:infra/scripts/derive_variant.py | sha256sum             -> 830a1f89…
$ git show HEAD:infra/scripts/activate_strategy_version.py | sha256sum  -> dc6abf95…
```

**Antes de tocar em qualquer coisa eu li o `--help` do `--deprecate` e a `docs/ACTIVATION.md` §7b**,
como o brief manda. As duas recusas estruturais (`purpose = 'live'` nunca; `purpose = 'paper'` só
com `--force-paper` **e** sem posição/slot aberto) não se aplicam às três versões desta tarefa, que
são `research_only` — e isso está conferido no `q00` §4 **antes** de qualquer escrita.

---

## 2. HIGIENE DO ROSTER — as três aposentadorias

### 2.1 O catálogo **antes** (`q00`, `read_at = 2026-09-08T23:31:52,955594Z` = **20:31:52** Brasília)

```
+-----------------------+------------+---------------+----------------------------+----------------------------+
|        versao         |   status   |    purpose    |         ativada_em         |       aposentada_em        |
+-----------------------+------------+---------------+----------------------------+----------------------------+
| breakout v1           | deprecated | research_only | 2026-09-08 16:23:39.791800 | 2026-09-08 19:35:34.497266 |
| breakout v2           | deprecated | research_only | 2026-09-08 17:35:22.628018 | 2026-09-08 19:35:36.380289 |
| derivatives v1        | draft      | research_only |                            |                            |
| ensemble v1           | draft      | research_only |                            |                            |
| mean_reversion v1     | active     | research_only | 2026-09-08 16:32:33.947955 |                            |
| mean_reversion v2     | active     | research_only | 2026-09-08 21:24:26.306302 |                            |
| mean_reversion v3     | active     | research_only | 2026-09-08 21:34:01.491564 |                            |
| mean_reversion v4     | active     | research_only | 2026-09-08 22:38:37.842745 |                            |   <- a aposentar
| mean_reversion v5     | active     | research_only | 2026-09-08 22:38:41.887854 |                            |   <- a aposentar
| mean_reversion v6     | active     | research_only | 2026-09-08 22:38:46.022557 |                            |
| mean_reversion v7     | active     | research_only | 2026-09-08 22:38:49.950926 |                            |
| momentum v1           | deprecated | research_only | 2026-09-06 03:36:36.988581 | 2026-09-08 04:33:56.865371 |
| momentum v2           | active     | research_only | 2026-09-08 04:33:56.865371 |                            |
| momentum v3           | active     | paper         | 2026-09-08 05:57:30.922979 |                            |
| momentum v4           | active     | research_only | 2026-09-08 13:05:13.558855 |                            |
| momentum v5           | deprecated | research_only | 2026-09-08 18:57:05.384576 | 2026-09-08 19:39:00.460160 |
| momentum v6           | active     | research_only | 2026-09-08 19:04:56.213531 |                            |
| momentum v7           | active     | research_only | 2026-09-08 22:29:28.783999 |                            |   <- a aposentar
| momentum v8           | active     | research_only | 2026-09-08 22:29:33.049734 |                            |
| narrative v1          | draft      | research_only |                            |                            |
| order_flow v1         | draft      | research_only |                            |                            |
| session_orb v1        | active     | research_only | 2026-09-08 19:42:56.116683 |                            |
| trendline_breakout v1 | active     | research_only | 2026-09-08 22:29:52.701952 |                            |
| volume_anomaly v1     | deprecated | research_only | 2026-09-06 03:36:47.845595 | 2026-09-08 04:32:42.178866 |
| volume_anomaly v2     | active     | research_only | 2026-09-08 04:32:42.178866 |                            |
+-----------------------+------------+---------------+----------------------------+----------------------------+
(25 rows)

+------------+---------+
|   status   | versoes |
| draft      |       4 |
| active     |      16 |     <- o número que a T3.47 CONCERN 2 chamou de "dobrei a carga"
| deprecated |       5 |
+------------+---------+
```

### 2.2 O que o `--deprecate` iria encontrar (`q00` §4)

```
+-------------------+---------------+--------+---------------+--------+---------------------+
|      versao       |    purpose    | status | slots_abertos | sinais | sinais_prospectivos |
+-------------------+---------------+--------+---------------+--------+---------------------+
| mean_reversion v4 | research_only | active |             3 |     16 |                   6 |
| mean_reversion v5 | research_only | active |             3 |     15 |                   6 |
| momentum v7       | research_only | active |             1 |    194 |                  10 |
+-------------------+---------------+--------+---------------+--------+---------------------+
```

**As três tinham acompanhamento aberto na hora de aposentar** (`q01`, `read_at = 23:33:14,322863Z` =
**20:33:14**), oito no total, todos `prospective`, todos abertos nos 47 min anteriores:

```
| mean_reversion v4 | DOGSUSDT | active | open | prospective | 22:46:40 | idade 00:46:33 | expira 2026-09-09 02:47 |
| mean_reversion v4 | KSMUSDT  | active | open | prospective | 23:30:59 | idade 00:02:15 | expira 2026-09-09 03:31 |
| mean_reversion v4 | VETUSDT  | active | open | prospective | 23:01:50 | idade 00:31:23 | expira 2026-09-09 03:02 |
| mean_reversion v5 | DOGSUSDT | active | open | prospective | 22:46:41 | …              | …                       |
| mean_reversion v5 | KSMUSDT  | active | open | prospective | 23:30:59 | …              | …                       |
| mean_reversion v5 | VETUSDT  | active | open | prospective | 23:01:50 | …              | …                       |
| momentum v7       | FORMUSDT | active | open | prospective | 23:30:22 | idade 00:02:51 | expira 2026-09-09 03:31 |
| momentum v7       | VVVUSDT  | active | open | prospective | 23:31:58 | idade 00:01:16 | expira 2026-09-09 03:32 |
```

**Eu esperava que isso fosse o custo escondido da tarefa e estava errado — e a verificação está em
§2.5.** A leitura ingênua do código é que `_advance_open_tracking` mora dentro de
`decide.evaluate_slot`, que só roda para versões do roster (`catalogue.load_version_roster` filtra
`status = 'active'`), logo aposentar congelaria os oito acompanhamentos para sempre. **Existe uma
segunda via, independente do roster**, e é ela que manda: `consumer.sweep_outcomes` →
`tracking_repo.load_open_trackings`, cuja consulta filtra por `tracking_state`, por mercado e por
coorte — **nunca por versão nem por status de versão**
(`services/strategy-worker/hunter_strategy_worker/tracking_repo.py:151-177`). Medi em vez de supor.

### 2.3 Os três `--dry-run` (nada escrito)

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py momentum v7 \
    --deprecate --successor v8 --changelog "…" --dry-run'
Tue Sep  8 23:34:09 UTC 2026                                                     <- 20:34:09
would deprecate momentum v7 (purpose research_only), code_ref hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c, params_hash 5e456ae9eb5b, successor=momentum v8: variante de v6 | derived_from=v6 | overrides=stop_atr=2.25,target2_atr=9,target3_atr=13.5,target_atr=4.5 | params_hash=5e456ae9eb5b | T3.47b: aposentada. Veredito da T3.47 (notes secao 13, C1): descartar - delta pareado -0,0040 R em 181 pares (pior que o pai momentum v6), 105 por cento da economia de pedagio devolvida no bruto, estresse sem_vantagem_na_base (-0,0568 R, PF 0,859 contra -0,0513 e PF 0,906 do pai); dominada pela irma v8 em toda metrica. Prefixo de linhagem preservado de proposito.
exit=0
Tue Sep  8 23:34:10 UTC 2026

Tue Sep  8 23:34:25 UTC 2026
would deprecate mean_reversion v4 (purpose research_only), code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f, params_hash 1b868c55ebed, successor=none: variante de v3 | derived_from=v3 | overrides=stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=1b868c55ebed | T3.47b: aposentada. Veredito da T3.47 (notes secao 13, A1): descartar como candidata - K1 (10 decisoes em 31 d), 8 das 10 saidas por horizonte, tudo em 4 dias de agosto, 30 por cento das decisoes acima do teto de stop do paper_v1, delta pareado +0,0472 R com IC95 [-0,134; +0,284] contendo zero. Sem sucessora: nada a substitui. Prefixo de linhagem preservado de proposito.
exit=0
would deprecate mean_reversion v5 (purpose research_only), code_ref …a970c9d9…, params_hash dd8b22cd30a0, successor=none: variante de v3 | derived_from=v3 | overrides=stop_atr=2,target2_atr=5,target_atr=3 | params_hash=dd8b22cd30a0 | T3.47b: aposentada. Veredito da T3.47 (notes secao 13, A2): descartar como candidata - K1 (9 decisoes em 31 d), PF 21 sobre 8 saidas por horizonte em 4 dias consecutivos de agosto (episodio reprecificado, nao estrategia), 44 por cento das decisoes acima do teto de stop do paper_v1, delta pareado +0,0572 R com IC95 [-0,318; +0,192]. Sem sucessora: nada a substitui. Prefixo de linhagem preservado de proposito.
exit=0
Tue Sep  8 23:34:29 UTC 2026
```

**Por que o changelog começa repetindo a linhagem.** `--deprecate` faz
`UPDATE … changelog = :changelog` (`deprecate.py`), e a linhagem legível-e-analisável de uma variante
**mora no `changelog`** (`derive_variant.py:17-22,88`: `variante de v2 | derived_from=v2 |
overrides=… | params_hash=…`, lida por `infra/scripts/obsidian_strategy_pages.py`). Aposentar com um
texto novo **apaga a linhagem** da linha. Preservei o prefixo verbatim e acrescentei o veredito
depois dele — `LINEAGE_RE` casa por prefixo, então `lineage_of()` continua devolvendo a mesma
string. **Isto é uma decisão minha, não do brief nem da doc**, e está no CONCERN 3.

`--successor v8` só na `momentum v7`, porque ali existe de verdade uma sucessora do **mesmo**
experimento (a irmã de stop ×2, que sobreviveu ao veredito). Nas duas `mean_reversion` o campo é
`none` porque **nada as substitui** — inventar uma sucessora para preencher a coluna seria mentir no
`system_events`.

### 2.4 As três escritas

```
Tue Sep  8 23:34:40 UTC 2026
deprecated momentum v7 (purpose research_only) at 2026-09-08T23:34:42.370162+00:00, successor=momentum v8
exit=0
Tue Sep  8 23:34:42 UTC 2026

Tue Sep  8 23:34:55 UTC 2026
deprecated mean_reversion v4 (purpose research_only) at 2026-09-08T23:34:57.087557+00:00, successor=none
exit=0
deprecated mean_reversion v5 (purpose research_only) at 2026-09-08T23:34:59.064478+00:00, successor=none
exit=0
Tue Sep  8 23:34:59 UTC 2026
```

| versão | aposentada (UTC) | **Brasília** | `params_hash` congelado | sucessora |
|---|---|---|---|---|
| `momentum v7` | 2026-09-08T23:34:42,370162Z | **20:34:42** | `5e456ae9eb5b` | `momentum v8` |
| `mean_reversion v4` | 2026-09-08T23:34:57,087557Z | **20:34:57** | `1b868c55ebed` | nenhuma |
| `mean_reversion v5` | 2026-09-08T23:34:59,064478Z | **20:34:59** | `dd8b22cd30a0` | nenhuma |

**Nenhuma recusa. Nenhum caso que a doc não previsse.** As três linhas em `system_events` são
`strategy_version_deprecated`, nível `info` (verbatim em §5).

### 2.5 O que aposentar mudou — e o que **não** mudou (`q13` §7, `read_at = 23:47:35,820039Z` = 20:47:35)

```
+-------------------+------------+----------+--------+-----------+---------------------+---------------------+---------------------+
|      versao       |   status   |  symbol  | estado | resultado |   acompanhado_ate   |      expira_em      |    atualizado_em    |
+-------------------+------------+----------+--------+-----------+---------------------+---------------------+---------------------+
| mean_reversion v4 | deprecated | DOGSUSDT | active | open      | 2026-09-08 23:48:00 | 2026-09-09 02:47:00 | 2026-09-08 23:48:04 |
| mean_reversion v4 | deprecated | KSMUSDT  | active | open      | 2026-09-08 23:47:00 | 2026-09-09 03:31:00 | 2026-09-08 23:48:02 |
| mean_reversion v4 | deprecated | VETUSDT  | active | open      | 2026-09-08 23:48:00 | 2026-09-09 03:02:00 | 2026-09-08 23:48:02 |
| mean_reversion v5 | deprecated | DOGSUSDT | active | open      | 2026-09-08 23:48:00 | 2026-09-09 02:47:00 | 2026-09-08 23:48:03 |
| mean_reversion v5 | deprecated | KSMUSDT  | active | open      | 2026-09-08 23:48:00 | 2026-09-09 03:31:00 | 2026-09-08 23:48:03 |
| mean_reversion v5 | deprecated | VETUSDT  | active | open      | 2026-09-08 23:48:00 | 2026-09-09 03:02:00 | 2026-09-08 23:48:02 |
| momentum v7       | deprecated | FORMUSDT | active | open      | 2026-09-08 23:48:00 | 2026-09-09 03:31:00 | 2026-09-08 23:48:02 |
| momentum v7       | deprecated | VVVUSDT  | active | open      | 2026-09-08 23:48:00 | 2026-09-09 03:32:00 | 2026-09-08 23:48:03 |
```

**`acompanhado_ate` = 23:47/23:48 e `atualizado_em` = 23:48:0x — treze minutos DEPOIS da
aposentadoria das 23:34.** Os oito acompanhamentos continuam andando minuto a minuto e vão liquidar
sozinhos (stop, alvo ou horizonte, entre 02:47 e 03:32Z). **Aposentar parou a decisão nova e não
abandonou nenhuma operação em voo** — exatamente o que o brief dizia ("as coortes prospectivas dessas
versões param, nada mais muda"), agora **medido** e não suposto.

### 2.6 O catálogo **depois** (`q13` §5/§6)

```
+-----------------------+------------+---------------+----------------+--------------+
|        versao         |   status   |    purpose    | aposentada_utc | params_hash  |
+-----------------------+------------+---------------+----------------+--------------+
| mean_reversion v1     | active     | research_only |                |              |
| mean_reversion v2     | active     | research_only |                | ecd26dfc017a |
| mean_reversion v3     | active     | research_only |                | a71311773886 |
| mean_reversion v6     | active     | research_only |                | 11ce73ed48b5 |
| mean_reversion v7     | active     | research_only |                | 6b6168718cf2 |
| mean_reversion v8     | active     | research_only |                | b64c4d0e4d4c |   <- minha, nova
| momentum v2           | active     | research_only |                |              |
| momentum v3           | active     | paper         |                |              |
| momentum v4           | active     | research_only |                |              |
| momentum v6           | active     | research_only |                | 8cb1aa497956 |
| momentum v8           | active     | research_only |                | 69152dbc9173 |
| session_orb v1        | active     | research_only |                |              |
| trendline_breakout v1 | active     | research_only |                |              |
| volume_anomaly v2     | active     | research_only |                |              |
| breakout v1           | deprecated | research_only | 19:35:34       |              |
| breakout v2           | deprecated | research_only | 19:35:36       |              |
| mean_reversion v4     | deprecated | research_only | 23:34:57       | 1b868c55ebed |   <- minha
| mean_reversion v5     | deprecated | research_only | 23:34:59       | dd8b22cd30a0 |   <- minha
| momentum v1           | deprecated | research_only | 04:33:56       |              |
| momentum v5           | deprecated | research_only | 19:39:00       |              |
| momentum v7           | deprecated | research_only | 23:34:42       | 5e456ae9eb5b |   <- minha
| volume_anomaly v1     | deprecated | research_only | 04:32:42       |              |
+-----------------------+------------+---------------+----------------+--------------+
(22 rows)

+------------+---------+
|   status   | versoes |
| draft      |       4 |
| active     |      14 |     <- 16 - 3 + 1
| deprecated |       8 |
+------------+---------+
```

**Dezesseis ativas viraram catorze.** A `paper` (`momentum v3`) segue intacta, `active`, primeira da
sua chave na ordem do roster. O saldo da tarefa é **−2 versões ativas**, não +2 como um experimento
novo costuma custar.

---

## 3. A VARIANTE QUE NÃO PRECISOU EXISTIR — a recusa da "v9" é o achado

O brief pedia **v9 = `atr_pct_min → 0,006` com `stop_atr 1,0`** ("só o piso — isola o efeito do
piso"). O script recusou:

```
$ ssh hunter-vps 'date -u; docker exec hunter-api-1 python infra/scripts/derive_variant.py mean_reversion v2 \
    --set atr_pct_min=0.006 --changelog "T3.47b D2: piso de ATR% 0,008 -> 0,006 e nada mais …" --dry-run'
Tue Sep  8 23:35:18 UTC 2026                                                     <- 20:35:18
RECUSADO: mean_reversion v1 já tem exatamente esses parâmetros neste code_ref (params_hash 8918b39b73fb): seria o mesmo experimento contado duas vezes
exit=1
```

**A recusa está prevista na `docs/ACTIVATION.md` §7** ("um conjunto que já existe no mesmo
`code_ref`"), então não é caso de parar e reportar — é caso de olhar para o que ela diz. E o que ela
diz é: a `mean_reversion v2` **nasceu** da `v1` subindo o piso de 0,006 para 0,008 (T3.42). Descer o
piso de volta sem mexer em mais nada **reconstrói a `v1`** (`q02` §1):

```
+-------------------+--------+---------------+-------------+-------------+----------+------------+-------------+-----------+-------------------+
|      versao       | status |    purpose    | atr_pct_min | atr_pct_max | stop_atr | target_atr | target2_atr | horizon_s | max_entry_delay_s |
+-------------------+--------+---------------+-------------+-------------+----------+------------+-------------+-----------+-------------------+
| mean_reversion v1 | active | research_only | 0.006       | 0.05        | 1        | 1.5        | 2.5         | 14400     | 120               |
| mean_reversion v2 | active | research_only | 0.008       | 0.05        | 1        | 1.5        | 2.5         | 14400     | 120               |
+-------------------+--------+---------------+-------------+-------------+----------+------------+-------------+-----------+-------------------+
```

E o braço "só o piso" **já foi replayado, no mesmo protocolo, com o mesmo relógio** (`q02` §2):

```
+--------------------------+-------------------+------------+------------+------+------------------------------------------------------------------+------+-----+-----+--------+-----+----+-----+---------------------+
|          coorte          |      versao       |     de     |    ate     | mkts |                             mercados                             | bars | sig | out | aberto | lag | wk | err |       inicio        |
+--------------------------+-------------------+------------+------------+------+------------------------------------------------------------------+------+-----+-----+--------+-----+----+-----+---------------------+
| replay:d0f77894-1e04-454 | mean_reversion v1 | 2026-08-08 | 2026-08-23 |    4 | binance:ETHUSDT,binance:SOLUSDT,binance:XRPUSDT,binance:DOGEUSDT | 5760 |  17 |  17 |      0 |   2 |  3 |   0 | 2026-09-08 16:37:38 |
| replay:d0f77894-1e04-454 | mean_reversion v1 | 2026-08-23 | 2026-09-08 |    4 | binance:ETHUSDT,binance:SOLUSDT,binance:XRPUSDT,binance:DOGEUSDT | 6144 |  37 |  37 |      0 |   2 |  3 |   0 | 2026-09-08 16:39:23 |
| replay:d570b19a-f6e2-431 | mean_reversion v2 | 2026-08-08 | 2026-08-23 |    4 | (as mesmas)                                                      | 5760 |  12 |  12 |      0 |   2 |  3 |   0 | 2026-09-08 21:25:01 |
| replay:d570b19a-f6e2-431 | mean_reversion v2 | 2026-08-23 | 2026-09-08 |    4 | (as mesmas)                                                      | 6144 |  17 |  17 |      0 |   2 |  3 |   0 | 2026-09-08 21:26:43 |
```

Mesma janela em duas fatias contíguas, mesmos quatro mercados, `decision_lag_s = 2`, `workers = 3`,
`errors = 0`. **O braço D2 do brief custa zero execuções**: ele é a `mean_reversion v1`, coorte
`replay:d0f77894`. Não derivei nada para ele, e o roster agradece.

### 3.1 A derivação e a ativação da v8 (a única versão nova)

```
$ … derive_variant.py mean_reversion v2 --set atr_pct_min=0.006 --set stop_atr=1.5 \
      --set target_atr=2.25 --set target2_atr=3.75 --changelog "T3.47b D1: …" --dry-run
Tue Sep  8 23:35:13 UTC 2026
derivaria mean_reversion v8 de v2 (purpose research_only, draft, nada ativado) em code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f: atr_pct_min 0.008 -> 0.006, stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash b64c4d0e4d4c]
exit=0

$ … (sem --dry-run)
Tue Sep  8 23:37:03 UTC 2026
derivada mean_reversion v8 de v2 (purpose research_only, draft, nada ativado) em code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f: atr_pct_min 0.008 -> 0.006, stop_atr 1 -> 1.5, target2_atr 2.5 -> 3.75, target_atr 1.5 -> 2.25 [params_hash b64c4d0e4d4c]
exit=0
Tue Sep  8 23:37:05 UTC 2026

$ … activate_strategy_version.py mean_reversion v8 --changelog "T3.47b D1: …" --dry-run
would activate mean_reversion v8 (purpose research_only) with code_ref …a970c9d9…239dadc3f0bd395f (18 parameters)
exit=0
$ … (sem --dry-run)
activated mean_reversion v8 (purpose research_only) at 2026-09-08T23:37:33.252307+00:00 with code_ref hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
exit=0
Tue Sep  8 23:37:33 UTC 2026
```

**O digest é `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d9…`, exatamente o do brief e o
do pai**, nos dois dry-runs, na derivação e na ativação. Conferido de novo depois, contra a linha do
pai (`q13` §8):

```
| mean_reversion v8 | active | research_only | piso 0.006 | stop 1.5 | alvos 2.25 / 3.75 | code_ref_igual_ao_pai = t | sufixo 239dadc3f0bd395f |
| changelog: variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.006,stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=b64c4d0e4d4c | T3.47b D1: coorte de pesquisa do piso de ATR% 0,006 com stop 1,5 ATR aberta (research_only, sem carteira) |
```

| variante | pai | piso | stop | escada | **ativada (UTC)** | **Brasília** | `params_hash` | coorte de replay |
|---|---|---|---|---|---|---|---|---|
| **D1** `mean_reversion v8` | `v2` | 0,008 → **0,006** | 1 → **1,5** | 1,5/2,5 → **2,25/3,75** | 2026-09-08T23:37:33,252307Z | **20:37:33** | `b64c4d0e4d4c` | `replay:8ac79cca-916b-4f7f-bd83-01b068b9f811` |
| **D2** `mean_reversion v1` (por identidade) | — | **0,006** | **1** | 1,5/2,5 | 2026-09-08T16:32:33,947955Z (T3.33e) | 13:32:33 | — | `replay:d0f77894-1e04-454e-a49f-d9a98d894968` |

**O desenho virou um fatorial 2×2 fechado**, com as duas células que faltavam já medidas pela T3.42
e pela T3.47:

| | `stop_atr = 1` | `stop_atr = 1,5` |
|---|---|---|
| **piso 0,006** | `v1` (37 decisões) | **`v8` (33) — nova** |
| **piso 0,008** | `v2` (17) | `v6` (15) |

---

## 4. O PORTEIRO DE ATR%, BARRA A BARRA (a pergunta central do brief)

O `--explain-ledger` grava uma linha por barra avaliada com a `Evaluation` que a própria estratégia
devolveu (`replay/explain.py`). O porteiro de ATR% é o **último** portão da `mean_reversion_v1`
(`packages/core/hunter_core/strategies/mean_reversion_v1.py:244-254`), depois de `no_uptrend_1h`,
`not_stretched` e `close_below_mid` — e **nenhum desses depende do piso**, o que torna o número de
barras que **chegam** ao porteiro idêntico nas três variantes. Histograma sobre os seis arquivos (os
meus dois de hoje e quatro que a T3.47 deixou em `/tmp` do `hunter-strategy-worker-1`):

```
== v8 piso 0,006 (stop 1,5) ==
barras 11904 | estados {'unavailable': 448, 'not_triggered': 11392, 'triggered': 64}
razoes: {'not_triggered/not_stretched': 5424, 'not_triggered/no_uptrend_1h': 5288,
         'not_triggered/close_below_mid': 525, 'unavailable/atr_warmup': 308,
         'not_triggered/atr_out_of_range': 155, 'unavailable/warmup': 140, 'triggered/signal': 64}
atr_out_of_range 155 (abaixo do piso 155, acima do teto 0)
faixas das recusas por ATR%: {'<0,004': 115, '[0,004;0,006)': 40}

== v6 piso 0,008 (stop 1,5) ==
barras 11904 | estados {'unavailable': 448, 'not_triggered': 11426, 'triggered': 30}
razoes: {… 'not_triggered/atr_out_of_range': 189, … 'triggered/signal': 30}
atr_out_of_range 189 (abaixo do piso 189, acima do teto 0)
faixas das recusas por ATR%: {'<0,004': 115, '[0,004;0,006)': 40, '[0,006;0,008)': 34}

== v4 piso 0,010 (stop 1,5) ==
barras 11904 | estados {'unavailable': 448, 'not_triggered': 11437, 'triggered': 19}
razoes: {… 'not_triggered/atr_out_of_range': 200, … 'triggered/signal': 19}
atr_out_of_range 200 (abaixo do piso 200, acima do teto 0)
faixas das recusas por ATR%: {'<0,004': 115, '[0,004;0,006)': 40, '[0,006;0,008)': 34, '[0,008;0,010)': 11}
```

**Barras que chegam ao porteiro: 219 nas três** (155+64 = 189+30 = 200+19 = 219). Isso é a prova,
por construção do livro-razão, de que **só o piso mudou**.

| piso | admite | recusa | % recusada **do que chega ao porteiro** |
|---|---:|---:|---:|
| 0,010 | 19 | 200 | **91,3 %** |
| 0,008 | 30 | 189 | **86,3 %** |
| **0,006** | **64** | **155** | **70,8 %** |

**Baixar 0,008 → 0,006 libera exatamente 34 barras** (a faixa `[0,006; 0,008)`) e **mais que dobra**
as barras admitidas (30 → 64, +113 %). Duas correções de enquadramento que esta medição obriga:

1. **O teto nunca recusou nada.** `acima do teto = 0` nas três: `atr_pct_max = 0,05` é letra morta
   nestes quatro mercados. Todo o efeito do parâmetro é do lado do piso.
2. **O piso não é o principal porteiro da estratégia — é o último e o menor.** Das 11 904 barras,
   `not_stretched` recusa 5 424 e `no_uptrend_1h` recusa 5 288; o piso recusa **189** (1,6 % das
   barras). A frase da T3.45 ("o piso recusa 67 % a 89 % das barras destes mercados") descreve a
   **distribuição de ATR% do universo**, não a posição dele no funil — e as duas coisas foram
   tratadas como a mesma na proposta da T3.47 §15. Baixar o piso **ainda dobra a população**, porque
   o funil já é estreito; mas "é lá que estão as decisões que faltam" era mais forte do que o dado
   sustenta.

Os recibos dos dois replays (`q13` §1) — 0 erros, cobertura fechada:

```
+--------------------------+-------------------+-------+-------+------+------+-----+-----+--------+--------+----+-----+--------------------------------------------------------------+-----+
|          coorte          |      versao       |  de   |  ate  | mkts | bars | sig | out | aberto |  seg   | wk | lag |                           estados                            | err |
+--------------------------+-------------------+-------+-------+------+------+-----+-----+--------+--------+----+-----+--------------------------------------------------------------+-----+
| replay:8ac79cca-916b-4f7 | mean_reversion v8 | 08-08 | 08-23 |    4 | 5760 |  16 |  16 |      0 | 90.996 |  3 |   2 | {"triggered": 28, "unavailable": 448, "not_triggered": 5284} |   0 |
| replay:8ac79cca-916b-4f7 | mean_reversion v8 | 08-23 | 09-08 |    4 | 6144 |  33 |  33 |      0 | 99.744 |  3 |   2 | {"triggered": 36, "not_triggered": 6108}                     |   0 |
+--------------------------+-------------------+-------+-------+------+------+-----+-----+--------+--------+----+-----+--------------------------------------------------------------+-----+
```

**Armadilha do denominador (a de sempre, desde a T3.33e):** `sig` conta a **coorte inteira**;
16 + 33 não são 49 — a população da `v8` é **33**. `triggered` é por fatia: 28 + 36 = **64**, o
número do livro-razão. A diferença 64 → 33 é ocupação de slot: com o piso mais baixo, mais barras
disparam no mesmo mercado dentro da mesma janela de 4 h e o segundo sinal é recusado.

Livros-razão: `/tmp/t347b-mr-v8-a.jsonl` (5 760 linhas) e `/tmp/t347b-mr-v8-b.jsonl` (6 144), com
`bars = lines` nos dois — recibo verbatim na saída do replay
(`replay_explain_ledger bars=5760 lines=5760` e `bars=6144 lines=6144`).

---

## 5. RECIBOS DA JANELA (`q13` §2, `system_events` a partir de 23:30Z)

```
+---------+---------------------------+----------------------------------+-------------------------------------------------------------------------+-------------------------------+
|  level  |         component         |              event               |                                mensagem                                 |          created_at           |
+---------+---------------------------+----------------------------------+-------------------------------------------------------------------------+-------------------------------+
| info    | activate_strategy_version | strategy_version_deprecated      | momentum v7 (purpose research_only) deprecated at 2026-09-08T23:34:42…  | 2026-09-08 23:34:42.370162+00 |
| info    | activate_strategy_version | strategy_version_deprecated      | mean_reversion v4 (purpose research_only) deprecated at 23:34:57…       | 2026-09-08 23:34:57.087557+00 |
| info    | activate_strategy_version | strategy_version_deprecated      | mean_reversion v5 (purpose research_only) deprecated at 23:34:59…       | 2026-09-08 23:34:59.064478+00 |
| warning | activate_strategy_version | strategy_version_variant_refused | mean_reversion v1 já tem exatamente esses parâmetros neste code_ref …   | 2026-09-08 23:35:18.231279+00 |
| info    | activate_strategy_version | strategy_version_variant_derived | mean_reversion v8 derived from v2 (variante, purpose research_only) …   | 2026-09-08 23:37:05.523288+00 |
| info    | activate_strategy_version | strategy_version_activated       | mean_reversion v8 (purpose research_only) activated with its already-…  | 2026-09-08 23:37:33.252307+00 |
| info    | replay_engine             | replay_run_finished              | replay mean_reversion v8 4 mercados 08-08..08-23: 5760 barras, 16 sinais| 2026-09-08 23:40:10.786694+00 |
| info    | replay_engine             | replay_run_finished              | replay mean_reversion v8 4 mercados 08-23..09-08: 6144 barras, 33 sinais| 2026-09-08 23:42:09.376843+00 |
+---------+---------------------------+----------------------------------+-------------------------------------------------------------------------+-------------------------------+
(8 rows)
```

**Oito linhas, oito atos — e nenhum outro.** A recusa da "v9" está gravada como `warning`, com o
motivo, que é o que um `Registro de Tentativas` honesto precisa ter.

### Isolamento — a coorte é a cerca (`q13` §3/§4)

```
+------------------+-----------------------+--------------+
| outbox_da_coorte | outbox_pendente_total | outbox_total |
|                0 |                     0 |         4975 |
+------------------+-----------------------+--------------+

| mean_reversion v8 | prospective                                 |  2 | 2026-09-08 23:46:51.979399+00 |
| mean_reversion v8 | replay:8ac79cca-916b-4f7f-bd83-01b068b9f811 | 33 | 2026-09-06 15:15:02+00        |
```

**Zero linhas de `shadow_outbox` para a coorte de replay** e zero pendentes na fila inteira. Os
sinais `prospective` da `v8` são o que "entrar no Lab" significa: eram 2 quando o `q13` rodou e
**4** na última leitura (`q13` §9, 2026-09-09T00:12Z), o **primeiro** às
**2026-09-08T23:45:26,854436Z** (**20:45:26** Brasília) — **7 min 53 s** depois da ativação — e o
quarto às 23:49:36,256214Z.

### Vigia (`hb:strategy:shadow`, a linha viva)

| relógio (UTC) | Brasília | marco | `evaluated_bars` | `outbox_lag_s` | `outbox_pending` | `errors` | `open_trackings` |
|---|---|---|---:|---:|---:|---:|---:|
| 23:38:14 | 20:38:14 | depois de aposentar 3 e ativar a `v8` | 21 422 | 0,0 | 0 | 0 | 67 |
| 23:49:08 | 20:49:08 | fechamento, após os dois replays e as duas passadas de estresse | 25 153 | 0,0 | 0 | 0 | 73 |

`hunter-api-1`, `hunter-web-1` e `hunter-strategy-worker-1` `healthy` em `2e39774` nas duas amostras;
`api /ready = 200` no fechamento. **Nenhum `errors` em nenhuma leitura.**

---

## 6. O FATORIAL 2×2 (`q10`, `read_at = 2026-09-08T23:44:06,880263Z` = **20:44:06**)

Mesma janela, mesmos quatro mercados, `decision_lag_s = 2`, `workers = 3` nas oito coortes.

```
+-------------------+-------+----------+----------+----------+------------+-------------+---------------+-------------+---------------+--------+------------+------------+----------+------+-------------+---------------+
|      versao       | piso  | stop_atr |  coorte  | decisoes | avaliaveis | exp_bruta_r | custo_medio_r | custo_p50_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | pf_bruto | dias | atr_pct_p50 | risco_pct_p50 |
+-------------------+-------+----------+----------+----------+------------+-------------+---------------+-------------+---------------+--------+------------+------------+----------+------+-------------+---------------+
| mean_reversion v1 | 0.006 | 1        | d0f77894 |       37 |         37 |      0.3210 |        0.2263 |      0.2290 |        0.0938 |   3.47 |       40.5 |     1.1856 |   1.7999 |   11 |     0.00760 |       0.00869 |
| mean_reversion v8 | 0.006 | 1.5      | 8ac79cca |       33 |         33 |      0.2383 |        0.1510 |      0.1631 |        0.0855 |   2.82 |       18.2 |     1.2262 |   1.7497 |   11 |     0.00760 |       0.01233 |
| mean_reversion v2 | 0.008 | 1        | d570b19a |       17 |         17 |      0.4686 |        0.1685 |      0.1871 |        0.2998 |   5.10 |       41.2 |     1.7483 |   2.4100 |    7 |     0.01051 |       0.01066 |
| mean_reversion v6 | 0.008 | 1.5      | 9d99748b |       15 |         15 |      0.3953 |        0.1075 |      0.1240 |        0.2861 |   4.29 |        6.7 |     2.2820 |   3.0027 |    7 |     0.01051 |       0.01631 |
| mean_reversion v7 | 0.008 | 2        | 264b227f |       14 |         14 |      0.4301 |        0.0838 |      0.0967 |        0.3450 |   4.83 |        7.1 |     4.7605 |   6.6357 |    7 |     0.01050 |       0.02077 |
| mean_reversion v3 | 0.01  | 1        | f4af4ffe |       11 |         11 |      0.6587 |        0.1452 |      0.1333 |        0.5131 |   5.64 |       36.4 |     2.6919 |   3.5380 |    4 |     0.01462 |       0.01511 |
| mean_reversion v4 | 0.01  | 1.5      | af24ee08 |       10 |         10 |      0.4251 |        0.0897 |      0.0864 |        0.3337 |   3.34 |       10.0 |     2.4787 |   3.1259 |    4 |     0.01602 |       0.02346 |
| mean_reversion v5 | 0.01  | 2        | 66fa85cb |        9 |          9 |      0.5541 |        0.0697 |      0.0678 |        0.4830 |   4.35 |       11.1 |    21.1793 |  51.5892 |    4 |     0.01462 |       0.02973 |
+-------------------+-------+----------+----------+----------+------------+-------------+---------------+-------------+---------------+--------+------------+------------+----------+------+-------------+---------------+
```

**Cobertura perfeita nas oito** (`q10` §2): 0 pendentes, 0 ativos, 0 não-entradas, 0 linhas sem
`R_net`; **K5 passa com 100 %** em todas.

Leitura em três linhas:

1. **O piso compra decisões na proporção que a T3.45 previa**: 17 → 37 (stop 1) e 15 → 33
   (stop 1,5), **+118 % e +120 %**. E compra **dias**: 7 → 11.
2. **A expectância líquida cai ~70 % nas duas colunas**: 0,2998 → 0,0938 e 0,2861 → 0,0855. **O R
   total cai junto** (5,10 → 3,47 e 4,29 → 2,82), o que é decisivo: não é diluição de uma
   expectância por mais operações, é **menos dinheiro no fim do mês**.
3. **O pedágio sobe, como a identidade manda**: 0,1685 → 0,2263 (+34 %) e 0,1075 → 0,1510 (+40 %),
   porque ATR% menor ⇒ risco% menor ⇒ `0,0020/risco%` maior.

### 6.1 O pareamento que o brief dizia ser impossível — e é possível, e é exato (`q11` §2/§3/§4)

O brief supunha "conjunto de entrada diferente, pareamento impossível". **Medido:**

```
+-----------------------+----+---------------+--------+---------+---------+
|         grupo         | n  | exp_liquida_r | soma_r | atr_min | atr_max |
+-----------------------+----+---------------+--------+---------+---------+
| nas duas              | 15 |        0.2861 |   4.29 | 0.00815 | 0.03565 |   <- v8 ∩ v6
| so na v8 (piso 0,006) | 18 |       -0.0817 |  -1.47 | 0.00603 | 0.00775 |
+-----------------------+----+---------------+--------+---------+---------+
(a lista das decisões da v6 que sumiram na v8: **0 linhas**)

+-----------------------+----+---------------+--------+---------+---------+
| nas duas              | 17 |        0.2998 |   5.10 | 0.00815 | 0.03565 |   <- v1 ∩ v2
| so na v1 (piso 0,006) | 20 |       -0.0814 |  -1.63 | 0.00603 | 0.00775 |
+-----------------------+----+---------------+--------+---------+---------+
```

**As 15 decisões da `v6` estão todas na `v8`, mercado a mercado e barra a barra, com o mesmo
`r_net`** (a expectância do grupo "nas duas" é `0.2861`, idêntica à população inteira da `v6`; e
`0.2998` = a população inteira da `v2`). **Zero decisões do pai desapareceram** — a ocupação de slot,
que era o risco óbvio, **não interferiu em 31 dias × 4 mercados**. A variante é **superconjunto
exato** do pai, e o piso é um filtro puro.

Duas consequências que valem mais que a tabela:

- o instrumento certo é o `t342-blocos/blocos.py` **como ele já é** (§7), não uma ferramenta nova;
- **a coorte da `v8` contém a coorte da `v6`**: quem rodar a `v8` prospectivamente mede as duas
  hipóteses com **uma** execução, filtrando por `atr_pct >= 0,008` depois. (Ressalva honesta: isso é
  uma **medição** sobre 4 mercados, não um teorema — no universo prospectivo de ~200 mercados o slot
  da `v8` pode, em princípio, tomar a barra que a `v6` tomaria. Nunca aconteceu nas 11 904 barras.)

### 6.2 O que exatamente o piso mais baixo comprou (`q11` §1) — **a tabela que decide a tarefa**

```
+-------------------+----------+-------------------------------+----+-------------+---------------+---------------+--------+------------+------------+------+-------------+
|      versao       |  coorte  |             faixa             | n  | exp_bruta_r | custo_medio_r | exp_liquida_r | soma_r | acerto_pct | pf_liquido | dias | atr_pct_p50 |
+-------------------+----------+-------------------------------+----+-------------+---------------+---------------+--------+------------+------------+------+-------------+
| mean_reversion v1 | d0f77894 | ja existia (ATR% >= 0,008)    | 17 |      0.4686 |        0.1685 |        0.2998 |   5.10 |       41.2 |     1.7483 |    7 |     0.01051 |
| mean_reversion v1 | d0f77894 | NOVA (ATR% em [0,006; 0,008)) | 20 |      0.1956 |        0.2753 |       -0.0814 |  -1.63 |       40.0 |     0.8630 |    8 |     0.00690 |
| mean_reversion v8 | 8ac79cca | ja existia (ATR% >= 0,008)    | 15 |      0.3953 |        0.1075 |        0.2861 |   4.29 |        6.7 |     2.2820 |    7 |     0.01051 |
| mean_reversion v8 | 8ac79cca | NOVA (ATR% em [0,006; 0,008)) | 18 |      0.1074 |        0.1873 |       -0.0817 |  -1.47 |       27.8 |     0.8388 |    8 |     0.00680 |
+-------------------+----------+-------------------------------+----+-------------+---------------+---------------+--------+------------+------------+------+-------------+
```

**A faixa nova perde nas duas colunas de stop, e perde o mesmo tanto: −0,0814 R e −0,0817 R.**
PF 0,86 e 0,84. Em dinheiro (1 R = 48,33 USDT, a conversão declarada do Lab na [[KB-0076]]):
**−3,94 USDT por decisão nova**, **−71 USDT em 31 dias** para as 18 que a `v8` comprou.

E o mecanismo, decomposto, é **o achado da T3.47 reproduzido num conjunto de decisões que ele nunca
viu**:

| faixa nova | bruto | pedágio | líquido |
|---|---:|---:|---:|
| com `stop_atr = 1` (v1) | +0,1956 | 0,2753 | **−0,0814** |
| com `stop_atr = 1,5` (v8) | +0,1074 | 0,1873 | **−0,0817** |
| **diferença** | **−0,0882** | **−0,0880** | **−0,0003** |

O stop largo cortou o pedágio da faixa nova por **1,47** (a identidade prevê 1,5) e **devolveu no
bruto 0,0882 R contra 0,0880 R economizados**. **A economia sobrevivente é 0,3 milésimo de R** —
zero, para qualquer instrumento que a gente tenha. Alargar o stop **não** paga o pedágio das barras
de ATR% baixo: só troca a unidade em que a mesma perda é medida.

### 6.3 Onde caem as decisões novas (`q14` §1) — **nos dias que o piso escondia**

```
+------------+------+-------+------+-------+------+-------+------+-------+
|    dia     | n_v2 | r_v2  | n_v1 | r_v1  | n_v6 | r_v6  | n_v8 | r_v8  |
+------------+------+-------+------+-------+------+-------+------+-------+
| 2026-08-20 |    1 |  1.68 |    5 |  4.98 |    1 |  1.35 |    5 |  4.98 |
| 2026-08-21 |    5 |  4.27 |    6 |  6.40 |    4 |  2.51 |    5 |  4.38 |
| 2026-08-22 |    6 |  0.55 |    6 |  0.55 |    6 | -0.60 |    6 | -0.60 |
| 2026-08-23 |    1 |  1.22 |    1 |  1.22 |    1 |  1.31 |    1 |  1.31 |
| 2026-08-24 |    0 |       |    3 |  0.26 |    0 |       |    2 | -0.72 |   <- dia que só existe com piso 0,006
| 2026-08-25 |    2 | -2.29 |    4 | -4.62 |    1 | -1.09 |    3 | -3.32 |
| 2026-08-27 |    1 |  0.86 |    3 |  1.02 |    1 |  0.14 |    3 |  1.80 |
| 2026-08-28 |    0 |       |    2 | -2.43 |    0 |       |    2 | -2.28 |   <- idem
| 2026-09-03 |    0 |       |    3 | -3.49 |    0 |       |    3 | -3.02 |   <- idem
| 2026-09-05 |    1 | -1.18 |    1 | -1.18 |    1 |  0.67 |    1 |  0.67 |
| 2026-09-06 |    0 |       |    3 |  0.78 |    0 |       |    2 | -0.38 |   <- idem
+------------+------+-------+------+-------+------+-------+------+-------+
```

**Quatro dias existem só com o piso baixo (08-24, 08-28, 09-03, 09-06) e os quatro são negativos na
`v8`** (−0,72, −2,28, −3,02, −0,38 = **−6,40 R**). Na `v1` três dos quatro são negativos (−2,43 e
−3,49 contra +0,26 e +0,78 = **−4,88 R**). **O piso de ATR% da `mean_reversion` estava funcionando
como filtro de regime, e o que ele filtrava eram dias ruins** — literalmente a suspeita que a T3.42
registrou sobre a `v3` ("11 decisões em 4 dias, filtro de regime disfarçado"), agora com o sinal
invertido e com dado.

### 6.4 Concentração por mercado (`q14` §2) — **K6 não dispara em nenhuma**

```
| mean_reversion v8 | DOGEUSDT 11 (33,3 %) | XRPUSDT 10 (30,3 %) | SOLUSDT 7 (21,2 %) | ETHUSDT 5 (15,2 %) |
| mean_reversion v1 | DOGEUSDT 12 (32,4 %) | XRPUSDT 11 (29,7 %) | SOLUSDT 8 (21,6 %) | ETHUSDT 6 (16,2 %) |
| mean_reversion v6 | XRPUSDT   6 (40,0 %) | DOGEUSDT 4 (26,7 %) | SOLUSDT 3 (20,0 %) | ETHUSDT 2 (13,3 %) |
| mean_reversion v2 | XRPUSDT   7 (41,2 %) | SOLUSDT  4 (23,5 %) | DOGEUSDT 4 (23,5 %) | ETHUSDT 2 (11,8 %) |
```

O piso baixo **melhora** a distribuição: o maior mercado sai de 40–41 % para 33 %.

### 6.5 Motivos de saída (`q10` §5) — o horizonte deixa de dominar

```
| mean_reversion v6 | expired 12 (80,0 %) +0.4252 | stop 2 (13,3 %) -1.0610 | target 1 (6,7 %)  +1.3107 |
| mean_reversion v8 | expired 18 (54,5 %) +0.2821 | stop 9 (27,3 %) -1.1130 | target 6 (18,2 %) +1.2933 |
| mean_reversion v2 | target  7 (41,2 %) +1.3028 | stop 6 (35,3 %) -1.1352 | expired 4 (23,5 %) +0.6970 |
| mean_reversion v1 | stop   16 (43,2 %) -1.1682 | target 15 (40,5 %) +1.2732 | expired 6 (16,2 %) +0.5104 |
```

A `v6` era 80 % horizonte (o vício que a T3.47 apontou); a `v8` cai para 54,5 % e **a taxa de acerto
sobe de 6,7 % para 18,2 %**. A `mean_reversion_v1` **não tem invalidação** (0 em todas as coortes),
então o livro tem só três modos de morrer.

---

## 7. IC 95 % POR BLOCO DE DIA (`t342-blocos/blocos.py`, **sem uma linha alterada**)

A ferramenta é a da T3.42, conferida byte a byte contra o `HEAD` antes de rodar, com os seis testes
sintéticos dela passando:

```
$ git -C C:/dev/project-hunter status --porcelain -- .claude/state/exp-drafts/t342-blocos/
(vazio)
$ sha256sum .claude/state/exp-drafts/t342-blocos/blocos.py
b2946bca6b72a1ee6d0e339531e4dbce98f884020d14100552ce76ab543f0c92
$ git show HEAD:.claude/state/exp-drafts/t342-blocos/blocos.py | sha256sum
b2946bca6b72a1ee6d0e339531e4dbce98f884020d14100552ce76ab543f0c92
$ cd .claude/state/exp-drafts/t342-blocos && uv run --project C:/dev/project-hunter pytest test_blocos.py -q -p no:cacheprovider
......                                                                   [100%]
6 passed in 1.63s
```

```
$ uv run python .claude/state/exp-drafts/t342-blocos/blocos.py .claude/state/exp-drafts/t347b-dumps/v8-piso0006-stop15.csv
piso 0.008 | dias 11 | n_pai 33 | n_var 15 | exp_pai +0.0855 | exp_var +0.2861 | delta +0.2006 | IC95 [-0.1032; +0.8083] | reamostragens 9999
piso 0.010 | dias 11 | n_pai 33 | n_var 10 | exp_pai +0.0855 | exp_var +0.3337 | delta +0.2482 | IC95 [-0.1327; +1.5808] | reamostragens 9925

$ uv run python .claude/state/exp-drafts/t342-blocos/blocos.py .claude/state/exp-drafts/t347b-dumps/v1-piso0006-stop10.csv
piso 0.008 | dias 11 | n_pai 37 | n_var 17 | exp_pai +0.0938 | exp_var +0.2998 | delta +0.2060 | IC95 [-0.1089; +0.7276] | reamostragens 9999
piso 0.010 | dias 11 | n_pai 37 | n_var 11 | exp_pai +0.0938 | exp_var +0.5131 | delta +0.4193 | IC95 [-0.0072; +1.7829] | reamostragens 9925
```

**Leia os rótulos com cuidado, porque a direção do contraste inverteu em relação à T3.42.** Ali a
variante era o **subconjunto** (piso mais alto) e o pai era o conjunto todo; aqui **a minha variante
é o conjunto todo** (piso 0,006) e o pai é o subconjunto (piso 0,008). Então, na saída acima,
`n_pai`/`exp_pai` é a **minha variante** e `n_var`/`exp_var` é o **pai**. Traduzindo para o estimando
do brief (variante − pai):

| contraste | Δ (variante − pai) | IC 95 % por bloco de dia | contém zero? |
|---|---:|---|---|
| `v8` (0,006/1,5) − `v6` (0,008/1,5) | **−0,2006 R** | **[−0,8083; +0,1032]** | **sim** |
| `v8` (0,006/1,5) − `v4` (0,010/1,5) | −0,2482 R | [−1,5808; +0,1327] | sim |
| `v1` (0,006/1,0) − `v2` (0,008/1,0) | **−0,2060 R** | **[−0,7276; +0,1089]** | **sim** |
| `v1` (0,006/1,0) − `v3` (0,010/1,0) | −0,4193 R | [−1,7829; +0,0072] | sim, **por 0,007** |

Três leituras:

1. **Todos os quatro intervalos contêm zero.** Com 11 dias de bloco, nada aqui é estatisticamente
   distinguível — o mesmo veredito que a T3.42, a T3.40 e a T3.47 deram nos seus eixos. **Nenhum
   número desta nota decide ativação sozinho** ([[KB-0010]]).
2. **Mas os quatro pontos estimados são negativos, e o mais estreito quase exclui zero pelo lado
   errado.** Quando quatro contrastes pré-declarados apontam todos para o mesmo lado, o conjunto
   vale mais do que cada um: **baixar o piso piora a expectância**, e o que o IC diz é "com 11 dias
   eu não consigo cravar o tamanho", não "pode ser que melhore".
3. `exp_var` do piso 0,008 sobre o dump da `v8` dá exatamente **+0,2861** com **n = 15** — a
   população inteira da `v6` — e o piso 0,010 dá **+0,3337** com **n = 10** — a população inteira da
   `v4`. **A escada `v8 ⊃ v6 ⊃ v4` é uma população só, filtrada por piso**, conferida por dois
   caminhos independentes (o SQL do `q11` e o bootstrap).

---

## 8. AS PASSADAS DE ESTRESSE (`replay.stress`, `READ ONLY`) — **K1 sobrevive nas duas, pela primeira vez na família**

### `mean_reversion v8` (piso 0,006 + stop 1,5) — `as_of 2026-09-08T23:46:42,854309Z` = **20:46:42**, 33 entradas congeladas

```
| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base` | reprecificacao | 33 | 0.0855 | 1.2262 | — | — |
| `custos_x2` | reprecificacao | 33 | -0.0628 | 0.8519 | -0.1482 | [-0.1824, -0.1094] |
| `stop_x0.75` | reprecificacao | 33 | -0.0017 | 0.9968 | -0.0871 | [-0.3432, +0.0888] |
| `stop_x1.25` | reprecificacao | 33 | 0.1121 | 1.4173 | 0.0267 | [-0.1018, +0.2080] |
| `alvo_x0.75` | reprecificacao | 33 | 0.0649 | 1.1719 | -0.0205 | [-0.1078, +0.0550] |
| `alvo_x1.25` | reprecificacao | 33 | 0.1259 | 1.3331 | 0.0404 | [+0.0082, +0.0788] |
| `entrada_mais_1_barra` | reprecificacao | 33 | 0.0656 | 1.1740 | -0.0199 | [-0.0631, +0.0245] |
| `sem_binance:DOGEUSDT` | recorte | 22 | 0.1096 | 1.2787 | — | — |
| `sem_binance:ETHUSDT` | recorte | 28 | -0.0206 | 0.9526 | — | — |
| `sem_binance:SOLUSDT` | recorte | 26 | 0.1144 | 1.3267 | — | — |
| `sem_binance:XRPUSDT` | recorte | 23 | 0.1588 | 1.4876 | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 27 | 0.2056 | 1.6170 | — | — |
| `2a_metade_apos_2026-08-28` | recorte |  6 | -0.4551 | 0.2134 | — | — |

**Veredito:** frágil a custos
- frágil a custos: custos_x2 → expectancy -0.06277958204798706799377060803 (n=33)
- frágil a parâmetros: stop_x0.75 → expectancy -0.001686145349484983948073442370 (n=33)
- dependente de um mercado: sem_binance:ETHUSDT → expectancy -0.02058493079443531037027443125 (n=28)
- dependente de metade: 2a_metade_apos_2026-08-28 → expectancy -0.4551387677527970539895730703 (n=6)
```

### `mean_reversion v1` (piso 0,006 + stop 1,0 — a "v9" por identidade) — `as_of 23:47:02,466644Z` = **20:47:02**, 37 entradas

```
| `base` | reprecificacao | 37 | 0.0938 | 1.1856 | — | — |
| `custos_x2` | reprecificacao | 37 | -0.1213 | 0.7878 | -0.2150 | [-0.2615, -0.1597] |
| `stop_x0.75` | reprecificacao | 37 | 0.0812 | 1.1289 | -0.0126 | [-0.1962, +0.1236] |
| `stop_x1.25` | reprecificacao | 37 | 0.1272 | 1.3244 | 0.0335 | [-0.0994, +0.2442] |
| `alvo_x0.75` | reprecificacao | 37 | 0.0438 | 1.0925 | -0.0500 | [-0.2122, +0.1346] |
| `alvo_x1.25` | reprecificacao | 37 | 0.1012 | 1.1881 | 0.0074 | [-0.2255, +0.1723] |
| `entrada_mais_1_barra` | reprecificacao | 37 | 0.0977 | 1.1931 | 0.0039 | [-0.0670, +0.1006] |
| `sem_binance:DOGEUSDT` | recorte | 25 | 0.1833 | 1.3935 | — | — |
| `sem_binance:ETHUSDT` | recorte | 31 | 0.0706 | 1.1350 | — | — |
| `sem_binance:SOLUSDT` | recorte | 29 | 0.0234 | 1.0446 | — | — |
| `sem_binance:XRPUSDT` | recorte | 26 | 0.1138 | 1.2270 | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 30 | 0.2456 | 1.5734 | — | — |
| `2a_metade_apos_2026-08-28` | recorte |  7 | -0.5568 | 0.3331 | — | — |

**Veredito:** frágil a custos
- frágil a custos: custos_x2 → expectancy -0.1212810318488431088962096740 (n=37)
- dependente de metade: 2a_metade_apos_2026-08-28 → expectancy -0.5567894557157569318179997923 (n=7)
```

Três coisas que estas duas passadas dizem e que nenhuma outra medição desta nota diz:

1. **Custo dobrado vira as duas negativas** (−0,0628 e −0,1213), enquanto a `v6` com piso 0,008
   **continuava positiva** (+0,1716, T3.47 §10). **O piso de ATR% era a margem de segurança de custo
   da versão**, e baixá-lo a consome. O eixo do stop largo cumpre o que promete aqui também — o Δ de
   `custos_x2` cai de **−0,2150** (stop 1,0) para **−0,1482** (stop 1,5), ÷1,45, quase o 1/k da
   identidade — mas a base cai junto e o resultado final é negativo nas duas.
2. **A `v8` acumula quatro bandeiras** (custo, parâmetro, um mercado, uma metade) contra duas da
   `v1`. Ser mais barata não a tornou mais robusta.
3. **A segunda metade da janela afunda as duas** (−0,4551 com n=6 e −0,5568 com n=7): o mesmo corte
   por metades que reprovou `momentum v6`/`v7`/`v8` na T3.47. Isso **não é** propriedade do piso; é
   propriedade da janela, e é por isso que o EXP-0019 congela o corte por metade como C7.

---

## 9. O TETO DE PEDÁGIO DO BRIEF, CONFERIDO (`q15`)

O brief declarou `0,0020/(1,5 × 0,006) = 0,222 R` como **teto** de pedágio da `v8`. Medido:

```
+----------+------------------+----+--------------------+---------------+-----------------+-----------------------+---------------+
|  coorte  | teto_declarado_r | n  | pedagio_max_medido | acima_do_teto | stop_atr_ef_min | atr_pct_min_observado | risco_pct_min |
+----------+------------------+----+--------------------+---------------+-----------------+-----------------------+---------------+
| 8ac79cca |           0.2222 | 33 |             0.2632 |             2 |          1.1136 |               0.00603 |       0.00766 |
| d0f77894 |           0.3333 | 37 |             0.4435 |             2 |          0.6063 |               0.00603 |       0.00453 |
+----------+------------------+----+--------------------+---------------+-----------------+-----------------------+---------------+
```

**O teto foi furado em 2 das 33 decisões (máximo 0,2632 R contra 0,222 previstos), e o motivo é o
mesmo CONCERN 4 da T3.47:** o `stop_atr` **efetivo** (risco inicial ÷ (ATR% × preço)) vai de
**1,1136** a 1,9149 numa versão que declara 1,5, porque o risco é `entrada − stop` e a entrada anda
entre o fechamento da decisão e a abertura da barra seguinte. **"Teto de pedágio" continua sendo
média, não garantia** — agora medido também no eixo do piso. A identidade em si continua exata: erro
máximo **0,00198 R** em 33 decisões (`q10` §3) e **0,00231 R** em 37.

### C5 — a banda de stop do `paper_v1` (`q10` §4 e `q15` §2)

```
+-------------------+----------+----+---------------------+----------------------+--------------+
|      versao       |  coorte  | n  | acima_do_teto_paper | abaixo_do_piso_paper | pct_recusado |
+-------------------+----------+----+---------------------+----------------------+--------------+
| mean_reversion v1 | d0f77894 | 37 |                   0 |                    0 |          0.0 |
| mean_reversion v2 | d570b19a | 17 |                   0 |                    0 |          0.0 |
| mean_reversion v3 | f4af4ffe | 11 |                   0 |                    0 |          0.0 |
| mean_reversion v8 | 8ac79cca | 33 |                   3 |                    0 |          9.1 |
| mean_reversion v6 | 9d99748b | 15 |                   3 |                    0 |         20.0 |
| mean_reversion v7 | 264b227f | 14 |                   4 |                    0 |         28.6 |
| mean_reversion v4 | af24ee08 | 10 |                   3 |                    0 |         30.0 |
| mean_reversion v5 | 66fa85cb |  9 |                   4 |                    0 |         44.4 |
+-------------------+----------+----+---------------------+----------------------+--------------+

por faixa de ATR% dentro da v8:
| ja existia (>= 0,008) | 15 | acima do teto: 3 | risco%_p50 0,01631 |
| NOVA [0,006; 0,008)   | 18 | acima do teto: 0 | risco%_p50 0,01090 |
```

**A única boa notícia da faixa nova:** ela **não** agrava o C5. As três decisões que estouram o teto
de stop do `paper_v1` (> 3 % do preço, `packages/risk-core/hunter_risk/limits.py:151-152`) são
exatamente as três da `v6`; as 18 novas têm stop pequeno porque o ATR% é pequeno. **O piso baixo e o
stop largo puxam o C5 em direções opostas** — de 20 % para 9,1 % —, e é um argumento real a favor da
`v8` numa eventual conversa de `--paper-line`. É o único.

---

## 10. VEREDITO POR VARIANTE

Régua: `descartar` / `manter em pesquisa` / `candidata a prospectivo`.

### D1 — `mean_reversion v8` (piso 0,006 + stop 1,5): **manter em pesquisa; NÃO promover pelo mérito, e sim pela mensurabilidade**

| critério | valor | dispara? |
|---|---|---|
| Δ vs pai (`v6`) | **−0,2006 R** | **sim, e é grande** |
| IC 95 % por bloco de dia exclui zero | [−0,8083; +0,1032] | não exclui |
| as decisões novas rendem | **−0,0817 R** cada (18 delas) | **sim** |
| `PF_net <= 0,80` | 1,2262 | não |
| `expectancy_net <= a do pai` | +0,0855 vs +0,2861 | **sim** |
| estresse | **frágil a custos** + 3 bandeiras | **sim** |
| K1 (< 20 decisões) | **33** | **não — a primeira `mean_reversion` a passar** |
| K5 (cobertura `R_net` < 70 %) | 100 % | não |
| K6 (>= 60 % num mercado) | 33,3 % | não |

O que sustenta manter: é a **única** versão da família com população que a régua consegue julgar em
30 dias; ela **contém** a `v6` exatamente, então uma execução prospectiva mede as duas hipóteses; e
reduz o C5 de 20 % para 9,1 %. O que não sustenta promover, e pesa mais: **as decisões que ela
acrescenta perdem dinheiro**, o `custos_x2` a vira negativa (o pai não virava) e o ponto estimado do
contraste é o pior desta série de tarefas.

### D2 — `mean_reversion v1` (piso 0,006 + stop 1,0): **já existia; agora tem veredito — manter em pesquisa**

Não é variante nova, é a avó da linhagem, e esta tarefa a mediu contra a filha pela primeira vez com
o instrumento certo: **Δ −0,2060 R**, faixa nova a **−0,0814 R**, estresse **frágil a custos**. É a
prova independente de que o efeito do piso **não** depende da largura do stop.

### O que isso faz com o veredito da T3.47 sobre a `mean_reversion v6`

A T3.47 chamou a `v6` de "melhor candidata das seis, mas K1 dispara (15 decisões)" e propôs baixar o
piso justamente para resolver o K1. **A proposta foi executada e a resposta é não.** O K1 da `v6`
**não** é piso mal calibrado: é **ausência de população boa**. Baixar o piso resolve o sintoma (n) e
destrói o que se queria medir (a vantagem). A leitura correta do K1 da `v6` volta a ser a da régua
original: **esperar mais meses**, não afrouxar o porteiro.

---

## 11. RESPOSTA AO EVERTON (dez linhas)

1. **Baixar o piso de volatilidade compra decisões — e todas as que ele compra são perdedoras.** Com
   o piso em 0,6 % de ATR em vez de 0,8 %, a `mean_reversion` sai de 15 para 33 decisões no mês.
2. As **18 decisões novas** rendem **−0,08 R cada uma** (−3,94 USDT), somando **−1,47 R = −71 USDT**
   em 31 dias. A expectância cai de **+0,286 R para +0,086 R** e o R total do mês, de **4,29 para
   2,82**.
3. **Testei nas duas larguras de stop e deu o mesmo número:** −0,0817 R com stop 1,5 ATR e
   −0,0814 R com stop 1,0. Não é coincidência: é a conta da semana passada de novo — o stop largo
   divide o pedágio por 1,5 e devolve exatamente isso no bruto.
4. **O que o piso escondia não eram decisões: eram dias.** Dos quatro dias que só existem com o piso
   baixo (24 e 28 de agosto, 3 e 6 de setembro), **os quatro são negativos**. O piso funcionava como
   filtro de regime sem que isso estivesse escrito em lugar nenhum.
5. **Custo é o ponto de ruptura.** Com o piso 0,008 a versão aguentava o custo dobrado e continuava
   positiva (+0,17 R); com o piso 0,006 ela vira negativa (−0,06 R). **O piso era a margem de
   segurança de custo — e essa margem é a coisa mais valiosa que a família tinha.**
6. **Limpei o roster, como pedido:** `momentum v7`, `mean_reversion v4` e `v5` foram aposentadas às
   **20:34 de hoje**, com o veredito da T3.47 escrito no registro. **Dezesseis versões ativas viraram
   catorze** — a tarefa **devolveu** carga em vez de somar.
7. Uma das duas variantes que o brief pedia **não precisou ser criada**: "piso 0,006 e nada mais" é,
   parâmetro por parâmetro, a `mean_reversion v1`, que já existia e já tinha sido replayada no mesmo
   protocolo. O script recusou sozinho e economizou uma execução e uma versão no Lab.
8. **Se for para rodar uma só prospectivamente agora, é a `mean_reversion v8`** — não porque seja a
   melhor, mas porque é a **única que dá para julgar**: 33 decisões passam a régua de amostra, e a
   coorte dela **contém** a da `v6` (medido decisão a decisão), então uma execução responde as duas
   perguntas. Ela já está no Lab desde as **20:37** de hoje.
9. **Se for para acreditar em alguma, continua sendo a `mean_reversion v6`** (piso 0,008, stop 1,5):
   +0,286 R por operação, PF 2,28, positiva com custo dobrado — e 15 decisões por mês, que é o preço
   honesto dela. **O K1 dela não se conserta baixando o piso; conserta-se com tempo.**
10. **A geometria acabou.** Piso de ATR% (T3.42 e esta), alvo (T3.40) e stop (T3.47): três eixos,
    três respostas iguais — mexem no pedágio, nenhum fabrica vantagem. O que falta medir não é mais
    uma variante: é **o custo real contra o livro da corretora** (a hipótese de 20 bps sustenta tudo
    isto e nunca foi verificada) e **a vantagem na entrada**.

---

## 12. TESTES

Nenhum código de produção foi escrito nem alterado nesta tarefa. Rodei (a) as provas de
não-antecipação que o meu contrato exige — incluindo a que prova que **uma vela não-final não move o
número** e a que prova que **uma estratégia trapaceira é pega** —, (b) o que governa
derivação/ativação/aposentadoria e a tabela de faixas, e (c) os testes da ferramenta de bootstrap
reusada.

```
$ uv run pytest packages/core/tests/unit/strategies/test_no_lookahead.py \
      packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
      packages/core/tests/unit/strategies/test_constraints.py -q -p no:cacheprovider
........................................................................ [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
190 passed in 31.24s

$ uv run pytest services/strategy-worker/tests/test_replay_lookahead.py \
      services/strategy-worker/tests/test_deprecate.py -q -p no:cacheprovider
...................                                                      [100%]
19 passed in 93.05s (0:01:33)

$ uv run pytest services/strategy-worker/tests/test_derive_variant.py \
      services/strategy-worker/tests/test_activate_derived_guard.py \
      infra/scripts/tests/test_derive_variant_lineage.py -q -p no:cacheprovider
................................................                         [100%]
48 passed in 71.33s (0:01:11)

$ cd .claude/state/exp-drafts/t342-blocos && uv run --project C:/dev/project-hunter pytest test_blocos.py -q -p no:cacheprovider
......                                                                   [100%]
6 passed in 1.63s
```

Os que sustentam nominalmente as regras desta tarefa:
`test_mean_reversion_ignores_the_future_the_forming_candle_and_a_mutated_future`,
`test_the_forming_hour_never_reaches_the_trend_gate`,
`test_a_cheating_strategy_is_caught_by_the_context` (o "trapaceiro" deliberado do contrato),
`TestReplayLookahead::test_a_candle_that_is_not_final_changes_nothing_either`,
`::test_rewriting_every_later_candle_changes_nothing` e
`::test_a_cut_moved_into_the_future_is_detected`.
**263 testes, 0 falhas.**

---

## CONCERNS

1. **Escrevi dois CSV fora do escrito de escrita do brief.** O brief autorizava
   `.claude/state/notes-T3.47b.md`, `.claude/state/exp-drafts/EXP-0019-piso-atr.md` e
   `infra/scripts/sql/research/2026-09-09-t347b-*.sql`. Os dumps do bootstrap foram para
   `.claude/state/exp-drafts/t347b-dumps/` (dois arquivos, 33 e 37 linhas). É fora de código de
   produção e é o insumo literal de `blocos.py`, mas **é um desvio e está declarado** — o mesmo
   CONCERN 1 da T3.47, agora sem a agravante de código novo.
2. **A "v9" do brief não existe e eu não a substituí por outra coisa.** Poderia ter derivado, por
   exemplo, um piso 0,004 para "salvar o braço", e não derivei: seria uma hipótese que ninguém
   pré-registrou, num roster que eu acabara de limpar, e a multiplicidade é justamente o que a
   [[KB-0010]] cobra. O braço "só o piso" foi respondido pela `v1`, que é a mesma coisa, com dado
   melhor (37 decisões) e custo zero. (A faixa `[0,004; 0,006)` tem **40 barras** esperando, se
   alguém quiser pré-registrar esse passo — está em C8 do EXP-0019.)
3. **Reescrevi o `changelog` das três aposentadas preservando o prefixo de linhagem, e essa decisão
   é minha.** `--deprecate` faz `UPDATE … changelog = :changelog` e a linhagem analisável de uma
   variante mora nessa coluna (`derive_variant.py:88`, lida por `obsidian_strategy_pages.py`).
   Aposentar com o texto do veredito puro — que é o que os exemplos da `docs/ACTIVATION.md` §7b
   fazem — **apagaria `derived_from` e `overrides` da linha**. Preservei o prefixo verbatim e
   acrescentei o veredito. **Isto é um efeito colateral do `--deprecate` que a documentação não
   menciona**, e a correção estrutural (não deixar o `--deprecate` reescrever o prefixo, ou guardar
   a linhagem fora do `changelog`) é trabalho de quem cuida do script, não meu.
4. **Eu li o código errado antes de aposentar e quase declarei um custo que não existe.**
   `_advance_open_tracking` mora dentro de `decide.evaluate_slot`, que só roda para versões do
   roster; a conclusão óbvia (e errada) é que aposentar congela os acompanhamentos abertos. Existe
   uma segunda via — `consumer.sweep_outcomes` → `tracking_repo.load_open_trackings` — que não
   filtra por versão. **Só soube porque medi depois** (§2.5). Registro porque a próxima pessoa que
   ler `evaluate_slot` vai tropeçar no mesmo lugar.
5. **`atr_pct_max = 0,05` nunca recusou uma barra** nestes quatro mercados, nas três variantes
   (`acima do teto = 0` em 219 avaliações do porteiro). Metade do parâmetro é letra morta, e nenhuma
   das quatro tarefas do eixo tinha medido isso.
6. **O enquadramento da T3.47 §15 estava mais forte do que o dado.** "O piso recusa 67 % a 89 % das
   barras destes mercados" é verdade sobre a **distribuição de ATR% do universo** (T3.45), mas o
   piso é o **último** portão e recusa **189 de 11 904 barras (1,6 %)**; quem recusa 91 % do livro é
   `not_stretched` + `no_uptrend_1h`. A proposta que gerou esta tarefa misturou as duas coisas. A
   conclusão prática não muda (baixar o piso **dobra** a população), mas a frase muda.
7. **A janela é a mesma que gerou a hipótese, de novo.** Os contrastes são REPLAY sobre
   2026-08-08…09-08, e a ideia do piso nasceu do diagnóstico desta mesma série. As coortes
   prospectivas (`v8` desde hoje 20:37) é que decidem, em 2026-10-08.
8. **A hipótese de custo continua declarada, não medida** (2 bps de spread + 5 de slippage/lado +
   4 de taxa/lado = 20 bps ida e volta). **Todo** este eixo é linear nela: se o custo real for
   metade, a faixa nova `[0,006; 0,008)` passa de −0,08 R para perto de **+0,06 R** e o veredito
   desta tarefa **inverte**. É a coisa mais importante escrita nesta nota, e continua sem dono desde
   a [[KB-0076]].
9. **`stop_atr` efetivo furou o teto declarado em 2 de 33 decisões** (§9). Repito o CONCERN 4 da
   T3.47 porque agora ele aparece também no eixo do piso, e porque a frase "teto de pedágio
   0,222 R" está no changelog da `v8`.
10. **Changelogs sem acento**, decisão minha para não arriscar corrupção de UTF-8 no caminho
    Windows → ssh → docker (a mesma da T3.42 e da T3.47). "×1,5" virou "x1,5", "§13" virou
    "secao 13", "%" virou "por cento" onde o texto atravessava aspas.
11. **`EXP-0019` era a vaga livre às 2026-09-08T23:55Z.** O rascunho está em
    `.claude/state/exp-drafts/`, **não** em `obsidian/**` (fora do meu escopo). Se outra tarefa tomar
    o número antes da Sexta-feira arquivar, renumerar.
12. **O replay herda o universo de hoje**, não o de agosto (`PIPELINE` §6c). Vale igualmente para as
    oito coortes — o aninhamento não fica enviesado —, mas nenhuma descreve o universo real da
    janela.
13. **Outra tarefa redeployou `hunter-api-1` e `hunter-web-1` no fim da minha janela** (~00:05 e
    ~00:09Z, para `69ae37c` e `95bc2f0`) e commitou no `main` durante a tarefa. **Nada disso é meu e
    nada disso toca os meus números** — o último ato meu foi às 23:47Z e o `hunter-strategy-worker-1`,
    que rodou os dois replays e as duas passadas de estresse, continua em `2e39774` sem ter sido
    tocado. Registro porque o `docker ps` de quem ler esta nota depois **não** vai bater com o §1.

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** o CONCERN 3 (reescrevi o `changelog` de três linhas congeladas preservando o
  prefixo, por decisão própria) e o CONCERN 1. Os dois são julgamento, não aritmética.
- **risk-engine-guardian:** a `v8` é `research_only`, sem linha em `agents`, `shadow_outbox` zerada
  para a coorte de replay. A novidade **boa** para você é o §9: a faixa de ATR% baixo **reduz** o C5
  (20 % → 9,1 % das decisões acima do teto de stop do `paper_v1`). A novidade **ruim** é o §8: com o
  piso 0,006 a versão **não sobrevive ao custo dobrado**, e com 0,008 sobrevivia.
- **Sexta-feira:** arquivar `EXP-0019`; ligar do `Strategy Backlog` e do `Experiments Index`;
  acrescentar no `Registro de Tentativas` **uma** linha de ativação (`mean_reversion v8`,
  2026-09-08T23:37:33,252307Z = **20:37:33** Brasília), **três** linhas de aposentadoria
  (23:34:42,370162Z / 23:34:57,087557Z / 23:34:59,064478Z = **20:34:42 / 20:34:57 / 20:34:59**) e
  **uma** linha de recusa (`mean_reversion v1 já tem exatamente esses parâmetros`, 23:35:18,231279Z
  = **20:35:18**) — uma recusa registrada vale tanto quanto uma execução, e esta economizou uma.
- **Everton:** a decisão que este trabalho põe na mesa é **parar de mexer na geometria**. Três eixos
  testados, três respostas iguais. O número honesto do dia é que **as decisões que faltavam custam
  −0,08 R cada uma**. A próxima execução deveria ser o custo real contra o livro (CONCERN 8), porque
  é a única medição capaz de **inverter** qualquer um dos três vereditos.

---

## ADENDO — o estado da árvore ao fechar (2026-09-09T00:11Z = **2026-09-08 21:11** Brasília)

```
$ git -C C:/dev/project-hunter status --porcelain -- infra/scripts/sql/research .claude/state/exp-drafts .claude/state/notes-T3.47b.md
?? .claude/state/exp-drafts/EXP-0019-piso-atr.md
?? .claude/state/exp-drafts/t347b-dumps/
?? .claude/state/notes-T3.47b.md
?? infra/scripts/sql/research/2026-09-09-t347b-q00-catalogo-antes.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q01-slots-abertos.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q02-v9-e-v1.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q10-populacoes.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q11-faixa-nova.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q12-dump-blocos.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q13-recibos-iso-roster.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q14-dias-e-mercados.sql
?? infra/scripts/sql/research/2026-09-09-t347b-q15-teto-de-pedagio.sql
```

**Tudo meu está `??` — nada commitado, nada indexado.**

**O `main` andou durante a tarefa e a VPS foi redeployada — as duas coisas por outras tarefas, e as
duas coisas DEPOIS do meu último ato.** O brief nasceu em `1c72134` e o `HEAD` da árvore estava em
**`95bc2f0`** quando fechei (T3.51 + T3.44d/e/f, e o hotfix `69ae37c` da T3.44c no meio).
**Nenhum commit é meu.** Linha do tempo, em UTC:

```
23:29:43  primeira amostra: hunter-api-1 / hunter-web-1 / hunter-strategy-worker-1 em 2e39774
23:34:42–23:34:59  as três aposentadorias        (hunter-api-1 em 2e39774)
23:37:05 / 23:37:33  derivação e ativação da v8  (hunter-api-1 em 2e39774)
23:38:39–23:42:09  os dois replays               (hunter-strategy-worker-1 em 2e39774)
23:46:42 / 23:47:02  as duas passadas de estresse(hunter-strategy-worker-1 em 2e39774)
23:49:17  amostra de fechamento: os três ainda em 2e39774, api /ready = 200
--------  fim de tudo o que eu escrevi  --------
~00:05    hunter-api-1 redeployado para 69ae37c   (outra tarefa)
~00:09    hunter-web-1 redeployado para 95bc2f0   (outra tarefa)
00:10:56  hunter-strategy-worker-1 AINDA em 2e39774, Up 2 hours — nunca foi tocado
```

**As três aposentadorias, a derivação, a ativação, os dois replays e as duas passadas de estresse
rodaram na imagem `2e39774`, publicada, a mesma do começo ao fim** — nada meu rodou em código em
voo, e nada meu foi afetado pelos redeploys, que vieram depois. Última leitura da vigia
(00:10:52Z = **21:10:52** Brasília, 33 min depois da ativação da `v8`): `outbox_lag_s` **0,0**,
`outbox_pending` **0**, `errors` **0**, `open_trackings` 66, `evaluated_bars` 29 704,
`evaluations_by_state {"not_triggered":23065,"triggered":290,"ineligible":78,"unavailable":6271}`,
todos os containers `healthy`.
