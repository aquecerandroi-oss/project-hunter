# notes-T3.91 — EXP-0029 "a discordância BTC × alts como estado": parou na checagem de população

**Data:** 2026-09-12, 04:36 → 04:55 BRT (07:36 → 07:55 UTC). **Owner:** quant-engineer (T3.91).
**Base local:** árvore compartilhada, **nada commitado**. **VPS:** HEAD `/opt/project-hunter` =
`24a1357` (2026-09-12 04:27:09 -03:00), 17 containers `healthy` (workers reiniciados às ~04:30 BRT
pelo deploy da T3.90), nenhum replay em curso, `/tmp/t391*` inexistente.
**Regras seguidas:** nenhum container parado/recriado; nenhum `.env*` tocado; nenhum `git pull` na
VPS; **nenhuma escrita na VPS de nenhum tipo** (todas as leituras SQL em `begin transaction isolation
level repeatable read read only`); nenhum `derive_variant.py`, nenhum `activate_strategy_version.py`,
nenhum replay — porque a checagem de população §2 mandou parar antes; todo comando local em primeiro
plano com `timeout ≤ 290`; nenhum `nohup`, nenhum loop na VPS chegou a ser escrito.

Horários em UTC (Git Bash `date`) com BRT = UTC − 3.

---

## STATUS

**DONE** — a entrega parou onde o brief manda parar: "if A or B is outside its band, STOP after
writing the result in the EXP (status `inviavel-populacao`) and report — do not derive".

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Preencher todo `‹backfill›` da EXP-0029 com SQL somente-leitura + checagem de população §2 | **OK** — §1–§3; **A = 1,48 %** (faixa 10–30 %), **B = 44,85 %** (faixa 20–40 %) → **`inviavel-populacao`**, parar |
| 2 | Derivar/ativar `v20`/`v21` | **NÃO FEITO, por regra** — a checagem §2 falhou nos dois braços; `v19` continua a última |
| 3 | Replay 24 fatias por braço | **NÃO FEITO, por regra** — zero replays, zero `nohup` |
| 4 | Estresse, análise, vereditos, aposentadorias | **Vereditos escritos** (EXP append-only, frontmatter, `mean_reversion.md`, INBOX H-P18 → `testada`, Index, diário 2026-09-12 criado); **nada a aposentar** (nada foi derivado); `obsidian_lint.py` → §6 |
| 5 | Estas notas | **OK** |

**Veredito de uma linha:** a célula pré-registrada A `[−0,10; −0,03)` cobre **124 de 8 352 barras de
15 min (1,48 %) em 9 dias** — 55 delas o próprio 10/09 que motivou H-P18 e **zero** em 07-16 → 08-15 —
e a B `[0; 0,10)` cobre **44,85 %**; a série é estreita (desvio 0,0132, p05 −0,0210) e o corte −0,03 é
percentil ~1,5. Nenhuma variante derivada, nenhum Δ, nenhum IC, nada aposentado.

---

## ARQUIVOS (só os meus desta tarefa; ver §7 para o `git status --porcelain`)

- `obsidian/05-EXPERIMENTS/EXP-0029-dispersao-btc-alts.md` — `‹backfill›` preenchidos (com hora BRT),
  seção "Avaliação de 2026-09-12 — as_of 07:41:13Z" **acrescentada** (a de pré-registro intacta),
  frontmatter (`status: inviavel-populacao`, `result: inconclusivo`, `version`), "Variantes tentadas",
  "Fontes".
- `obsidian/05-EXPERIMENTS/Experiments Index.md` — as duas linhas da EXP-0029.
- `obsidian/03-TRADING/Estrategias/mean_reversion.md` — ligação nova + "Acréscimo de 2026-09-12".
- `obsidian/00-INBOX/Hipoteses-do-plantao.md` — linha H-P18 (2026-09-10) → `testada (EXP-0029 …)`.
- `obsidian/09-OPERATIONS/Diario/2026-09-12.md` — **criado** (não existia; formato do de 11/09).
- `infra/scripts/sql/research/2026-09-12-t391-q01-dispersao-distribuicao.sql`,
  `-q02-dispersao-nas-barras-de-15m.sql`, `-q03-celulas-do-pai.sql` — somente leitura.
- `.claude/state/notes-T3.91.md` — esta nota.

---

## 0. ESTADO INICIAL (07:36–07:38Z = 04:36–04:38 BRT)

```
$ date -u  →  2026-09-12T07:36:18Z
$ ssh hunter-vps 'cd /opt/project-hunter && git rev-parse --short HEAD && git log -1 --format="%h %ci %s"'
24a1357
24a1357 2026-09-12 04:27:09 -0300 Dockerfile.api-workers: copiar services/meme-worker (...)
$ docker ps  → 17 containers, todos Up/healthy (workers "Up 6 minutes", redis 22 h, postgres/caddy 5 dias)
$ ps -eo pid,etime,cmd | grep -E "replay|t391"  → nada
$ ls /tmp/t39* /tmp/exp002*  → nada
```

```
$ psql -At -c "select dispersion_version, horizon_minutes, count(*), count(*) filter (where usable), min(end_time), max(end_time) from market_dispersion group by 1,2;"
dispersion_24h_v1|1440|126907|126907|2026-06-16 00:00:00+00|2026-09-12 07:36:00+00

$ psql -At … strategy_versions (mean_reversion v10, v15..v22):
mean_reversion|v10|active|research_only||2026-09-09 03:22:10.768913+00
mean_reversion|v15|deprecated|research_only|{"regime": {… "allow": ["LOW_VOLATILITY","SIDEWAYS"] …}}|2026-09-10 15:26:45+00
mean_reversion|v16|deprecated|research_only|{"regime": {… "allow": ["SIDEWAYS"] …}}|2026-09-10 15:26:52+00
mean_reversion|v17|deprecated|research_only|{"regime": {… "allow": ["HIGH_VOLATILITY"] …}}|2026-09-10 15:26:59+00
mean_reversion|v18|deprecated|research_only|{"breadth": {"max": "0.60", "min": "0.10", "version": "breadth_v2", "window_m": 5}}|2026-09-11 12:45:49+00
mean_reversion|v19|deprecated|research_only|{"breadth": {"max": "1.00", "min": "0.60", "version": "breadth_v2", "window_m": 5}}|2026-09-11 12:46:02+00
(v20/v21 não existem)
```

**Fato que fixa a janela:** a série começa em **2026-06-16 00:00Z** (não 06-14 como a `breadth_v2`):
126 720 linhas de backfill (88 dias × 1 440, 06-16 → 09-11) + a faixa viva desde 12/09 00:00Z;
**zero inutilizáveis**. A página congelada manda "Janela: ‹backfill› (o início da série) → 2026-09-11,
com a população do pai cortada no mesmo início" → janela **2026-06-16 → 2026-09-11** (87 dias de
barras, 8 352 fechamentos de 15 min). O brief citava as datas da T3.89 (06-14…) "like T3.89"; a página
congelada vence e a diferença fica declarada aqui — irrelevante no fim, porque nada foi replayado.

## 1. q01 — DISTRIBUIÇÃO DA SÉRIE (07:40:21Z = 04:40 BRT; re-rodado 07:43:51Z após corrigir o passo 8)

```
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
    < infra/scripts/sql/research/2026-09-12-t391-q01-dispersao-distribuicao.sql
```

Primeira passada (07:40Z) parou no passo (8) com `ERROR: column "details" does not exist` —
`audit_logs` tem `metadata`/`before`/`after` (`\d audit_logs`); corrigido o SELECT e re-rodado
(07:43:51Z). Passos (1)–(7) idênticos nas duas passadas a menos da faixa viva (+7 minutos).

```
== (1) inventário da série ==
 dispersion_24h_v1 | 1440 | exchanges 1 | linhas 126914 | usaveis 126914 | inutilizaveis 0 | 2026-06-16 00:00:00+00 → 2026-09-12 07:43:00+00 | universo 16..16

== (2) quantis de dispersion (usáveis, série inteira) ==
 n 126914 | media -0.001124 | minimo -0.083542 | p05 -0.021014 | p10 -0.016014 | p25 -0.008182 | p50 -0.001284
 | p75 0.005168 | p90 0.012106 | p95 0.018891 | maximo 0.131334 | desvio 0.013216

== (3) share de MINUTOS usáveis por célula ==
 a_discordancia 1842 (1.4514 %) | b_falseamento 56530 (44.5420 %) | queda_conjunta 68427 (53.9160 %)
 | extrema_neg 0 | acima_010 115 (0.0906 %) | abaixo de -0,03: 1.4514 %

== (4) histograma em degraus de 0,01 ==
 -0.09: 2 | -0.08: 18 | -0.07: 10 | -0.06: 40 | -0.05: 359 | -0.04: 1413 | -0.03: 5569 (4.39 %)
 | -0.02: 18015 (14.19 %) | -0.01: 44843 (35.33 %) | 0.00: 40000 (31.52 %) | 0.01: 10832 (8.53 %)
 | 0.02: 2947 | 0.03: 1770 | 0.04: 494 | 0.05: 232 | 0.06: 138 | 0.07: 50 | 0.08: 27 | 0.09: 40
 | 0.10: 40 | 0.11: 46 | 0.12: 28 | 0.13: 1

== (5) tercis (calibração 2026-06-13..07-31; a série começa em 06-16) ==
 n_calibracao 66240 | de 2026-06-16 00:00:00+00 | ate 2026-07-31 23:59:00+00 | t1 -0.005913 | t2 0.001660

== (6) cobertura por dia == 89 linhas: 06-16 → 09-11 todas 1440/1440, cobertura_min 1.0000, cobertos_min 16;
 12/09 parcial (191 min às 07:40Z). Dias extremos: 08-22 média +0.0453 máx +0.1313; 08-23 mín -0.0835;
 09-10 média -0.0300 mín -0.0490 máx -0.0135 (o dia inteiro em ou perto do braço A).

== (6b) == dias 89 | dias_cobertura_ok 89 | dias_completos 88
== (7) linhas inutilizáveis == (0 rows)
== (8) auditoria == 2026-09-12 07:33:49.487896+00 | system | market_dispersion.backfill | market_dispersion
 | {"tool": "infra/scripts/backfill_dispersion.py", "reason": "EXP-0029 (T3.90): série dispersion_24h_v1, 90 d,
   universo 16, pré-registro antes da derivação", "universe_rule": "monitored_perpetual_min_history_90d",
   "horizon_minutes": 1440, "include_unusable": false, "min_history_days": 90, "referenc…
== (9) as leituras que motivaram H-P18, na série ==
 2026-09-10 19:10:00+00 | btc -0.015185 | mediana -0.050809 | dispersao -0.035624 | share_below 0.9333 | 16 | 1.0
 2026-09-11 11:11:00+00 | btc -0.013273 | mediana -0.040210 | dispersao -0.026937 | share_below 0.7333 | 16 | 1.0
 2026-09-11 12:36:00+00 | btc -0.003312 | mediana -0.018776 | dispersao -0.015464 | share_below 0.6667 | 16 | 1.0
COMMIT
```

## 2. q02 — SHARE NAS BARRAS DE 15 MIN, A CHECAGEM DE POPULAÇÃO §2 (07:40:28Z = 04:40 BRT)

```
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql … -f -" \
    < infra/scripts/sql/research/2026-09-12-t391-q02-dispersao-nas-barras-de-15m.sql

== (1) share por célula nos fechamentos de 15 min (2026-06-16..2026-09-11) ==
 barras_15m 8352 | com_linha_usavel 8352 | a_barras 124 | a_pct 1.4847 | b_barras 3746 | b_pct 44.8515
 | queda_conjunta 4475 (53.5800) | extrema_neg 0 | acima_010 7 (0.0838) | sem_linha_usavel 0 (0.0000)

== (2) por janela de 30 dias ==
 J1 2026-06-16..07-16 (30 d) | 2880 | a 0.1389 % (4)   | b 41.2847 % (1189) | queda 58.5764 | media -0.002237
 J2 2026-07-16..08-15 (30 d) | 2880 | a 0.0000 % (0)   | b 42.6736 % (1229) | queda 57.3264 | media -0.001316
 J3 2026-08-15..09-11 (27 d) | 2592 | a 4.6296 % (120) | b 51.2346 % (1328) | queda 43.8657 | acima_010 0.2701 | media 0.000497

== (3) dias distintos com ao menos uma barra por braço ==
 dias_a 9 | dias_b 75 | dias_total 88
COMMIT
```

Leitura extra (07:44Z, `-c` inline, somente leitura): **os 9 dias de A** e as barras `>= 0,10`:

```
 2026-06-23 | 4  | -0.0327..-0.0311      2026-08-24 | 28 | -0.0517..-0.0301
 2026-08-20 | 1  | -0.0305               2026-08-25 | 9  | -0.0413..-0.0304
 2026-08-21 | 4  | -0.0351..-0.0307      2026-08-26 | 14 | -0.0393..-0.0302
 2026-08-23 | 7  | -0.0771..-0.0406      2026-09-09 | 2  | -0.0374..-0.0343
                                         2026-09-10 | 55 | -0.0471..-0.0305
 >= 0,10: 2026-08-22 | 7 (todas)
```

**Checagem §2, contra a previsão congelada:** A entre 10 % e 30 % → **1,48 %** (fora, 6,7× abaixo do
piso); B entre 20 % e 40 % → **44,85 %** (fora, acima do teto). **PARAR. Não derivar.**

Projeção de n para A: 764 decisões do pai cortado × 1,48 % ≈ 11; a célula só existe em 9 dias, então a
condição 2 (≥ 30 dias distintos) é inatingível mesmo no limite de toda barra decidindo em todo mercado.

## 3. q03 — CÉLULAS DO PAI E TERCIS (07:41:13Z = 04:41 BRT)

```
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql … -v t1=-0.005913 -v t2=0.001660 -f -" \
    < infra/scripts/sql/research/2026-09-12-t391-q03-celulas-do-pai.sql

== (1) as decisões do pai por célula (todas as 798) ==
 1 A [-0,10; -0,03)          |   7 |  2 | -0.0261 |  -0.1826 | 2026-08-24 17:15Z → 2026-08-25 07:00Z
 2 B [0,00; 0,10)            | 414 | 61 |  0.0203 |   8.4233 | 2026-06-16 04:30Z → 2026-09-09 11:00Z
 3 [-0,03; 0,00) (sem braço) | 342 | 69 | -0.0721 | -24.6663 | 2026-06-16 11:30Z → 2026-09-09 20:15Z
 5 >= 0,10 (sem braço)       |   1 |  1 | -1.0203 |  -1.0203 | 2026-08-22 04:45Z
 6 sem linha usável          |  34 |  4 | -0.1737 |  -5.9057 | 2026-06-12 21:00Z → 2026-06-15 23:15Z
 (célula 4, < -0,10: nenhuma decisão)

== (1b) o pai cortado em 2026-06-16 ==
 n 764 | dias 85 | media -0.0228 | soma -17.4459 | 2026-06-16 04:30Z → 2026-09-09 20:15Z

== (2) tercis (t1 -0.005913 / t2 0.001660) sobre as decisões do pai de 2026-08-01 em diante ==
 T1 baixo  [-1; t1) |  77 | 23 dias |  0.1502 | 11.5651
 T2 meio   [t1; t2) |  60 | 21 dias | -0.0468 | -2.8062
 T3 alto   [t2; +1] | 213 | 29 dias |  0.1016 | 21.6383

== (3) K4 do pai (recibo original, 90 d) ==
 replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3 | 12 fatias | 138240 barras | unavailable 1280 | k4_pct 0.9259
COMMIT
```

## 4. O QUE NÃO FOI FEITO, E POR QUÊ

- **Derivação/ativação de `v20`/`v21`:** não feita. Brief §1: "if A or B is outside its band, STOP …
  do not derive". `strategy_versions` continua com `v19` como última da família.
- **Replay (24 fatias), loop `nohup` na VPS, `--explain-ledger`, estresse, `blocos90.py`, semente
  20260913, cláusula de identidade:** nada rodou. Nenhum `/tmp/t391-replay.sh`, nenhum `/tmp/t391.log`.
- **Aposentadorias:** nada a aposentar — nada foi criado.
- **`infra/scripts/sql/research/2026-09-12-t390-*.sql`** citados na página: nunca existiram; a página
  agora aponta para os `t391-q0{1,2,3}`.

## 5. PÁGINAS (04:45–04:52 BRT)

- **EXP-0029** — todos os `‹backfill›` preenchidos (distribuição, shares por célula e por janela, dias
  por braço, tercis com n, células do pai, tercis descritivos, janela do protocolo), cada bloco com a
  hora BRT da leitura; seção **"Avaliação de 2026-09-12 — `as_of = 2026-09-12T07:41:13Z` (04:41 BRT)"**
  acrescentada (previsões pontuadas: 1 forma certa/cauda 10× errada; 2 falsificada nos dois; 3–4 não
  mensuráveis; 5 confirmada 0,00 %); frontmatter `status: inviavel-populacao`, `result: inconclusivo`
  (vocabulário do lint: `inconclusivo|validada|reprovada|nao-iniciado`), `evaluable: 0`, `days: 0`;
  "Variantes tentadas" com `v20`/`v21` **não derivadas**; "Fontes" ampliadas. A seção de pré-registro
  ("Avaliação de 2026-09-12 — pré-registro arquivado…") **não foi tocada**.
- **Experiments Index** — as duas linhas da EXP-0029 (a de "IDs reservados" e a tabela detalhada).
- **mean_reversion.md** — `updated: 2026-09-12`, ligação "portão de dispersão (v10→v20/v21, não
  derivadas)", parágrafo "Acréscimo de 2026-09-12 (T3.91)". Nenhuma linha de versão nova (nada existe).
- **INBOX H-P18** (linha de 2026-09-10) — status `testada ([[EXP-0029…]], 12/09 04:41 BRT): inviável
  por população — …`.
- **Diário 2026-09-12** — criado (não existia às 04:45 BRT), no formato do de 11/09, com veredito,
  medições, decisões (nenhuma humana), §1, "O que espera o Everton", "Saúde", "Relacionadas".

## 6. `obsidian_lint.py` — ver saída colada no fim desta nota (§8).

## 7. `git status --porcelain` — ver §8.

## 8. SAÍDAS FINAIS (07:49Z = 04:49 BRT)

Primeira passada do lint (07:49:03Z) acusou **1 nota órfã** — o diário novo `Diario/2026-09-12.md`,
que nenhuma página referenciava; acrescentei o link em "Relacionadas" da EXP-0029 e re-rodei:

```
$ timeout 290 uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 267 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

As duas ocorrências restantes de `‹backfill›` na EXP-0029 (linhas 22 e 313) são **menções** ao
placeholder — o aviso do cabeçalho e o "Next Action" da seção de pré-registro congelada — não
placeholders por preencher.

```
$ git status --porcelain -- <os meus arquivos>
 M obsidian/00-INBOX/Hipoteses-do-plantao.md
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/05-EXPERIMENTS/EXP-0029-dispersao-btc-alts.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
?? .claude/state/notes-T3.91.md
?? infra/scripts/sql/research/2026-09-12-t391-q01-dispersao-distribuicao.sql
?? infra/scripts/sql/research/2026-09-12-t391-q02-dispersao-nas-barras-de-15m.sql
?? infra/scripts/sql/research/2026-09-12-t391-q03-celulas-do-pai.sql
?? obsidian/09-OPERATIONS/Diario/2026-09-12.md
```

Checagem final na VPS (07:49Z): `strategy_versions` **sem** `v20`/`v21`; `/tmp/t391*` **inexistente**.
Nada commitado.

## 9. CONCERNS HONESTOS

1. **A régua não previa a célula "B fora da faixa por cima".** O pré-registro só nomeia a morte por
   população para A (n < 100); para B (44,85 % contra 20–40 %) apliquei o mesmo STOP do brief e
   registrei que "concordância" é o padrão da série, não um estado. Se o orquestrador entender que B
   mereceria correr sozinho, é decisão dele — mas correr um braço de falseamento sem o braço principal
   não testa a hipótese, e a página diz que "se B aprovar e A não, o que sobra nasce como EXP nova".
2. **A janela do brief (06-14…) e a da página (início da série = 06-16) diferem** — segui a página
   (congelada) e declarei; sem replay, não teve efeito.
3. **`result: inconclusivo`** é a palavra do vocabulário do lint que melhor cabe em "não testável nesta
   história" (a página exige `descartar por população` para o braço, não para a hipótese). O `status`
   é livre e recebeu `inviavel-populacao`, como o brief pediu.
4. **O diário de hoje foi criado por mim**, no formato do de 11/09 e assinado `quant-engineer`; a
   Sexta-feira pode estender, mas o `owner` do frontmatter é meu, não dela.
