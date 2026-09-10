# T3.73 — o Shadow Lab decidia sobre linhas SPOT com um modelo de custo de perpétuo

**Escopo:** medição somente leitura na VPS (`hunter-vps`, `hunter-postgres-1`), toda consulta dentro
de `begin transaction isolation level repeatable read read only; … commit;`; depois a menor correção
correta, com testes. **Nenhuma escrita na VPS. Nenhuma mudança de parâmetro de versão viva. Nenhum
commit.** Leitura de referência: **2026-09-10 04:07Z = 01:07 BRT** (`TimeZone = UTC` no servidor).
Horários em Brasília (UTC−3) com o UTC ao lado.

SQL, verbatim, em `infra/scripts/sql/research/`:

| arquivo | o que responde |
|---|---|
| `2026-09-10-t373-q00-spot-vs-perp.sql` | universo de `markets`; sinais e desfechos por versão × tipo de mercado desde 01/09 |
| `2026-09-10-t373-q01-spot-sem-r.sql` | motivo de R nulo por tipo; `funding_rates` por tipo; duplicação (versão, símbolo, barra) |
| `2026-09-10-t373-q02-no-entry.sql` | o denominador escondido: `no_entry` por motivo e por dia |
| `2026-09-10-t373-q03-late-delay.sql` | o que `late:delay` mede: o atraso decisão-menos-barra, por dia |
| `2026-09-10-t373-q04-linha-paper.sql` | quais versões são `paper` e em que tipo de mercado decidem |

Receita usada em todas:

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t373-q00-spot-vs-perp.sql
```

---

## 1. A medição

### 1.1 Há duas linhas de `markets` por símbolo, e as duas decidem

```
+-----------+--------+-------------+----------+
|   tipo    | linhas | monitoradas | simbolos |
+-----------+--------+-------------+----------+
| perpetual |    528 |         200 |      528 |
| spot      |    490 |          18 |      490 |
+-----------+--------+-------------+----------+
```

Sinais por dia UTC (q01 bloco 3) — o spot entra **no dia em que o caminho spot subiu**, 08/09, e
some depois das 22:32Z de 09/09 (o `market-worker` parou de publicar vela spot; não investigado
aqui):

```
+------------+-------------+-------------+---------------+
|    dia     | sinais_spot | sinais_perp | simbolos_spot |
+------------+-------------+-------------+---------------+
| 2026-09-01 |           0 |         102 |             0 |
| ...        |             |             |               |
| 2026-09-07 |           0 |        1734 |             0 |
| 2026-09-08 |          93 |        2041 |            17 |
| 2026-09-09 |         247 |        3304 |            17 |
| 2026-09-10 |           0 |         136 |             0 |
+------------+-------------+-------------+---------------+
```

**340 sinais** em linha spot no total. Onze versões participaram; entre elas as **duas linhas
`paper`** (q04): `momentum v3` com 44 sinais spot e `mean_reversion v14` com 7.

### 1.2 Todo desfecho spot sai sem R — os 133 de 133

```
+---------------------------------------------+-----------+-----------+-----------+-----------------+
|                   coorte                    |   tipo    | desfechos | terminais | terminais_sem_r |
+---------------------------------------------+-----------+-----------+-----------+-----------------+
| prospective                                 | perpetual |      8318 |      6557 |              76 |
| prospective                                 | spot      |       340 |       133 |             133 |
```

E o motivo é sempre o mesmo (q01 bloco 1):

```
| perpetual | (sem motivo)                                     |      6481 |  6481 |
| perpetual | funding_missing:<instante>  (26 motivos)          |    …   70 |     0 |
| perpetual | funding_ambiguous_exit                           |         6 |     0 |
| spot      | funding_schedule_unknown                         |       133 |     0 |
```

A causa é estrutural, não um buraco de dado: `funding_rates` tem 8 235 linhas e **zero** para
mercado spot — não pode ter outra coisa, um mercado à vista não liquida funding.

```
+-----------+----------------+----------+
|   tipo    | linhas_funding | mercados |
+-----------+----------------+----------+
| perpetual |           8235 |      298 |
+-----------+----------------+----------+
```

O caminho: `settle.settle` chama `repo.load_funding` (nenhuma linha) → `funding.resolve_funding`
recebe `history = []` → `_cadence([])` devolve `None` porque `len(distinct) < 2` →
`FundingReading(None, "funding_schedule_unknown", 0, None)` → `settle` grava `r_multiple = NULL` e
`meta.r_net_reason`. **`_cadence` está certa**: ela responde "não sei a cadência deste mercado", e
essa é a resposta honesta para uma pergunta que não devia ter sido feita a um mercado spot.

### 1.3 A duplicação: a mesma aposta contada duas vezes

**179 trios (versão, símbolo, barra de observação) foram decididos nas duas linhas** de `markets`
(q01 blocos 4 e 5) — NEAR e ZEC de 09/09 são os casos que o D-P9 viu (`NEARUSDT`, barra 21:30Z, sete
versões nas duas linhas). Qualquer "aposta única" por `market_id` conta essas 179 duas vezes.

Efeito no Placar, medido pelo código e não suposto: `lab_scoreboard._evaluable_rows` filtra
`r_multiple is not None`, então os 133 desfechos spot **não** entram na régua 100/30 nem em
expectancy/PF — eles entram nas contagens de cobertura ("desfechos", "sem R por funding"), onde
aparecem sob um rótulo errado ("funding não apurável" em vez de "mercado sem funding"), e nas
contagens de decisão por versão. O Placar vive em `apps/**`, fora do escopo desta tarefa.

---

## 2. A decisão: o universo de decisão do Lab é só o perpétuo (opção **a** do brief)

Os documentos **não são silenciosos**, e dizem (a) em três lugares:

1. `docs/PIPELINE.md` §1d item 1: o caminho spot existe como **preço de execução da carteira**,
   "enquanto todo o resto do pipeline (Feature/Anomaly/Regime/Opportunity/**Agents**) continua
   raciocinando só sobre o perpétuo";
2. `docs/PIPELINE.md` §1d item 7: "o scanner não consome spot" — e o descarte é feito na porta,
   antes de coalescer o lote (`touch_batch_handler`). O precedente da forma da correção é esse;
3. o replay **sempre** restringiu a `MarketType.PERPETUAL`
   (`hunter_strategy_worker/replay/plan.py:137`), e `repo.load_market` documenta o default
   `PERPETUAL` como "that is what the shadow lab trades today".

E o argumento decisivo do lado da carteira, que é o que o brief teme perder: **um sinal `paper`
nunca precisou nascer numa linha spot para ser executável numa.** A ponte de execução mapeia o
sinal perpétuo para o par spot da mesma exchange e base/quote e reescala os níveis congelados
(`bridge_universe.spot_pair_for` + `Screened._scaled`, `1000SHIBUSDT` → `SHIBUSDT`), e recusa por
nome quando o par não existe (`spot_pair_unavailable`). Ou seja: com (a) a linha paper continua com
o mesmo funil de candidatos que ela sempre teve, e passa a ter **R em todos os desfechos**, que é o
que o brief pede. Conferido também que **nenhuma posição jamais foi aberta** (`positions` está
vazia), então (a) não muda comportamento de carteira nenhum.

**Por que não (b).** Resolver funding como zero num mercado spot conserta o R e deixa de pé tudo o
que está errado antes dele: a mesma aposta contada duas vezes, custos assumidos calibrados no
perpétuo aplicados a um livro spot, e features de derivativos (funding, OI) legitimamente ausentes
alimentando estratégias que as leem. Além disso, hoje seria **código morto**: com (a) nenhum caminho
cria decisão em linha spot (o replay já é perpétuo-only) e **não há nenhum acompanhamento spot
aberto** para liquidar — os 340 desfechos spot estão todos finais (133 `terminal`, 207 `no_entry`,
**0** `active`/`pending_entry`). Pesquisar spot de propósito é outra tarefa, com modelo de custo
próprio: funding zero **com nome**, custos assumidos do spot e uma regra de deduplicação contra o
gêmeo perpétuo. Até lá a recusa é fail-closed **e contada**, nunca silenciosa.

### 2.1 A correção

`services/strategy-worker/hunter_strategy_worker/consumer.py`, em `handle_candle`, logo depois do
`is_final` e **antes** de resolver a linha de `markets`:

```python
if candle.market_type is not DECISION_MARKET_TYPE:
    # Not in the decision universe at all — refused before the market row is
    # even resolved, so it costs one comparison and not one query per bar.
    shadow_bars_skipped_total.labels(reason=f"market_type:{candle.market_type.value}").inc()
    return
```

`DECISION_MARKET_TYPE = MarketType.PERPETUAL`, com o porquê documentado no módulo.
`hunter_shadow_bars_skipped_total{reason}` é nova (`metrics.py`): uma barra que nunca chega a uma
versão não é avaliação de estado nenhum, então não podia entrar em `shadow_evaluations_total` — e
não podia ficar invisível.

Não foram tocados: as sete módulos do fecho de `code_ref` (`hunter_core/strategies/{aggregate,
base,canonical,envelope,indicators,numeric,schema}.py`), `funding.py`, `settle.py`, `decide.py`,
`record.py`, nenhum parâmetro de versão, nenhuma migração. A não-antecipação é a mesma: a guarda é
uma propriedade da própria vela, não lê relógio nem série.

### 2.2 Os testes

`services/strategy-worker/tests/test_spot_not_in_shadow_universe.py` — 5 unitários (sem banco) e 1
testcontainer:

- a barra spot não é avaliada por versão nenhuma e não incrementa `evaluated_bars`;
- a barra spot **não resolve nem a linha de `markets`** (a recusa é anterior ao banco);
- a recusa é contada em `hunter_shadow_bars_skipped_total{reason="market_type:spot"}`;
- controle: a barra **perpétua do mesmo símbolo** continua decidindo;
- compatibilidade: payload sem `market_type` (anterior à T3.0c) significa perpétuo e decide;
- integração (Postgres real): a mesma série que faz `volume_anomaly_v1` disparar, inserida na linha
  spot **e** na perpétua, produz `0/0/0/0` (sinal/desfecho/episódio/outbox) quando a vela entregue é
  spot e `1/1/1/1` quando é perpétua, com o `market_id` do sinal igual ao da linha perpétua. O
  controle no mesmo teste é o que prova que o zero é a guarda e não uma fixture inerte.

TDD: os três primeiros unitários foram escritos antes e falharam pelo motivo certo —
`assert wired["markets"] == []` recebia `[('binance', 'BTCUSDT', <MarketType.SPOT: 'spot'>)]`.

---

## 3. `late:delay` — o denominador escondido é atraso de processamento, não mercado

**O que a palavra significa no código.** `plan.py::plan_entry` escolhe `entry_bar_open =
next_minute_open(decision_at)` (o primeiro minuto que abre estritamente depois da decisão) e calcula
`delay_s = entry_bar_open − source_bar_close`; se `delay_s > costs.max_entry_delay_s` (120 s,
congelado na versão), o desfecho nasce `no_entry` com `late:delay`. Note o que **não** está nessa
conta: preço. Nenhum termo dela olha para onde o mercado foi — `late:delay` diz que **a decisão
chegou tarde à barra**, e como `entry_bar_open` é o minuto seguinte à decisão, isso é equivalente a
"o worker levou mais de ~60 s desde o fechamento da barra de referência até persistir a decisão". A
leitura do D-P9 §2.1 ("o preço fugiu da zona antes dos 120 s de janela de entrada") precisa ser
corrigida: é **lag de processamento**, não regra de mercado, e o irmão `late:missed_open` (2 casos)
é o caso em que o relógio já passou da abertura escolhida na hora de gravar. É um **sintoma
medido**, não um bug de uma linha: não há correção nesta tarefa.

**O tamanho.** `no_entry` por dia e por motivo (q02):

| dia UTC | sinais | `no_entry` | % | `late:delay` | `geometry` | `late:missed_open` |
|---|---|---|---|---|---|---|
| 06/09 | 1 237 | 49 | 4,0 % | 18 | 31 | 0 |
| 07/09 | 1 633 | 19 | 1,2 % | 10 | 9 | 0 |
| 08/09 | 2 118 | 129 | 6,1 % | 105 | 24 | 0 |
| **09/09** | **3 534** | **1 669** | **47,2 %** | **1 637** | 30 | 2 |
| 10/09 (parcial) | 136 | 73 | **53,7 %** | 73 | 0 | 0 |

E a causa, medida diretamente (q03, `emitted_at − supporting_features.observation_ts`):

| dia UTC | atraso médio | mediana | p95 | máx |
|---|---|---|---|---|
| 01–05/09 | 2,0 s | 2,0 s | 2,0 s | 2,0 s |
| 06/09 | 15,6 s | 10,3 s | 34,1 s | 276,4 s |
| 07/09 | 15,4 s | 11,8 s | 36,4 s | 290,1 s |
| 08/09 | 37,9 s | 21,8 s | 118,5 s | 299,6 s |
| **09/09** | **115,3 s** | **107,9 s** | **263,8 s** | 298,8 s |
| 10/09 | 134,0 s | 125,1 s | 221,6 s | 281,9 s |

A mediana cruzou os 60 s e por isso metade das decisões nasce morta. O teto de ~300 s nos máximos
não é coincidência: acima de `eligibility_max_lag_s` (300 s, `config.py`) a barra é recusada como
`unavailable` e **não vira sinal nenhum** — ou seja, o denominador verdadeiro é maior do que a
tabela acima e a parte que falta **não está na base**, só no contador
`hunter_shadow_evaluations_total{state="unavailable"}` do worker. O suspeito natural do crescimento
é o custo por barra do roster (q03 bloco 3: de 14 versões em 12 mercados em 01/09 para **21 versões
em 232 mercados** em 09/09); confirmar isso exige o log/métrica do worker, não SQL. Retirar o spot
do universo devolve ~10 % das velas de decisão (18 mercados spot monitorados contra 200 perpétuos),
o que **ajuda e não resolve**.

---

## 4. Ressalvas honestas

- Nenhum reprocessamento: as 340 linhas spot continuam na base com `r_multiple` nulo. Toda leitura
  de pesquisa da janela 08–09/09 precisa filtrar `markets.market_type = 'perpetual'`, inclusive as
  do D-P9.
- Não medi por que o spot parou de gerar sinal depois de 09/09 22:32Z (nenhum sinal spot em 10/09).
  Pode ser o `MARKET_SPOT_ENABLED`, o shard 0 ou a banda de saída do universo spot — fora do escopo.
- A guarda vale para **toda** vela não-perpétua, não só spot: se um terceiro `market_type` existir
  um dia, ele é recusado com o próprio nome no contador, nunca aceito por omissão.
- A correção só passa a valer na VPS depois do deploy; até lá o número de sinais spot pode crescer.

---

## 5. Arquivos tocados/criados (a árvore é compartilhada — abaixo só o que é desta tarefa)

```
 M docs/PIPELINE.md
 M obsidian/07-BUGS/Open Bugs.md
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/metrics.py
?? .claude/state/brief-T3.73-spot-no-shadow.md
?? .claude/state/notes-T3.73.md
?? infra/scripts/sql/research/2026-09-10-t373-q00-spot-vs-perp.sql
?? infra/scripts/sql/research/2026-09-10-t373-q01-spot-sem-r.sql
?? infra/scripts/sql/research/2026-09-10-t373-q02-no-entry.sql
?? infra/scripts/sql/research/2026-09-10-t373-q03-late-delay.sql
?? infra/scripts/sql/research/2026-09-10-t373-q04-linha-paper.sql
?? services/strategy-worker/tests/test_spot_not_in_shadow_universe.py
```

`git diff --stat` dos quatro modificados (só hunks desta tarefa, conferido com `git diff -U0`):
`docs/PIPELINE.md +2`, `obsidian/07-BUGS/Open Bugs.md +42/-1`,
`consumer.py +38`, `metrics.py +12`.

## 6. Comandos de qualidade (saída real)

```
$ uv run pytest services/strategy-worker/tests/test_spot_not_in_shadow_universe.py -q
......                                                                   [100%]
6 passed in 35.01s

$ uv run pytest services/strategy-worker/tests -q -m unit
288 passed, 325 deselected in 12.70s

$ uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
15 passed in 119.90s (0:01:59)
  (a suíte que exercita `handle_candle` de ponta a ponta contra Postgres/Redis reais)

$ uv run ruff check services/strategy-worker/
All checks passed!

$ uv run ruff format --check services/strategy-worker/
119 files already formatted

$ uv run pyright services/strategy-worker
2 errors, 0 warnings, 0 informations
  (os dois são pré-existentes em tests/test_replay_stress.py:35, reportPrivateUsage)

$ uv run python infra/scripts/check_file_size.py
error   377 > 350  apps/api/hunter_api/services/orders.py
scanned 592 files; 1 over budget, 0 grandfathered
  (pré-existente, de outra frente em `apps/**`; nenhum arquivo desta tarefa passa do orçamento:
   consumer.py 327, metrics.py 125)
```
