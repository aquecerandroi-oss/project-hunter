# notes-D-P23 — a curva de movimento depois da entrada: **o ganho bruto da mãe continua subindo depois dos 80 min, mas pela cauda**

**Data:** 2026-09-11, 10:05 → 10:25 BRT (13:05 → 13:25 UTC). Plantão run 11, faixa 3, item 3 —
primeira da ordem da Astra.
**Owner:** quant-engineer.
**Base local:** árvore compartilhada, **nada commitado**, **nada escrito na VPS** (todas as leituras
em `begin transaction isolation level repeatable read read only; … commit;`).
**Nenhum replay novo, nenhum container tocado, nenhum `.env*` tocado, nenhum testcontainer,
nenhum shell em background.** Código de estratégia **não** editado.

---

## STATUS

**DONE.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Curva pós-entrada das 542 decisões da mãe (`mean_reversion v1`, coorte `replay:fa005985…`) nos horizontes pedidos, **bruta a partir do OPEN da barra de entrada** (correção da Astra), em ATR da própria decisão, long-only | **OK.** §3 |
| 2 | Por horizonte: média, mediana, p25/p75, fração positiva; e o Δ(240 − 80) **pareado** com IC 95 % de blocos de dia (`blocos90.py` reusado) | **OK.** §3, §4 |
| 3 | Mesma curva para as 373 decisões da irmã de 5 min (EXP-0028, `replay:92c8d080…`), horizontes +5…+80 | **OK.** §5 |
| 4 | E a curva da mãe restrita aos MESMOS mercados/dias que a irmã negociou, só para comparação | **OK.** §6 |
| 5 | Artefatos (`exp-drafts/dp23/`, SQL de pesquisa, esta nota), D-P23 → `medida` no INBOX, adendo datado na KB-0079 | **OK.** §9 |

**O resultado em uma frase, no vocabulário permitido:** **há** evidência de acumulação adicional de
movimento bruto entre +80 e +240 min nas entradas da mãe — Δ pareado **+0,3007 ATR** com IC 95 %
**[+0,0071; +0,5820]**, que exclui zero por pouco —, mas essa acumulação é **de cauda, não de
maioria**: a **mediana** do mesmo Δ é **+0,0598 ATR** com IC **[−0,1864; +0,3470]**, que **não**
exclui zero, e só **51,8 %** dos 542 pares têm Δ > 0. O horizonte de 80 min da irmã cai **antes** do
ponto em que a curva bruta da mãe pára de subir (aos +80 min a mãe tem **40,4 %** do movimento que
ela tem aos +240 min) — e, ao mesmo tempo, **41,0 %** das operações reais da mãe já estavam fechadas
antes dos 80 min (p50 de duração real **61 min**) e só **8,3 %** chegaram aos 240 min, então o pedaço
de curva entre 80 e 240 min é, para nove de cada dez decisões, **contrafactual**.

**O que esta nota não diz, por construção:** nada sobre a **causa** da perda da irmã. A transposição
mudou três coisas de uma vez (tendência 1 h → 15 min, ATR 15 → 5 min, horizonte 14 400 → 4 800 s,
`mean_reversion_m5_v1.py:27`); a curva da mãe é uma propriedade das **entradas da mãe**, e a irmã
entra em barras diferentes. A aposentadoria da `mean_reversion_m5 v1` (2026-09-11T10:54:08Z) continua
de pé e **nada aqui a reabre**. A expressão "sinal destruído" não é usada nesta nota.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-11-dp23-q00-catalogo.sql` | catálogo das duas coortes: n, `entry_ts`, ATR, direção, horizonte declarado, existência da vela de entrada, os recortes de comparação |
| `infra/scripts/sql/research/2026-09-11-dp23-q01-curva-mtm.sql` | o dump CSV (formato longo) da curva: uma linha por (decisão, horizonte) |
| `infra/scripts/sql/research/2026-09-11-dp23-q02-duracao-real.sql` | quanto tempo a operação **real** ficou aberta (o que torna o trecho 80→240 contrafactual) |
| `.claude/state/exp-drafts/dp23/curva.py` | o módulo de leitura: `ret_atr`, `resumo`, `curva_por_horizonte`, `delta_pareado_por_decisao`, `diferencas_pareadas`, `ic_mediana_blocos`, `endpoint_open_time`, `escolhe_endpoint` |
| `.claude/state/exp-drafts/dp23/test_curva.py` | **22 testes** com séries sintéticas e valor esperado calculado à mão, incluindo os 5 de anti-antecipação |
| `.claude/state/exp-drafts/dp23/analise.py` | as seis seções da leitura |
| `.claude/state/exp-drafts/dp23/dp23-curva.csv` | as 7 116 linhas lidas da VPS (542 × 9 + 373 × 6) |
| `.claude/state/exp-drafts/dp23/saida-q00.txt`, `saida-q02.txt`, `saida-analise.txt` | as saídas cruas, verbatim |
| `.claude/state/notes-D-P23.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O MÉTODO, E AS QUATRO ESCOLHAS QUE A ASTRA FIXOU

A régua desta medição é a do MUST-FIX 3 de `.claude/state/astra-review-plantao-20260911-0935.md`,
mais a correção que o brief carimbou (a base é o **open da barra de entrada**, não `virtual_entry`).

1. **BASE = `candles.open` da barra de entrada** (`open_time = signal_outcomes.entry_ts`). O walker
   entra no **open** da barra seguinte ao fechamento da barra de decisão (`walker.py:42`), e
   `virtual_entry` já carrega 6 bps de spread + slippage (`pricing.py:47`:
   `cost_bps = spread/2 + slippage = 1 + 5`). Uma curva construída sobre `virtual_entry` já nasceria
   com a fricção de entrada dentro e **não** seria bruta.
   **Conferido, não suposto:** nas **915** decisões das duas coortes,
   `virtual_entry = open × 1,0006` a menos de **1e-9** (q00 §4, coluna
   `open_inconsistente_com_virtual_entry = 0`).
2. **PONTO em +h min = o `close` da vela de 1 min que FECHA em `entry_ts + h`**, isto é, a vela cujo
   `open_time = entry_ts + (h − 1) min`. Usar a vela que **abre** em `entry_ts + h` acrescentaria um
   minuto ao horizonte e leria uma vela que, no instante `+h`, ainda estava em formação — o cenário
   de falha que a Astra nomeou. Está congelado em `endpoint_open_time()` e tem **cinco** testes
   próprios (§7).
3. **UNIDADE = o ATR congelado da própria decisão**,
   `agent_signals.supporting_features->'atr'->>'value'` (`mean_reversion_v1.py:294`) — 15 m/97 barras
   na mãe, 5 m na irmã. Não é um ATR recalculado hoje.
4. **Long-only, conferido:** 542 de 542 e 373 de 373 são `long` (q00 §2), então `direção ×` é `×(+1)`
   e a coluna `direcao` viaja no CSV para que isso seja verificável por quem reler.
5. **Sem stop, sem alvo, sem preenchimento.** Ausência de endpoint sairia vazia e sairia do
   denominador daquele horizonte — jamais preenchida com o preço anterior. **Não houve nenhuma**
   (§2).
6. **Vela obrigatoriamente `is_final` e `timeframe = '1m'`** (PIPELINE §2, anti-antecipação).

**Defeito achado e corrigido na primeira passada, registrado porque ele muda o denominador:** a
primeira versão do q01 juntava `candles` por `markets.symbol` e `markets` tem **duas** linhas por
símbolo na binance (perpétuo e spot, PIPELINE §1d item 3) — o dump saiu com **14 526** linhas em vez
de 7 116, cada decisão dobrada. A junção passou a viajar por `agent_signals.market_id`, a identidade
que a decisão realmente carrega. O motivo está no cabeçalho do arquivo.

---

## 2. COBERTURA — a exigência da Astra ("as mesmas 542 em todos os pontos, ou a diferença dita")

**As mesmas 542 em todos os nove pontos, e as mesmas 373 nos seis.** Sem exceção:

```
mae  mean_reversion v1: 542 decisoes, 16 mercados, 83 dias
   +  5 / +10 / +15 / +30 / +60 / +80 / +120 / +180 / +240 min : 542/542 (100,00 %) em todos
irma mean_reversion_m5 v1: 373 decisoes, 14 mercados, 72 dias
   +  5 / +10 / +15 / +30 / +60 / +80 min : 373/373 (100,00 %) em todos
```

Isso é consequência da fita 100 % completa nos 90 dias (T3.62b §1.2) e é o que permite tratar a
curva como **uma população lida em nove instantes**, e não como nove populações diferentes.

**Checagem cruzada de duas implementações independentes:** o `ret_atr` calculado em SQL
(`(close − open)/atr`, arredondado em 8 casas) contra o `ret_atr` recalculado em Python a partir das
colunas cruas — **7 116 pontos, maior divergência absoluta 5,0e-09**, dentro do arredondamento. É o
substituto do teste de antecipação que roda contra Postgres e que este brief não autoriza (§7).

Catálogo das duas coortes (q00 §1):

| coorte | versão | terminais | mercados | dias | primeira entrada | última entrada | horizonte |
|---|---|---:|---:|---:|---|---|---:|
| `replay:fa005985-0b55-4820-904c-8ada589e441c` | `mean_reversion v1` | 542 | 16 | 83 | 2026-06-12 21:01Z | 2026-09-09 20:16Z | 14 400 s |
| `replay:92c8d080-6009-4a59-9868-31282b1bd493` | `mean_reversion_m5 v1` | 373 | 14 | 72 | 2026-06-12 10:46Z | 2026-09-09 17:56Z | 4 800 s |

---

## 3. A CURVA DA MÃE — 542 decisões, bruta, em ATR da própria decisão

```
 h(min)     n     media   mediana       p25       p75     %>0  zeros
      5   542   +0.0143   +0.0000   -0.1815   +0.2043   47.4%     18
     10   542   +0.0262   +0.0000   -0.2263   +0.3155   49.1%     17
     15   542   +0.0238   +0.0000   -0.3044   +0.3421   49.6%      8
     30   542   +0.0869   +0.0661   -0.3445   +0.5088   52.4%     16
     60   542   +0.1205   +0.1195   -0.4852   +0.7071   56.5%      2
     80   542   +0.2038   +0.0937   -0.5245   +0.8403   54.1%      4
    120   542   +0.2593   +0.2077   -0.7405   +1.0693   54.8%      2
    180   542   +0.3413   +0.1533   -0.9228   +1.3227   53.0%      2
    240   542   +0.5045   +0.2741   -1.1224   +1.4915   55.7%      3
```

Três leituras que o número exige:

- **a média sobe monotonicamente** de +0,014 ATR aos 5 min a +0,505 ATR aos 240 min — nenhum ponto
  de inflexão, nenhum platô visível dentro do horizonte da versão. Nos primeiros 15 min o movimento
  bruto é **praticamente zero** (a mediana é exatamente 0,0000 nos três primeiros pontos, com 18/17/8
  zeros exatos — mercados que não andaram um tick nesse prazo);
- **a fração positiva sobe pouco e não monotonicamente** (47,4 % → 56,5 % aos 60 min → 54,1 % aos
  80 → 55,7 % aos 240). A curva de **média** sobe muito mais do que a de **acerto**: o que cresce é o
  tamanho do movimento condicional, não a proporção de decisões em que o preço está acima da entrada;
- **a dispersão cresce mais rápido que a média.** O intervalo p25–p75 vai de 0,386 ATR (aos 5 min) a
  **2,614 ATR** (aos 240 min) — 6,8× — enquanto a média cresce 35×, partindo de perto de zero. A
  curva é tão uma curva de **incerteza acumulada** quanto de movimento acumulado.

---

## 4. O Δ PAREADO — o número que o brief pede, com os dois estimadores

Pareado **por decisão** (a mesma linha nos dois horizontes), estimador = **média das diferenças**,
nunca a diferença das médias de duas populações; IC 95 % por bootstrap de **blocos de dia**
(20 000 reamostragens, semente 20260910, `blocos90.ic_media` **reusado e não reimplementado**).
**0** decisões têm só um dos dois pontos.

```
     D(h-80)     n  dias     media   mediana   IC95 inf   IC95 sup  exclui 0
           5   542    83   -0.1896   -0.0808    -0.3477    -0.0309       sim
          10   542    83   -0.1776   -0.0853    -0.3286    -0.0256       sim
          15   542    83   -0.1800   -0.0584    -0.3220    -0.0354       sim
          30   542    83   -0.1169   -0.0353    -0.2378    +0.0024       nao
          60   542    83   -0.0833   -0.0321    -0.1569    -0.0125       sim
         120   542    83   +0.0554   +0.0438    -0.0365    +0.1427       nao
         180   542    83   +0.1374   +0.0000    -0.0816    +0.3616       nao
         240   542    83   +0.3007   +0.0598    +0.0071    +0.5820       sim
```

**O número do brief, isolado:**

```
D(240 - 80) = +0.3007 ATR   IC95 [+0.0071; +0.5820]   n = 542 pares em 83 dias
mediana do MESMO D = +0.0598 ATR   IC95 [-0.1864; +0.3470]
fracao de pares com D > 0: 51.8 %
```

### 4.1 O que a média e a mediana **discordando** significa, e por que isso é o achado

A média do Δ exclui zero; a **mediana do mesmo Δ não exclui**, e a fração de pares com Δ > 0 é
**51,8 %** — quase uma moeda. As duas coisas juntas dizem uma frase só:

> A acumulação adicional entre 80 e 240 min existe em **média** e é feita por uma **minoria de
> decisões com movimento tardio grande**, não por um deslocamento da distribuição inteira.

Isso não é uma ressalva menor; é a diferença entre dois experimentos futuros distintos. "Metade das
decisões anda mais um pouco" pediria alongar o horizonte; "uma em vinte anda muito mais" pede um
gatilho que identifique *qual*, e alongar o horizonte de todas paga a cauda esquerda das outras
dezenove. **Este diagnóstico não distingue os dois casos** — ele só mostra que o segundo é o mais
compatível com o dado.

O `ic_mediana_blocos` é código novo desta tarefa, irmão de `blocos90.ic_media` (mesmo bloco, mesma
justificativa de KB-0010), com quatro testes próprios; e `diferencas_pareadas` existe para que o
segundo estimador leia **exatamente** a mesma população pareada que o primeiro, com um teste que
afirma essa identidade.

### 4.2 A razão descritiva, e por que ela não decide nada

`curva(80)/curva(240) = 0,4041` (+0,2038 / +0,5045). O denominador é positivo e está longe de zero
neste recorte, então a razão é legível — mas ela é **só descritiva**, exatamente como a
pré-registração exige, e o cenário de falha que a Astra nomeou (`curva(80) = −0,01` e
`curva(240) = +0,001` dando razão −10) continua sendo a razão pela qual ela não é o veredito. O
veredito é o Δ pareado com IC, e ele vem com a ressalva de §4.1.

### 4.3 O trecho 80→240 min é contrafactual para nove de cada dez decisões (q02)

A curva é um MTM **sem stop e sem alvo** — é o que o brief pede, e é preciso dizer o que ela
**não** é:

```
        versao        |  n  | media_min |  p25  |  p50  |  p75   | max | aberta_apos_80 | aberta_em_240
 mean_reversion v1    | 542 |     85.28 | 27.25 | 61.00 | 126.75 | 240 |            222 |            45
 mean_reversion_m5 v1 | 373 |     26.34 |  7.00 | 18.00 |  38.00 |  80 |              0 |             0

 mean_reversion v1    | stop    | 281 | p50 43 min
 mean_reversion v1    | target  | 216 | p50 68 min
 mean_reversion v1    | expired |  45 | p50 240 min
 mean_reversion_m5 v1 | stop    | 197 | p50  9 min
 mean_reversion_m5 v1 | target  | 142 | p50 22 min
 mean_reversion_m5 v1 | expired |  34 | p50 80 min
```

**222 de 542 (41,0 %) das operações da mãe ainda estavam abertas depois dos 80 min; só 45 (8,3 %)
chegaram aos 240** — as que expiraram no horizonte. A duração real mediana é de **61 min**. Então o
+0,5045 ATR aos 240 min **não é o que a mãe ganhou**: é o que o preço fez, para uma população cuja
maioria já tinha saído por stop (281) ou alvo (216) antes. Ler essa curva como "expectativa por
horizonte" seria trocar uma trajetória de preço por um resultado de operação — e o resultado da
operação já está medido e é outro número (EXP-0025: `r_ex_funding` **−0,0910 R** em 90 d).

---

## 5. A CURVA DA IRMÃ DE 5 min — 373 decisões, +5…+80 min (o horizonte dela)

```
 h(min)     n     media   mediana       p25       p75     %>0  zeros
      5   373   -0.0724   -0.0592   -0.3655   +0.2526   42.6%     15
     10   373   -0.0785   -0.0239   -0.5184   +0.4004   48.5%      3
     15   373   -0.0166   +0.0257   -0.5954   +0.6315   50.7%      5
     30   373   +0.1122   +0.0910   -0.7433   +0.9669   54.4%      1
     60   373   +0.1747   +0.2434   -0.9699   +1.1804   54.7%      4
     80   373   +0.2259   +0.2249   -1.0179   +1.3309   54.2%      1

     D(h-80)     n  dias     media   mediana   IC95 inf   IC95 sup  exclui 0
           5   373    72   -0.2983   -0.2249    -0.5510    -0.0261       sim
          10   373    72   -0.3044   -0.2257    -0.5388    -0.0517       sim
          15   373    72   -0.2425   -0.2410    -0.4420    -0.0195       sim
          30   373    72   -0.1136   -0.1555    -0.3044    +0.1139       nao
          60   373    72   -0.0512   +0.0000    -0.1718    +0.0900       nao
```

A forma é a mesma: os primeiros 15 min são **negativos** em média (−0,072 / −0,079 / −0,017 ATR) e a
curva só passa de zero entre 15 e 30 min. Dentro do horizonte dela a curva também está subindo aos
+80 min — não há platô visível.

### 5.1 CONCERN 1 (meu) — **as duas curvas não estão na mesma unidade, e o brief pede a unidade que esconde isso**

O ATR da mãe é de **15 min** e o da irmã é de **5 min**; a EXP-0028 mediu ATR% p50 de **0,5585 %**
(15 m) contra **0,2714 %** (5 m). Então "+0,2038 ATR" (mãe, 80 min) e "+0,2259 ATR" (irmã, 80 min)
**não são o mesmo movimento de preço** — parecem quase iguais porque os denominadores diferem por
~2×. A mesma curva em **% do preço de entrada**, a única unidade que as duas coortes dividem (§5 do
`analise.py`):

```
 h(min)   mae (% do preco)   irma (% do preco)
      5            +0.0300             -0.0855
     10            +0.0449             -0.1242
     15            +0.0398             -0.0841
     30            +0.1076             +0.0449
     60            +0.1400             +0.0994
     80            +0.2234             +0.1188
    120            +0.2651                  —
    180            +0.3726                  —
    240            +0.5228                  —
```

**Aos 80 min as entradas da mãe andaram +0,223 % e as da irmã +0,119 % — cerca de metade.** Essa
comparação é **descritiva e entre populações diferentes** (entradas diferentes, dias diferentes,
mercados diferentes), não um contraste pareado, e não atribui causa a nada. Ela está aqui só para
impedir que a tabela em ATR seja lida como "a irmã captura o mesmo movimento".

---

## 6. A MÃE RESTRITA AOS MESMOS MERCADOS/DIAS DA IRMÃ — só para comparação

A irmã negociou **14** dos 16 mercados (BTCUSDT e BNBUSDT não produziram nenhuma decisão em 90 d),
**72** dias, **200** pares (mercado, dia) distintos. Dois recortes, os dois declarados, porque
"mesmos mercados/dias" admite duas fronteiras:

- **estrito** — a decisão da mãe está num par (mercado, dia) que a irmã também negociou: **249** das
  542;
- **largo** — o mercado está entre os 14 **e** o dia está entre os 72, sem exigir o par: **473** das
  542.

```
recorte estrito (249 decisoes, 55 dias)
 h(min)     n     media   mediana       p25       p75     %>0
      5   249   +0.0297   +0.0140   -0.1663   +0.2347   50.6%
     10   249   +0.0731   +0.0365   -0.1923   +0.3384   52.2%
     15   249   +0.0660   +0.0080   -0.2608   +0.3846   50.2%
     30   249   +0.1090   +0.0657   -0.3439   +0.4637   51.8%
     60   249   +0.1834   +0.1854   -0.4906   +0.7648   58.6%
     80   249   +0.2999   +0.1505   -0.4977   +1.0145   57.4%
    120   249   +0.2770   +0.1527   -0.7742   +1.1385   52.6%
    180   249   +0.5778   +0.1561   -0.8261   +1.4867   53.0%
    240   249   +0.8310   +0.2761   -1.0280   +2.0634   56.6%
   media   D(240-80) = +0.5311  IC95 [+0.1417; +0.9225]
   mediana D(240-80) = +0.0758  IC95 [-0.1927; +0.5067]     pares com D > 0: 53.0 %

recorte largo (473 decisoes, 67 dias)
     80   473   +0.1864   +0.0974   -0.5458   +0.8240   54.3%
    240   473   +0.5407   +0.2761   -1.1176   +1.5151   56.0%
   media   D(240-80) = +0.3543  IC95 [+0.0385; +0.6517]
   mediana D(240-80) = +0.0812  IC95 [-0.1816; +0.3853]     pares com D > 0: 53.1 %
```

**Os dois recortes contam a mesma história que a população cheia, com o mesmo padrão média-vs-mediana:**
o Δ médio é maior (+0,53 e +0,35 contra +0,30) e continua excluindo zero; a mediana é **menor**
(+0,076 e +0,081) e continua **não** excluindo zero. O recorte estrito é o mais chamativo — a curva
vai a **+0,83 ATR** aos 240 min — e é também o de menor n (249 em 55 dias) e o mais exposto à
multiplicidade: **eu escolhi três recortes** (cheio, estrito, largo) e reporto os três, sem correção
de multiplicidade, exatamente porque nenhum deles é um teste de hipótese aqui.

**O que o recorte não faz:** ele **não** pareia por (mercado, barra) e portanto **não** é um contraste
entre as duas versões. A PIPELINE §4b item 11 é explícita: comparar populações de versões diferentes
exige parear por (mercado, barra) sobre as barras elegíveis compartilhadas, e as decisões de uma não
são subconjunto das da outra. O recorte só responde "a curva da mãe muda quando eu olho só onde a
irmã esteve?" — e a resposta é "não muda de forma; fica mais alta e com menos n".

---

## 7. TESTES

Esta tarefa **não escreveu código de produção**: ela produz evidência, SQL de pesquisa e um módulo
de leitura local com testes próprios.

O módulo novo, TDD, séries sintéticas com valor esperado calculado à mão (a primeira passada foi
vermelha por `ModuleNotFoundError: No module named 'curva'`, antes de o módulo existir):

```
$ cd .claude/state/exp-drafts/dp23 && uv run --with numpy --with pytest pytest test_curva.py -q -p no:randomly
......................                                                   [100%]
22 passed in 1.61s
```

**Os cinco testes de anti-antecipação (a exigência do contrato).** Não há feature nova aqui, mas há
uma **escolha de janela** que é exatamente onde a antecipação entraria nesta medição — qual vela é o
endpoint de `+h`. Os testes fixam:

- `endpoint_open_time(0, 5) == 4` — o ponto de `+5` é o `close` da vela que **fecha** no minuto 5,
  não o da que **abre** nele (que fecha no 6);
- `test_mudar_a_vela_que_ainda_nao_fechou_no_instante_medido_nao_muda_a_curva` — o endpoint de `+5`
  é idêntico com a vela do minuto 5 valendo +999, −999, ou não existindo. **É a prova pedida: uma
  vela não final mudando não muda a leitura**;
- `test_uma_vela_nao_final_no_proprio_endpoint_e_ausencia_nunca_substituida` — `is_final = false` no
  próprio endpoint devolve ausência, nunca o fechamento anterior;
- `test_virar_is_final_para_true_e_o_que_faz_o_ponto_existir` — o espelho do anterior: é o bit
  virando que faz o ponto nascer, como em `test_beta_job.py::test_a_minute_that_is_not_final_...`.

O código de produção de que a leitura depende (não tocado por esta tarefa):

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
                packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py -q -p no:randomly
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 3.97s

$ uv run pytest services/strategy-worker/tests/test_outcome_walk.py \
                services/strategy-worker/tests/test_entry_plan.py -q -p no:randomly -m "not integration"
.......................................                                  [100%]
39 passed in 0.83s

$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py                 packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py                 services/strategy-worker/tests/test_outcome_walk.py                 services/strategy-worker/tests/test_entry_plan.py -q -p no:randomly -m "not integration"
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 4.35s
```

**O que eu NÃO rodei, e por quê.** `services/strategy-worker/tests/test_replay_lookahead.py` (a
prova, com o contra-teste da estratégia que trapaceia de propósito, de que uma decisão replayada não
lê vela que fecha depois do corte) é `@pytest.mark.integration` e precisa de Postgres por
testcontainer — **proibido pelo brief**. O substituto empírico que **esta** tarefa produz é a
checagem cruzada de duas implementações do `ret_atr` (§2, 7 116 pontos, divergência máxima 5,0e-09) e
os cinco testes de janela acima.

---

## 8. ASSUNÇÕES NUMÉRICAS QUE EU TIVE DE FAZER

1. **O endpoint de `+h` é a vela cujo `open_time = entry_ts + (h − 1) min`** (ela fecha em
   `entry_ts + h`). A convenção alternativa (`open_time = entry_ts + h`) mediria `h + 1` minutos.
   Escolhida porque a entrada acontece no **open** da barra `entry_ts`, logo o instante da entrada é
   o início dessa vela. **Congelada em código com cinco testes** (§7).
2. **Os horizontes são a união de duas listas.** O brief pediu 5/10/15/30/60/80/120/240 e a linha do
   INBOX pediu 5/15/30/60/80/120/180/240. Medi os **nove** da união (5/10/15/30/60/80/120/180/240)
   para não escolher entre duas fontes. Nenhum ponto foi descartado depois de medido, e os nove estão
   na tabela — a defesa contra "procurar o melhor horizonte entre oito pontos" (Astra) é que o
   veredito está fixado no Δ(240 − 80) desde a pré-registração, e é ele que aparece isolado em §4.
3. **O bloco do bootstrap é o DIA de calendário UTC da ENTRADA** (`entry_ts`), não o de `emitted_at`
   (que a T3.62b usou). Os dois diferem só para uma decisão cuja barra fecha em 23:59Z; o bloco
   serve para capturar correlação intradiária entre 16 mercados, e ancorá-lo na entrada é o que
   corresponde à grandeza medida. 20 000 reamostragens, semente **20260910** — as da
   pré-registração, para reprodução.
4. **`blocos90.ic_media` é reusado, não reimplementado.** `ic_mediana_blocos` é novo e é o mesmo
   procedimento com a mediana no lugar da média; ele existe porque a média do Δ é sensível à cauda
   (§4.1) e sem um segundo estimador a leitura seria incompleta. Quatro testes próprios.
5. **Percentis por interpolação linear** (a convenção de `numpy.percentile`, e a mesma de
   `percentile_cont` no q02, para que as duas leituras sejam comparáveis). Mediana de amostra par é a
   média dos dois centrais.
6. **`%>0` conta positivos ESTRITOS**; o número de zeros exatos viaja ao lado em toda tabela porque
   nos três primeiros horizontes da mãe ele não é desprezível (18/17/8 de 542) — um mercado que não
   andou um tick em 5 min não é "não positivo" no mesmo sentido de um que caiu.
7. **A unidade do brief (ATR da própria decisão) não é comparável entre as duas coortes** (ATR 15 m
   vs 5 m). A tabela em % do preço de entrada de §5.1 é acréscimo meu, não substituição, e é o único
   lugar desta nota em que os dois números podem ser postos lado a lado.
8. **`exit_ts − entry_ts` é a duração real** do q02, com `entry_ts` = `open_time` da barra de entrada.
   Para os 45 `expired` da mãe ela dá exatamente 240 min, o que confirma que a régua de horizonte do
   walker e a régua desta curva concordam no mesmo minuto.

---

## 9. O QUE EU DELIBERADAMENTE NÃO FIZ

- **Não rodei replay nenhum.** As duas coortes já existiam; esta tarefa é leitura.
- **Não escrevi nada na VPS** nem toquei em container, `.env*`, partição ou `strategy_versions`.
- **Não reabri a `mean_reversion_m5 v1`** nem propus reabri-la. Ela está aposentada
  (2026-09-11T10:54:08Z, `successor=none`) e este diagnóstico não é fundamento para reverter isso —
  a própria Astra: "não pode concluir 'a perda da filha é horizonte' nem justificar sua reabertura
  sozinho".
- **Não classifiquei causa.** Nenhuma frase desta nota atribui a diferença entre as duas versões a
  horizonte, a ATR ou a tendência; a transposição mudou os três de uma vez.
- **Não editei código de estratégia**, `stress.py`, nem a página EXP-0028 (é do orquestrador, pela
  divisão registrada no lane3).
- **Não propus experimento novo.** §4.1 diz qual pergunta um experimento futuro teria de separar
  (cauda vs deslocamento), e isso é insumo para um pré-registro, não um pré-registro.
- **Não apliquei correção de multiplicidade** aos três recortes de §6 nem aos oito Δ de §4 — eles são
  descritivos e estão todos reportados, o que é a alternativa honesta a corrigir uma família que eu
  mesmo escolhi.

---

## 10. AS 10 LINHAS PARA O EVERTON

> **Onde a `mean_reversion` de 15 min ganha, ao longo das 4 horas que ela segura a posição.**
> 1. Medi, nas **542 entradas** que já estavam congeladas (nada de replay novo), quanto o preço andou depois de entrar: aos 5, 10, 15, 30, 60, **80**, 120, 180 e **240 minutos**. As 542 aparecem nos **nove** pontos — **100 % de cobertura**, sem um buraco.
> 2. A conta é **bruta**, a partir do **preço de abertura** da barra de entrada — não do preço com spread e slippage, que já viria descontado. A Astra pediu essa correção e ela foi conferida: nas 915 operações das duas versões, a entrada com custo é exatamente a abertura × 1,0006.
> 3. **A curva sobe até o fim:** +0,01 ATR aos 5 min, +0,20 aos 80 min, **+0,50 aos 240 min**. Aos 80 minutos o preço andou só **40 %** do que ele anda até as 4 horas.
> 4. **Sim, há acumulação depois dos 80 min:** +0,30 ATR em média, com intervalo de confiança **[+0,01; +0,58]**, que não passa por zero — por pouco.
> 5. **Mas o achado de verdade é o contrário do que parece.** Pela **mediana** o ganho extra é de só **+0,06 ATR**, com intervalo **[−0,19; +0,35]** que **passa** por zero, e só **52 %** das operações andam mais entre 80 e 240 min. Ou seja: **não é "quase todas andam mais um pouco"; é "poucas andam muito mais"**.
> 6. Isso muda o que se faria com a informação: alongar o horizonte de todas para colher a cauda de poucas paga o prejuízo das outras. O caminho seria **identificar quais**, e isso é um experimento novo que eu **não** propus aqui.
> 7. **Um freio importante:** essa curva é o preço, não a operação. Na vida real a mãe fecha em **61 minutos** (mediana); **41 %** das operações passam dos 80 min e só **8 %** chegam às 4 horas. O trecho entre 80 e 240 min é **contrafactual** para nove de cada dez decisões.
> 8. A irmã de 5 minutos, no horizonte dela, tem curva da **mesma forma** — negativa nos primeiros 15 min, positiva depois. E ela fecha em **18 minutos** de mediana, muito antes dos 80 do próprio limite.
> 9. **Cuidado com uma comparação fácil:** "+0,20 ATR" nas duas **não é o mesmo movimento** — o ATR da mãe é de 15 min e o da irmã é de 5 min. Na mesma régua (% do preço), aos 80 min a mãe andou **+0,22 %** e a irmã **+0,12 %**, cerca de metade.
> 10. **O que isto não diz:** nada sobre **por que** a irmã de 5 minutos perdeu — a transposição mudou tendência, ATR e horizonte de uma vez. A aposentadoria dela continua de pé, e nada aqui a reabre.

---

## 11. PROVENIÊNCIA — como reproduzir, verbatim

```
$ date -u +%FT%TZ                                             # 2026-09-11T13:05:16Z = 10:05 BRT
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-dp23-q00-catalogo.sql
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-dp23-q01-curva-mtm.sql \
    > .claude/state/exp-drafts/dp23/dp23-curva.csv                       # 7 116 linhas, 6 s
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-dp23-q02-duracao-real.sql
$ cd .claude/state/exp-drafts/dp23 && uv run --with numpy python analise.py dp23-curva.csv
                                                                          # 23 s (18 bootstraps)
```

Os três SQL abrem `begin transaction isolation level repeatable read read only` e fecham com
`commit`; nenhum deles cria view, tabela temporária ou índice. `statement_timeout = 240s` em todos.
