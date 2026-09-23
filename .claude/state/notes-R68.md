# R68 — "comprar antes e vender na alta" da próxima vela: **não**. O custo come o movimento onde há previsibilidade; onde o custo é pequeno, não prevemos nada.

**Pergunta (Everton, 23/09/2026 12:1x BRT):** "analisando, tentamos prever o futuro da
próxima vela, comprando antes e vendendo na alta."

**Método:** leitura read-only da VPS (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`,
só `COPY TO STDOUT`; nada foi escrito). Desenho **pré-registado antes de correr**
(`.claude/state/r68/preregistro.md`), **emendado uma vez** depois da revisão de desenho da
Astra (`.claude/state/astra-review-r68.md`) e **ainda antes** de qualquer teste. Código e
saídas em `.claude/state/r68/` (282 KB). Os CSV brutos (57 MB) ficaram no *scratchpad* da
sessão, fora do repositório. Dinheiro em `Decimal` na fronteira (constantes de custo).

---

## Resposta curta — **veredito (b)**

**Não existe horizonte + preditor, entre os 25 que congelei, cuja vantagem fora de amostra
sobreviva ao nosso custo.** Os cinco números:

1. **A 1 minuto o custo é 3,1× o movimento típico.** Mediana de `|retorno|` = **0,045 %**
   contra **0,14 %** de ida-e-volta. O equilíbrio correcto `p* = (b+c)/(a+b)`, com os
   ganhos e perdas médios **incondicionais** medidos, dá **1,34** — maior que 1: mantendo
   esse perfil de payoff, **nem acertar 100 % das vezes empata**. (Um selector melhor
   mudaria `a` e `b`; é isso que a parte B testa, e não encontra.)
2. **Só 7,04 %** dos 2,38 M minutos têm retorno futuro acima de 0,14 %; **0,39 %** acima de
   0,54 % (o custo real do bilhete de 0,05 SOL com a rede). Prever "qual minuto sobe" não
   chega: é preciso prever *qual dos 7 %* sobe o suficiente.
3. **25 células congeladas** (5 preditores fixos × 5 horizontes), fora de amostra, no
   universo primário de 16 perpétuos e 104 dias: **zero confirmações** pelos quatro
   critérios pré-registados. **Ao custo da mesa (0,54 %) as 25 têm média estimada
   negativa** — a menos má é −12,42 bp. A 0,14 % há quatro médias positivas, todas a
   h = 240 (a maior: **+27,58 bp**, h = 240 volume) e **todas com IC que atravessa zero**
   — são inconclusivas, não vantagens.
4. **20 das 25 células têm o limite superior do IC 95 % abaixo de +10 bp** (o ganho mínimo
   que fixei como relevante). Isto é **evidência contra** uma vantagem útil, não só ausência
   de evidência. *São IC individuais, não simultâneos* — o Holm corrige os p, não a largura
   dos intervalos. As **cinco células de h = 240 continuam inconclusivas** quanto ao MRE.
5. A única célula que passou a regra mecanicamente vive num **subgrupo que a regra congelada
   proíbe de confirmar sozinho** (U1 = os mercados da mesa **sem os 8 que já estão em U2**,
   26 mercados, só 25 dias): h = 60, reversão, **+26,5 bp**, IC [+6,8, +44,7], Holm 0,029.
   **Ao custo da mesa dá −13,5 bp**, e no universo primário — que tem 4× o período — a
   mesma célula dá **−0,85 bp com p = 0,853**. Classificação honesta:
   **achado exploratório no proxy de U1, não confirmado para a mesa** — e também **não
   demonstrado como artefacto**.

**Precisão de linguagem (a mesma que o R67 exigiu, e que a Astra apertou depois de ver o
veredito):** *não confirmado* ≠ *refutado*. A redacção exacta que este estudo autoriza é:

> Nas 25 células fixas pré-especificadas de U2, **nenhuma confirmou vantagem líquida a
> 0,14 % pelos critérios definidos**. Vinte têm limite superior individual abaixo de
> +10 bp; **as cinco de 240 minutos continuam inconclusivas** quanto a esse ganho mínimo.
> A 0,54 %, todas têm média estimada negativa. Isto **não demonstra inexistência de
> previsibilidade** fora destas regras, mercados e período.

---

## 0. O que os dados são (e a restrição que mudou o desenho)

`candles`, `timeframe='1m'`, **só `is_final`**, 10 389 968 linhas, 481 mercados,
2026-06-11 19:42 → 2026-09-23 14:58 UTC.

A profundidade **não é uniforme**, e isto decidiu o desenho antes de qualquer teste:

| profundidade | mercados |
|---|---:|
| 149 478 velas (104 d, desde 11/06) | **15** + SAHARA (135 972) |
| ~35 800 velas (25 d, desde 29/08) | 126 |
| < 30 000 | 339 |

- **U2 "profundo" (primário):** os 16 com 104 dias — BTC, ETH, XRP, LINK, DASH, ZEC, BNB,
  DOGE, SOL, UNI, NEAR, ARB, SUI, TAO, PROM, SAHARA (perpétuas). É o único universo onde
  cabe um walk-forward com 13 dobras.
- **U1 "mesa" (subgrupo):** os perpétuos dos `spot_desk_markets` com `enabled = true`
  (35 linhas; 34 com velas), **menos** os 8 que já estão em U2 → 26 mercados, 29/08–23/09.
- **Só 8 dos 35 mercados da mesa têm os 104 dias.** É o primeiro facto desconfortável: a
  mesa spot/1 opera sobretudo mercados com 25 dias de histórico.

---

## 1. A guarda anti-look-ahead (o que matou a v1 do R66)

`.claude/state/r68/load68.py`. Três regras, todas testadas:

- **Uma barra de horizonte `h` só existe se tiver as `h` velas de 1 m, todas `is_final`.**
  Bucket incompleto desaparece — nada é interpolado, nada é preenchido.
- **`assert_causal(fontes, instante_de_decisão)`** levanta `LookAheadError` se alguma
  linha-fonte fechar **depois** do instante de decisão. `Bars.take` é o **único** acesso a
  histórico usado pelos preditores e chama a guarda em todas as leituras.
- **Sem desfecho, o ponto é censurado, não preenchido:** se a barra de saída contígua não
  existir, o ponto de decisão desaparece em vez de virar retorno zero.

```
uv run --with pytest --with numpy python -m pytest test_load68.py -q
........                                                                 [100%]
8 passed in 0.64s
```

Os dois testes que importam:

- `test_cheat_strategy_is_caught_by_take` — a "estratégia batoteira" lê a barra seguinte
  (`idx = decisão + 1`) e é **recusada**; ler a barra anterior passa.
- `test_feature_does_not_change_when_a_non_final_candle_changes` — mexer nos minutos que
  ainda não fecham o bucket não altera **nenhuma** feature já calculada até ao corte
  anterior (a exigência do `docs/PIPELINE.md` §2).

---

## 2. Parte A — o muro do custo (U2, 16 mercados, 104 dias)

Retorno close-to-close do horizonte seguinte, por ponto de decisão.

| h (min) | n | p25 \|r\| | **mediana \|r\|** | p75 | p90 | MFE mediana | MFE p90 | média bruta | % > 0 | a (ganho médio) | b (perda média) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 378 230 | 0,016 % | **0,045 %** | 0,094 % | 0,170 % | 0,036 % | 0,165 % | +0,05 bp | 45,1 % | 0,083 % | 0,083 % |
| 5 | 475 616 | 0,042 % | **0,099 %** | 0,206 % | 0,377 % | 0,095 % | 0,387 % | +0,23 bp | 47,4 % | 0,179 % | 0,171 % |
| 15 | 158 521 | 0,073 % | **0,171 %** | 0,354 % | 0,651 % | 0,175 % | 0,692 % | +0,70 bp | 48,5 % | 0,305 % | 0,288 % |
| 60 | 39 612 | 0,145 % | **0,340 %** | 0,699 % | 1,307 % | 0,365 % | 1,435 % | +2,80 bp | 49,5 % | 0,613 % | 0,561 % |
| 240 | 9 878 | 0,284 % | **0,688 %** | 1,412 % | 2,579 % | 0,786 % | 3,038 % | +11,39 bp | 49,6 % | 1,277 % | 1,043 % |

### Horizonte × custo → acerto necessário para empatar

`p*` correcto = `(b + c) / (a + b)` com `a = E[r | r > 0]` e `b = −E[r | r < 0]`
**médias condicionais medidas** (correcção que a Astra exigiu: a fórmula `0,5 + c/2m` com a
mediana é enganadora para saída por tempo; fica ao lado, marcada como **modelo** `±m`).
`P(r > c)` é o número directo: a fracção de barras cujo retorno futuro bate o custo.

| h | custo | `p*` correcto | `p*` modelo ±m | **P(r > c)** | P(MFE > c) | sempre-long líquido |
|---:|---|---:|---:|---:|---:|---:|
| **1** | 0,14 % | **1,34** | 2,05 | 7,04 % | 13,04 % | −14,0 bp |
| 1 | 0,30 % | 2,31 | 3,82 | 1,61 % | 3,22 % | −30,0 bp |
| 1 | 0,50 % | 3,51 | 6,04 | 0,47 % | 1,01 % | −50,0 bp |
| 1 | **0,54 %** (0,14 + rede) | **3,75** | 6,48 | 0,39 % | 0,84 % | −54,0 bp |
| **5** | 0,14 % | **0,89** | 1,20 | 19,07 % | 37,23 % | −13,8 bp |
| 5 | 0,30 % | 1,35 | 2,01 | 7,56 % | 15,09 % | −29,8 bp |
| 5 | 0,50 % | 1,92 | 3,01 | 3,09 % | 6,34 % | −49,8 bp |
| 5 | **0,54 %** | **2,03** | 3,21 | 2,65 % | 5,47 % | −53,8 bp |
| **15** | 0,14 % | **0,72** | 0,91 | 28,38 % | 57,23 % | −13,3 bp |
| 15 | 0,30 % | 0,99 | 1,38 | 15,35 % | 31,58 % | −29,3 bp |
| 15 | 0,50 % | 1,33 | 1,96 | 8,02 % | 16,71 % | −49,3 bp |
| 15 | **0,54 %** | **1,40** | 2,08 | 7,15 % | 14,92 % | −53,3 bp |
| **60** | 0,14 % | **0,60** | 0,71 | 38,05 % | 77,31 % | −11,2 bp |
| 60 | 0,30 % | 0,73 | 0,94 | 27,29 % | 56,78 % | −27,2 bp |
| 60 | 0,50 % | 0,90 | 1,24 | 18,36 % | 39,14 % | −47,2 bp |
| 60 | **0,54 %** | **0,94** | 1,29 | 17,04 % | 36,48 % | −51,2 bp |
| **240** | 0,14 % | **0,51** | 0,60 | 44,08 % | 89,70 % | −2,6 bp |
| 240 | 0,30 % | 0,58 | 0,72 | 37,06 % | 77,84 % | −18,6 bp |
| 240 | 0,50 % | 0,67 | 0,86 | 29,99 % | 64,83 % | −38,6 bp |
| 240 | **0,54 %** | **0,68** | 0,89 | 28,97 % | 62,74 % | −42,6 bp |

(U1 mesa, 25 dias, é mais volátil e desloca tudo um degrau: mediana `|r|` a 1 min = 0,073 %,
a 240 min = 1,137 %; `p*` a 0,54 % vai de **2,56** (h=1) a **0,587** (h=240). Tabela completa em
`.claude/state/r68/parta.txt`.)

### Onde o custo come o movimento típico — dito sem rodeios

- **h = 1 e h = 5 estão mortos a qualquer custo nosso — para regras com estes perfis de
  ganho e perda.** A 1 minuto, `p* = 1,34 > 1`: mantendo `a = 0,083 %` e `b = 0,083 %`,
  nem acertar **sempre** cobre 0,14 % de ida-e-volta. **Ressalva que a Astra exigiu e é
  correcta:** `a` e `b` aqui são **incondicionais** (sobre todas as barras); um selector
  suficientemente bom muda os dois. Portanto a parte A é um **diagnóstico forte do
  obstáculo económico**, não uma impossibilidade matemática de selecção lucrativa —
  a impossibilidade de selecção é o que a parte B testa, e não encontra.
  A 5 minutos, `p* = 0,89` a 0,14 % — precisaria de acertar 9 em 10 — e **2,03** ao custo da
  mesa: outra vez impossível. **A "próxima vela" que o Everton perguntou é exactamente o
  caso em que o custo é maior que o prémio inteiro.**
- **h = 15 fica no limite do absurdo:** 0,72 a 0,14 %, **1,40** ao custo da mesa.
- **h = 60 e h = 240 são os únicos aritmeticamente possíveis:** `p* = 0,94` e `0,68` ao custo
  da mesa. Mas aí já não estamos a falar da próxima vela — é uma posição de 1 a 4 horas —
  **e a parte B mostra que não sabemos prever esse horizonte.**
- **A deriva não salva ninguém.** "Sempre long" é negativo em **todos** os 20 pares
  horizonte × custo em U2 (o menos mau: −2,6 bp a h=240 com 0,14 %). O mercado destes 104
  dias não teve deriva suficiente para pagar sequer uma entrada e uma saída.
- **MFE é oportunidade retrospectiva, não saída realizável.** A 240 min, 89,7 % das barras
  tocam +0,14 % nalgum momento — e isso não é dinheiro: é o preço máximo que uma saída
  perfeita teria apanhado. Está na tabela porque o Everton pediu "vender na alta"; não está
  como prova de nada.

**Emenda à instrução do brief:** a parte A **não** eliminou horizonte nenhum. O portão
`p* < 0,70` que eu tinha pré-registado caiu na EMENDA 1 (Astra must-fix #2): filtrar pela
mediana selecciona *amplitude*, não *previsibilidade*, e mataria exactamente a hipótese de
um sinal que apanha episódios raros e grandes. Os cinco horizontes foram testados em B.

---

## 3. Parte B — o walk-forward (U2 primário, 104 dias, 13 dobras)

25 células congeladas: 5 preditores de limiar **fixo** (análise primária; ver EMENDA 1 E1.5)
× 5 horizontes. Baseline "sempre long" na **mesma população elegível**. Bootstrap de
**blocos temporais conjuntos de 3 dias** (todos os mercados juntos, 5 000 reamostragens,
seed 68), p-valor centrado sob o nulo, **Holm** para controlo familiar (BH também gravado no
JSON). `P5_hora_do_dia` não tem limiar fixo possível e ficou só no exploratório.

| h | preditor | n | entradas | **líquido @ 0,14 %** | IC 95 % | p | Holm | sempre-long | Δ | @ 0,54 % | em SOL | atraso 1 barra |
|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | P1 momentum | 1 071 977 | 45,1 % | −14,19 bp | [−14,27; −14,10] | 0,000 | 0,000 | −13,95 | −0,24 | −54,19 | −14,25 | −14,01 |
| 1 | P2 reversão | 94 535 | 4,0 % | −13,34 | [−13,57; −13,13] | 0,000 | 0,000 | −13,95 | **+0,61** | −53,34 | −13,45 | −13,83 |
| 1 | P3 volume | 284 838 | 12,0 % | −13,79 | [−13,91; −13,66] | 0,000 | 0,000 | −13,95 | +0,16 | −53,79 | −13,90 | −13,79 |
| 1 | P4 taker | 1 006 883 | 42,4 % | −14,09 | [−14,15; −14,02] | 0,000 | 0,000 | −13,95 | −0,14 | −54,09 | −14,12 | −13,99 |
| 1 | P6 rompimento | 127 475 | 5,4 % | −14,16 | [−14,38; −13,91] | 0,000 | 0,000 | −13,95 | −0,20 | −54,16 | −14,13 | −13,93 |
| 5 | P1 | 225 144 | 47,4 % | −14,01 | [−14,29; −13,71] | 0,000 | 0,000 | −13,77 | −0,25 | −54,01 | −14,12 | −13,89 |
| 5 | P2 | 17 797 | 3,8 % | −12,59 | [−13,85; −11,50] | 0,000 | 0,000 | −13,77 | **+1,18** | −52,59 | −13,26 | −13,58 |
| 5 | P3 | 54 346 | 11,5 % | −12,94 | [−13,66; −12,17] | 0,000 | 0,000 | −13,77 | +0,83 | −52,94 | −13,75 | −12,98 |
| 5 | P4 | 166 614 | 35,1 % | −13,72 | [−13,95; −13,46] | 0,000 | 0,000 | −13,77 | +0,04 | −53,72 | −13,85 | −13,96 |
| 5 | P6 | 23 129 | 4,9 % | −13,98 | [−14,78; −13,17] | 0,000 | 0,000 | −13,77 | −0,22 | −53,98 | −14,15 | −13,53 |
| 15 | P1 | 76 456 | 48,5 % | −13,41 | [−14,38; −12,25] | 0,000 | 0,000 | −13,30 | −0,11 | −53,41 | −14,05 | −13,71 |
| 15 | P2 | 6 034 | 3,8 % | −13,48 | [−16,19; −10,65] | 0,000 | 0,000 | −13,30 | −0,17 | −53,48 | −15,40 | −11,47 |
| 15 | P3 | 18 618 | 11,8 % | −11,12 | [−13,01; −9,26] | 0,000 | 0,000 | −13,30 | **+2,19** | −51,12 | −13,54 | −11,62 |
| 15 | P4 | 44 159 | 28,0 % | −13,46 | [−14,24; −12,47] | 0,000 | 0,000 | −13,30 | −0,16 | −53,46 | −14,19 | −13,66 |
| 15 | P6 | 7 255 | 4,6 % | −11,97 | [−15,18; −8,34] | 0,000 | 0,000 | −13,30 | **+1,34** | −51,97 | −14,37 | −14,50 |
| 60 | P1 | 19 126 | 49,5 % | −12,37 | [−15,93; −8,09] | 0,000 | 0,000 | −11,22 | −1,15 | −52,37 | −14,36 | −11,89 |
| **60** | **P2** | 1 473 | 3,8 % | **−0,85** | [−9,46; **+8,30**] | 0,853 | 1,000 | −11,22 | **+10,38** | −40,85 | −8,06 | −20,20 |
| 60 | P3 | 5 063 | 13,1 % | −6,57 | [−14,04; +0,94] | 0,085 | 0,680 | −11,22 | +4,66 | −46,57 | −13,74 | −8,07 |
| 60 | P4 | 5 976 | 15,5 % | −12,07 | [−15,67; −7,91] | 0,000 | 0,000 | −11,22 | −0,85 | −52,07 | −15,42 | −10,03 |
| 60 | P6 | 1 784 | 4,6 % | −4,51 | [−16,12; +6,06] | 0,442 | 1,000 | −11,22 | +6,71 | −44,51 | −12,32 | −11,83 |
| 240 | P1 | 4 432 | 49,8 % | −2,60 | [−20,62; +18,98] | 0,800 | 1,000 | −1,66 | −0,93 | −42,60 | −7,38 | −1,40 |
| 240 | P2 | 287 | 3,2 % | −13,24 | [−43,92; +17,85] | 0,397 | 1,000 | −1,66 | −11,58 | −53,24 | −7,67 | −2,83 |
| **240** | **P3** | 1 335 | 15,0 % | **+27,58** | [**−12,67**; +72,71] | 0,254 | 1,000 | −1,66 | +29,25 | **−12,42** | −0,71 | +23,52 |
| 240 | P4 | 373 | 4,2 % | +1,55 | [−21,57; +27,56] | 0,895 | 1,000 | −1,66 | +3,21 | −38,45 | +3,77 | +2,56 |
| 240 | P6 | 468 | 5,3 % | +14,77 | [−52,82; +67,20] | 0,665 | 1,000 | −1,66 | +16,43 | −25,23 | +8,47 | +18,29 |

**`CONFIRMAM (regra congelada, Holm < 0,05): 0`**
**`EVIDENCIA CONTRA vantagem util (IC sup < +10 bp): 20/25`**

Lê-se assim:

- Os `p = 0,000` das 20 primeiras células **não são vitórias**: o nulo testado é "líquido = 0"
  e elas são significativamente **negativas**. São a assinatura do custo, não de sinal.
- **A maior média líquida a 0,14 % de toda a grelha é +27,58 bp** (h=240, P3 volume) — e o
  seu IC é [−12,67; +72,71]. As quatro positivas (h=240 P3 +27,58, P6 +14,77, P4 +1,55, e
  h=60 nenhuma) têm IC que atravessa zero com larguras de 40 a 120 bp, sobre **1 335, 468 e
  373 operações** em 104 dias e ~35 blocos de 3 dias. Isso é **falta de potência, não
  vantagem — e também não é "não existe"**: para estas cinco células de h=240 o estudo
  devolve *inconclusivo*.
- **Ao custo da mesa (0,54 %) nenhuma das 25 é positiva.** A melhor, h=240 P3, dá −12,42 bp.
- **Numerário SOL** (a mesa quer acabar com mais SOL, não mais USDT): a coluna "em SOL" é
  quase sempre **pior** que a USDT, porque nos 104 dias o SOL subiu com o resto. Das quatro
  positivas em USDT, só duas continuam positivas em SOL (+3,77 e +8,47 bp), ambas com IC
  largo. **Ganhar em dólares e perder em SOL é um modo de falha real desta mesa** e não
  estava na pergunta original.
- **Atraso de uma barra:** a h=1 e h=5 (atraso realista de 1 e 5 min) não muda nada — porque
  não havia nada. A h=60/240 o meu teste troca a janela `[t, t+h]` pela `[t+h, t+2h]`: é um
  teste de **persistência do sinal**, não de latência operacional. Ver §6.2.

### Walk-forward adaptativo (secundário: limiar escolhido no treino)

Treino 14 d / teste 7 d, passo 7 d, **com purga** de `h` no fim do treino (nenhum rótulo do
ajuste termina dentro do teste), 13 dobras, grelha de limiares congelada no pré-registo.
`.claude/state/r68/partb_adapt_U2.txt`:

**`CONFIRMAM (adaptativo, Holm < 0,05): 0`**

Melhor célula: h=60 P3 volume, **+0,52 bp** a 0,14 %, IC [−8,58; +12,49] — e **−39,48 bp** ao
custo da mesa. h=240 P6 dá +30,59 bp com IC [−51,16; +86,85] sobre **380 operações**. Ajustar
o limiar no treino **não** produziu nada que os limiares fixos não produzissem; produziu as
mesmas caudas largas com menos operações.

**Correcção aplicada depois da revisão do veredito (bug real, apanhado pela Astra):** o
baseline "sempre long" do adaptativo estava a ser calculado sobre **todos** os pontos
elegíveis do painel, incluindo períodos fora das janelas de teste — ou seja, comparava o
sinal com um baseline de outro regime. `evaluate` passou a aceitar `base_mask` e o
adaptativo passa a união das janelas de teste. Os Δ mudaram (p. ex. h=60 P3 de +11,74 para
+11,17 bp; h=240 P6 de +32,25 para +27,78 bp); **a média líquida das entradas e o veredito
não mudaram** — continua zero confirmações. Os números acima e em
`partb_adapt_U2.txt` já são os corrigidos.

**Desvios do protocolo que ficam declarados** (nice-to-have da Astra): `P5_hora_do_dia`
não entrou no adaptativo; a purga foi arredondada para **1 dia** em vez de `h` minutos
exactos (mais conservador); o desempate na grelha **ficou com o primeiro** limiar, que é o
**menos** conservador, e não o mais conservador como a E1.5 dizia; e o relatório de censura
prometido na E1.9b não foi publicado (os pontos sem barra de saída contígua são descartados
em `forward`/`panel`, e a diferença entre `n` do painel e `elegíveis` está impressa no topo
de `partb_U2.txt`).

---

## 4. O subgrupo da mesa (U1, 26 mercados, 25 dias) — e por que não confirma

`.claude/state/r68/partb_U1desk.txt`. Uma célula passa os quatro critérios mecanicamente:

**h = 60, P2 reversão: +26,48 bp líquidos a 0,14 %, IC [+6,78; +44,65], p 0,003, Holm 0,029,
Δ vs sempre-long +36,13 bp, 483 operações.**

Quatro razões para **não** a tratar como achado, todas escritas antes de a ver:

1. **A regra congelada (E1.8) proíbe U1 de confirmar sozinho.** U1 e U2 não são replicações
   independentes — partilham exchange, datas e regime; U2 era o universo primário declarado.
2. **Não se reproduz onde há mais dados.** A mesma célula em U2, com **4× o período**, dá
   **−0,85 bp com p = 0,853** e IC que contém zero folgadamente.
3. **Morre ao custo da mesa.** A 0,54 % — o custo do bilhete de 0,05 SOL, que é o custo desta
   mesa e não uma sensibilidade — dá **−13,52 bp**. Ou seja: mesmo aceitando o efeito como
   real, a mesa spot/1 perderia dinheiro a executá-lo.
4. **Morre com atraso.** Com uma barra de atraso: **−20,54 bp**. (Ressalva honesta: a h=60
   isso é uma hora de atraso, duro demais — ver §6.)

Acrescento um quinto, aritmético: 483 operações em 25 dias ≈ **8 blocos** de 3 dias. Um IC de
bootstrap com 8 blocos é largo e enviesado mesmo quando o ponto parece bom.

---

## 5. Reconciliação com o R63 §3a (momentum −42,9 / reversão +14,9)

R63 mediu, em 7 dias nos 10 mercados da mesa: `momentum v3` **Σ R −42,87** em 223 sinais;
`mean_reversion` v14/v6 **+14,90** em 23 sinais cada. A pergunta era se o walk-forward
reproduz a **direcção**. Comparando Δ contra "sempre long" em U2 (antes de custo, que é o
que compara famílias):

| família | h=1 | h=5 | h=15 | h=60 | h=240 |
|---|---:|---:|---:|---:|---:|
| **P1 momentum** (sinal do retorno anterior) | −0,24 | −0,25 | −0,11 | −1,15 | −0,93 |
| **P6 rompimento de 20** (*parente do `momentum v3`, não a mesma regra — ver aviso abaixo*) | −0,20 | −0,22 | **+1,34** | **+6,71** | **+16,43** |
| **P2 reversão** (z < −2) | **+0,61** | **+1,18** | −0,17 | **+10,38** | −11,58 |

- **Reproduz para o momentum ingénuo:** P1 é **negativo contra sempre-long nos cinco
  horizontes**. Comprar porque a vela anterior subiu perde, exactamente na direcção do
  R63.
- **Reproduz, em grande parte, para a reversão:** P2 bate sempre-long em **3 dos 5**
  horizontes, e o maior Δ de toda a grelha (+10,38 bp a h=60) é dela. Mesma direcção do
  +14,9 do R63.
- **P6 não contradiz o `momentum v3` — porque não é o `momentum v3`.** Aviso que a Astra
  apanhou e é correcto: o meu P6 compara o fecho com o máximo das **máximas** das 20 barras
  anteriores, na escala do horizonte testado. O `momentum_v1`/v3 do Lab
  (`packages/core/hunter_core/strategies/momentum_v1.py`) compara com o máximo dos
  **fechos** anteriores, **em 15 m**, e ainda exige retorno positivo, `rvol ≥ rvol_min` e
  ATR % dentro de uma banda, com stop/alvo a 1,5 ATR. Mudam a entrada, a escala e a
  população. O que o meu número diz é: **nesta família de rompimento, com saída por tempo
  puro, entrar não é o que perde** (+1,3 / +6,7 / +16,4 bp contra sempre-long a h ≥ 15).
  Daí nasce uma **hipótese, não um facto**: a perda de −42,9 R do R63 pode ser sobretudo
  da política de saída (100 dos 223 sinais terminaram `invalidated` com R negativo). O R68
  **não testa** essa hipótese — testá-la é trabalho para o replay histórico
  (`docs/PIPELINE.md` §6c) com a estratégia real.
- **Nada disto sobrevive ao custo.** Os Δ positivos valem 1 a 16 bp; o custo é 14 a 54 bp.
  A reconciliação é sobre *direcção*, não sobre dinheiro.

---

## 6. Ressalvas — a que mais importa primeiro

1. **A que mais importa: o proxy não é a mesa.** Tudo isto é medido em **perpétuos da
   Binance**, com entrada e saída ao **fecho da vela** que a decisão acabou de observar.
   Isso é um **proxy de retorno**, não execução demonstrada: não tem atraso de publicação,
   nem slippage, nem impacto, nem falha de transacção, e o preço de um pool da Solana não é
   o da perpétua. O R63 já mediu 0,14 % de ida-e-volta no Jupiter para tamanhos pequenos;
   o que **não** está medido aqui é quanto do movimento sobra depois da latência real da
   mesa. **Um veredito negativo com um proxy optimista é forte** (se nem com execução
   perfeita paga, não paga); um veredito positivo com ele teria sido fraco. Só posso usar
   a força que a direcção do resultado me dá.
2. **A sensibilidade de "atraso" não é um teste de latência, e eu exagerei ao dizer que
   era.** O código troca a janela `[t, t+h]` pela `[t+h, t+2h]`: a h=60 mede a **hora
   seguinte** à oportunidade, a h=240 espera quatro horas. Isso é uma sensibilidade de
   **persistência do sinal** — legítima, e informativa — mas a frase "se morre com atraso,
   não é da mesa" é excessiva e fica retirada. O teste de latência correcto seria um atraso
   `δ` em tempo de relógio **independente de `h`** (p. ex. 1 min), com entrada no primeiro
   preço posterior a `δ` e saída em `t+δ+h` (mantendo a duração) ou em `t+h` (mantendo o
   vencimento), reportando a outra como sensibilidade. Não está feito. A h=1 e h=5 o que
   corri coincide com um atraso de 1 e 5 minutos, e lá não havia nada para matar.
3. **Potência, outra vez.** Nos dois horizontes onde a aritmética do custo é possível
   (60 e 240 min), 104 dias dão 39 612 e 9 878 pontos de decisão em 16 mercados — mas
   apenas ~35 blocos independentes de 3 dias. Os IC a h=240 têm 40–120 bp de largura. Sobre
   as 5 células sem "evidência contra", o estudo diz **inconclusivo**, não "não existe".
4. **Um regime só.** 11/06–23/09 é um período e o "sempre long" foi negativo nele em quase
   todos os cortes. Um mercado com deriva teria mudado todos os números da coluna baseline
   (não necessariamente os Δ).
5. **Só 8 dos 35 mercados da mesa** entram no universo primário; os outros 26 só têm 25 dias.
   A conclusão sobre a mesa é, em rigor, uma conclusão sobre um proxy dela.
6. **`P5_hora_do_dia` não foi testado na análise primária** — não tem limiar fixo possível, e
   a h=240 só existem 6 fatias horárias. Fica declarado como **não investigado**.
7. **Não fiz** a decomposição por mercado/dobra nem a concentração nas maiores operações
   (nice-to-have da Astra). O JSON tem os dados por célula para quem quiser.

---

## 7. O que teria de ser falso para eu mudar de ideias

Uma **regra de refutação** deste veredito, escrita agora:

- Um custo de ida-e-volta **abaixo de ~0,03 %** a h=1 (o que exigiria `a = 0,083 %` cobrir o
  custo com margem) muda a parte A. Não existe rota conhecida para isso na Solana.
- Um preditor com **selectividade muito maior** — entrada em < 0,5 % das barras, com ganho
  condicional acima de 0,5 % — não foi testado e não é excluído por este estudo. Os meus
  preditores entram em 3–45 % das barras.
- **Informação que estas velas não têm**: livro, fluxo de ordens tick-a-tick, cadeia. O R68
  testou só o que está em `candles`. O KB-0145 já diz que a Binance é o sinal e a Solana a
  execução; nada aqui fecha a porta a um sinal *de outra fonte*.
- A hipótese gerada em §5 — **a perda do `momentum v3` ser sobretudo da saída e não da
  entrada** — é testável com o replay histórico (`docs/PIPELINE.md` §6c), com a estratégia
  real (não o meu P6, que é outra regra), e não foi testada.
- **Validação temporal independente.** Limiares congelados antes desta execução **não**
  tornam automaticamente 104 dias de histórico "fora de amostra": a análise fixa percorre o
  painel inteiro e a motivação dos preditores já incorpora o R63. Distinguem-se três coisas
  diferentes — teste histórico de regras fixas (o que fiz), walk-forward retrospectivo (o
  que fiz no secundário) e **sombra prospectiva** (o que não fiz). Se alguém quiser
  ressuscitar a célula h=60 de U1, o caminho é uma hipótese única congelada, com prazo,
  custo, numerário e atraso operacional definidos — e **nenhum novo ajuste seria
  "confirmação do R68"**.

**O que a mesa spot/1 teria de mudar para usar algo disto: nada, porque não há nada.**
Nenhuma célula é positiva ao custo real da mesa. Nenhum parâmetro vai ao real, nem a sombra.

---

## 8. Segunda opinião (Astra)

**Antes de correr** (`.claude/state/astra-review-r68.md`, revisão do desenho): nove must-fix.
**Aceitei oito inteiros e um parcialmente**, e a EMENDA 1 do pré-registo foi escrita **antes
de qualquer teste**. Os que mudaram o resultado:

| # | O que ela apanhou | O que fiz |
|---|---|---|
| 1 | `p* = 0,5 + c/2m` com a mediana é enganador para saída por tempo | Passei a `(b+c)/(a+b)` com médias condicionais medidas; a versão ±m ficou rotulada como modelo |
| 2 | O portão `p* < 0,70` selecciona amplitude, não previsibilidade, e mataria um sinal de episódios raros | **Caiu.** A parte A ficou descritiva; os 5 horizontes foram testados |
| 3 | Bootstrap por mercado trata exposições ao mesmo choque como réplicas independentes | Primário passou a **blocos temporais conjuntos de 3 dias** |
| 4 | Permutação dentro do dia destrói a autocorrelação em rajada que é o que o sinal apanha | **Caiu** como p-valor; substituída por bootstrap centrado sob o nulo |
| 5 | Ajustar limiar no treino é frágil; falta congelar o algoritmo inteiro | **Limiares fixos** viraram o primário; o adaptativo virou secundário. Ambos correram, ambos dão zero |
| 6 | Rótulo de treino que termina dentro do teste é fuga | Purga de `h` no fim do treino; e "entrada ao fecho" passou a ser chamada **proxy**, não execução |
| 7 | Numerário: ganhar em USDT e perder em SOL | Coluna "em SOL" acrescentada — e é **pior** que a USDT em quase toda a grelha |
| 8 | Filtrar horizontes em A e depois corrigir só os sobreviventes é selecção pelo teste | 25 células congeladas sem filtro; **Holm** (familiar) para confirmar, BH reportado |
| 9 | Faltava regra de encerramento e ganho mínimo relevante | MRE = +10 bp fixado antes; daí o "20/25 com evidência **contra**" |

**Rejeitei parcialmente um:** ela queria reservar uma avaliação **prospectiva** com prazo
fixo para concluir sobre a mesa. Concordo com o princípio e não o fiz — o R68 tinha de
responder hoje. Consequência declarada: qualquer "confirma" deste estudo seria candidato a
**sombra**, nunca parâmetro de mesa real. Como deu zero, a questão não se põe.

**Depois de correr** (`.claude/state/astra-review-r68-veredito.md`): seis must-fix no
veredito. **Aceitei os seis.**

| # | O que ela apanhou | O que fiz |
|---|---|---|
| 1 | Eu tinha escrito "o melhor líquido é −0,85 bp" — **falso**: h=240 P3 dá **+27,58 bp** (IC a atravessar zero). E os IC são **individuais**, não simultâneos | Reescrevi a resposta curta com a redacção dela; as 5 células de h=240 passaram de "sem vantagem" a **inconclusivas** |
| 2 | `a` e `b` são incondicionais; `p* = 1,34` é impossibilidade **mantendo aquele payoff**, não impossibilidade de selecção | Qualificado em §2 e na resposta curta |
| 3 | U1 não está provado ser artefacto; e o meu U1 é a mesa **sem** os 8 partilhados, não a mesa | Reclassificado como "achado exploratório no proxy de U1, não confirmado para a mesa, não demonstrado como artefacto"; população corrigida |
| 4 | "Atraso de uma barra" mede **persistência do sinal**, não latência; "se morre, não é da mesa" é excessivo | Frase retirada; §6.2 reescrita com o teste correcto que **não** fiz |
| 5 | **Bug real:** o baseline do adaptativo usava o painel inteiro em vez das janelas de teste | Corrigido (`base_mask`), re-corrido, Δ actualizados; veredito inalterado |
| 6 | P6 **não** é a regra do `momentum v3` (máximas vs fechos, 15 m, portões de rvol/ATR, stop por ATR) | §5 reescrita: a reconciliação vira hipótese sobre a família, não sobre a estratégia |

**A ressalva que ela põe acima de todas (e eu concordo):** limiares congelados antes da
execução **não** tornam 104 dias de histórico "fora de amostra"; falta uma **validação
temporal independente** (sombra prospectiva). Isto não muda o veredito negativo — torna-o
mais conservador —, mas impediria qualquer veredito positivo de ir para a mesa.

---

## 9. Ficheiros

| ficheiro | o quê |
|---|---|
| `.claude/state/r68/preregistro.md` | protocolo congelado + EMENDA 1 (pós-Astra, pré-teste) |
| `.claude/state/r68/load68.py` | carregador, agregação de barras, **guarda anti-look-ahead** |
| `.claude/state/r68/test_load68.py` | 8 provas, incluindo a estratégia batoteira e a vela não-final |
| `.claude/state/r68/signals68.py` | os 5 preditores de limiar fixo |
| `.claude/state/r68/parta.py` / `.txt` / `.json` | muro do custo |
| `.claude/state/r68/partb.py` / `partb_U2.txt` / `partb_U1desk.txt` | walk-forward primário |
| `.claude/state/r68/partb_adaptive.py` / `partb_adapt_U2.txt` | walk-forward adaptativo (secundário) |
| `.claude/state/r68/q_deep.sql`, `q_desk.sql` | as duas únicas leituras da VPS (`COPY TO STDOUT`) |

CSV brutos (57 MB) no *scratchpad* da sessão, fora do repositório; `.claude/state/r68/` = 282 KB.
