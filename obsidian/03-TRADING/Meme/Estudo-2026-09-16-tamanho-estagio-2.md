---
tags: [trading, meme, pumpfun, estudo, risco, execucao, estagio-2, m4]
titulo: O que cabe em US$ 1 000 por operação sob os nossos próprios tetos — curva × pool
status: vivo
owner: sexta-feira
data: 2026-09-16
updated: 2026-09-16
tarefa: T4.29b
---

# Estudo — o que US$ 1 000 por operação realmente permite no pump.fun (16/09/2026)

**A pergunta (T4.29b):** o Everton autorizou o **estágio 2 = até US$ 1 000 por operação**, com clique
([[06-DECISIONS/2026-09-12-teste-pequeno-meme-real|a decisão de 12/09]]). Antes de alguém construir o estágio 2:
**com o nosso teto de participação (≤ 1 % do volume orgânico do último minuto), o nosso teto de impacto de preço
(≤ 0,5 %) e a matemática da curva, quantos minutos-moeda por dia admitem uma compra de 1 / 2 / 5 / 9,8 SOL?**

**Cotação usada:** `hb:meme:radar lab_sol_usd` = **97,4697 US$/SOL** (lido do Redis da VPS em 16/09 15:0x BRT).
Logo **US$ 1 000 = 10,26 SOL** hoje; os portões escritos falam em **9,8 SOL** (US$ 955,20 nesta cotação). Este
estudo usa **9,8 SOL** porque é o número do arquivo de portões; a conclusão não muda com 10,26.

**Resposta em uma linha, sem suavizar: zero.** Nem 9,8, nem 5, nem 2, nem **1 SOL** cabem em curva nenhuma sob o
nosso teto de impacto de 0,5 % — não é raridade, é **impossibilidade aritmética**. O maior tamanho que a curva mais
profunda que existe admite a 0,5 % é **0,582 SOL (US$ 56,74)**, e isso no instante exato da graduação; dentro da
janela que a mesa usa hoje (progresso 5–50 %) o teto é **0,241 SOL (US$ 23,48)**.

**Proveniência:** toda tabela abaixo aponta para um arquivo em `infra/scripts/sql/research/2026-09-16-t429b-*.sql`
(rodados no banco da VPS pelo caminho de leitura auditado, SELECT apenas) ou para a fórmula da §2, cujo recibo é
`packages/exchange-adapters/tests/unit/test_pumpfun_impact_ceiling.py` (42 testes, verdes).

---

## 1. Quanto volume um minuto-moeda tem (o teto de participação)

`q01` — `2026-09-16-t429b-q01-volume-por-minuto-moeda.sql`. Universo: `meme_features_1m`, idade 0–30 min, moeda
**não-Mayhem**, minuto **ainda na curva** (antes de `migrated_at`), volume do minuto conhecido. A série só existe
desde 12/09 07:30Z, então a janela de 7 dias mediu **4,444 dias**; os "por dia" usam esse vão medido, não 7.

| Medida | Valor |
|---|---|
| minutos-moeda | **432 443** (66 161 moedas · 97 300 minutos-moeda/dia) |
| p50 do volume de 1 min | **0,0000 SOL** |
| p90 | 4,4464 SOL |
| p99 | **57,357 SOL** |
| p99,9 | 147,77 SOL |
| máximo | 1 187,16 SOL |

**Quantos minutos têm o volume que cada tamanho exige a 1 % de participação:**

| Compra | Volume exigido (1 min) | Minutos-moeda | % do universo | Por dia |
|---|---|---|---|---|
| 1 SOL | ≥ 100 SOL | **1 208** | 0,279 % | 272 |
| 2 SOL | ≥ 200 SOL | **160** | 0,037 % | 36 |
| 5 SOL | ≥ 500 SOL | **2** | 0,0005 % | 0,45 |
| 9,8 SOL | ≥ 980 SOL | **2** | 0,0005 % | 0,45 |

**Ressalva honesta sobre os dois extremos:** os únicos 2 minutos com ≥ 500 SOL (1 187,16 e 1 180,22 SOL, mints
`Yzwxnn…pump` em 15/09 22:46Z e `7vfCXT…voxs` em 13/09 03:48Z) têm `curve_progress_pct` **NULL** — denominador
desconhecido. Nenhum portão nosso aprova uma moeda sem progresso, e uma curva que gradua com ~85 SOL reais não
comporta 1 180 SOL de volume orgânico num minuto sem giro enorme ou contaminação de pool no número da API externa
(`tape_source = activity_1m`). Por isso eles **somem** das contas da §3 — e, mesmo que fossem reais, seriam 0,45
minuto por dia.

---

## 2. Impacto de preço na curva — a fórmula e a tabela

**A fórmula, derivada de `packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py`:**

```
buy_cost:  s = floor(a · vsol / (vtok − a)) + 1        (a = tokens, vsol/vtok = reservas virtuais)
=> o produto vsol · vtok é invariante (produto constante)
impacto = preço médio do fill / preço marginal anterior − 1 = a/(vtok − a) = s / vsol
```

**Ou seja: o impacto de uma compra na curva é simplesmente `SOL pré-taxa ÷ reserva virtual de SOL`.** Não depende
do progresso a não ser através de `vsol`. É exatamente o que `packages/risk-core/hunter_risk_meme/sizing.py` já
escreve no cap `impact`: `teto_em_SOL = max_price_impact_pct × vsol × (1 + taxa)`, taxa da curva 1,25 %
(95 bps protocolo + 30 bps criador, `BONDING_CURVE_FEE_TIER_2026_05_20`).

**O ponto decisivo:** numa curva padrão (GlobalParams do registro 2025-07-18: `V0_sol` 30 SOL, `V0_tok` 1,073 B,
`R0` 793,1 M) `vsol` vai de **30 SOL no lançamento a 115,005359057 SOL na graduação** — e nada mais. A curva
**não tem profundidade para crescer**: ela gradua com ≈ 85 SOL reais captados e acaba.

`q02` — `2026-09-16-t429b-q02-teto-de-impacto-na-curva.sql` (forma fechada; `real_sol ≥ X/(1,0125·p) − 30`):

| Compra | `real_sol` para ≤ 0,5 % | para ≤ 1 % | para ≤ 5 % | Veredito a 0,5 % |
|---|---|---|---|---|
| 0,05 SOL | qualquer curva | qualquer | qualquer | cabe sempre |
| 0,10 SOL | qualquer curva | qualquer | qualquer | cabe sempre |
| 0,25 SOL | ≥ 19,38 (progresso ≥ 53,1 %) | qualquer | qualquer | só depois de 53 % da curva |
| 0,50 SOL | ≥ 68,77 (progresso ≥ 94,2 %) | ≥ 19,38 | qualquer | só na véspera da graduação |
| **1 SOL** | ≥ **167,53** | ≥ 68,77 | ≥ 0 | **IMPOSSÍVEL** (curva gradua a 85,005) |
| **2 SOL** | ≥ 365,06 | ≥ 167,53 | ≥ 9,51 | **IMPOSSÍVEL** |
| **5 SOL** | ≥ 957,65 | ≥ 463,83 | ≥ 68,77 | **IMPOSSÍVEL** |
| **9,8 SOL** | ≥ **1 905,80** | ≥ 937,90 | ≥ 163,58 | **IMPOSSÍVEL até a 5 %** |

**O mesmo de cabeça para baixo — o maior tamanho que o teto de 0,5 % admite, por estado da curva:**

| Progresso | `vsol` | `real_sol` | Teto a 0,5 % | Teto a 1 % | Teto a 5 % |
|---|---|---|---|---|---|
| 0 % (lançamento) | 30,00 | 0,00 | **0,1519 SOL** (US$ 14,80) | 0,3038 | 1,5188 |
| 5 % | 31,15 | 1,15 | **0,1577** (US$ 15,37) | 0,3154 | 1,5770 |
| 25 % | 36,80 | 6,80 | **0,1863** (US$ 18,16) | 0,3726 | 1,8630 |
| 50 % (topo da janela da mesa) | 47,59 | 17,59 | **0,2409** (US$ 23,48) | 0,4818 | 2,4091 |
| 75 % | 67,32 | 37,32 | 0,3408 | 0,6816 | 3,4080 |
| 100 % (graduação) | 115,0054 | 85,0054 | **0,5822** (US$ 56,74) | 1,1644 | 5,8221 |

**Impacto de 9,8 SOL no ponto mais profundo que uma curva alcança:** 9,8 ÷ 1,0125 ÷ 115,0054 = **8,42 %** — 17× o
nosso teto. Dentro da janela da mesa (5–50 %) é **31,1 % a 20,3 %**. E o impacto é pago **duas vezes**: entrada e
saída movem o preço no mesmo sentido contra nós.

### 2b. A mesma conta nas reservas realmente observadas (não derivada do progresso)

`q06` — `2026-09-16-t429b-q06-reservas-observadas.sql`, `meme_curve_snapshots` das últimas 48 h, não-Mayhem
(950 496 fotografias, 58 068 moedas; reservas em SOL humano nesta tabela):

| Medida | Valor |
|---|---|
| `virtual_sol_reserves` p50 / p99 / máx | **30,050** / 92,195 / 2 000,000 SOL |
| fotos que admitem 0,05 SOL a 0,5 % | 937 814 (**98,7 %**) |
| fotos que admitem 0,25 SOL a 0,5 % | 62 796 (6,6 %) |
| fotos que admitem **1 SOL** a 0,5 % | **314** (207 moedas em 48 h) |
| fotos que admitem **9,8 SOL** a 0,5 % | **5** |
| nessas 314: `real_sol_reserves` mediana / máxima | **0,017 SOL** / 9,657 SOL |

**Leia a última linha.** As poucas curvas cuja reserva virtual é grande o bastante para admitir 1 SOL a 0,5 %
têm, na mediana, **0,017 SOL de dinheiro real dentro**. A profundidade delas é SOL **virtual injetado** (moeda
Mayhem com o flag não lido, ou parâmetros globais fora do padrão), não comprador — exatamente o erro que a
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098 §5]] desmontou: o SOL **real** é
o teto do que todos os holders juntos poderiam retirar. Comprar 1 SOL ali é ser 100 % da liquidez real e não ter
para quem vender. **Essas 314 fotos não são oportunidade; são a armadilha que o teto de impacto sozinho não pega.**

---

## 3. Os dois tetos juntos — quantos minutos-moeda por dia

`q03` — `2026-09-16-t429b-q03-combinado-dois-tetos.sql`. `admitido = min(0,01 × volume_1m ; 0,005 × vsol × 1,0125)`,
`vsol` pela forma fechada da §2 a partir de `curve_progress_pct`. Universo: 402 862 minutos-moeda (idade 0–30 min,
não-Mayhem, na curva, progresso e volume conhecidos), 4,444 dias.

| Compra | Minutos sob **ambos** | % | Moedas | **Moedas/dia** | Só participação | Só impacto | Ambos **na janela 5–50 %** |
|---|---|---|---|---|---|---|---|
| 0,05 SOL | 36 290 | 9,01 % | 18 984 | **4 271** | 36 290 | 402 862 | 17 787 min / 11 057 moedas |
| 0,10 SOL | 26 874 | 6,67 % | 14 823 | **3 335** | 26 874 | 402 862 | 12 465 min / 8 571 moedas |
| 0,25 SOL | 4 972 | 1,23 % | 2 589 | **582** | 13 810 | 17 355 | **0 / 0** |
| 0,50 SOL | 111 | 0,028 % | 93 | **20,9** | 5 192 | 1 256 | **0 / 0** |
| **1 SOL** | **0** | 0 | **0** | **0** | 1 118 | **0** | 0 |
| **2 SOL** | **0** | 0 | **0** | **0** | 144 | **0** | 0 |
| **5 SOL** | **0** | 0 | **0** | **0** | 0 | **0** | 0 |
| **9,8 SOL** | **0** | 0 | **0** | **0** | 0 | **0** | 0 |

Três leituras, todas desconfortáveis:

1. **A partir de 1 SOL quem recusa é o impacto, e recusa 100 % dos minutos** — a coluna "só impacto" é zero. Não
   existe minuto, moeda, horário ou progresso que mude isso.
2. **Na janela que a mesa usa hoje (5–50 %, alinhada em 16/09), o teto efetivo é 0,241 SOL** — por isso as linhas
   de 0,25 e 0,50 SOL dão **zero** na última coluna. As 582 moedas/dia de 0,25 SOL vivem todas **acima de 53 % da
   curva**, fora da janela, justamente onde a venda pós-migração (T4.18) ainda não existe.
3. **Mesmo o tamanho do estágio 1 (0,05 SOL) só passa em 9 % dos minutos-moeda** — quem corta é a participação
   (91 % dos minutos não têm nem 5 SOL de volume no minuto).

### 3b. Por hora de Brasília

`q04` — `2026-09-16-t429b-q04-por-hora-brt.sql` (minutos-moeda por hora BRT; as colunas de 1 SOL e 9,8 SOL são
**só** o teto de participação, porque o de impacto já zerou tudo):

| Hora BRT | minutos-moeda | admite 0,05 | admite 0,10 | admite 0,25 | admite 0,50 | volume p/ 1 SOL | volume p/ 9,8 SOL |
|---|---|---|---|---|---|---|---|
| 22 | 21 058 | **2 457** | **1 819** | **283** | 7 | 109 | **0** |
| 19 | 18 474 | 2 070 | 1 553 | 270 | 4 | **117** | **0** |
| 14 | 19 499 | 2 020 | 1 503 | 258 | 4 | 93 | **0** |
| 18 | 16 302 | 1 890 | 1 428 | 227 | 7 | 83 | **0** |
| 13 | 17 343 | 1 838 | 1 422 | 265 | 7 | 68 | **0** |
| 04 (o pior) | 12 323 | 790 | 587 | 111 | 7 | 19 | **0** |

O perfil confirma a KB-0098: o horário útil é **13–22 BRT, com pico às 22 h**. Mas o pico melhora o **número de
minutos**, nunca o **tamanho**: a coluna de 9,8 SOL é zero em **todas as 24 horas**.

---

## 4. Depois da migração — o que o nosso banco sabe da pool

**Primeiro o que não temos, para ninguém achar que temos:** não existe tabela de **reservas/liquidez** da pool
PumpSwap no schema (varredura de `information_schema.tables`: nenhuma `meme_pool*`). A única observação nossa da
pool é a **fita** (`meme_trades` com `program = 'pump_amm'`, T4.11), e ela só é puxada para os mints que o Lab
rastreia. **Logo: impacto de preço na pool não é calculável do nosso banco hoje** — só participação sobre a fita,
que é o modelo que `packages/indicators/hunter_indicators/meme/pool.py` já usa (participação em 5 min, teto 1 %).

`q05` — `2026-09-16-t429b-q05-pool-depois-da-migracao.sql` (7 dias):

| Medida | Valor |
|---|---|
| moedas migradas nos 7 dias (`meme_tokens.migrated_at`) | **4 381** (≈ 626/dia) |
| dessas, com **alguma** fita de pool no nosso banco | **528 (12,1 %)** — cobertura por desenho, não medida do mercado |
| minutos-moeda de pool com fita | 834 |
| volume de 1 min p50 / p90 / p99 / máx | **26,96** / 80,81 / 139,86 / **240,90 SOL** |
| minutos com ≥ 100 / 200 / 500 / 980 SOL | 44 / 3 / **0** / **0** |

`q07` — `2026-09-16-t429b-q07-pool-janela-5min.sql`, na janela de 5 min que o nosso próprio modelo usa
(56 363 trades, 528 moedas):

| Volume 5 min | p50 | p90 | p99 | máx |
|---|---|---|---|---|
| SOL | **30,23** | 280,22 | 578,67 | **808,85** |

| Ordem | Precisa (1 % em 5 min) | Instantes que cabem | Moedas |
|---|---|---|---|
| 0,05 SOL | 5 SOL | 49 501 (87,8 %) | — |
| 1 SOL | 100 SOL | 9 854 (17,5 %) | 59 |
| 2 SOL | 200 SOL | 6 720 (11,9 %) | — |
| 5 SOL | 500 SOL | 1 336 (2,4 %) | — |
| **9,8 SOL** | 980 SOL | **0** | **0** |

**A pool é 5–10× mais funda que a curva em participação — e ainda assim 9,8 SOL nunca coube** em 7 dias de fita.

**E o impacto na pool, que não medimos?** A conta do produto constante é a mesma da §2: para 9,8 SOL ficarem em
0,5 % é preciso **≈ 1 960 SOL do lado SOL da pool ≈ US$ 191 k**, ou **≈ US$ 382 k de liquidez total**. Dois
pontos de referência:

- **Nosso, derivado:** ao migrar, a pool recebe aproximadamente o SOL real da curva, ≈ **85 SOL** (`docs/PUMPFUN.md`
  §4.2; a migração custa 0,015 SOL). Nesse instante 9,8 SOL dão **≈ 11,5 % de impacto**, e o teto de 0,5 % vale
  **≈ 0,43 SOL**.
- **Externo, rotulado como externo** (plantão de mercado de 15/09, DEX Screener, [[02-MARKET/Meme/2026-09-15|nota
  do dia]]): nas **149 graduadas** lidas às 18:56 BRT, **liquidez mediana US$ 2 919** (mcap mediano US$ 2 815;
  `mcap/liq` 0,99, faixa 0,51–170); no run 19, 50 graduadas, **liquidez mediana US$ 3 810**. Isto é **fonte de
  terceiro, leitura pontual, seleção por graduação** — não é medida nossa. Se for a ordem de grandeza certa,
  a pool mediana pós-graduação tem ≈ **30 SOL de liquidez total** (≈ 15 SOL do lado SOL) e o teto de 0,5 % vale
  **≈ 0,075 SOL**. Ou seja: horas depois de migrar, a pool é **mais rasa que a curva**.

**Também está fora por contrato:** `docs/RISK_ENGINE_MEME.md` §1 proíbe **comprar** na PumpSwap
(`pumpswap_buy_not_allowed`) — a pool existe no contrato só como porta de saída. "Pôr US$ 1 000 na pool" não é
afrouxar um número: é mudar o contrato de risco e construir um caminho de compra que não existe.

---

## 5. Conclusão para o dono — 5 linhas

1. **US$ 1 000 por operação não cabe na curva sob os nossos tetos, e não é questão de raridade: é aritmética.**
   O impacto de uma compra é `SOL ÷ reserva virtual de SOL`, e a reserva virtual de uma curva nunca passa de
   115 SOL — 9,8 SOL custam **8,42 % de impacto** no ponto mais fundo, **17× o teto de 0,5 %**. Em 4,4 dias
   medidos: **0 minutos-moeda, 0 moedas, em todas as 24 horas**.
2. **O que a curva admite hoje é isto:** 0,05 SOL (US$ 4,87) em **4 271 moedas/dia**; 0,10 SOL em **3 335**;
   0,25 SOL em 582/dia, mas **só acima de 53 % da curva** — fora da janela 5–50 % da mesa, onde o teto efetivo
   é **0,241 SOL (US$ 23,48)** e o número de minutos que admitem 0,25 SOL é **zero**.
3. **A pool depois da migração é o único lugar onde 1–5 SOL chega a caber** (1 SOL em 17,5 % dos instantes de
   fita, 5 SOL em 2,4 %), e **mesmo lá 9,8 SOL nunca coube** em 7 dias. Além disso comprar na PumpSwap é
   **proibido pelo contrato** e a **venda** na PumpSwap (T4.18) ainda não existe — uma posição de US$ 1 000 que
   graduasse hoje ficaria presa, saindo só pelo Terminal, à mão.
4. **Conjunto de limites recomendado para o estágio 2 (curva):** `max_sol_per_trade` **0,25 SOL**,
   `max_participation_pct` **1 %**, `max_price_impact_pct` **0,5 %** — e o US$ 1 000 dele passa a ser um teto de
   **exposição do dia**, não de ticket: ~40 compras de 0,25 SOL, não uma de 9,8. **Trade-offs nomeados:** (a)
   0,25 SOL só passa acima de 53 % de progresso, então ou a mesa abre a janela até ~85 % **e** a T4.18 entrega a
   venda na pool, ou o teto real continua 0,15–0,24 SOL; (b) manter 9,8 SOL exigiria subir o teto de impacto para
   ~**32 %** (a 5 % de progresso) ou ~**21 %** (a 50 %) — isso não é afrouxar um limite, é decidir pagar 20–30 %
   acima do preço na entrada **e de novo na saída**; (c) subir a participação sem subir o impacto não muda nada:
   de 1 SOL para cima quem recusa é o impacto, sozinho, em 100 % dos minutos.
5. **E o aviso que nenhum número acima cancela:** o Portão B continua vermelho (EXP-M1 sem 100 apostas / 30 dias)
   e o estágio 1 fechou **0 compras reais** até 16/09 13:5x BRT. **O tamanho não é o gargalo do lucro; a vantagem
   é.** Medir "quanto cabe" foi necessário para não prometer o impossível — mas 4 271 moedas/dia a 0,05 SOL só
   viram dinheiro depois que uma regra provar vantagem fora da amostra.

---

## 6. Suposições numéricas declaradas

| Suposição | Valor | Por quê / risco |
|---|---|---|
| Cotação do SOL | 97,4697 US$/SOL | `hb:meme:radar lab_sol_usd`, 16/09 15:0x BRT. US$ 1 000 = 10,26 SOL; o estudo usa 9,8 SOL (o número dos portões) |
| Taxa da curva | 1,25 % (95 + 30 bps) | `BONDING_CURVE_FEE_TIER_2026_05_20`, constante **datada** (20/05/2026). A T4.29c passou a ler o `FeeConfig` da cadeia; **o impacto `s/vsol` não depende da taxa** — só a conversão para "SOL total" depende |
| Parâmetros da curva | `V0_sol` 30 · `V0_tok` 1,073 B · `R0` 793,1 M | registro de 2025-07-18 (`docs/PUMPFUN-ONCHAIN.md` §1.2). A `q06` confirma: `vsol − real_sol` mediana **30,000** nas 950 k fotos de 48 h |
| Janela de dados da série de 1 min | 4,444 dias (não 7) | `meme_features_1m` só tem dados desde 12/09 07:30Z; todos os "por dia" dividem pelo vão medido |
| "Volume orgânico do minuto" | `curve_volume_1m_sol` | vem de `activity_1m` (API externa, 587 k linhas) ou `swap_api_trades` (81 k), janela 60 s em ambas. Não separamos bot de humano — **"orgânico" aqui é "não-Mayhem", não "humano"** |
| Pool: lado SOL ≈ metade da liquidez | produto constante | convenção de AMM 50/50; a PumpSwap canônica é produto constante. Se a pool não for 50/50 o número muda, e não temos reservas gravadas para conferir |
| Liquidez mediana pós-graduação | US$ 2 919 / US$ 3 810 | **externo** (DEX Screener via plantão de 15/09, runs 23 e 19). Leitura pontual, seleção por graduação, sem carimbo nosso |

## 7. Arquivos

- Consultas: `infra/scripts/sql/research/2026-09-16-t429b-q0{1,2,3,4,5,6,7}-*.sql`
- Recibo da fórmula: `packages/exchange-adapters/tests/unit/test_pumpfun_impact_ceiling.py` (42 testes)
- Motor que aplica os tetos: `packages/risk-core/hunter_risk_meme/sizing.py` (caps `participation` e `impact`)

## Ligações
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] · [[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] ·
[[09-OPERATIONS/Diario/2026-09-16]] · [[05-EXPERIMENTS/EXP-M4-moonshot]] · [[00-INBOX/Hipoteses-do-plantao|M-P47]] ·
`docs/RISK_ENGINE_MEME.md` §3.1/§5 · `docs/PUMPFUN.md` §4.2
