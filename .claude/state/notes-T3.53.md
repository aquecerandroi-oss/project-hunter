# notes-T3.53 — o mapa de onde cada versão ganha e perde: 6 187 desfechos cruzados por mercado, hora, dia da semana, regime, pedágio e coorte

**Data:** 2026-09-09 (Brasília, UTC−3; UTC como detalhe). **Owner:** quant-engineer.
**Base:** `main` — árvore compartilhada, **nada commitado**, nada tocado em `apps/`, `services/`,
`packages/`. **VPS estritamente somente leitura**: toda consulta dentro de
`begin transaction isolation level repeatable read read only; … commit;`, entregue pelo stdin de
`psql`. Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado.
**`t342-blocos/blocos.py` e `t347-blocos/blocos_pareado.py` foram reusados sem uma linha alterada**
(o primeiro entra como **oráculo de conferência** do bootstrap novo — teste
`test_mesmo_estimador_do_laco_ingenuo_de_blocos`).

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | População: todo desfecho terminal com `r_multiple`, cruzado com versão, coorte, mercado, `source_bar_close`, regime horário do BTC (`end_time <= source_bar_close`), faixa de pedágio, hora BRT/UTC, dia da semana | **OK** — 6 187 linhas, contagens por versão e por tamanho de célula coladas (§2, §3) |
| 2 | Células por versão (n ≥ 100) e por família, com expectancy líquida, PF, acerto, n; IC por bootstrap de blocos de dia; Holm; mínimo n ≥ 30 e ≥ 7 dias | **OK** — 2 248 células enumeradas, **86 julgáveis**, 5 selos de Holm (§4, §5) |
| 3 | Os dois rankings (onde ganha / onde perde) + contagem honesta testadas × sobreviventes | **OK** — §5 e §6; **86 testadas, 5 selos, 3 hipóteses distintas** (duas são a mesma população contada como versão e como família) |
| 4 | Regime por família, com a fatia em `UNKNOWN` | **OK** — §7 (SQL `q02` 2a/2a2) |
| 5 | Veredicto em ≤ 10 linhas | **OK** — §9 |
| 6 | Rascunho do KB-0079 | **OK** — `.claude/state/exp-drafts/KB-0079-onde-ganha-e-perde.md` |

**Resposta curta:** o mapa existe e é quase todo ruído. **De 2 248 células, só 86 podiam ser
julgadas** (n ≥ 30 e ≥ 7 dias distintos) — porque as maiores populações do Lab, as prospectivas,
têm **1 a 3 dias de calendário**, e nenhuma dimensão sobrevive a um bootstrap cujo bloco é o dia
quando só existem três blocos. Das 86, **5 células ganharam selo de Holm** e elas são **3
hipóteses**: `regime = UNKNOWN` e `trend/vol = up/high` na `volume_anomaly v2` de replay, e
`SIDEWAYS = flat/normal` na `momentum v8` de replay. **Duas das três morrem no controle mais
simples**: recalculadas sobre o **R bruto** (sem pedágio), a de `UNKNOWN` cai de −0,5387 R para
−0,0587 R (p 0,69) e a de `up/high` cai de +0,5582 R para +0,2143 R (p 0,087). **Sobra uma:**
`momentum v8` perde 0,3609 R por decisão quando a hora anterior do BTC é `flat/normal`, e perde
0,3556 R **também no bruto** (p 0,0032 nos dois) — não é pedágio, é o mercado. É a única candidata
a virar variante, e vem com três ressalvas grandes (§8).

**As CONCERNs (§8), em uma linha cada:** (1) as populações prospectivas não têm calendário para
nenhuma inferência de bloco; (2) o pool "família" de `momentum` replay conta **233 decisões
distintas 3,59 vezes**, então o IC dele é estreito demais; (3) a população cresce entre leituras
(6 187 → 6 189 → 6 192 em 18 minutos) e os números vêm de três snapshots declarados; (4) a
célula `UNKNOWN` é, além de pedágio, **calendário puro** — 9 dias que quase não se sobrepõem aos
outros 20; (5) `regime` e `trend × vol` são a mesma partição em vários rótulos e eu tive de fundir
as células para Holm não cobrar duas vezes pela mesma hipótese.

---

## 0. LEITURA PRÉVIA

`docs/PIPELINE.md` §2 (Feature Engine), §3 (Anomaly), §4 e **§4b** (o regime horário
`regime_hourly_v1`, que é a série que esta nota usa), §5 (Opportunity), §6/§6b/§6c (Strategy
Agents, Shadow Lab, replay), §9 (Analytics — a fronteira `Decimal`); `docs/ARCHITECTURE.md` §6
(os protocolos `FeatureCalculator`/`AnomalyDetector`/`RegimeClassifier`/`OpportunityScorer`/
`Strategy`). Do lado da pesquisa: `KB-0076` (a identidade do pedágio, que define a dimensão
"faixa de custo" deste mapa), `KB-0078` (o precedente de "amostra insuficiente é o achado") e as
notas T3.42/T3.47, de onde vêm os dois módulos de bootstrap reusados.

**A regra do §4b que autoriza a junção de regime**, e por que eu fui ainda mais conservador: a
linha da hora `ts` é decidida com velas fechadas **antes** de `ts` e vale em `[ts, ts+1h)`, então
casar um sinal das 12:34 com a linha das 12:00 já não antecipa nada. O brief pediu mais estrito —
a última linha com `end_time <= source_bar_close`, isto é, a hora **inteira que já fechou** antes
da barra — e é isso que está no SQL. As duas convenções divergem em **3,54 % das linhas** (§3.4),
então a escolha não move conclusão nenhuma.

**O relógio de toda esta nota é `meta->'entry_plan'->>'source_bar_close'`** — a última vela fechada
que a estratégia leu. Não `entry_ts` (posterior à decisão) e não `emitted_at` (carrega latência de
fila). Hora do dia, dia da semana e junção de regime saem todos dele.

---

## 1. Arquivos

**SQL (somente leitura, cada um executável sozinho):**
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t353-q00-catalogo.sql`
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t353-q01-populacao-csv.sql`
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t353-q02-regime-e-celulas.sql`
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t353-q03-juncao-de-regime.sql`

**Análise (rascunho, fora de produção):**
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\celulas.py` — bootstrap de blocos de dia por
  célula, Holm, deduplicação de hipóteses idênticas
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\test_celulas.py` — 11 testes com série
  sintética e valor esperado, incluindo a conferência contra `t342-blocos/blocos.py`
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\mapa.py` — a manivela que produz as tabelas
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\populacao.csv` — 6 187 linhas (o dump de `q01`)
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\celulas.csv` — 2 248 células com n, dias,
  Δ, IC95, p, selo de Holm e julgabilidade
- `C:\dev\project-hunter\.claude\state\exp-drafts\t353\q00.out`, `q02.out`, `q03.out`, `mapa.out`
  — as saídas cruas

**Entregas de texto:**
- `C:\dev\project-hunter\.claude\state\notes-T3.53.md` (este arquivo)
- `C:\dev\project-hunter\.claude\state\exp-drafts\KB-0079-onde-ganha-e-perde.md`

---

## 2. Corte, snapshots e a população

**Corte declarado (`as_of`):** `agent_signals.emitted_at < 2026-09-09T02:30:00Z` — **2026-09-08
23:30 de Brasília**. O corte fixa a **emissão**, não a **resolução**: o Lab segue fechando
acompanhamentos, então uma releitura devolve `n` maior. Isso não é hipótese, foi medido nesta
sessão:

| leitura | horário (BRT / UTC) | população avaliável |
|---|---|---|
| `q00` + `q01` (o CSV que alimenta todo bootstrap) | 00:51–00:53 / 03:51–03:53 → **2026-09-08 23:51 BRT** | **6 187** |
| `q02` (tabelas descritivas) | 2026-09-09 00:05 BRT / 03:05 UTC | 6 189 (+2 em `volume_anomaly` prospectiva) |
| `q03` (robustez da junção) | 2026-09-09 00:11 BRT / 03:11 UTC | 6 192 |

**Todo IC, p-valor e selo de Holm desta nota vem do snapshot de 6 187.** As duas linhas a mais
caíram numa população onde **zero** células são julgáveis, então nenhuma conclusão se move.

**Terminal ≠ avaliável.** `q00` tabela 0:

```
== 0. terminal x avaliavel (o que o corte deixa de fora) ==
+----------+-------------+------+-------+
|  estado  |   motivo    |  n   | sem_r |
+----------+-------------+------+-------+
| active   | open        |   44 |    44 |
| no_entry | open        |  365 |  365  |
| terminal | invalidated | 2802 |  294  |
| terminal | target      | 2018 |  225  |
| terminal | stop        | 1710 |  144  |
| terminal | expired     |  345 |   25  |
+----------+-------------+------+-------+
```

São **6 875 terminais** e **6 187 avaliáveis**: 688 terminais não têm `r_multiple` (invalidação
antes da entrada, sobretudo) e ficam de fora de qualquer média — não são zero. Os **6 854** do
título do brief são a contagem de terminais no momento em que ele foi escrito; hoje são 6 875.

---

## 3. Catálogo — `2026-09-09-t353-q00-catalogo.sql` (lido 2026-09-08 23:51 BRT)

### 3.1 Por versão × coorte

```
+-----------------------+-------------+------+----------+---------+------------------------+------------------------+---------------+---------+------------+--------+--------------------+-----------+
|        versao         |   coorte    |  n   | mercados | dias_br |       barra_min        |       barra_max        | exp_liquida_r | soma_r  | acerto_pct |   pf   | custo_r_identidade | sem_barra |
+-----------------------+-------------+------+----------+---------+------------------------+------------------------+---------------+---------+------------+--------+--------------------+-----------+
| volume_anomaly v1     | prospective | 2079 |      237 |       3 | 2026-09-06 03:40:00+00 | 2026-09-08 04:05:00+00 |       -0.3301 | -686.21 |       26.6 |  0.534 |             0.3399 |         0 |
| momentum v1           | prospective |  929 |      230 |       3 | 2026-09-06 03:45:00+00 | 2026-09-08 04:00:00+00 |       -0.1905 | -176.94 |       37.8 |  0.613 |             0.1507 |         0 |
| volume_anomaly v2     | prospective |  775 |      199 |       1 | 2026-09-08 04:35:00+00 | 2026-09-09 02:25:00+00 |       -0.2745 | -212.75 |       27.6 |  0.584 |             0.3157 |         0 |
| momentum v2           | prospective |  359 |      173 |       1 | 2026-09-08 04:45:00+00 | 2026-09-09 02:00:00+00 |       -0.2238 |  -80.33 |       32.9 |  0.565 |             0.1472 |         0 |
| momentum v3           | prospective |  340 |      168 |       1 | 2026-09-08 06:00:00+00 | 2026-09-09 02:00:00+00 |       -0.2391 |  -81.30 |       31.8 |  0.539 |             0.1475 |         0 |
| volume_anomaly v2     | replay      |  339 |        4 |      28 | 2026-08-09 06:55:00+00 | 2026-09-06 02:40:00+00 |       -0.5954 | -201.83 |       29.5 |  0.279 |             0.6139 |         0 |
| momentum v2           | replay      |  248 |        4 |      24 | 2026-08-11 14:15:00+00 | 2026-09-07 23:15:00+00 |       -0.2247 |  -55.73 |       39.1 |  0.566 |             0.2600 |         0 |
| momentum v6           | replay      |  195 |        4 |      24 | 2026-08-11 14:15:00+00 | 2026-09-07 23:15:00+00 |       -0.0513 |  -10.01 |       27.2 |  0.906 |             0.2556 |         0 |
| momentum v7           | replay      |  183 |        4 |      24 | 2026-08-11 14:15:00+00 | 2026-09-07 23:15:00+00 |       -0.0568 |  -10.39 |       14.8 |  0.859 |             0.1733 |         0 |
| momentum v8           | replay      |  181 |        4 |      24 | 2026-08-11 14:15:00+00 | 2026-09-07 23:15:00+00 |       -0.0299 |   -5.42 |       11.6 |  0.906 |             0.1305 |         0 |
| momentum v4           | prospective |  133 |       88 |       1 | 2026-09-08 13:15:00+00 | 2026-09-09 02:00:00+00 |       -0.1888 |  -25.11 |       32.3 |  0.593 |             0.1078 |         0 |
| momentum v6           | prospective |   48 |       39 |       1 | 2026-09-08 19:15:00+00 | 2026-09-09 02:00:00+00 |       -0.3095 |  -14.85 |       16.7 |  0.477 |             0.1409 |         0 |
| trendline_breakout v1 | replay      |   47 |        4 |      14 | 2026-08-19 23:45:00+00 | 2026-09-03 22:00:00+00 |       -0.0382 |   -1.79 |       17.0 |  0.922 |             0.1401 |         0 |
| mean_reversion v1     | prospective |   46 |       42 |       1 | 2026-09-08 17:30:00+00 | 2026-09-09 01:15:00+00 |        0.0802 |    3.69 |       45.7 |  1.167 |             0.1666 |         0 |
| mean_reversion v1     | replay      |   37 |        4 |      10 | 2026-08-20 03:45:00+00 | 2026-09-06 15:15:00+00 |        0.0938 |    3.47 |       40.5 |  1.186 |             0.2261 |         0 |
| mean_reversion v8     | replay      |   33 |        4 |      10 | 2026-08-20 03:45:00+00 | 2026-09-06 15:15:00+00 |        0.0855 |    2.82 |       18.2 |  1.226 |             0.1509 |         0 |
| momentum v4           | replay      |   30 |        4 |       8 | 2026-08-19 15:30:00+00 | 2026-09-05 18:00:00+00 |       -0.1506 |   -4.52 |       36.7 |  0.722 |             0.1316 |         0 |
| momentum v8           | prospective |   25 |       23 |       1 | 2026-09-08 22:30:00+00 | 2026-09-09 02:00:00+00 |       -0.3388 |   -8.47 |        4.0 |  0.149 |             0.0618 |         0 |
| session_orb v1        | replay      |   20 |        4 |      10 | 2026-08-20 02:15:00+00 | 2026-09-06 01:15:00+00 |       -0.1928 |   -3.86 |       10.0 |  0.662 |             0.1430 |         0 |
| mean_reversion v2     | replay      |   17 |        4 |       7 | 2026-08-20 19:30:00+00 | 2026-09-05 23:00:00+00 |        0.2998 |    5.10 |       41.2 |  1.748 |             0.1682 |         0 |
| mean_reversion v6     | replay      |   15 |        4 |       7 | 2026-08-20 19:30:00+00 | 2026-09-05 23:00:00+00 |        0.2861 |    4.29 |        6.7 |  2.282 |             0.1072 |         0 |
| mean_reversion v2     | prospective |   15 |       13 |       1 | 2026-09-08 21:30:00+00 | 2026-09-09 01:15:00+00 |        0.0449 |    0.67 |       46.7 |  1.090 |             0.1484 |         0 |
| mean_reversion v7     | replay      |   14 |        4 |       7 | 2026-08-20 19:30:00+00 | 2026-09-05 23:00:00+00 |        0.3450 |    4.83 |        7.1 |  4.760 |             0.0834 |         0 |
| trendline_breakout v1 | prospective |   12 |       12 |       1 | 2026-09-08 22:30:00+00 | 2026-09-09 02:00:00+00 |       -0.7068 |   -8.48 |        0.0 |        |             0.1038 |         0 |
| mean_reversion v3     | replay      |   11 |        4 |       4 | 2026-08-20 19:30:00+00 | 2026-08-23 20:15:00+00 |        0.5131 |    5.64 |       36.4 |  2.692 |             0.1446 |         0 |
| mean_reversion v4     | replay      |   10 |        4 |       4 | 2026-08-20 19:30:00+00 | 2026-08-23 20:15:00+00 |        0.3337 |    3.34 |       10.0 |  2.479 |             0.0894 |         0 |
| mean_reversion v5     | replay      |    9 |        4 |       4 | 2026-08-20 19:30:00+00 | 2026-08-23 20:15:00+00 |        0.4830 |    4.35 |       11.1 | 21.179 |             0.0692 |         0 |
| mean_reversion v3     | prospective |    9 |        7 |       1 | 2026-09-08 21:45:00+00 | 2026-09-09 01:15:00+00 |        0.0259 |    0.23 |       44.4 |  1.054 |             0.1419 |         0 |
| breakout v2           | replay      |    8 |        3 |       7 | 2026-08-19 21:00:00+00 | 2026-09-06 03:45:00+00 |       -0.0810 |   -0.65 |       50.0 |  0.798 |             0.0912 |         0 |
| momentum v7           | prospective |    7 |        7 |       1 | 2026-09-08 22:30:00+00 | 2026-09-08 23:30:00+00 |       -0.4395 |   -3.08 |        0.0 |        |             0.0688 |         0 |
| mean_reversion v6     | prospective |    4 |        4 |       1 | 2026-09-08 22:45:00+00 | 2026-09-08 23:30:00+00 |        0.7522 |    3.01 |       50.0 |  7.226 |             0.1050 |         0 |
| mean_reversion v7     | prospective |    3 |        3 |       1 | 2026-09-08 22:45:00+00 | 2026-09-08 23:00:00+00 |        0.5085 |    1.53 |       33.3 |  5.076 |             0.0787 |         0 |
| mean_reversion v4     | prospective |    3 |        3 |       1 | 2026-09-08 22:45:00+00 | 2026-09-08 23:30:00+00 |        1.1640 |    3.49 |       66.7 |        |             0.0940 |         0 |
| mean_reversion v5     | prospective |    2 |        2 |       1 | 2026-09-08 22:45:00+00 | 2026-09-08 23:00:00+00 |        0.9498 |    1.90 |       50.0 |        |             0.0646 |         0 |
| momentum v5           | prospective |    1 |        1 |       1 | 2026-09-08 19:15:00+00 | 2026-09-08 19:15:00+00 |       -0.3113 |   -0.31 |        0.0 |        |             0.0348 |         0 |
+-----------------------+-------------+------+----------+---------+------------------------+------------------------+---------------+---------+------------+--------+--------------------+-----------+
(35 rows)
```

**A coluna que decide o destino desta tarefa é `dias_br`.** As cinco maiores populações são
prospectivas e têm **1 a 3 dias de calendário**. `volume_anomaly v1` tem 2 079 desfechos em **três
dias**; `volume_anomaly v2`, 775 em **um dia**. Um bootstrap cujo bloco é o dia — a convenção da
casa desde [[KB-0010]], porque decisões do mesmo dia em mercados correlacionados compartilham
choque — reamostra **três** objetos. Não há intervalo honesto a construir ali, por mais desfechos
que a linha mostre. Quem tem calendário é o replay: 24 dias (`momentum`), 28 (`volume_anomaly v2`),
10 (`mean_reversion`) — e 4 mercados só.

### 3.2 Famílias

```
+--------------------+-------------+------+---------------+---------+
|      familia       |   coorte    |  n   | exp_liquida_r | soma_r  |
+--------------------+-------------+------+---------------+---------+
| breakout           | replay      |    8 |       -0.0810 |   -0.65 |
| mean_reversion     | prospective |   82 |        0.1771 |   14.52 |
| mean_reversion     | replay      |  146 |        0.2317 |   33.84 |
| momentum           | prospective | 1842 |       -0.2119 | -390.39 |
| momentum           | replay      |  837 |       -0.1028 |  -86.06 |
| session_orb        | replay      |   20 |       -0.1928 |   -3.86 |
| trendline_breakout | prospective |   12 |       -0.7068 |   -8.48 |
| trendline_breakout | replay      |   47 |       -0.0382 |   -1.79 |
| volume_anomaly     | prospective | 2854 |       -0.3150 | -898.96 |
| volume_anomaly     | replay      |  339 |       -0.5954 | -201.83 |
+--------------------+-------------+------+---------------+---------+
```

### 3.3 Cobertura de regime (junção `end_time <= source_bar_close`)

```
+-----------------+---------+---------+------+------+
|     regime      |  trend  |   vol   |  n   | pct  |
+-----------------+---------+---------+------+------+
| SIDEWAYS        | flat    | normal  | 3719 | 60.1 |
| LOW_VOLATILITY  | flat    | low     | 1252 | 20.2 |
| HIGH_VOLATILITY | up      | high    |  417 |  6.7 |
| BTC_BULL        | up      | normal  |  227 |  3.7 |
| UNKNOWN         | unknown | unknown |  160 |  2.6 |
| BTC_BULL        | up      | low     |  158 |  2.6 |
| BTC_BEAR        | down    | normal  |  111 |  1.8 |
| HIGH_VOLATILITY | flat    | high    |   94 |  1.5 |
| UNKNOWN         | unknown | low     |   30 |  0.5 |
| BTC_BEAR        | down    | low     |   13 |  0.2 |
| UNKNOWN         | unknown | normal  |    6 |  0.1 |
+-----------------+---------+---------+------+------+
```

**Zero linhas `SEM_LINHA`**: toda decisão da população tem uma hora de regime fechada antes dela.
`UNKNOWN` = 196 de 6 187 = **3,2 %** (por família, §7). E fica registrado o que a tabela mostra:
`SIDEWAYS ≡ flat/normal` e `LOW_VOLATILITY ≡ flat/low` são **a mesma partição** com dois nomes —
o rótulo de regime é uma agregação de `trend × vol`, e em vários rótulos a agregação não agrega
nada. É por isso que o motor funde células idênticas antes de Holm (§4).

### 3.4 A junção de regime é sensível à convenção? — `q03` (lido 2026-09-09 00:11 BRT)

```
+------+----------+--------------+--------------+------------+
|  n   | divergem | pct_divergem | sem_anterior | sem_contem |
+------+----------+--------------+--------------+------------+
| 6192 |      219 |         3.54 |            0 |          0 |
+------+----------+--------------+--------------+------------+
```

A convenção conservadora do brief (`end_time <= barra`) e a convenção do PIPELINE §4b (a janela que
contém a barra) discordam em **3,54 %** das linhas. Nenhuma conclusão desta nota muda com a troca.

---

## 4. O método, e as três decisões que mudam o resultado

Tudo em `celulas.py`. NumPy sobre janelas em memória; nenhum `Decimal`, porque nada aqui é dinheiro
persistido (a fronteira `Decimal` fica no banco, PIPELINE §9). Nada de pandas.

1. **O dia é o bloco.** Reamostram-se **dias inteiros** com reposição; dentro do dia, todas as
   decisões vão juntas — a mesma convenção de `t342-blocos/blocos.py`. O estimando é
   `Δ = média(célula) − média(resto da mesma população)`.
2. **Célula contra RESTO, não contra o todo.** `blocos.contraste_por_piso` compara a variante com a
   população inteira (que a contém). As duas quantidades têm o mesmo sinal em toda reamostragem,
   pela identidade `média(célula) − média(tudo) = (1−w)·(média(célula) − média(resto))`, e é por
   essa identidade que o teste `test_mesmo_estimador_do_laco_ingenuo_de_blocos` confere o motor novo
   contra o velho, sem tocar no velho.
3. **Hora BRT e hora UTC são a mesma partição** (deslocada de 3 h). Testá-las como duas dimensões
   dobraria a multiplicidade sem trazer informação nenhuma. A hora é testada **uma vez** e o rótulo
   sai nos dois relógios (`17h BRT (20h UTC)`).

**Mínimo de julgabilidade:** n ≥ 30 **e** ≥ 7 dias distintos **e** resto com n ≥ 30. Célula abaixo
disso aparece nas tabelas marcada como **não julgável** e **fica fora da família de Holm** — não
gasta orçamento nem ganha selo.

**Multiplicidade:** Holm ao nível 5 % sobre todas as células julgáveis **da mesma população**.
**p-valor:** nível de significância alcançado do bootstrap, `2·min(#{Δ*≤0}+1, #{Δ*≥0}+1)/(B+1)`,
com B = 10 000 — é o p que o próprio intervalo percentil implica, sem nenhuma aproximação normal.

**Deduplicação de hipóteses.** Antes de Holm, células com **máscara idêntica** (`SIDEWAYS` e
`flat/normal`) ou **complementar** são fundidas em um teste só. Sem isso, Holm cobraria duas vezes
pela mesma pergunta e ficaria conservador na conta errada. Na prática isso reduziu a família de 12
para 11 testes nas populações de replay — e é justamente o que fez `up/high` da `volume_anomaly v2`
passar de "não sobrevive" (limiar 0,05/12 = 0,00417 contra p = 0,0046) para "sobrevive" (limiar
0,05/11 = 0,00455 no primeiro passo, e 0,05/10 = 0,0050 no segundo). Registro a fragilidade: **esse
selo depende de uma casa decimal.**

### 4.1 Os testes — `uv run pytest`

```
$ cd C:/dev/project-hunter && uv run pytest .claude/state/exp-drafts/t353/test_celulas.py \
    .claude/state/exp-drafts/t342-blocos/test_blocos.py \
    .claude/state/exp-drafts/t347-blocos/test_blocos_pareado.py -q -p no:cacheprovider

.......................                                                  [100%]
23 passed in 1.41s
```

(**11 testes novos + os 12 pré-existentes** dos dois módulos reusados, que continuam passando sem
alteração — `11 passed in 1.14s` e `12 passed in 1.07s` quando rodados em separado.) Um deles merece ser citado porque é a definição de "não inventar incerteza": em série
sintética com efeito exato de +1,0 R, o motor devolve `Δ = 1,0`, `IC95 = [1,0; 1,0]` e
`p = 2/2001` — e no primeiro rascunho **eu errei o valor esperado do teste de Holm** (achei que
0,020 falharia no passo 2, quando ele só é comparado a 0,025 no passo 3); o teste pegou o erro, não
o contrário.

---

## 5. O mapa — `mapa.py` sobre as 6 187 linhas

### 5.1 As 16 populações com n ≥ 100

```
== A. populacoes analisadas (n >= 100) ==
versao                      coorte            n  dias  merc   exp_liq  exp_bruta  pedagio     somaR     PF  acerto%
volume_anomaly (familia)    prospective    2854     3   259   -0.3150    +0.0182   0.3333   -898.96  0.547     26.9
volume_anomaly v1           prospective    2079     3   237   -0.3301    +0.0094   0.3399   -686.21  0.534     26.6
momentum (familia)          prospective    1842     3   251   -0.2119    -0.0671   0.1445   -390.39  0.576     34.1
momentum v1                 prospective     929     3   230   -0.1905    -0.0399   0.1507   -176.94  0.613     37.8
momentum (familia)          replay          837    24     4   -0.1028    +0.1053   0.2074    -86.06  0.775     25.0
volume_anomaly v2           prospective     775     1   199   -0.2745    +0.0419   0.3157   -212.75  0.584     27.6
momentum v2                 prospective     359     1   173   -0.2238    -0.0758   0.1472    -80.33  0.565     32.9
momentum v3                 prospective     340     1   168   -0.2391    -0.0908   0.1475    -81.30  0.539     31.8
volume_anomaly v2           replay          339    28     4   -0.5954    +0.0185   0.6139   -201.83  0.279     29.5
volume_anomaly (familia)    replay          339    28     4   -0.5954    +0.0185   0.6139   -201.83  0.279     29.5
momentum v2                 replay          248    24     4   -0.2247    +0.0355   0.2600    -55.73  0.566     39.1
momentum v6                 replay          195    24     4   -0.0513    +0.2052   0.2556    -10.01  0.906     27.2
momentum v7                 replay          183    24     4   -0.0568    +0.1175   0.1733    -10.39  0.859     14.8
momentum v8                 replay          181    24     4   -0.0299    +0.1013   0.1305     -5.42  0.906     11.6
mean_reversion (familia)    replay          146    10     4   +0.2317    +0.3845   0.1513    +33.84  1.699     24.7
momentum v4                 prospective     133     1    88   -0.1888    -0.0803   0.1078    -25.11  0.593     32.3
```

`volume_anomaly (família) replay` **é** `volume_anomaly v2 replay` — as mesmas 339 linhas, porque
só a v2 tem replay. Conta como **uma** população, aparece duas vezes por construção do pool.

### 5.2 As populações prospectivas: nenhuma célula julgável

```
== B. volume_anomaly (familia) / prospective - 292 celulas, 0 julgaveis, 0 sobrevivem a Holm 5% ==
   nenhuma celula julgavel nesta populacao (a populacao tem 3 dias distintos)
== B. volume_anomaly v1 / prospective - 270 celulas, 0 julgaveis, 0 sobrevivem ==  (3 dias)
== B. momentum (familia) / prospective - 284 celulas, 0 julgaveis, 0 sobrevivem ==  (3 dias)
== B. momentum v1 / prospective - 263 celulas, 0 julgaveis, 0 sobrevivem ==  (3 dias)
== B. volume_anomaly v2 / prospective - 226 celulas, 0 julgaveis, 0 sobrevivem ==  (1 dia)
== B. momentum v2 / prospective - 200 celulas, 0 julgaveis, 0 sobrevivem ==  (1 dia)
== B. momentum v3 / prospective - 193 celulas, 0 julgaveis, 0 sobrevivem ==  (1 dia)
== B. momentum v4 / prospective - 106 celulas, 0 julgaveis, 0 sobrevivem ==  (1 dia)
```

**1 774 células enumeradas nas oito populações prospectivas; zero julgáveis.** A `q02` 2f mostra
o mesmo pelo lado do SQL: `momentum v1 prospective` tem 16 células de hora com n ≥ 30 e **nenhuma**
com 7 dias; `volume_anomaly v1 prospective` tem 24 células de hora com n ≥ 30 e **nenhuma** com 7
dias; e 237 mercados dos quais **um** chega a n = 30.

### 5.3 `momentum` (família) / replay — 52 células, 16 julgáveis, **0** selos

```
   dim         celula                        n dias      exp    resto    delta                 IC95       p  Holm     PF acerto  pedag
   trend_x_vol up/high                     220    7  +0.3055  -0.2484  +0.5539     [+0.023; +0.776]  0.0452     -  1.955   40.5  0.157
   hora        17h BRT (20h UTC)            54    8  +0.3902  -0.1368  +0.5270     [+0.027; +1.052]  0.0408     -  3.329   42.6  0.209
   regime      HIGH_VOLATILITY             282    8  +0.1004  -0.2061  +0.3064     [-0.200; +0.719]  0.2036     -  1.259   31.6  0.161
   mercado     DOGEUSDT                    219   20  +0.0405  -0.1536  +0.1942     [+0.011; +0.380]  0.0394     -  1.104   29.2  0.207
   pedagio     pedagio 0,10-0,20 R         358   23  +0.0025  -0.1815  +0.1840     [+0.038; +0.360]  0.0094     -  1.007   24.3  0.152
   trend_x_vol up/normal                   151    7  +0.0116  -0.1280  +0.1396     [-0.260; +0.604]  0.4880     -  1.031   31.1  0.195
   pedagio     pedagio < 0,10 R             98   13  -0.0320  -0.1122  +0.0802     [-0.133; +0.273]  0.4840     -  0.910   18.4  0.081
   mercado     SOLUSDT                     239   23  -0.1126  -0.0989  -0.0137     [-0.208; +0.176]  0.9221     -  0.755   23.4  0.214
   mercado     XRPUSDT                     208   17  -0.1337  -0.0926  -0.0412     [-0.184; +0.107]  0.5317     -  0.726   26.0  0.180
   regime      BTC_BULL                    193    8  -0.1409  -0.0914  -0.0494     [-0.410; +0.318]  0.7706     -  0.702   29.0  0.220
   hora        23h BRT (02h UTC)            55    7  -0.1911  -0.0966  -0.0945     [-0.641; +0.741]  0.7998     -  0.666   21.8  0.220
   mercado     ETHUSDT                     171   17  -0.2351  -0.0689  -0.1662     [-0.387; +0.107]  0.2162     -  0.533   20.5  0.232
   pedagio     pedagio > 0,20 R            381   23  -0.2200  -0.0049  -0.2151     [-0.414; -0.040]  0.0134     -  0.608   27.3  0.292
   hora        11h BRT (14h UTC)            76   13  -0.3079  -0.0823  -0.2256     [-0.524; +0.068]  0.1240     -  0.388   14.5  0.211
   regime+trend_x_vol SIDEWAYS = flat/normal 165   8  -0.3530  -0.0414  -0.3116     [-0.750; +0.046]  0.0854     -  0.396   14.5  0.224
   hora        10h BRT (13h UTC)            78    9  -0.4318  -0.0690  -0.3628     [-0.814; +0.321]  0.2366     -  0.371   17.9  0.240
   nao julgaveis: 36 celulas - maiores: qui (BRT) (n=201, 4d), seg (BRT) (n=143, 3d), qua (BRT) (n=135, 3d), dom (BRT) (n=126, 4d)
   celulas fundidas: trend_x_vol:flat/low == regime:LOW_VOLATILITY; trend_x_vol:flat/normal == regime:SIDEWAYS
```

Com 16 testes, o primeiro limiar de Holm é 0,05/16 = **0,0031** e o menor p é 0,0094. **Nada
sobrevive.** Note também: **os sete dias da semana estão todos entre as não julgáveis** — cada dia
da semana aparece em 3 ou 4 datas distintas na janela de replay, então "dia da semana" não é uma
dimensão que esta janela consiga responder para ninguém.

### 5.4 `volume_anomaly v2` / replay — 54 células, 11 julgáveis, **2** selos

```
   dim         celula                        n dias      exp    resto    delta                 IC95       p  Holm     PF acerto  pedag
   trend_x_vol up/high                      72    8  -0.1557  -0.7139  +0.5582     [+0.199; +0.938]  0.0046   sim  0.720   38.9  0.343
   regime      HIGH_VOLATILITY              85    9  -0.2772  -0.7018  +0.4246     [+0.067; +0.791]  0.0232     -  0.560   35.3  0.368
   regime      BTC_BULL                     53    7  -0.3030  -0.6495  +0.3465     [-0.029; +0.608]  0.0710     -  0.478   39.6  0.404
   mercado     XRPUSDT                      81   17  -0.3950  -0.6583  +0.2633     [-0.044; +0.491]  0.0988     -  0.442   35.8  0.534
   mercado     SOLUSDT                     127   28  -0.5502  -0.6224  +0.0723     [-0.075; +0.256]  0.3442     -  0.318   29.1  0.581
   hora        12h BRT (15h UTC)            38   16  -0.5897  -0.5961  +0.0064     [-0.429; +0.324]  0.9419     -  0.284   26.3  0.541
   mercado     DOGEUSDT                     95   21  -0.6261  -0.5834  -0.0427     [-0.310; +0.188]  0.7417     -  0.209   26.3  0.528
   regime+trend_x_vol SIDEWAYS = flat/normal 30   7  -0.7192  -0.5833  -0.1359     [-0.536; +0.299]  0.5265     -  0.172   16.7  0.425
   pedagio     pedagio > 0,20 R            307   28  -0.6394  -0.1727  -0.4668     [-0.993; -0.009]  0.0456     -  0.263   28.7  0.665
   trend_x_vol unknown/unknown             128    7  -0.8888  -0.4174  -0.4714     [-0.805; -0.075]  0.0236     -  0.153   22.7  0.871
   regime      UNKNOWN                     156    9  -0.8862  -0.3475  -0.5387     [-0.809; -0.206]  0.0020   sim  0.140   24.4  0.873
```

### 5.5 `momentum v8` / replay — 53 células, 11 julgáveis, **1** selo

```
   dim         celula                        n dias      exp    resto    delta                 IC95       p  Holm     PF acerto  pedag
   trend_x_vol up/high                      44    7  +0.3229  -0.1432  +0.4661     [-0.147; +0.793]  0.0834     -  2.418   22.7  0.100
   regime      HIGH_VOLATILITY              57    8  +0.1654  -0.1197  +0.2851     [-0.190; +0.736]  0.1980     -  1.637   17.5  0.102
   mercado     DOGEUSDT                     46   20  +0.0733  -0.0651  +0.1384     [-0.007; +0.290]  0.0602     -  1.283   10.9  0.128
   mercado     SOLUSDT                      54   23  +0.0413  -0.0602  +0.1015     [-0.060; +0.265]  0.1992     -  1.145   13.0  0.133
   pedagio     pedagio 0,10-0,20 R         113   22  +0.0063  -0.0901  +0.0964     [-0.249; +0.426]  0.5493     -  1.020   13.3  0.146
   trend_x_vol up/normal                    35    7  +0.0356  -0.0456  +0.0813     [-0.306; +0.612]  0.7335     -  1.123   14.3  0.127
   pedagio     pedagio < 0,10 R             56   13  -0.0007  -0.0430  +0.0423     [-0.283; +0.421]  0.8623     -  0.997   10.7  0.079
   mercado     XRPUSDT                      42   17  -0.0431  -0.0259  -0.0172     [-0.188; +0.178]  0.8015     -  0.877   14.3  0.115
   regime      BTC_BULL                     42    8  -0.0446  -0.0255  -0.0191     [-0.379; +0.391]  0.8830     -  0.873   14.3  0.136
   mercado     ETHUSDT                      39   17  -0.2360  +0.0267  -0.2627     [-0.448; -0.057]  0.0152     -  0.401    7.7  0.148
   regime+trend_x_vol SIDEWAYS = flat/normal 36   8  -0.3191  +0.0419  -0.3609     [-0.654; -0.108]  0.0032   sim  0.166    0.0  0.135
```

As demais populações de replay (`momentum v2`, `v6`, `v7`, `mean_reversion` família) estão em
`mapa.out` e não têm nenhum selo. `mean_reversion` família replay tem **4** células julgáveis, de
42 — a menor família de testes da nota.

### 5.6 O placar de multiplicidade (a conta honesta)

```
== C. placar de multiplicidade ==
versao                      coorte         celulas  julgaveis  sobrevivem
mean_reversion (familia)    replay              42          4           0
momentum (familia)          prospective        284          0           0
momentum (familia)          replay              52         16           0
momentum v1                 prospective        263          0           0
momentum v2                 prospective        200          0           0
momentum v2                 replay              53         11           0
momentum v3                 prospective        193          0           0
momentum v4                 prospective        106          0           0
momentum v6                 replay              53         11           0
momentum v7                 replay              53         11           0
momentum v8                 replay              53         11           1
volume_anomaly (familia)    prospective        292          0           0
volume_anomaly (familia)    replay              54         11           2
volume_anomaly v1           prospective        270          0           0
volume_anomaly v2           prospective        226          0           0
volume_anomaly v2           replay              54         11           2
TOTAL                                         2248         86           5
```

**2 248 células enumeradas · 86 julgadas · 5 selos · 3 hipóteses distintas** (as duas de
`volume_anomaly` contam duas vezes porque a família é a versão).

---

## 6. Os dois rankings que o Everton pediu

### 6.1 Onde cada versão **ganha** (topo que sobrevive a Holm)

| versão / coorte | célula | n | dias | exp na célula | Δ vs resto | IC 95 % | p | Holm |
|---|---|---:|---:|---:|---:|---|---:|---|
| `volume_anomaly v2` / replay | `trend/vol = up/high` (BTC subindo, vol alta) | 72 | 8 | −0,1557 R | **+0,5582 R** | [+0,199; +0,938] | 0,0046 | **sim** |

**É a única célula "de ganho" com selo em toda a nota** — e mesmo ela não é lucrativa: a
`volume_anomaly v2` em `up/high` perde 0,16 R por decisão, só perde **menos** que os 0,71 R do
resto. Nenhuma célula de nenhuma versão tem expectancy líquida positiva **e** selo de Holm.

Candidatas de topo que **não** sobreviveram, para o registro (todas com p entre 0,03 e 0,05, que é
exatamente onde a multiplicidade morde): `momentum` família replay `up/high` (+0,5539, p 0,0452),
`momentum` família replay `17h BRT / 20h UTC` (+0,5270, p 0,0408), `momentum v6` replay `up/high`
(+0,6901, p 0,0432), `momentum v2` replay `up/high` (+0,5375, p 0,0060 — perdeu para o limiar
0,05/11 = 0,00455 por 0,0015).

### 6.2 Onde cada versão **perde** (fundo que sobrevive a Holm)

| versão / coorte | célula | n | dias | exp na célula | Δ vs resto | IC 95 % | p | Holm |
|---|---|---:|---:|---:|---:|---|---:|---|
| `volume_anomaly v2` / replay | `regime = UNKNOWN` | 156 | 9 | −0,8862 R | **−0,5387 R** | [−0,809; −0,206] | 0,0020 | **sim** |
| `momentum v8` / replay | `SIDEWAYS = flat/normal` | 36 | 8 | −0,3191 R | **−0,3609 R** | [−0,654; −0,108] | 0,0032 | **sim** |

### 6.3 O controle que separa padrão de acaso: refazer tudo no **R bruto**

Se a célula só ganha porque paga menos pedágio, ela não achou mercado, achou o custo do próprio
stop — e o filtro implementável não é o rótulo da célula, é o pedágio (que já é a tese da
[[KB-0076]] e já virou variante nas T3.42/T3.47). Então cada sobrevivente foi refeita sobre
`r_gross`, com o mesmo bootstrap:

```
== D. as celulas que sobreviveram, sob suspeita (confundidores obvios) ==
   volume_anomaly v2 / replay :: regime = UNKNOWN
      delta liquido -0.5387 R  IC95 [-0.809; -0.206] p=0.0020
      delta BRUTO   -0.0587 R  IC95 [-0.342; +0.213] p=0.6919
      delta pedagio +0.4801 R (dentro 0.873 / fora 0.393)
      calendario dentro: 2026-08-09 .. 2026-08-17 (9 dias)
      calendario fora  : 2026-08-17 .. 2026-09-05 (20 dias)
      sobreposicao de dias: 1 dias em comum
   volume_anomaly v2 / replay :: trend_x_vol = up/high
      delta liquido +0.5582 R  IC95 [+0.199; +0.938] p=0.0046
      delta BRUTO   +0.2143 R  IC95 [-0.040; +0.478] p=0.0866
      delta pedagio -0.3444 R (dentro 0.343 / fora 0.687)
      calendario dentro: 2026-08-18 .. 2026-09-04 (8 dias)
      calendario fora  : 2026-08-09 .. 2026-09-05 (24 dias)
      sobreposicao de dias: 4 dias em comum
   momentum v8 / replay :: regime+trend_x_vol = SIDEWAYS = flat/normal
      delta liquido -0.3609 R  IC95 [-0.654; -0.108] p=0.0032
      delta BRUTO   -0.3556 R  IC95 [-0.639; -0.104] p=0.0032
      delta pedagio +0.0062 R (dentro 0.135 / fora 0.129)
      calendario dentro: 2026-08-24 .. 2026-09-07 (8 dias)
      calendario fora  : 2026-08-11 .. 2026-09-06 (21 dias)
      sobreposicao de dias: 5 dias em comum
```

Leitura, uma a uma:

- **`UNKNOWN` da `volume_anomaly v2` não é regime, é pedágio e é calendário.** No bruto o efeito
  desaparece (−0,0587 R, p 0,69) enquanto o pedágio médio dentro da célula é **0,873 R contra
  0,393 R** fora. E os 9 dias de dentro têm **um** dia em comum com os 20 de fora: `UNKNOWN` é o
  rótulo do **aquecimento do classificador** (PIPELINE §4b item 5), ou seja, os primeiros dias da
  janela de replay. Um "filtro por UNKNOWN" seria um filtro por data. **Descartada.**
- **`up/high` perde 62 % do efeito no bruto** (+0,5582 → +0,2143) e o p sai de 0,0046 para 0,0866.
  O que sobra é uma direção plausível, não um achado. **Sugestiva, não provada.**
- **`flat/normal` da `momentum v8` atravessa o controle intacta**: −0,3609 líquido, −0,3556 bruto,
  pedágio praticamente igual dentro e fora (0,135 vs 0,129), p 0,0032 nas duas leituras. **Esta é a
  única do mapa que não é o custo disfarçado.**

### 6.4 A coerência entre versões — e por que ela vale menos do que parece

```
== E. coerencia dos dois rotulos de regime entre versoes (NAO sao replicacoes independentes:
      v2/v6/v7/v8 decidem as MESMAS barras com geometria diferente) ==
   versao                    coorte      rotulo            n dias      exp  delta_liq   p_liq  delta_bruto  p_bruto
   volume_anomaly (familia)  prospective flat/normal    1975    3  -0.3041    +0.0354  0.1059      +0.0231   0.1059
   volume_anomaly v1         prospective flat/normal    1200    3  -0.3232    +0.0164  0.4071      +0.0124   0.4071
   momentum (familia)        prospective flat/normal    1422    3  -0.2108    +0.0048  0.7299      -0.0100   0.6277
   momentum v1               prospective flat/normal     509    3  -0.1697    +0.0460  0.7299      +0.0357   0.7299
   momentum (familia)        replay      flat/normal     165    8  -0.3530    -0.3116  0.0854      -0.2918   0.0876
   volume_anomaly v2         replay      flat/normal      30    7  -0.7192    -0.1359  0.5265      -0.3438   0.0590
   momentum v2               replay      flat/normal      52    8  -0.4254    -0.2540  0.1804      -0.2298   0.1914
   momentum v6               replay      flat/normal      38    8  -0.2701    -0.2717  0.3206      -0.2446   0.3492
   momentum v7               replay      flat/normal      36    8  -0.3269    -0.3362  0.0676      -0.3262   0.0644
   momentum v8               replay      flat/normal      36    8  -0.3191    -0.3609  0.0032      -0.3556   0.0032
   mean_reversion (familia)  replay      flat/normal      13    1  -0.0609    -0.3212  0.2196      -0.2610   0.3200
   momentum (familia)        replay      up/high         220    7  +0.3055    +0.5539  0.0452      +0.4853   0.0582
   volume_anomaly v2         replay      up/high          72    8  -0.1557    +0.5582  0.0046      +0.2143   0.0866
   momentum v2               replay      up/high          61    7  +0.1806    +0.5375  0.0060      +0.4505   0.0148
   momentum v6               replay      up/high          52    7  +0.4548    +0.6901  0.0432      +0.6054   0.0570
   momentum v7               replay      up/high          44    7  +0.4453    +0.6610  0.0656      +0.6094   0.0714
   momentum v8               replay      up/high          44    7  +0.3229    +0.4661  0.0834      +0.4259   0.0956
   mean_reversion (familia)  replay      up/high         104    4  +0.3022    +0.2448  0.5405      +0.1743   0.6628
```

O sinal é **o mesmo em todas as populações de replay**: `flat/normal` negativo em 7 de 7,
`up/high` positivo em 7 de 7. Isso parece uma replicação e **não é**: `momentum v2/v4/v6/v7/v8` de
replay são **233 decisões distintas `(mercado, barra)` contadas 3,59 vezes** com geometrias
diferentes de stop e alvo (medido: `n = 837`, pares distintos `= 233`). O `mean_reversion` de
replay é pior: **38 pares distintos contados 3,84 vezes** (`n = 146`). São a mesma barra vista de
vários ângulos, não sete experimentos.

**E nas prospectivas o sinal simplesmente não está lá:** `flat/normal` dá Δ entre **+0,005 e
+0,046 R** (p de 0,41 a 0,73) — sinal trocado em relação ao replay. Ressalva na direção contrária,
para não fazer o argumento fácil: na coorte prospectiva **77 % da população já é `flat/normal`**
(§7), então o "resto" é quase só `LOW_VOLATILITY` e o contraste é fraco por construção — a
prospectiva não refuta o achado do replay, ela **não consegue testá-lo**.

---

## 7. Regime por família (item 4 do brief) — `q02` 2a/2a2 (lido 2026-09-09 00:05 BRT)

```
== 2a. expectancy por rotulo de regime, por familia x coorte ==
|      familia       |   coorte    |     regime      |  n   | pct_da_pop | dias | exp_liquida_r | exp_bruta_r | pedagio_r | soma_r  | acerto_pct |    pf    |
| mean_reversion     | prospective | SIDEWAYS        |   84 |      100.0 |    1 |        0.1483 |      0.2970 |    0.1468 |   12.46 |       45.2 |    1.338 |
| mean_reversion     | replay      | HIGH_VOLATILITY |  113 |       77.4 |    6 |        0.2142 |      0.3544 |    0.1387 |   24.21 |       18.6 |    1.647 |
| mean_reversion     | replay      | BTC_BULL        |   16 |       11.0 |    2 |        0.6964 |      0.8771 |    0.1785 |   11.14 |       62.5 |    4.176 |
| mean_reversion     | replay      | SIDEWAYS        |   13 |        8.9 |    1 |       -0.0609 |      0.1468 |    0.2076 |   -0.79 |       30.8 |    0.866 |
| mean_reversion     | replay      | LOW_VOLATILITY  |    4 |        2.7 |    1 |       -0.1804 |      0.0395 |    0.2154 |   -0.72 |       25.0 |    0.553 |
| momentum           | prospective | SIDEWAYS        | 1422 |       77.2 |    3 |       -0.2108 |     -0.0694 |    0.1410 | -299.82 |       33.1 |    0.577 |
| momentum           | prospective | LOW_VOLATILITY  |  382 |       20.7 |    1 |       -0.1961 |     -0.0398 |    0.1564 |  -74.93 |       38.0 |    0.603 |
| momentum           | prospective | BTC_BULL        |   38 |        2.1 |    1 |       -0.4117 |     -0.2562 |    0.1552 |  -15.64 |       34.2 |    0.360 |
| momentum           | replay      | HIGH_VOLATILITY |  282 |       33.7 |    8 |        0.1004 |      0.2624 |    0.1614 |   28.30 |       31.6 |    1.259 |
| momentum           | replay      | BTC_BULL        |  193 |       23.1 |    8 |       -0.1409 |      0.0805 |    0.2203 |  -27.19 |       29.0 |    0.702 |
| momentum           | replay      | SIDEWAYS        |  165 |       19.7 |    8 |       -0.3530 |     -0.1290 |    0.2239 |  -58.25 |       14.5 |    0.396 |
| momentum           | replay      | BTC_BEAR        |  108 |       12.9 |    4 |       -0.0631 |      0.1773 |    0.2402 |   -6.82 |       21.3 |    0.848 |
| momentum           | replay      | LOW_VOLATILITY  |   49 |        5.9 |    3 |       -0.4683 |     -0.2162 |    0.2521 |  -22.95 |       14.3 |    0.226 |
| momentum           | replay      | UNKNOWN         |   40 |        4.8 |    3 |        0.0209 |      0.2825 |    0.2589 |    0.83 |       25.0 |    1.075 |
| volume_anomaly     | prospective | SIDEWAYS        | 1977 |       69.2 |    3 |       -0.3026 |      0.0269 |    0.3296 | -598.29 |       26.9 |    0.557 |
| volume_anomaly     | prospective | LOW_VOLATILITY  |  813 |       28.5 |    1 |       -0.3549 |     -0.0103 |    0.3448 | -288.55 |       26.4 |    0.513 |
| volume_anomaly     | prospective | BTC_BULL        |   66 |        2.3 |    1 |       -0.1497 |      0.1563 |    0.3054 |   -9.88 |       31.8 |    0.769 |
| volume_anomaly     | replay      | UNKNOWN         |  156 |       46.0 |    9 |       -0.8862 |     -0.0132 |    0.8731 | -138.24 |       24.4 |    0.140 |
| volume_anomaly     | replay      | HIGH_VOLATILITY |   85 |       25.1 |    9 |       -0.2772 |      0.0906 |    0.3677 |  -23.56 |       35.3 |    0.560 |
| volume_anomaly     | replay      | BTC_BULL        |   53 |       15.6 |    7 |       -0.3030 |      0.1013 |    0.4042 |  -16.06 |       39.6 |    0.478 |
| volume_anomaly     | replay      | SIDEWAYS        |   30 |        8.8 |    7 |       -0.7192 |     -0.2949 |    0.4251 |  -21.58 |       16.7 |    0.172 |
| volume_anomaly     | replay      | BTC_BEAR        |   11 |        3.2 |    4 |       -0.6468 |     -0.2297 |    0.4175 |   -7.11 |       18.2 |    0.177 |
| volume_anomaly     | replay      | LOW_VOLATILITY  |    4 |        1.2 |    1 |        1.1821 |      1.6581 |    0.4742 |    4.73 |      100.0 |          |
```

```
== 2a2. fatia UNKNOWN por familia x coorte ==
|      familia       |   coorte    |  n   | n_unknown | pct_unknown | n_sem_linha | unknown_de | unknown_ate |
| mean_reversion     | replay      |  146 |         0 |         0.0 |           0 |            |             |
| momentum           | prospective | 1842 |         0 |         0.0 |           0 |            |             |
| momentum           | replay      |  837 |        40 |         4.8 |           0 | 2026-08-11 | 2026-08-16  |
| volume_anomaly     | prospective | 2856 |         0 |         0.0 |           0 |            |             |
| volume_anomaly     | replay      |  339 |       156 |        46.0 |           0 | 2026-08-09 | 2026-08-17  |
| trendline_breakout | replay      |   47 |         0 |         0.0 |           0 |            |             |
| session_orb        | replay      |   20 |         0 |         0.0 |           0 |            |             |
| breakout           | replay      |    8 |         0 |         0.0 |           0 |            |             |
```

**Para a T3.52 (portão de regime), os quatro fatos que importam:**

1. **`UNKNOWN` não é um buraco de dado, é uma data.** Zero na coorte prospectiva (o classificador
   já está aquecido), **46 %** na `volume_anomaly` de replay e **4,8 %** na `momentum` de replay —
   e sempre entre **2026-08-09 e 2026-08-17**, o começo da janela. Um portão que trate `UNKNOWN`
   como "não operar" é gratuito hoje e caro só em replay antigo.
2. **A ordem dos rótulos é a mesma nas duas famílias de replay:** `HIGH_VOLATILITY` no topo
   (`momentum` +0,1004 R, a **única** célula de regime com expectancy líquida positiva e n ≥ 100),
   `SIDEWAYS` no fundo (`momentum` −0,3530, `volume_anomaly` −0,7192).
3. **No bruto a ordem persiste** (`momentum` replay: `HIGH_VOLATILITY` +0,2624 vs `SIDEWAYS`
   −0,1290), então não é só pedágio — mas nenhum desses contrastes por rótulo **agregado** ganhou
   selo de Holm; quem ganhou foi a célula fina `flat/normal` da v8.
4. **A coorte prospectiva não tem contraste de regime para dar:** `momentum` é 77,2 % `SIDEWAYS` +
   20,7 % `LOW_VOLATILITY` + 2,1 % `BTC_BULL`, em 3 dias. Um portão calibrado no replay entra no
   Lab **sem** validação prospectiva possível hoje.

---

## 8. CONCERNs

**CONCERN 1 — as maiores populações do Lab não têm calendário para inferência nenhuma.**
6 187 desfechos parecem muitos; 4 636 deles estão em oito populações prospectivas com **1 a 3 dias
distintos**. Com o dia como bloco (e é a convenção certa: [[KB-0010]]), reamostrar 3 objetos não
produz intervalo. Não é limitação do método — é a janela. **Consequência prática:** qualquer
afirmação sobre hora, dia da semana ou mercado na coorte prospectiva é, hoje, inverificável.
**O que destrava:** dias de calendário, não desfechos. Sete dias corridos de Lab prospectivo com as
versões atuais dariam a primeira família de testes prospectiva julgável.

**CONCERN 2 — o pool "família" conta a mesma barra várias vezes.** Medido nesta sessão:

```
momentum         replay       n=  837 pares_distintos=  233 razao=3.59
momentum         prospective  n= 1842 pares_distintos= 1308 razao=1.41
mean_reversion   replay       n=  146 pares_distintos=   38 razao=3.84
volume_anomaly   replay       n=  339 pares_distintos=  337 razao=1.01
volume_anomaly   prospective  n= 2854 pares_distintos= 2854 razao=1.00
```

O bootstrap de blocos de dia trata a correlação **entre decisões do mesmo dia**, mas o pool de
família ainda infla `n` por um fator de ~3,6 em `momentum` replay e ~3,8 em `mean_reversion`
replay. **Os ICs dessas duas linhas são estreitos demais** e eu não os uso para nenhuma conclusão —
nenhuma delas ganhou selo, o que reduz o dano, mas o `p = 0,0452` do `up/high` da família
`momentum` seria maior ainda com o `n` efetivo.

**CONCERN 3 — a população se move entre leituras.** 6 187 → 6 189 → 6 192 em 18 minutos, com o
`as_of` **fixo** na emissão. Todo bootstrap vem do snapshot de 6 187 (2026-09-08 23:51 BRT); as
tabelas descritivas de `q02` vêm de 6 189 e `q03` de 6 192. As diferenças caem em
`volume_anomaly prospective`, onde nada é julgável.

**CONCERN 4 — o selo de `up/high` depende da deduplicação.** Sem fundir `SIDEWAYS` com
`flat/normal`, a família tem 12 testes, o limiar do primeiro passo é 0,004167 e o p de 0,0046 **não
passa**. Com 11 testes, passa no segundo passo (limiar 0,0050). A fusão é defensável (é literalmente
a mesma máscara de linhas), mas quem lê precisa saber que este selo mora numa casa decimal.

**CONCERN 5 — o teste da célula é sempre "célula contra o resto da MESMA população".** Não é
teste fora de amostra e não vira promessa de retorno: `volume_anomaly v2` em `up/high` continua
perdendo 0,16 R por decisão. "Ganha" nesta nota quer dizer "perde menos que o resto".

**CONCERN 6 — três dimensões do brief não foram respondidas por falta de dado, não por escolha.**
*Dia da semana:* nas populações de replay cada dia da semana aparece em 3 ou 4 datas distintas —
todas as sete células caem em "não julgável" em todas as populações. *Hora:* só **duas** células de
hora em toda a nota são julgáveis (`17h BRT` na família `momentum` replay, `12h BRT` na
`volume_anomaly v2` replay). *Mercado:* nas prospectivas, um único mercado em 237 chega a n = 30.

---

## 9. Veredicto (≤ 10 linhas)

1. Existe **um** filtro que sobrevive à multiplicidade e ao controle de pedágio: **`momentum v8`
   perde 0,36 R por decisão quando a hora fechada anterior do BTC é `flat/normal` (`SIDEWAYS`)** —
   −0,3609 R líquido e −0,3556 R **bruto**, p 0,0032 nos dois, IC 95 % [−0,654; −0,108].
2. É a **única** das 86 células julgadas que não é o custo disfarçado, e a direção repete em 7 de 7
   populações de replay — que **não** são 7 experimentos (233 barras contadas 3,59 vezes).
3. **Vira variante primeiro:** um portão de regime para `momentum` que **não decide** quando
   `trend = flat` e `vol = normal` (e trata `UNKNOWN` como "não operar", que hoje custa zero na
   coorte prospectiva). É o insumo direto da T3.52.
4. É **ruído**: hora do dia (2 células julgáveis em toda a nota, nenhuma com selo), dia da semana
   (nenhuma célula julgável em nenhuma população) e mercado (nenhum selo; o melhor é `DOGEUSDT`
   com p 0,039 contra limiar 0,0031).
5. É **artefato**: `regime = UNKNOWN` na `volume_anomaly v2` — no bruto o efeito some (p 0,69), o
   pedágio dentro da célula é 0,873 R contra 0,393 R fora, e os 9 dias de dentro têm 1 dia em comum
   com os 20 de fora. É calendário de aquecimento, não regime.
6. É **sugestivo, não provado**: `up/high` (BTC subindo com volatilidade alta) — positivo em todas
   as populações de replay, mas perde 62 % do efeito no bruto e cai para p 0,087.
7. O padrão mais forte e mais reprodutível do mapa continua sendo **o pedágio**, e ele já está
   endereçado: em 6 de 6 populações a faixa `> 0,20 R` é a pior, enquanto a expectancy **bruta**
   por faixa é plana ou até crescente (`volume_anomaly` prospectiva: +0,0018 / +0,0085 / +0,0292).
   Continua valendo a [[KB-0076]]: a perda é o custo.
8. Nada disto autoriza dinheiro real; nada disto tem coorte prospectiva com calendário para
   validar.
