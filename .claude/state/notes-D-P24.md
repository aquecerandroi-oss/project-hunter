# notes-D-P24 — de onde vem o Δ(240 − 80): **das saídas por ALVO, e em minutos em que a posição já estava fechada**

**Data:** 2026-09-12, 02:17 → 02:50 BRT (05:17 → 05:50 UTC). Plantão run 12, faixa 4, item 2 —
primeira da ordem da Astra (`astra-review-plantao-20260911-1030.md`: "eu faria **D-P24 primeiro**").
**Owner:** quant-engineer.
**Base local:** árvore compartilhada, **nada commitado**, **nada escrito na VPS** (todas as leituras
em `begin transaction isolation level repeatable read read only; … commit;`).
**Nenhum replay novo, nenhum container tocado, nenhum `.env*` tocado, nenhum testcontainer,
nenhum shell em background, nenhum arquivo de `apps/**`, `services/execution-worker/**`,
`packages/exchange-adapters/**` tocado.** Código de estratégia **não** editado.

---

## STATUS

**DONE.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | `Δ_i(240 − 80)` pareado das 542 decisões congeladas da `mean_reversion v1`, **em ATR e em % do preço** | **OK.** §2 — e reproduz o D-P23 dígito a dígito a partir de **outro dump** (§2.1) |
| 2 | **Decomposto pelo motivo REAL de saída** (`stop` / `target` / `time-stop` / `context-lost` / `other`, de `signal_outcomes`) | **OK.** §3. `context-lost` e `other` têm **n = 0**, e aparecem na tabela com zero em vez de desaparecer |
| 3 | Por grupo: n, dias, média, mediana, **IC 95 % de blocos de dia** (`blocos90.py` reusado; o IC da mediana do dp23 reusado) | **OK.** §3, §4 |
| 4 | **Contribuição de cada grupo ao Δ total** (`Σ Δ_i do grupo / 542`), recompondo os +0,3007 ATR | **OK.** §3 — identidade fechada com erro **5,55e-17** |
| 5 | MFE/MAE por horizonte **como coluna auxiliar apenas** | **OK.** §6 — e são **MFE/MAE de closes**, nome explícito (MUST-FIX 2) |
| 6 | A mesma tabela restrita a **time-stop contra stop** | **OK.** §5 |
| 7 | Artefatos (`exp-drafts/dp24/`, SQL de pesquisa, esta nota), D-P24 → `medida` no INBOX, adendo datado na KB-0079 | **OK.** §9, §10 |

**O resultado em uma frase, no vocabulário permitido:** o movimento bruto adicional entre +80 e
+240 min **não** se acumula no grupo em que um horizonte mais longo poderia tocá-lo (`time-stop`:
**+0,0113** de +0,3007 ATR, **3,8 %**, IC 95 % [−0,0047; +0,0274]) nem no `stop` (+0,0145, IC
[−0,1457; +0,1791]) — ele está **concentrado nas saídas por ALVO**: **+0,2749 ATR, 91,4 % do total,
IC [+0,0902; +0,4476]**, o **único** grupo cujo IC exclui zero. E partindo o **mesmo** Δ pelo instante
da saída real, **+0,2399 de +0,3007 (79,8 %)** se acumula em minutos em que a posição **já estava
fechada**. Descritivamente: é majoritariamente dinheiro que a estratégia, **como ela está configurada
hoje**, não podia tocar.

**O que esta nota não diz, por construção:** **nada** sobre o que uma política de saída diferente
**teria** rendido. Uma variante sem alvo não "captura" os +0,0910 ATR que o grupo `target` acumula
depois da própria saída: ela teria **outra** trajetória de desfechos (a armadilha nomeada na
[[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] — alvo → stop → alta grande lido como dinheiro
recuperável). Medir isso exige reexecutar o walker com outra geometria, e isso é **experimento**, não
leitura. Nenhuma versão viva é tocada, nada é proposto aqui.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-12-dp24-q00-motivos.sql` | catálogo: motivo canônico por `result`+`tracking_state`, a coluna `result` **contra** o envelope `meta.progress.result`, duração e `m_saida` por grupo, cobertura de velas, direção/horizonte/ATR, e a única decisão não terminal |
| `infra/scripts/sql/research/2026-09-12-dp24-q01-decisoes.sql` | dump CSV de **uma linha por decisão** (542): motivo, `m_saida`, `entry_open`, ATR, ATR%, os dois pontos do Δ nas duas unidades e os fechamentos extremos das **quatro** janelas de excursão |
| `infra/scripts/sql/research/2026-09-12-dp24-q02-caminho.sql` | dump CSV do **caminho minuto a minuto** (542 × 240 = 130 080 linhas) — o que permite a aritmética rodar no módulo testado em vez de dentro de um `filter (where …)` |
| `.claude/state/exp-drafts/dp24/decomp.py` | `motivo_canonico`, `delta_por_decisao`, `divide_delta`, `contribuicao`, `contribuicao_decil`, `tamanho_do_decil`, `bootstrap_conjunto`, `decompoe`, `janela_de_closes`, `mfe_mae_closes`, `ret_pct` |
| `.claude/state/exp-drafts/dp24/test_decomp.py` | **41 testes** com séries sintéticas e valor esperado calculado à mão — 5 de anti-antecipação, 1 de equivalência com `blocos90.ic_media`, 1 da identidade dentro de **cada** reamostragem |
| `.claude/state/exp-drafts/dp24/analise.py` | as sete seções da leitura (§0 a §6) |
| `.claude/state/exp-drafts/dp24/dp24-decisoes.csv` | as 542 linhas do q01 |
| `.claude/state/exp-drafts/dp24/dp24-caminho.csv` | as 130 080 linhas do q02 (7,0 MB) |
| `.claude/state/exp-drafts/dp24/saida-q00.txt`, `saida-analise.txt` | as saídas cruas, verbatim |
| `.claude/state/notes-D-P24.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`. **Reuso, não cópia:** `blocos90.ic_media` e
`blocos90.delta_pareado_por_dia` (T3.62b) e `curva.ret_atr` + `curva.ic_mediana_blocos` (D-P23) são
**importados**; `decomp.py` só adiciona o que não existia.

---

## 1. A POPULAÇÃO, E O QUE FOI CONFERIDO ANTES DE MEDIR (q00)

Coorte `replay:fa005985-0b55-4820-904c-8ada589e441c`, `mean_reversion v1`, desfechos `terminal`:
**542 decisões, 16 mercados, 83 dias** — a mesma população da T3.62b, do EXP-0025 e do D-P23.

```
  motivo   | result  | tracking_state |  n  | dias | mercados |  primeira_entrada   |   ultima_entrada
-----------+---------+----------------+-----+------+----------+---------------------+---------------------
 stop      | stop    | terminal       | 281 |   73 |       14 | 2026-06-13 13:46:00 | 2026-09-09 20:01:00
 target    | target  | terminal       | 216 |   65 |       14 | 2026-06-13 20:16:00 | 2026-09-09 20:16:00
 time-stop | expired | terminal       |  45 |   26 |       16 | 2026-06-12 21:01:00 | 2026-09-09 15:31:00
```

Cinco checagens, cada uma fechando um jeito específico de errar:

1. **`context-lost` e `other` têm n = 0** — nenhuma decisão da coorte saiu por `invalidated`. Isso é
   uma propriedade da versão: a `mean_reversion v1` não tem invalidação estrutural própria, e o
   vocabulário do brief pedia os cinco grupos justamente para que um grupo vazio **apareça como
   vazio** em vez de desaparecer. Na tabela eles têm contribuição `+0,0000` e média `—` (não `0,0`:
   média de conjunto vazio não é zero, e o módulo recusa inventá-la — teste
   `test_grupo_ausente_tem_n_zero_contribuicao_zero_e_media_NAN_nunca_zero`).
2. **A coluna canônica contra o envelope:** o D-P23 leu `meta->'progress'->>'result'`; esta nota lê a
   coluna `signal_outcomes.result`. **542 linhas, 0 discordâncias.** Se houvesse uma, uma decisão
   trocaria de grupo sem que ninguém visse.
3. **`exit_ts` nunca nulo e sempre no minuto cheio** (0 fora do minuto) — é o que torna
   `m_saida = (exit_ts − entry_ts)/1min` um inteiro e a partição das janelas exata.
4. **Cobertura total, declarada:** 542/542 com a barra de entrada, com o endpoint de +80, com o de
   +240 **e com os 240 minutos `is_final` completos**; `0` minutos faltando no total. Isso é
   consequência da fita 100 % completa nos 90 dias (T3.62b §1.2) e é o que permite tratar a partição
   antes/depois como exata em vez de aproximada.
5. **Long-only (542/542), horizonte declarado 14 400 s em todas, ATR presente e positivo em todas.**

**A 543ª decisão, que não está aqui e por quê.** Sem o filtro `terminal` a coorte tem **543** linhas:
a extra é `tracking_state = no_entry`, `no_entry_reason = geometry`, **sem `entry_ts`**. Sem entrada
não há preço-base, não há `ret(80)` nem `ret(240)`, e portanto não há `Δ` — ela sai do numerador
**e** do denominador, e está registrada aqui para que o 542 não pareça um recorte escolhido.

---

## 2. A MEDIDA PRINCIPAL — `Δ_i = ret_i(240) − ret_i(80)`, pareada por decisão

A régua é a do **MUST-FIX 1** da Astra, literal: a medida principal continua sendo o Δ pareado, e
não MFE. O motivo dela: *"uma trajetória pode atingir +5 ATR aos 60 minutos, estar em +3 aos 80 e
terminar em −1 aos 240: MFE enorme, mas contribuição de −4 ATR ao achado investigado."* As excursões
estão em §6, como coluna auxiliar, e em nenhum lugar decompõem o Δ.

Base = `candles.open` da barra de entrada (bruto, sem os 6 bps de `pricing.py:47`); ponto de `+h` = o
`close` da vela de 1 min que **fecha** em `entry_ts + h`; unidade = o ATR **congelado** da própria
decisão **e** o % do preço de entrada. **0** decisões com só um dos dois pontos.

### 2.1 A reprodução — o mesmo número, de um dump independente

```
pares com os DOIS pontos: 542   so +80: 0   so +240: 0
  D(240-80) em ATR         media +0.3007 IC95 [+0.0071; +0.5820]   mediana +0.0598 IC95 [-0.1864; +0.3470]   51.8% dos pares com D > 0   dias 83
  D(240-80) em % do preco  media +0.2995 IC95 [+0.0081; +0.5817]   mediana +0.0664 IC95 [-0.2092; +0.2814]   51.8% dos pares com D > 0   dias 83
```

A linha em ATR é **idêntica** às quatro casas ao D-P23 (§4 daquela nota) — e ela foi produzida por
uma SQL diferente (caminho minuto a minuto em vez de nove endpoints), com o motivo de saída lido de
outra coluna, e recalculada em Python a partir dos fechamentos crus. **Não é uma verificação de
rotina:** é a evidência de que a decomposição abaixo se aplica ao mesmo número que foi publicado, e
não a um Δ vizinho.

**As duas unidades quase coincidem no agregado** (+0,3007 ATR contra +0,2995 pontos percentuais) —
coincidência aritmética deste recorte, em que o ATR% da população fica perto de 1 % (média **1,08 %**,
mediana **0,84 %**, calculadas dos `atr_pct` por grupo de §3). **Elas não coincidem por grupo**, e isso
é o CONCERN 1 (§8).

### 2.2 A checagem cruzada das duas implementações (§0 da saída)

```
maior divergencia absoluta SQL x Python (em ATR), por coluna:
   ret80        4.995e-09      mfe80     0.000e+00      antes_max   0.000e+00
   ret240       4.996e-09      mae80     0.000e+00      antes_min   0.000e+00
                               mfe240    0.000e+00      depois_max  0.000e+00
                               mae240    0.000e+00      depois_min  0.000e+00
n_antes conferido em 542/542 decisoes; n_depois em 542/542
```

Os `5e-09` são o arredondamento em 8 casas que o SQL aplica; os zeros exatos são seleções (máximo e
mínimo de fechamento) que as duas implementações fazem sobre os mesmos valores. É o substituto
empírico do teste de antecipação contra Postgres (`test_replay_lookahead.py`, `@pytest.mark.integration`),
que este brief **não** autoriza — mais os cinco testes de janela de §7.

---

## 3. A TABELA — a decomposição pelo motivo REAL de saída

**Em ATR da própria decisão.** `contrib` = `Σ Δ_i do grupo / 542` (o divisor é o N **total**, nunca o
n do grupo — é o que faz as contribuições **recomporem** a média e evita dividir por uma soma total
próxima de zero, a alternativa que a Astra recusou). IC 95 % por bootstrap de blocos de **dia**,
20 000 reamostragens, semente 20260910, **os três grupos reamostrados juntos** no mesmo sorteio de
dias.

```
motivo           n  dias     media   mediana            IC95 media   contrib          IC95 contrib    %>0
stop           281    73   +0.0279   -0.2448    [-0.2639; +0.3663]   +0.0145    [-0.1457; +0.1791]  44.5%
target         216    65   +0.6899   +0.4803    [+0.2346; +1.0810]   +0.2749    [+0.0902; +0.4476]  59.3%
time-stop       45    26   +0.1356   +0.2410    [-0.0538; +0.3931]   +0.0113    [-0.0047; +0.0274]  62.2%
context-lost     0     0         —         —    [      —;       —]   +0.0000    [+0.0000; +0.0000]      —
other            0     0         —         —    [      —;       —]   +0.0000    [+0.0000; +0.0000]      —
todos          542    83   +0.3007   +0.0598    [+0.0071; +0.5820]   +0.3007    [+0.0071; +0.5820]  51.8%
IDENTIDADE    soma das contribuicoes = +0.300655   media total = +0.300655   erro = 5.55e-17
```

**Em % do preço de entrada:**

```
motivo           n  dias     media   mediana            IC95 media   contrib          IC95 contrib    %>0
stop           281    73   +0.0801   -0.2387    [-0.2193; +0.4290]   +0.0415    [-0.1190; +0.2113]  44.5%
target         216    65   +0.6195   +0.4626    [+0.1388; +1.0138]   +0.2469    [+0.0531; +0.4138]  59.3%
time-stop       45    26   +0.1327   +0.2117    [-0.1577; +0.5412]   +0.0110    [-0.0152; +0.0365]  62.2%
todos          542    83   +0.2995   +0.0664    [+0.0081; +0.5817]   +0.2995    [+0.0081; +0.5817]  51.8%
IDENTIDADE    soma das contribuicoes = +0.299460   media total = +0.299460   erro = 0.00e+00
```

Quatro leituras que o número exige:

- **a resposta do brief:** a contribuição está **concentrada nas saídas por alvo** — 91,4 % do total
  em ATR (82,4 % em % do preço), e é o **único** grupo cujo IC de contribuição exclui zero;
- **o `time-stop` — o grupo onde um horizonte mais longo poderia importar — contribui 3,8 %**
  (+0,0113 de +0,3007), com IC [−0,0047; +0,0274] que **não** exclui zero. Ele tem o **maior %
  positivo** dos três (62,2 %) e média própria +0,1356 ATR, mas são **45 de 542 decisões** (8,3 %): a
  contribuição pequena é aritmética de n, não ausência de movimento. Ler "o time-stop não anda" seria
  errado; o que o dado diz é "o time-stop **não é de onde vem o agregado**";
- **o `stop` quase desaparece no total (+0,0145) mas por cancelamento, não por imobilidade:** a
  mediana do Δ do grupo é **−0,2448 ATR** e só 44,5 % dos stops têm Δ > 0 — o grupo é o único em que
  a maioria das decisões anda **para baixo** entre 80 e 240 min. §4 mostra o cancelamento explícito;
- **o denominador não é o mesmo entre grupos**, e é por isso que as duas unidades dão contas
  diferentes: ATR% p50 de **0,8308 %** no `stop`, **0,8193 %** no `target` e **1,1134 %** no
  `time-stop` (médias 1,0258 / 1,0575 / 1,5797). O `time-stop` é o grupo de ATR mais largo, então em
  ATR ele **encolhe** e em % do preço ele quase não muda. CONCERN 1.

### 3.1 Os decis — o número que a Astra pediu no MUST-FIX 3

"Cauda, não maioria" era **leitura a confirmar** no D-P23, não achado: média com IC acima de zero e
mediana com IC cruzando zero **não** demonstram concentração. O número que separa as duas leituras:

```
motivo           n  decil   contrib  decil sup  decil inf  sup/contrib   mediana          IC95 mediana
stop           281     29   +0.0145    +0.2156    -0.1515      +14.89x   -0.2448    [-0.5219; +0.0758]
target         216     22   +0.2749    +0.2414    -0.1373       +0.88x   +0.4803    [-0.0016; +0.9263]
time-stop       45      5   +0.0113    +0.0107    -0.0093       +0.95x   +0.2410    [-0.0783; +0.5524]
todos          542     55   +0.3007    +0.4917    -0.3036       +1.64x   +0.0598    [      —;       —]
```

**A frase honesta que substitui "cauda, não maioria":** o decil superior (55 decisões) contribui
**+0,4917** e o decil inferior **−0,3036**; os **432 do meio** contribuem **+0,1125**, isto é
**37,4 %** do agregado. Então **não** é "poucas decisões explicam tudo" (o meio carrega mais de um
terço, com sinal positivo) **nem** "a distribuição inteira se deslocou" (o *net* das duas caudas
carrega os outros 63 %). É uma distribuição com **as duas caudas grandes e a direita maior** — e o
que decide o sinal do agregado é a diferença entre elas, que é a parte menos estável de qualquer
amostra (CONCERN 2).

---

## 4. O MESMO Δ PARTIDO PELO INSTANTE DA SAÍDA REAL — a resposta literal do brief

A pergunta do brief é se o extra é "dinheiro que a estratégia poderia ter guardado ou dinheiro que
ela nunca poderia tocar". O motivo de saída responde isso por grupo; a partição abaixo responde **por
minuto**, e é aritmética exata. Com `c = clamp(m_saida, 80, 240)`:

```
Δ_i = [ret(c) − ret(80)]  +  [ret(240) − ret(c)]
      \__ dentro da posição real __/   \__ depois da saída real __/
```

Telescopa por construção (maior erro por decisão: **1,78e-15**). Em ATR:

```
motivo           n  contrib dentro           IC95 dentro  contrib depois           IC95 depois      soma
stop           281         -0.1345    [-0.1721; -0.0992]         +0.1490    [+0.0078; +0.2942]   +0.0145
target         216         +0.1840    [+0.1395; +0.2302]         +0.0910    [-0.0707; +0.2377]   +0.2749
time-stop       45         +0.0113    [-0.0047; +0.0274]         +0.0000    [+0.0000; +0.0000]   +0.0113
todos          542         +0.0607    [-0.0128; +0.1366]         +0.2399    [-0.0136; +0.4768]   +0.3007
decisoes cujo trecho 80->240 e INTEIRAMENTE depois da saida: 320 (59.0%);
   inteiramente dentro da posicao: 45 (8.3%); partido: 177
```

Em % do preço: `stop` −0,1312 / +0,1727, `target` +0,1895 / +0,0574, `time-stop` +0,0110 / +0,0000,
total **+0,0694 / +0,2301**.

Três leituras:

- **79,8 % do Δ agregado (+0,2399 de +0,3007) acumula depois da saída real** — em minutos em que a
  posição não existia mais. O trecho "dentro da posição" soma +0,0607 ATR e o IC dele
  ([−0,0128; +0,1366]) **não** exclui zero;
- **o cancelamento do `stop` fica explícito:** enquanto as 83 posições stopadas depois dos 80 min
  ainda estavam abertas, o preço **caiu** (contribuição **−0,1345**, IC que **exclui** zero pelo lado
  negativo); depois de stopadas, subiu (**+0,1490**, IC que exclui zero pelo lado positivo). As duas
  metades quase se cancelam e produzem o +0,0145 do total. Esta é a leitura mais forte desta nota e é
  a que a coluna única do §3 esconderia;
- **para o `time-stop` a parte "depois" é zero por construção** (`m_saida = 240` em todas as 45): elas
  atravessaram o trecho inteiro. É o único grupo em que o Δ é integralmente movimento que a posição
  viveu — e ele vale 3,8 % do agregado.

**O que esta partição não é.** A parte "dentro da posição" **não** é o resultado realizado: o corte é
o **fechamento que cai em `exit_ts`**, não o `exit_price` (que o walker limita em `target1` num gap
favorável, `walker.py:_close`), e a conta inteira é bruta. O resultado realizado da versão é outro
número e já está medido: `r_ex_funding` **−0,0910 R** em 90 dias (EXP-0025).

---

## 5. TIME-STOP CONTRA STOP — os dois grupos que a pergunta separa

A mesma tabela restrita aos dois grupos. **O divisor da contribuição passa a ser o N desta população
(326)**, para que as contribuições recomponham a média **dela**; as contribuições ao total de 542
continuam sendo as de §3.

```
populacao restrita: 326 decisoes (45 time-stop + 281 stop), 77 dias

  --- em ATR
motivo           n  dias     media   mediana            IC95 media   contrib     %>0  decil sup
stop           281    73   +0.0279   -0.2448    [-0.2674; +0.3615]   +0.0241   44.5%    +0.3584
time-stop       45    26   +0.1356   +0.2410    [-0.0586; +0.3896]   +0.0187   62.2%    +0.0179
todos          326    77   +0.0428   -0.1130    [-0.2192; +0.3373]   +0.0428   46.9%    +0.3855
  contraste time-stop - stop = +0.1077 IC95 [-0.2452; +0.4734]  (pareado por DIA, 20000/20000 reamostragens com os dois lados)

  --- em % do preco
stop           281    73   +0.0801   -0.2387    [-0.2201; +0.4261]   +0.0691   44.5%    +0.4005
time-stop       45    26   +0.1327   +0.2117    [-0.1590; +0.5392]   +0.0183   62.2%    +0.0278
todos          326    77   +0.0874   -0.0840    [-0.1832; +0.3934]   +0.0874   46.9%    +0.4269
  contraste time-stop - stop = +0.0526 IC95 [-0.3667; +0.5502]
```

- **os dois grupos juntos somam +0,0428 ATR de média** — praticamente nada, contra +0,3007 da
  população cheia. Dito de outro modo: **tirando as saídas por alvo, o achado do D-P23 desaparece**;
- **o contraste `time-stop − stop` é +0,1077 ATR com IC [−0,2452; +0,4734]** (pareado por dia,
  as 20 000 reamostragens com os dois lados presentes). **Não distingue os dois grupos.** Em % do
  preço, +0,0526 [−0,3667; +0,5502] — a mesma conclusão, com o Δ menor porque o `time-stop` é o grupo
  de ATR mais largo;
- o contraste é **pareado por dia** (`blocos90.delta_pareado_por_dia`, reusado) porque os dois grupos
  dividem o calendário. Ele **não** é pareado por (mercado, barra) e portanto não é um contraste entre
  versões — não é essa a pergunta aqui; é um contraste entre **desfechos** da mesma versão, e o
  desfecho só é conhecido **depois**, então ele não é — e não pode virar — seletor de entrada.

---

## 6. EXCURSÕES DE CLOSES — COLUNAS AUXILIARES (§6 da saída, MUST-FIX 2)

**São de fechamentos, e o nome carrega isso.** OHLC não revela ordem intrabar; nada aqui é "o máximo
que a posição viu". `mfe` é o **máximo** e `mae` o **mínimo** do retorno de fechamento na janela, com
sinal preservado — o mínimo de uma janela inteiramente lucrativa é **positivo**, e chamar isso de
"excursão adversa" seria mentir sobre o sinal (teste
`test_o_MAE_de_uma_janela_so_de_lucro_e_POSITIVO_e_isso_nao_e_defeito`).

A janela "depois" começa **na saída**, nunca na entrada — era a exigência literal da Astra
("`MFE_240 > 0` calculado desde a entrada pode refletir somente uma alta **anterior** ao stop").

```
motivo           n    mfe80    mae80   mfe240   mae240  m_saida  mfe antes  mae antes  n>0 dep  mfe depois  mae depois
stop           281  +0.4012  -1.0557  +0.7291  -1.8100       43    +0.2698    -0.9432      281     +0.2203     -1.8100
target         216  +1.4795  -0.3124  +2.6505  -0.5129       68    +1.5056    -0.2657      216     +2.6425     +0.3442
time-stop       45  +0.7491  -0.2801  +1.1440  -0.4300      240    +1.1440    -0.4300        0           —           —
todos          542  +0.7496  -0.6264  +1.4758  -1.1482       61    +0.9475    -0.7175      497     +1.6179     -1.2598
```

Medianas, em ATR. O que elas acrescentam **sem** decompor nada: o `stop` tem MAE de closes mediano
**−1,8100 ATR** na janela de 240 min e **−1,8100** também na janela **depois** da saída — o preço
seguiu caindo depois do stop na mediana, o que é o outro lado da contribuição negativa de "dentro da
posição" em §4. No `target`, o MAE de closes **depois** da saída é **+0,3442** (positivo): na mediana,
o preço nunca voltou à entrada depois do alvo. **Nada disso diz o que um alvo diferente teria
rendido** — é a armadilha da KB-0054, e é exatamente por isso que estas colunas são auxiliares.

Para as 45 saídas por `time-stop` a janela "depois" é **vazia** (`m_saida = 240`), e vazia é o que ela
tem de ser: `—`, nunca zero.

---

## 7. TESTES

Esta tarefa **não escreveu código de produção**: ela produz evidência, SQL de pesquisa e um módulo de
leitura local com testes próprios. TDD: a primeira passada foi vermelha
(`ModuleNotFoundError: No module named 'decomp'`), e a segunda leva de cinco testes
(`divide_delta`) também foi escrita antes da função.

```
$ cd .claude/state/exp-drafts/dp24 && uv run --with numpy --with pytest pytest test_decomp.py -q -p no:randomly
.........................................                                [100%]
41 passed in 1.30s
```

Os que valem ser nomeados:

- **anti-antecipação (5).** Não há feature nova, mas há a mesma escolha de janela onde a antecipação
  entraria: `test_ANTI_ANTECIPACAO_vela_nao_final_nao_entra_na_janela`,
  `test_ANTI_ANTECIPACAO_mudar_a_vela_nao_final_NAO_muda_a_leitura` (a prova pedida pelo contrato: a
  leitura é idêntica com a vela em formação valendo +10 000, −10 000 ou 100),
  `test_ANTI_ANTECIPACAO_virar_is_final_para_true_e_o_que_faz_o_ponto_nascer` (o espelho — é o bit
  virando que faz o ponto existir, como em `test_beta_job.py`),
  `test_ANTI_ANTECIPACAO_vela_depois_do_fim_nao_muda_o_horizonte_curto`, e
  `test_a_janela_de_h_minutos_termina_na_vela_que_FECHA_em_h`;
- **`test_bootstrap_conjunto_com_um_grupo_so_e_IDENTICO_a_blocos90_ic_media`** — a prova de que o
  reuso não mudou o estimador: mesmo sorteio, mesma semente, intervalo idêntico a 1e-12. É o que
  autoriza chamar `bootstrap_conjunto` de "o `ic_media` com os grupos amarrados";
- **`test_dentro_de_CADA_reamostragem_as_contribuicoes_somam_o_total`** — a identidade não vale só no
  ponto estimado: vale em todas as 200 reamostragens do teste (erro < 1e-12). Sem isso, o IC do total
  não seria o IC da soma das contribuições;
- **`test_a_reamostragem_e_a_MESMA_para_todos_os_grupos_no_mesmo_passo`** — dois grupos que aparecem
  um por dia têm `n` reamostrado idêntico em todo passo. É o que um bootstrap por grupo quebraria;
- **`test_a_soma_das_duas_partes_e_EXATAMENTE_o_delta_em_todo_m_saida`** — a partição de §4 em
  `m_saida ∈ {1, 40, 80, 100, 120, 200, 240, 999}`;
- **`test_reamostragem_que_esvazia_um_grupo_nao_entra_no_IC_e_e_CONTADA`** — um grupo raro pode sumir
  de um sorteio; a reamostragem é descartada **e contada**, nunca descartada em silêncio.

O código de produção de que a leitura depende (não tocado por esta tarefa):

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
                services/strategy-worker/tests/test_outcome_walk.py \
                services/strategy-worker/tests/test_entry_plan.py -q -p no:randomly -m "not integration"
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 1.75s
```

**O que eu NÃO rodei, e por quê.** `services/strategy-worker/tests/test_replay_lookahead.py` (a prova,
com o contra-teste da estratégia que trapaceia de propósito, de que uma decisão replayada não lê vela
que fecha depois do corte) é `@pytest.mark.integration` e precisa de Postgres por testcontainer —
**proibido pelo brief**. O substituto empírico desta tarefa é a checagem cruzada de duas
implementações (§2.2: 542 decisões × 10 colunas, divergência máxima 5,0e-09 nas convertidas e
**0,000e+00** nas seleções) mais os cinco testes de janela.

---

## 8. CONCERNS (meus) E ASSUNÇÕES NUMÉRICAS

### CONCERN 1 — as duas unidades dão contas diferentes, e a narrativa tem de carregar a unidade

O ATR é um denominador **por decisão**, e os grupos não têm o mesmo ATR%: `time-stop` tem ATR% p50 de
**1,1134 %** contra **0,8308 %** do `stop` e **0,8193 %** do `target`. Consequência: a participação do
`target` é **91,4 %** em ATR e **82,4 %** em % do preço; a do `stop` é **4,8 %** em ATR e **13,9 %**
em % do preço. **A ordem dos grupos não muda** (target ≫ stop > time-stop nas duas unidades), mas
"95 %" ou "91 %" é um número **da unidade**, não do mundo. As duas tabelas estão em §3 exatamente por
isso.

### CONCERN 2 — a exclusão de zero do agregado não sobrevive à retirada de um dia

```
tirando um dia de cada vez (83 dias): a media vai de +0.3007 para, no extremo, +0.2342 (sem 2026-08-20)
tirando um mercado de cada vez (16 mercados): a media vai de +0.3007 para, no extremo, +0.3617 (sem ZECUSDT)
```

Nenhum dia e nenhum mercado **carrega** o achado (a variação máxima é ±0,067, ~22 % do valor). Mas o
limite inferior do IC é **+0,0071** — a distância até zero é **nove vezes menor** que o efeito de
tirar um único dia. Isto não contradiz o bootstrap (que já reamostra dias): é a leitura honesta de que
"exclui zero" aqui é uma propriedade **frágil**, e que a decomposição de §3 — cujo IC do `target`
exclui zero com folga muito maior (+0,0902 no limite inferior) — é a parte robusta do resultado.

### CONCERN 3 — "a contribuição está concentrada no alvo" não é "o alvo está cortando dinheiro nosso"

É a armadilha registrada na KB-0054 e o cenário de falha que a Astra nomeou. Os +0,0910 ATR que o
grupo `target` acumula **depois** da própria saída são movimento de preço numa janela em que a
posição não existia — e uma variante sem alvo **não herda essa janela**: ela herda outra trajetória
de desfechos, na qual parte das 216 operações que hoje fecham no alvo viraria stop ou expiração.
Nenhuma frase desta nota estima esse líquido, e a condição que a fila do plantão registrou para a
**H-P25** ("se a contribuição estiver concentrada em `target`, isso **justifica propor**, não decide")
está descritivamente satisfeita — **propor** é decisão de quem opera a fila, não desta nota, e o meu
brief é explícito: nenhuma proposta de mudar versão viva.

### CONCERN 4 — o `time-stop` tem 45 decisões em 26 dias, e o IC dele diz mais sobre n do que sobre movimento

O IC da média do `time-stop` ([−0,0538; +0,3931]) vem de **26 blocos de dia**. "Não exclui zero" aqui
é compatível tanto com "não há movimento" quanto com "há movimento e a amostra é pequena" — e a
mediana do grupo (+0,2410, a maior das três) e o `%>0` (62,2 %, o maior dos três) empurram para a
segunda leitura. O que **não** depende de n é a contribuição: 45 de 542 decisões não podem responder
por um agregado, qualquer que seja a média delas.

### Assunções numéricas

1. **O endpoint de `+h` é a vela que FECHA em `entry_ts + h`** (`open_time = entry_ts + h − 1 min`),
   herdado do D-P23 e congelado em teste. A convenção alternativa mediria `h + 1` minutos.
2. **O corte da partição de §4 é o fechamento que cai em `exit_ts`**, não o `exit_price`. Escolhido
   porque a leitura inteira é de fechamentos brutos e misturar o preenchimento sintético da saída
   (limitado em `target1` num gap favorável) dentro de uma trajetória bruta daria um número que não é
   nem trajetória nem resultado. Consequência declarada: a parte "dentro da posição" **não** é o
   resultado realizado.
3. **A janela "depois" é `[m_saida + 1, 240]` e a "antes" é `[1, m_saida]`.** Uniforme para os dois
   tipos de saída do walker: saída no open carimba `exit_ts = open_time` (o fechamento daquela barra
   já é "depois"), saída intrabar carimba `exit_ts = close_time` (aquela barra é "antes"). Em nenhum
   caso a barra de saída recebe ordem intrabar que o OHLC não mostra.
4. **O decil é `ceil(n/10)` do GRUPO** (29 no `stop`, 22 no `target`, 5 no `time-stop`, 55 no total) e
   a contribuição do decil divide pelo **N total**. As duas escolhas são diferentes de propósito e
   estão fixadas em `test_o_decil_e_do_GRUPO_e_o_divisor_e_do_TOTAL`.
5. **O bloco do bootstrap é o dia de calendário UTC da ENTRADA** (`entry_ts`), 20 000 reamostragens,
   semente **20260910** — as mesmas da pré-registração do D-P23, para que os números sejam
   comparáveis linha a linha.
6. **Na tabela restrita de §5 o divisor da contribuição é 326**, não 542, e o bootstrap usa os **77**
   dias daqueles dois grupos, não os 83. Declarado na própria seção porque muda o valor de `contrib`.
7. **`%>0` conta positivos estritos.** Nenhum grupo tem número relevante de zeros exatos no Δ de
   80→240 (ao contrário dos primeiros horizontes do D-P23).
8. **Percentis por interpolação linear** (`numpy.percentile`, e `percentile_cont` no SQL), mediana de
   amostra par = média dos dois centrais.
9. **`MFE`/`MAE` reportados como MEDIANA por grupo** (§6). As médias não estão impressas; o CSV
   `dp24-decisoes.csv` tem os extremos crus de cada decisão para quem quiser recalcular.
10. **Sem correção de multiplicidade.** São 5 grupos × 2 unidades × 2 estimadores × 2 recortes, todos
    reportados, nenhum escolhido depois de olhar. O veredito estava fixado na pré-registração da fila
    ("a contribuição ao Δ agregado está / não está concentrada nas saídas por alvo") **antes** desta
    leitura.

---

## 9. O QUE EU DELIBERADAMENTE NÃO FIZ

- **Não rodei replay nenhum.** A coorte já existia; esta tarefa é leitura de `signal_outcomes`,
  `agent_signals` e `candles`.
- **Não escrevi nada na VPS** nem toquei em container, `.env*`, partição, `strategy_versions` ou
  `opportunity_weights`. Três consultas, todas em `repeatable read read only`, `statement_timeout = 240s`,
  nenhuma criando view, tabela temporária ou índice.
- **Não classifiquei causa** e **não estimei o que outra saída teria rendido** (CONCERN 3).
- **Não propus experimento nem pré-registro.** A condição que a fila registrou para a H-P25 está
  descritivamente satisfeita; a decisão de pré-registrar não é minha.
- **Não editei a frase do adendo D-P23 na KB-0079** ("feita por uma minoria de decisões com movimento
  tardio grande"). A KB é append-only por precedente e o meu brief autoriza **append**; a correção
  daquela frase — que a Astra pediu no MUST-FIX 3 — está **dentro** do adendo D-P24, com os números
  dos decis que a sustentam. Quem operar a próxima passada da KB pode querer inserir um ponteiro na
  linha antiga.
- **Não toquei em `apps/**`, `services/execution-worker/**`, `packages/exchange-adapters/**` nem em
  nenhuma KB além do adendo da KB-0079**, que é meu por brief.
- **Não usei `git stash`, `checkout --`, `restore`, `reset`, `clean` nem `commit`.** Nada commitado.

---

## 10. AS 10 LINHAS PARA O EVERTON

> **De onde vinha aquele "dinheiro extra" depois dos 80 minutos — e a resposta é: de onde não dá para pegar.**
> 1. Ontem eu medi que o preço, nas 542 entradas da `mean_reversion` de 15 min, continua andando entre os 80 e os 240 minutos: **+0,30 ATR em média**. Hoje eu abri esse +0,30 pelo **motivo real de saída** de cada operação, sem rodar replay novo.
> 2. **91 % desse extra vem das operações que saíram no ALVO** (+0,2749 de +0,3007), e é o único grupo cujo intervalo de confiança não passa por zero. Ou seja: o preço continuou subindo **depois** de a operação ter fechado no lucro.
> 3. **As que saíram por tempo — o único grupo em que segurar mais tempo poderia importar — respondem por 3,8 %** (+0,0113). São só 45 das 542 operações; o intervalo delas passa por zero.
> 4. **As que saíram no stop respondem por 5 %**, e por cancelamento: enquanto ainda estavam abertas o preço **caía** (−0,13), depois de stopadas **subia** (+0,15). As duas metades quase se anulam.
> 5. Partindo o mesmo +0,30 minuto a minuto: **80 % dele acontece quando a posição já estava fechada.** Só +0,06 acontece dentro da posição — e esse pedaço tem intervalo que passa por zero.
> 6. **Traduzindo:** o movimento extra é, na maior parte, dinheiro que a estratégia **não podia tocar** do jeito que ela está montada hoje. Não é lucro deixado na mesa por falta de paciência.
> 7. **E o cuidado que essa frase exige:** isso **não** significa "tira o alvo que a gente pega esse dinheiro". Uma versão sem alvo teria outras saídas — parte das 216 que hoje fecham no alvo viraria stop. Esse líquido é **experimento**, não leitura, e eu não o estimei nem propus.
> 8. **Corrigi uma frase minha de ontem.** Eu havia dito que o extra era "de cauda, não de maioria". Medido: o decil de cima contribui +0,49, o de baixo −0,30 e os **432 do meio contribuem +0,11 — 37 % do total**. Então são **as duas caudas grandes, com a direita maior**, não "poucas explicam tudo".
> 9. **Fragilidade que eu preciso declarar:** o +0,30 agregado "exclui zero" por muito pouco (limite inferior +0,007), e tirar **um único dia** da série (20/08) já o derruba para +0,23. A parte **robusta** do resultado é a decomposição, não a significância do agregado.
> 10. **Integridade:** nada foi escrito na VPS, nada commitado, nenhuma versão viva tocada, nenhum replay rodado. 41 testes com valores calculados à mão, e o número de ontem foi reproduzido **dígito a dígito** por um caminho de dados diferente — o que dá confiança de que a decomposição é do mesmo número, não de um número parecido.

---

## 11. PROVENIÊNCIA — como reproduzir, verbatim

```
$ date -u +%FT%TZ                                             # 2026-09-12T05:17:14Z = 02:17 BRT
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-12-dp24-q00-motivos.sql \
    | tee .claude/state/exp-drafts/dp24/saida-q00.txt
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-12-dp24-q01-decisoes.sql \
    > .claude/state/exp-drafts/dp24/dp24-decisoes.csv          # 542 linhas
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-12-dp24-q02-caminho.sql \
    > .claude/state/exp-drafts/dp24/dp24-caminho.csv           # 130 080 linhas, 46 s
$ cd .claude/state/exp-drafts/dp24 \
    && uv run --with numpy --with pytest pytest test_decomp.py -q -p no:randomly   # 41 passed
$ PYTHONIOENCODING=utf-8 uv run --with numpy python analise.py \
    dp24-decisoes.csv dp24-caminho.csv > saida-analise.txt     # 76 s (8 bootstraps de 20 000)
```

Os três SQL abrem `begin transaction isolation level repeatable read read only` e fecham com
`commit`; nenhum cria view, tabela temporária ou índice; `statement_timeout = 240s` em todos.
