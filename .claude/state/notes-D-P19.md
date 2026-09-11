# notes-D-P19 — a meta de R$ 9.000/dia em DINHEIRO: por mercado, por hora, e o que ela exige

**Data:** 2026-09-11 (Brasília, UTC−3; UTC como detalhe). **Owner:** risk-engine-guardian.
**Origem:** plantão run 7, faixa 3, item 2 (`sentinel-trader-research`) →
`.claude/state/plantao/2026-09-11-0445-lane3.md`; primeiro da fila da Astra em
`obsidian/00-INBOX/Hipoteses-do-plantao.md`.
**Base:** `main` em `6fa5c7b` — árvore compartilhada, **nada commitado**. Nada tocado em `apps/`,
`services/`, `packages/`. **Nenhum limite alterado; `packages/risk-core` não recebeu uma linha.**
**VPS estritamente somente leitura**: toda consulta dentro de
`begin transaction isolation level repeatable read read only; … commit;` entregue pelo stdin de
`psql`. Nenhum container parado ou recriado. Nenhum `.env*` tocado. Nenhum shell em segundo plano;
todo comando em primeiro plano com `timeout 290`. Nenhum testcontainer.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Distribuição do volume de 1 min por hora do dia (p10/p50/p90), 30 dias, 16 mercados + gêmeo SPOT | **OK** — `volume_por_hora.csv` (§3); SPOT com a ressalva da cobertura (§9.1) |
| 2 | Notional máximo que a participação permite (1 % do minuto) | **OK** — `teto_por_mercado_hora.csv`, `resumo_por_mercado.csv` (§4) |
| 3 | Distância de stop que a família usa (mediana `initial_risk`/entrada, por mercado) | **OK** — `stops_e_apostas.csv`, q02 (§2) |
| 4 | Máximo de R em BRL por aposta (notional × stop%) | **OK** — §4, coluna `r_brl` |
| 5 | Máximo de BRL/dia com apostas únicas/dia e acerto medidos | **OK** — §5, `cenarios.csv` |
| 6 | O mesmo para participação 2 % e 5 % (sensibilidade) e para as escalas da T3.60 | **OK** — §6; `limits.py` **não** foi tocado |
| 7 | Modelo de impacto raiz-quadrada como coluna de sensibilidade, rotulada | **OK** — §7, `impacto_na_meta.csv`; `k` varrido, nunca importado como verdade |
| 8 | Entregas (`exp-drafts/dp19/`, SQL, notas, apêndice, INBOX) | **OK** — §1 |

**Resposta curta.** Com os limites de hoje, o universo executável de hoje e a família de hoje, o
**teto** (não o esperado: *toda* aposta fechando +1 R) é **R$ 393,60/dia** sobre R$ 100 mil nos 16
perpétuos, e **R$ 157,41/dia** se a execução for no SPOT, que é onde a carteira compra. O **esperado**
com o R medido da família é **−R$ 310,58/dia** (perpétuo) e **−R$ 137,56/dia** (SPOT). A meta pede
**23 vezes** o teto e tem sinal trocado em relação ao esperado. A trava dura não é a participação
sozinha: **`max_concurrent_positions = 5` com horizonte de 4 h limita a carteira a 30 entradas por
dia**, então R$ 9.000/dia exige 1 R entre **R$ 300 e R$ 6.000** conforme a expectancy — e mesmo no
cenário generoso de R̄ = +0,20 R isso é um notional de **13.858 USDT**, que pede **R$ 709 mil de
patrimônio** (teto de 10 % por moeda) e um minuto de **1,39 M USDT** que só **BTC e ETH** têm.
Subir a participação de 1 % para 5 % **não resolve e piora o esperado**: com expectancy negativa,
tamanho maior é prejuízo maior (−R$ 310,58 → −R$ 434,76 em R$ 100 mil).

**CONCERNs em uma linha cada (detalhe na §9):** (1) o SPOT só tem 4 dias de velas de 1 min, contra 30
do perpétuo; (2) a família só tem **3 dias** de coorte prospectiva e **22 apostas únicas** dentro dos
16 mercados — nenhum p10/p50/p90 de resultado é distribuição; (3) o `r_medio` de 8 dos 16 mercados é
herdado da família porque eles não tiveram uma única aposta; (4) `book_depth`, `aggregate_risk` e β
ficaram de fora dos tetos (todos empurram o tamanho **para baixo**, então os números são **teto
superior**); (5) o `k` do modelo raiz-quadrada não é nosso e não foi calibrado; (6) o volume de 24 h
que eu meço das velas diverge de `markets.volume_24h_usd` em alguns pares (PROM: 106 M contra 14,4 M)
— reporto os dois, não escolho; (7) o giro de 30 entradas/dia supõe o horizonte de 4 h da família,
não uma medição de tempo em posição.

---

## 0. LEITURA PRÉVIA

`docs/RISK_ENGINE.md` v2.4 (§1 insumos e o D1 "SPOT executa, o perpétuo decide"; §2 o perfil
`paper_v1`; §3 a ordem dos checks; §4 o sizing, os nove tetos, a `CAP_ORDER` e a janela da referência
de volume; §5 o kill switch e o dia de São Paulo; §7 falhar fechado; §11 escopo de capital),
`docs/PIPELINE.md` §7–§8 e `docs/ARCHITECTURE.md` §6. Do lado da pesquisa: `notes-T3.60.md` (a conta
de 09/09 e o 1 R = R$ 34,48), `notes-T3.78.md` (o schema de `lab/daily-goal`, o dedupe e o percentil
nearest-rank), `notes-D-P9.md` (a hora 21Z e "9 apostas, não 39"),
`.claude/state/proposta-carteira-2026-09-09.md`.

**O que a T3.60 já tinha e esta nota estende.** Lá: o universo de 253 mercados, dois dias de coorte,
o minuto de cada entrada, e a conclusão "1 R = R$ 34,48; R$ 9.000/dia pediria 1 R = R$ 3.719". Aqui:
os **16 mercados que o Lab de fato observa** desde a T3.82, **30 dias** de volume em vez do minuto de
cada sinal, a distribuição **por hora de Brasília**, o **gêmeo SPOT** (onde a carteira executa) e a
inversão feita contra o **teto estrutural das vagas**, que a T3.60 não usou. As duas conclusões são
compatíveis: o 1 R de R$ 3.719 da T3.60 é, nesta conta, o ponto R̄ ≈ +0,08 da tabela da §5.

---

## 1. Arquivos

**SQL (somente leitura, cada um executável sozinho, `infra/scripts/sql/research/`):**
- `2026-09-11-dp19-q00-catalogo.sql` — corte, os 16 mercados + gêmeos SPOT, cobertura de velas, câmbio, a família
- `2026-09-11-dp19-q01-volume-por-minuto.sql` — dump CSV do `quote_volume` de cada minuto, 30 dias
- `2026-09-11-dp19-q02-stop-por-mercado.sql` — `d_stop` por mercado (p10/p50/p90) e o custo declarado
- `2026-09-11-dp19-q03-apostas-por-dia.sql` — apostas únicas por dia/mercado, R, acerto
- `2026-09-11-dp19-q04-stops-e-apostas-csv.sql` — o mesmo em CSV, uma linha por mercado + a família
- `2026-09-11-dp19-q05-apostas-por-hora-csv.sql` — apostas únicas por hora de Brasília

**Análise (rascunho, fora de produção, `.claude/state/exp-drafts/dp19/`):**
- `meta_em_dinheiro.py` — a aritmética pura em `Decimal` (percentis, referência de volume, tetos, 1 R, impacto)
- `test_meta_em_dinheiro.py` — 23 casos (§8)
- `roda.py` — a manivela: lê os dumps, escreve as tabelas
- `volume_1m.csv.gz` (759.400 minutos), `stops_e_apostas.csv`, `apostas_por_hora.csv` — dumps da VPS
- `volume_por_hora.csv`, `teto_por_mercado_hora.csv`, `resumo_por_mercado.csv`, `teto_por_hora.csv`,
  `cenarios.csv`, `o_que_falta.csv`, `impacto_na_meta.csv` — as tabelas
- `q00.out`, `q02.out`, `q03.out`, `roda.out`, `pytest.out` — saída real

**Texto:** este arquivo; a seção "D-P19: a meta em dinheiro" em
`.claude/state/proposta-carteira-2026-09-09.md`; a linha D-P19 em `obsidian/00-INBOX/Hipoteses-do-plantao.md`.

**Cortes declarados:** `q00` **05:05 BRT** (08:05Z); `q01` (o dump de volume) **05:07 BRT**;
`q02` **05:10 BRT**; `q03`/`q04` **05:14 BRT**; `q05` **05:19 BRT**. Câmbio:
`fx_observations` `USDTBRL = 5,1198`, observado **05:05:35 BRT** (`binance.spot.ticker`).
R$ 100.000 = **19.532,01 USDT** nesta taxa (a T3.60 usou 19.333,01 a 5,1725).

---

## 2. A distância de stop que a família usa — q02, `stops_e_apostas.csv`

859 desfechos prospectivos terminais da família `mean_reversion*` nos últimos 30 dias (que na prática
são **3 dias**: 08, 09 e 10/09 BRT).

```
familia inteira:  n=859   d_stop p10=1,048 %   p50=2,114 %   p90=4,538 %
                  abaixo do piso de 0,3 %: 0      acima do teto de 3 %: 238 (27,7 %)
```

**Um em cada quatro sinais da família nasce com stop fora da banda `[0,3 %; 3 %]` do perfil** e seria
recusado pelo check 8 antes de qualquer conta de dinheiro. Dentro dos 16 mercados executáveis os
stops são mais estreitos (mercados mais fundos, ATR menor):

| mercado | n desfechos | d_stop p50 | apostas únicas (3 d) | R̄ medido |
|---|---|---|---|---|
| XRPUSDT | 1 | 0,705 % | 1 | +0,075 |
| SAHARAUSDT | 1 | 0,914 % | 1 | +0,973 |
| ZECUSDT | 19 | 1,393 % | 6 | **−0,994** |
| NEARUSDT | 15 | 1,503 % | 5 | **−0,713** |
| PROMUSDT | 10 | 1,529 % | 3 | −0,205 |
| DASHUSDT | 7 | 1,724 % | 1 | +1,515 |
| TAOUSDT | 9 | 2,096 % | 2 | +0,022 |
| **os outros 9** | **0** | — (usa a mediana da família, 2,114 %) | **0** | — |

**Nove dos dezesseis mercados do universo executável não receberam uma única aposta em três dias**
(ARB, BNB, BTC, DOGE, ETH, LINK, SOL, SUI, UNI). O `d_stop` deles nesta nota é a mediana da família,
sempre rotulado na coluna `fonte_d_stop` — nunca um número sem procedência.

**Custo:** `hunter_risk.sizing.round_trip_cost_fraction` sobre o `meta.assumed_costs` do Lab
(fee 4 bps, spread 2 bps, slippage 5 bps) = **0,0020**. `d_efetiva = d_stop + 0,0020` é o denominador
do teto de risco; o dinheiro de 1 R usa `d_stop` puro, porque o `r_multiple` do Lab tem denominador
`|entrada − stop|` **sem** custo (identidade da T3.60 §2). Os dois R nunca são somados.

---

## 3. O volume do minuto por hora de Brasília — `volume_por_hora.csv`

30 dias completos (43.199 minutos) por perpétuo; o SPOT tem 4 dias (§9.1). A referência que o motor
usa não é o minuto cru: é `min(último minuto completo, mediana das 30 barras completas)` (§4 do
contrato), recomputada minuto a minuto, com **janela incompleta virando indisponibilidade** — está em
`referencias_de_volume`, com teste de buraco na janela.

BTCUSDT perpétuo, referência em USDT por minuto (p10 / p50 / p90 por hora):

| hora BRT | ref p10 | ref p50 | ref p90 |
|---|---|---|---|
| 05 | 760.441 | 3.216.589 | 11.481.304 |
| **11** | 990.743 | **7.148.139** | 20.616.077 |
| 13 | 1.542.044 | 4.582.121 | 12.550.493 |
| **18** | 497.753 | **1.498.985** | 6.106.385 |

**Duas leituras que valem para os 16:** (i) a hora manda — o minuto mediano das 11 h BRT é **4,8×** o
das 18 h; (ii) **dentro** de uma mesma hora o p90 é 10–15× o p10, então o teto de participação de um
minuto ruim é uma ordem de grandeza menor que o de um minuto bom. Quem dimensiona contra "o volume
médio" está dimensionando contra um número que quase nunca acontece.

E a hora em que a família aposta é a hora de **menor** capacidade:

```
teto_por_hora.csv (16 perpétuos, participação 1 %, R$100 mil) — 1 R mediano entre os 16:
  hora 11 BRT: R$ 87,95     hora 12: R$ 82,52     hora 13: R$ 78,98
  hora 16 BRT: R$ 39,58     hora 17: R$ 39,46     hora 18: R$ 37,21
apostas únicas da família nos 16, por hora (q05): 16 h → 3, 17 h → 7, 18 h → 4
```

**14 das 22 apostas (64 %) caem entre 16 h e 18 h BRT, onde 1 R vale menos da metade do que valeria
às 11 h.** Não é recomendação de "operar às 11 h" — n = 22 não sustenta regra nenhuma —, é a medida de
que giro e capacidade estão **anticorrelacionados** nesta família.

---

## 4. O notional que os tetos permitem, e quanto é 1 R em reais — `resumo_por_mercado.csv`

Um lance isolado numa carteira vazia, participação 1 %, patrimônio R$ 100 mil (19.532,01 USDT),
referência = p50 da hora agregada do dia:

| mercado (perp) | ref p50 (USDT/min) | notional | **quem limita** | 1 R |
|---|---|---|---|---|
| BTCUSDT | 2.738.488 | 1.953,20 | `asset_exposure` | **R$ 211,42** |
| ETHUSDT | 2.125.219 | 1.953,20 | `asset_exposure` | R$ 211,42 |
| SOLUSDT | 546.793 | 1.953,20 | `asset_exposure` | R$ 211,42 |
| ZECUSDT | 402.103 | 1.953,20 | `asset_exposure` | R$ 139,28 |
| XRPUSDT | 299.760 | 1.953,20 | `asset_exposure` | R$ 70,50 |
| DOGEUSDT | 121.896 | 1.218,96 | `market_participation` | R$ 131,94 |
| BNBUSDT | 94.442 | 944,42 | `market_participation` | R$ 102,23 |
| SUIUSDT | 67.729 | 677,29 | `market_participation` | R$ 73,31 |
| LINKUSDT | 49.487 | 494,87 | `market_participation` | R$ 53,57 |
| UNIUSDT | 49.064 | 490,64 | `market_participation` | R$ 53,11 |
| NEARUSDT | 42.948 | 429,48 | `market_participation` | R$ 33,04 |
| TAOUSDT | 30.870 | 308,70 | `market_participation` | R$ 33,13 |
| PROMUSDT | 13.720 | 137,20 | `market_participation` | R$ 10,74 |
| DASHUSDT | 12.079 | 120,79 | `market_participation` | R$ 10,66 |
| ARBUSDT | 11.867 | 118,67 | `market_participation` | R$ 12,85 |
| SAHARAUSDT | 704 | 7,04 | `market_participation` | **R$ 0,33** |

**Correção fina à T3.60, e ela importa.** No universo de 253 mercados quem mandava era a participação
em 24 de 27 entradas. **Nos 16 mercados executáveis, em 5 deles (BTC, ETH, SOL, ZEC, XRP) quem manda
já é o `max_asset_exposure_pct` de 10 %** — o teto do *nosso* patrimônio, não o do mercado. Isso muda
a alavanca: nesses cinco, **mais capital compra mais tamanho**; nos outros onze, não compra nada.
`SAHARAUSDT` é o caso extremo do outro lado: notional de **7,04 USDT** — passa raspando o
`min_notional` de 5 USDT — e 1 R vale **33 centavos**. A ordem existe; o dinheiro, não.

**E a carteira compra no SPOT** (`max_leverage = 1`, D1). O minuto SPOT é uma fração do perpétuo:
BTC 323.779 contra 2.738.488 (11,8 %), ETH 223.695 contra 2.125.219 (10,5 %), ZEC 77.343 contra
402.103 (19,2 %). No SPOT só **BTC e ETH** chegam a ter o `asset_exposure` como limitante; nos outros
onze a participação morde, e o 1 R mediano cai de **R$ 53,57 para R$ 18,14**. Um mercado dos 13 com
vela SPOT (ARBUSDT, 45,6 M/dia medidos) fica **abaixo do piso de 50 M/24 h** do perfil e nem chega ao
sizing; DASH, LINK e TAO **não têm vela SPOT nenhuma** no banco.

---

## 5. O dinheiro por dia: teto e esperado, lado a lado — `cenarios.csv`, `o_que_falta.csv`

A forma é a que a Astra pediu: `lucro/dia = câmbio × Σᵢ Nᵢ × notionalᵢ × d_stopᵢ × R̄ᵢ`, por mercado,
com apostas **únicas** (dedupe `(market_id, source_bar_close)`, vence a versão com `activated_at`
mais antigo — T3.78) e o R̄ medido de cada mercado. Denominador de dias: **3** (08–10/09 BRT).

Participação 1 % (o limite vigente), R$ 100 mil:

| universo | apostas/dia | **teto** R$/dia (tudo +1 R) | **esperado** R$/dia (R medido) | 1 R mediano |
|---|---|---|---|---|
| 16 perpétuos | 6,33 | **+393,60** | **−310,58** | R$ 53,57 |
| 16 SPOT (só o sinal que nasceu no SPOT) | 1,00 | +31,58 | −3,13 | R$ 18,14 |
| **16 SPOT executando o sinal do perpétuo** | 5,33 | **+157,41** | **−137,56** | R$ 18,14 |

A linha do meio da tabela é a que vale para a carteira: o perpétuo decide, o SPOT executa. **R$ 157
de teto, R$ −138 de esperado.** A meta é **57×** esse teto.

**O teto que ninguém tinha colocado na conta: as vagas.** `max_concurrent_positions = 5` com o
horizonte de 4 h da família (`meta.horizon_s = 14400`) dá **5 × 6 = 30 entradas por dia**, no
máximo, haja quantos sinais houver. Invertendo a meta contra esse teto (participação 1 %, `d_stop`
mediano da família de 2,114 %):

| R̄ hipotético | 1 R necessário | notional | minuto necessário | mercados dos 16 que têm | patrimônio necessário (teto de 10 %/moeda) |
|---|---|---|---|---|---|
| +0,05 | R$ 6.000 | 55.431 USDT | 5,54 M USDT | **0** | R$ 2.837.981 |
| +0,10 | R$ 3.000 | 27.716 USDT | 2,77 M USDT | **0** | R$ 1.418.991 |
| +0,20 | R$ 1.500 | 13.858 USDT | 1,39 M USDT | **2** (BTC, ETH) | R$ 709.495 |
| +0,40 | R$ 750 | 6.929 USDT | 693 k USDT | 2 | R$ 354.748 |
| +1,00 (fantasia) | R$ 300 | 2.772 USDT | 277 k USDT | 5 | R$ 141.899 |

**O R̄ medido da família hoje é −0,0994** (191 apostas únicas, 3 dias, soma −18,19 R; acerto
44,3 % = 81/183). Nenhuma linha da tabela acima existe com sinal negativo: **com expectancy ≤ 0 não há
tamanho positivo que resolva** — só há prejuízo maior.

O teto aritmético absoluto do universo, para fechar a moldura: uma aposta em **cada** um dos 16, em
**cada** hora do dia (384 apostas/dia — 12,8× o que as vagas permitem), **todas** fechando +1 R, dá
**R$ 33.032,80/dia** no perpétuo e **R$ 16.545,65/dia** no SPOT a 1 %/R$ 100 mil. É o limite superior
absoluto; a meta cabe **dentro** dele, e é só isso que ele diz.

---

## 6. Sensibilidade de participação (2 %, 5 %) e de escala — **`limits.py` intocado**

`max_participation_pct` continua **0,01**. As linhas abaixo são cenário, como no brief; 5 % é o
`participation_cap` do `sentinel-trader-research`, que é **hipótese do autor**, não capacidade
provada.

| participação | patrimônio | teto R$/dia | esperado R$/dia | 1 R mediano |
|---|---|---|---|---|
| 1 % | R$ 100 k | +393,60 | **−310,58** | R$ 53,57 |
| 1 % | R$ 400 k | +701,08 | −602,74 | R$ 53,57 |
| 2 % | R$ 100 k | +485,17 | −346,06 | R$ 106,22 |
| 2 % | R$ 400 k | +1.369,49 | −1.172,98 | R$ 107,13 |
| 5 % | R$ 100 k | +734,91 | −434,76 | R$ 165,63 |
| 5 % | R$ 400 k | +1.666,00 | **−1.277,78** | R$ 267,83 |

(16 perpétuos; a tabela SPOT está em `cenarios.csv`.)

Três leituras:

1. **Quintuplicar a participação multiplica o teto por 1,87, não por 5** — nos cinco mercados fundos
   quem limita é o patrimônio, e afrouxar participação não os toca.
2. **Quadruplicar o capital com participação 1 % multiplica o teto por 1,78** — o mesmo efeito da
   T3.60 (R$ 107 → R$ 261), agora com o mecanismo nomeado: só os cinco mercados `asset_exposure`
   escalam.
3. **Todas as combinações pioram o esperado**, porque o sinal do R̄ é negativo. A combinação mais
   agressiva da tabela (5 % e R$ 400 mil) é a que **mais** perde: −R$ 1.277,78/dia.

Mesmo a célula mais generosa (5 %, R$ 400 mil) entrega **18,5 %** da meta no teto, com 100 % de
acerto e nenhuma perda — que é uma hipótese impossível, não um cenário.

---

## 7. Impacto raiz-quadrada — **SENSIBILIDADE, rotulada** — `impacto_na_meta.csv`

`slippage ≈ k·√(notional/ADV)` é o modelo escrito em `sentinel/carry/capacity.py`. O autor **não
publica o `k` calibrado**, e a Astra registrou que os coeficientes de custo dele não fecham como
decomposição aditiva (+0,035 → −0,091 implica 0,126 R de taxa; −0,091 → −0,243 implica 0,152 R, não
os 0,187 R declarados). Então: `k` entra como **grade declarada**, a coluna é rotulada, e nenhum
número daqui vira limite. Impacto no notional que a meta pediria (13.858 USDT, cenário R̄ = +0,20):

| mercado | ADV medido (USDT) | k=0,1 | k=0,3 | k=1,0 |
|---|---|---|---|---|
| BTCUSDT | 11,51 bi | 1,10 bps | 3,29 bps | 10,97 bps |
| ETHUSDT | 8,81 bi | 1,25 | 3,76 | 12,54 |
| ZECUSDT | 1,52 bi | 3,02 | 9,07 | 30,23 |
| NEARUSDT | 177,7 M | 8,83 | 26,49 | 88,30 |
| DASHUSDT | 93,9 M | 12,15 | 36,44 | 121,47 |
| SAHARAUSDT | 5,4 M | 50,45 | 151,35 | **504,49** |

Réguas: o custo de ida e volta que o Lab já cobra é **20 bps**; o `max_slippage_pct` do perfil é
**10 bps**. Leitura honesta: **nos tamanhos que os limites de hoje autorizam** (118 a 1.953 USDT) o
impacto raiz-quadrada fica em 0,4–5 bps com k=0,3 — ele **não** é o que nos impede de ganhar. Ele
passa a morder exatamente no tamanho que a **meta** exigiria, e só nos mercados finos: nos dois
únicos mercados que comportam o minuto necessário (BTC, ETH) o impacto continua em 3–4 bps com
k=0,3. Barone & Lillo (item 7 do plantão, Hyperliquid, β = 0,303) diz que a raiz é **conservadora**
para tamanhos grandes e otimista para pequenos — mais um motivo para esta coluna ser sensibilidade e
não custo.

---

## 8. Testes — saída real

```
$ uv run pytest .claude/state/exp-drafts/dp19/test_meta_em_dinheiro.py -v
...
collected 23 items
... test_a_referencia_e_o_minimo_entre_o_ultimo_minuto_e_a_mediana_de_30 PASSED
... test_buraco_na_janela_invalida_a_referencia_em_vez_de_encolher_a_janela PASSED
... test_com_mercado_fino_quem_manda_e_a_participacao PASSED
... test_com_mercado_fundo_e_stop_largo_quem_manda_e_o_risco_por_operacao PASSED
... test_com_stop_mediano_o_teto_por_moeda_ja_passa_na_frente_do_risco PASSED
... test_empate_entre_tetos_resolve_pela_ordem_declarada_do_contrato PASSED
... test_referencia_de_volume_ausente_nao_vira_zero PASSED
... test_com_expectancy_negativa_o_dinheiro_do_dia_e_negativo_nao_zero PASSED
============================= 23 passed in 1.17s ==============================
```

Cada função pura tem caso que passa **e** caso que falha/degenera: população vazia levanta erro em vez
de devolver zero, janela incompleta ou com buraco **não** produz referência, `d_stop = 0` levanta em
vez de dividir por zero, ADV = 0 levanta. O empate entre tetos resolve pela `CAP_ORDER` do contrato,
não pela ordem do dicionário. `pytest.out` tem a saída completa.

---

## 9. CONCERNs

1. **O SPOT tem 4 dias, o perpétuo tem 30.** As velas SPOT começam em 07/09 (SAHARA em 10/09), e
   DASH, LINK e TAO não têm nenhuma. Toda linha SPOT desta nota é uma janela de 4 dias comparada com
   uma de 30 — a sazonalidade semanal não está lá. Os números SPOT são indicativos de **ordem de
   grandeza**, não distribuição.
2. **Três dias de família, 22 apostas nos 16 mercados.** 191 apostas únicas no total, das quais
   apenas 22 caem no universo executável (o resto veio do universo de 200 que a T3.82 desligou
   ontem). O R̄ por mercado tem n entre 1 e 6. **Nada aqui é veredito sobre a estratégia**; é a
   aritmética do dinheiro sobre o giro observado.
3. **Oito mercados herdam o `d_stop` da família e nove herdam o R̄.** Está na coluna
   `fonte_d_stop`/`fonte_r` de cada linha. Se a família passar a entrar em BTC/ETH/SOL, os números
   desses mercados mudam — e são justamente os que mais dinheiro comportam.
4. **Três tetos do motor ficaram de fora:** `aggregate_risk` (precisa do estado da carteira ao longo
   do dia — é o trabalho do `t360/carteira.py`), `book_depth` (precisa do livro; a KB-0070 cobre 11 s
   de ask) e `beta_exposure` (o β não existe em código, KB-0071). Os três só **reduzem** tamanho:
   todo número desta nota é **teto superior**.
5. **O `k` do impacto não é medido por nós** e não entra em lugar nenhum além da coluna rotulada.
6. **Dois volumes de 24 h convivem.** O meu (soma das velas de 1 min / dias cobertos) e
   `markets.volume_24h_usd`. Divergem em alguns pares (PROM: 106 M contra 14,4 M; SAHARA: 5,4 M
   contra 16,8 M; ARB SPOT: 45,6 M contra 21,6 M). O check `liquidity_24h` do motor usa o **segundo**;
   a coluna `passa_piso_50m` desta nota usa o **primeiro**. Reporto os dois e **não** escolho — é uma
   reconciliação que merece o seu próprio diagnóstico.
7. **As 30 entradas/dia supõem o horizonte declarado (4 h), não o tempo em posição medido.** Se a
   família sair antes (stop rápido), o giro pode ser maior; se travar em posição, menor. Medir tempo
   em posição por motivo de saída é a D-P21, não esta.
8. **A carteira paper continua sem executar.** Tudo aqui é simulação sobre sinais do Lab e velas
   reais; `orders = 0` na T3.60 e nada mudou nesse eixo.

---

## 10. Veredito em dez linhas

1. Nos 16 mercados executáveis, o motor autoriza entre **7 e 1.953 USDT** por entrada com R$ 100 mil.
2. Isso é **1 R entre R$ 0,33 (SAHARA) e R$ 211 (BTC/ETH/SOL)**; o mediano é **R$ 53,57**.
3. A família fez **6,33 apostas únicas/dia** nesses 16 mercados em três dias — e **nove deles ficaram zerados**.
4. Teto (tudo +1 R): **R$ 393,60/dia** no perpétuo, **R$ 157,41/dia** no SPOT, que é onde se compra.
5. Esperado com o R medido (−0,0994 por aposta): **−R$ 310,58/dia** e **−R$ 137,56/dia**.
6. Quem limita mudou: em BTC, ETH, SOL, ZEC e XRP já é o **teto de 10 % por moeda**, não a participação.
7. **`max_concurrent_positions = 5` × horizonte de 4 h = 30 entradas/dia** — o teto que faltava na conta.
8. R$ 9.000/dia com R̄ = +0,20 pede **1 R = R$ 1.500**, notional de **13.858 USDT**, minuto de **1,39 M USDT** (só BTC e ETH) e **R$ 709 mil** de patrimônio.
9. Participação 2 % ou 5 % multiplica o teto por 1,2–1,9 e **piora** o esperado; capital ×4 multiplica o teto por 1,78.
10. **A meta é decisão de capital, de universo e de expectancy — nesta ordem. Mais versões da mesma ideia não movem nenhum dos três.**
