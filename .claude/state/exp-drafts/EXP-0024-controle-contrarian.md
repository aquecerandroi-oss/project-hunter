---
tags: [experimento, mean-reversion, controle, plantao, microestrutura, custos]
updated: 2026-09-09
status: medido
owner: quant-engineer
exp: EXP-0024
strategy: mean_reversion
version: v1, v2, v6, v10 (por versao e agregado)
result: inconclusivo
evaluable: 621
days: 31
last_eval: 2026-09-09 (T3.66)
---

<!-- O frontmatter é METADADO do vault (dataview) e foi atualizado depois da medição:
     status/result/evaluable/days/last_eval. O corpo acima de `## Resultado` — hipóteses,
     população, controles, métrica, testes e réguas — continua exatamente como foi
     congelado às 19:49Z de 2026-09-09, antes de qualquer estatística. -->

**Nota de leitura de `days: 31`:** são os dias distintos do **agregado**, que conta a mesma
`(mercado, barra)` mais de uma vez. **Nenhuma versão isolada cumpre a régua de 100 avaliáveis
E 30 dias** — `v10` tem 335 e **29**. Ver §8.

# EXP-0024 — o controle contrarian lag-1: o edge da `mean_reversion` é mais do que "reversão da última barra de 15 m"?

> **PRÉ-REGISTRO do quant-engineer (T3.66, 2026-09-09).** Este arquivo foi escrito **antes** de
> qualquer estatística ser calculada. Tudo abaixo da linha `## Resultado` é acrescentado depois,
> datado, e **nada acima dela é editado** — nem para consertar uma escolha ruim. Se uma escolha se
> revelar ruim, ela fica, e a correção vira EXP novo.
>
> Origem: H-P1a / H-P1b em [[Hipoteses-do-plantao]],
> [[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]] (Kitron & Wengrowicz, arXiv 2608.21888v1) e o
> parecer da Astra em `.claude/state/astra-review-plantao-20260909-1700.md`.
> **Pesquisa apenas. Nada é ativado, nada é depreciado, nada é escrito na VPS.**

## O que já foi lido antes de congelar (declarado, para ninguém supor que o desenho veio depois do resultado)

Antes de escrever este arquivo eu li, na VPS, **só metadado de desenho** — nunca um R, um retorno ou
uma expectancy (`infra/scripts/sql/research/2026-09-09-t366-q00-catalogo.sql`, `read_at`
2026-09-09 19:42:19Z / 16:42 BRT):

1. os parâmetros congelados das 14 versões de `mean_reversion` (geometria, banda de ATR%, custos);
2. a **contagem** de desfechos por versão, coorte e `tracking_state`, os mercados distintos e a
   primeira/última barra de origem.

Números de desenho que saíram dali e que este pré-registro usa: `v1` 37 replay + 47 prospective com
`r_multiple`; `v2` 17 + 16; `v6` 161 + 8; `v10` 195 + 0; janela 2026-08-09T16:45Z → 2026-09-09T01:30Z.
Todas as quatro versões têm `horizon_s = 14400`, razão alvo:risco **1,5** e custos
`spread 2 / slippage 5 / fee 4` (20 bps ida e volta). A geometria difere: `v1`/`v2` stop 1,0 ATR e
alvo 1,5 ATR; `v6`/`v10` stop 1,5 e alvo 2,25. `v10` difere de `v6` só no ATR (1 h × 24 barras contra
15 m × 97).

## Hipóteses (congeladas)

- **H-P1a (incremental).** O R por decisão da `mean_reversion` **menos** o do controle contrarian
  lag-1 pareado é **> 0**. Se não for, a família não acrescenta nada ao "aposte contra a última
  barra" — é uma forma cara de comprar reversão da última barra de 15 m.
- **H-P1b (líquido).** A expectancy **líquida a 20 bps** das mesmas decisões é **> 0**.

Falta de significância **não confirma** nenhuma das duas. As duas são direcionais, mas o `p` primário
é **bicaudal** (a convenção da casa em `t357b/pareado.py`) — conservador de propósito — e a conclusão
exige, além do `p`, que a **estimativa pontual** esteja do lado declarado.

## População (congelada)

- **Receita:** a da T3.53 (`infra/scripts/sql/research/2026-09-09-t353-q01-populacao-csv.sql`), com o
  **mesmo corte** `agent_signals.emitted_at < 2026-09-09T02:30:00Z` (23:30 BRT de 08/09), para que
  esta medida seja comparável às da T3.53/T3.59c sem uma segunda definição de "hoje".
- **Filtro:** `strategies.key = 'mean_reversion'`, versões **v1, v2, v6, v10**,
  `tracking_state = 'terminal'` e `r_multiple IS NOT NULL`. As duas coortes (`replay` e
  `prospective`) entram, **rotuladas**, e são reportadas separadas antes de qualquer agregado.
- **O relógio é a barra de origem** (`meta->'entry_plan'->>'source_bar_close'`), nunca `emitted_at`
  nem `entry_ts`. Dia = dia em **Brasília** dessa barra (a mesma convenção da T3.53).
- **Sobreposição entre versões, declarada:** `v6` e `v10` decidem sobre o mesmo alfabeto de barras
  com ATRs diferentes, então a mesma `(mercado, barra)` pode aparecer em mais de uma versão. O
  agregado é a **união** das decisões (uma linha por desfecho), e eu publico quantas
  `(mercado, barra)` distintas ele tem. O bootstrap por **bloco de dia** absorve a dependência
  transversal, não a duplicação exata — por isso o número **por versão** é o que conclui, e o
  agregado é leitura.

## Os dois controles (congelados)

Os dois usam **a mesma máquina de saída** da família (`walker.walk`: stop no aberto, alvo no aberto,
expiração no aberto, e intrabarra com **stop vencendo alvo**; sem invalidação, porque
`mean_reversion` tem `invalidations = ()`), a **mesma convenção de entrada** (abertura da vela de
1 min seguinte ao `source_bar_close`, `P_entry = open × (1 + 6/10000)`), o **mesmo horizonte** (4 h) e
os **mesmos 20 bps** (`spread 2 + 2×slippage 5 + 2×fee 4`).

**A barra "anterior" é a última barra de 15 m fechada antes da entrada** — que, para uma estratégia de
15 m, é **a própria barra que a estratégia leu** (`[source_bar_close − 15 min, source_bar_close)`).
É a definição da Astra e é a única sem antecipação: a barra de entrada abre em
`source_bar_close + 1 min`. Sinal: `sign(close − open)` da barra, com **doji** (`close = open`)
tratado como "não dispara" e contado à parte. A barra de 15 m é a dobra de **15 velas de 1 min
`is_final`** (`date_bin` desde a época); balde incompleto **não** vira sinal — a decisão é excluída do
teste e a exclusão é publicada.

### Controle C1 — mesma barra, mesma geometria

Na **mesma** `(mercado, barra)` da decisão: compra se a barra fechou **em baixa**; não opera se
fechou em alta ou é doji. Geometria: `risco_pct = risco_decisão / P_entry_decisão` e razão
alvo:risco `tr = (alvo1_decisão − P_entry_decisão) / risco_decisão`, aplicadas ao `P_entry` da mesma
barra.

**A degenerescência é declarada aqui, e não descoberta depois:** como o mercado, a barra, a entrada,
a geometria, a saída e os custos são os mesmos, quando C1 dispara ele é **a própria operação da
decisão** e `R_decisão − R_C1 ≡ 0`. Logo C1 **não mede** "edge incremental sobre lag-1" no sentido
usual; ele mede exatamente uma coisa, e é uma coisa que interessa: **quanto do R da família vem de
barras que um contrarian lag-1 teria pulado**. Quando C1 não dispara, `R_C1 = 0` (ficou de fora, sem
custo). Então

    Δ1 = média_d( R_d − R_C1(d) ) = (fração de decisões em barra de alta) × (R médio nessas decisões)

e testar `Δ1 > 0` é testar "a parte que o lag-1 **não** explica paga". Publico junto a **taxa de
concordância** (fração das decisões cuja barra fechou em baixa): se ela for perto de 100 %, a família
é, na prática, um subconjunto do lag-1 e a pergunta se transfere inteira para C2.

### Controle C2 — a mesma regra em barras aleatórias pareadas por mercado e hora do dia

Para cada decisão `d` em `(mercado m, barra b, hora UTC h)`: candidatas são todas as barras de 15 m
`b' ≠ b` do **mesmo mercado**, com **`hour(b') = h` em UTC**, dentro da janela da população
(2026-08-09 → 2026-09-09T02:30Z), cuja **própria barra fechou em baixa** (é *a mesma regra*, não um
sorteio de qualquer barra) e com cobertura de 1 min completa da janela de acompanhamento.
Geometria: `risco_pct` e `tr` **da decisão pareada**, aplicados ao `P_entry` da barra candidata —
é assim que "mesmo stop/alvo" sobrevive a um preço diferente e que a identidade de pedágio
`custo_R = 0,0020 / risco_pct` fica **idêntica** nos dois lados.

Sorteio **determinístico e reproduzível**: `order by md5(signal_id || market_id || b')`, `limit 20`
por decisão (`K = 20`, congelado). O valor do controle para `d` é a **média** dos R do pool dela —
uma média de tratamento por célula, para que o ruído de sorteio não entre no IC. Decisão sem nenhuma
candidata elegível fica **fora** de C2 e a exclusão é publicada.

    Δ2 = média_d( R_d − R̄_pool(d) )

**Hora do dia em UTC**, não em Brasília: é a grade em que o portão de horas e o regime horário já
falam (PIPELINE §4b item 10), e um deslocamento fixo de 3 h não muda o pareamento.

## Métrica (congelada)

Para os dois lados, do mesmo jeito, a partir de OHLC e da hipótese de custo — nunca de uma cotação:

    P_entry  = open(barra de entrada) × (1 + 6/10000)
    risco    = P_entry − stop
    P_exit   = exit_base × (1 − 6/10000)
    R        = (P_exit − P_entry − 0,0004·P_entry − 0,0004·P_exit) / risco

`exit_base` é o alvo1 quando o alvo vence (nunca crédito acima dele), o `stop` quando o stop vence
intrabarra, o **aberto** quando o stop vence no aberto ou o horizonte expira.

**Funding fica de fora dos dois lados.** O R primário é `r_ex_funding` para a decisão (a coluna que o
Lab já persiste) e o R sem perna de funding para o controle: o controle não tem cadência de funding
computável sem reimplementar `funding.py` sobre barras hipotéticas, e comparar um lado com perna de
funding contra outro sem ela seria fabricar uma diferença. O `r_multiple` completo (com funding) é
publicado **ao lado**, como leitura secundária, para que ninguém confunda 20 bps com o custo total.
Consequência declarada: **H-P1b é testada a 20 bps**, que é literalmente o que ela afirma.

## Testes (congelados)

- **(a) incremental:** `Δ1 > 0` (controle C1, o do brief). Estatística = média de `R_d − R_C1(d)`.
- **(b) líquido:** `expectancy(r_ex_funding) > 0` sobre as mesmas decisões.
- **Régua:** bootstrap por **blocos de dia** (dia em Brasília da barra de origem), **10 000**
  reamostragens, seed `20260909`, dias inteiros com reposição e **conjuntos entre mercados** (todas as
  decisões do dia viajam juntas — KB-0010/KB-0051). IC 95 % por percentis 2,5/97,5. `p` bicaudal com
  piso `2/B`, como em `t357b/pareado.py`.
- **Multiplicidade:** **Holm** sobre a família de **dois** `p` — (a) e (b) — por versão e no agregado,
  cada família fechada dentro do seu recorte.
- **Fora da família de Holm, declarado:** `Δ2` (controle C2) é reportado com IC e `p` próprios como
  **controle secundário pré-registrado**. Publico também, como sensibilidade, o Holm sobre os **três**
  `p` — a versão mais estrita — para que a escolha da família não possa ser lida como a escolha
  conveniente.
- **Reuso de código:** `t342-blocos/blocos.py` e `t357b/pareado.py` são a origem do estimador
  (reamostragem por dia, `p` bicaudal com piso, Holm monótono); o módulo desta tarefa vive em
  `.claude/state/exp-drafts/t366/` e é testado com séries sintéticas de valor esperado conhecido.

## Régua editorial (congelada, e já sei que ela morde)

O limiar da casa é **≥ 100 avaliáveis E ≥ 30 dias distintos**. Pelas contagens de desenho, `v2` (33) e
`v1` (84) **não alcançam** os 100, e nenhuma versão isolada deve alcançar os 30 dias distintos nesta
janela. **Portanto o resultado desta medida será, muito provavelmente, `inconclusivo` pelo limiar
editorial mesmo que os testes deem significativos** — isso está escrito aqui *antes* de rodar
exatamente para que não vire uma ressalva conveniente depois. O que a medida entrega mesmo assim é
**direção e tamanho de efeito**, e a taxa de concordância com o lag-1, que é um fato descritivo e não
depende de poder.

## Validação obrigatória antes de qualquer leitura (congelada)

O controle exige caminhar barras hipotéticas em SQL, o que é uma **segunda implementação** das regras
de saída. Ela só pode ser lida se reproduzir a primeira:

1. **Reprodução da população.** Caminhar o plano **da própria decisão** (mesmo stop, alvo, horizonte,
   barra de entrada) sobre as velas de 1 min e comparar `result` e `r_ex_funding` com o que
   `signal_outcomes` persistiu. **Critério: 100 % de igualdade de `result` e diferença de R
   ≤ 1e-6 em todas as decisões.** Qualquer divergência **cancela a leitura** dos controles e vira
   achado, não nota de rodapé.
2. **Não antecipação.** Nenhuma vela com `open_time < entry_bar_open` entra em nenhum caminhar; o
   sinal da barra anterior usa só o balde `[b − 15 min, b)`, todo ele `is_final`; a barra que contém a
   entrada nunca assina o sinal.
3. **Contiguidade.** Janela de acompanhamento com minuto faltando = **censurada** e **excluída**,
   nunca preenchida — nem para a decisão, nem para o controle. Exclusões publicadas por lado.

## O que este experimento **não** faz

- Não mede tercis de `|i| = |2·taker_buy/volume − 1|` (KB-0082). Isso exige carregar
  `taker_buy_volume` no `Bar` (`aggregate.py:40,77`) e é outra tarefa; aqui o corte é **só o sinal**.
- Não separa mecanismo (provisão de liquidez × informação) — o artigo também não separa.
- Não confirma nada fora da amostra: a janela é uma só.
- Não escreve nada na VPS nem ativa/depreca versão nenhuma.

## Resultado

**Medido em 2026-09-09, entre 16:42 e 17:03 de Brasília (19:42–20:03 UTC).** Nada acima desta linha
foi editado depois do pré-registro.

### 0. Congelamento e deriva declarada

`q01` exportou 621 decisões (v1 84, v2 33, v6 169, v10 335). **A população se moveu entre o
desenho e a medição:** às 19:42Z `v10` tinha 195 desfechos e às 19:47Z tinha 335 — uma corrida de
replay (`replay:71c76d86…`, 54 linhas, ao lado de `replay:d82356d9…`, 281) terminou de escrever no
meio. A conferência de `q03` (20:03:45Z) devolve exatamente os mesmos 621, então **o arquivo é a
população de registro** e ela está estável desde a exportação. Registro isto porque "decisões
congeladas" é verdade sobre um instante, não sobre a tabela.

Sobreposição declarada: as 621 decisões cobrem **361** pares `(mercado, barra)` distintos — `v6` e
`v10` decidem quase sempre sobre a mesma barra com ATRs diferentes. Por isso o número **por versão**
conclui e o agregado é leitura.

### 1. A validação passou — e passou exata

Recaminhei o plano **da própria decisão** com `walker.walk` sobre as velas de 1 min:

```
validação: 621 recaminhadas | sem velas/censuradas 0 | divergências 0 | max |ΔR| 0.000e+00
```

621 de 621 reproduzem `result` **e** `r_ex_funding` do que `signal_outcomes` persistiu, com desvio
máximo **zero**. O critério congelado ("100 % de `result` e ΔR ≤ 1e-6") está cumprido, então os
controles podem ser lidos. Não houve nenhuma exclusão por buraco de vela.

Atraso da barra de entrada: **589** decisões entraram em `barra + 1 min` e **32** em `barra + 2 min`
(fila da faixa viva). O controle sempre entra em `barra + 1 min`, como o pré-registro manda.

### 2. A degenerescência de C1, como declarada

Em **245 das 248** decisões cuja barra fechou em baixa, `R_C1` é **idêntico** a `r_ex_funding`
(`|Δ| < 1e-9`). As 3 exceções estão entre as 32 que entraram um minuto depois — ali o controle entra
uma vela antes e o desfecho pode divergir (máximo observado 2,61 R). É exatamente o que o
pré-registro previu: quando C1 dispara, ele **é** a operação da decisão.

### 3. O fato descritivo que responde a pergunta antes de qualquer teste

| | agregado | v1 | v2 | v6 | v10 |
|---|---|---|---|---|---|
| decisões | 621 | 84 | 33 | 169 | 335 |
| barra de **baixa** (lag-1 concorda) | **39,9 %** (248) | 53,6 % | 48,5 % | 36,7 % | 37,3 % |
| doji | 1,9 % (12) | 2 | 0 | 2 | 8 |
| barra de **alta** | 58,1 % (361) | 44,0 % | 51,5 % | 62,1 % | 60,4 % |

A taxa-base de barras de baixa na grade de 15 min desses 56 perpétuos, na mesma janela, é **49,8 %**
(39 125 de 78 542 pares de baldes consecutivos completos, ambos não-doji). Comparando na mesma base (excluindo os 12 dojis), a família
dispara depois de baixa em **40,7 %** (248 de 609) — contra 49,8 % do acaso. **A `mean_reversion`
dispara depois de uma barra de baixa *menos* vezes que o acaso** — ela pende para comprar depois de
barras de **alta**. Isso não é
surpresa quando se lê a regra: o z-score é sobre o *nível* contra os 20 fechamentos anteriores, e a
estabilização (`close ≥ (high+low)/2`) empurra para a barra de repique. **A premissa "é só reversão
da última barra de 15 m" já morre aqui, e morre por descrição, não por teste.**

### 4. Os dois testes pré-registrados (bootstrap de blocos de dia, 10 000 reamostragens, seed 20260909)

| recorte | (a) Δ1 = R − C1 | (b) expectancy `r_ex_funding` | Holm(2) |
|---|---|---|---|
| **agregado** (n 621, 31 dias) | **+0,0735** IC95 [−0,0517; +0,1715] p 0,2250 | **+0,1082** IC95 [−0,0836; +0,2873] p 0,2798 | 0,4500 / 0,4500 |
| v1 (n 84, 11 dias) | +0,0828 [−0,1807; +0,2106] p 0,3566 | +0,0962 [−0,3236; +0,4676] p 0,4720 | 0,7132 / 0,7132 |
| v2 (n 33, 8 dias) | +0,1143 [−0,3451; +0,3835] p 0,4758 | +0,2006 [−0,1613; +0,6949] p 0,1910 | 0,4758 / 0,3820 |
| v6 (n 169, 24 dias) | +0,0656 [−0,0753; +0,1990] p 0,3714 | +0,0601 [−0,1306; +0,2565] p 0,5912 | 0,7428 / 0,7428 |
| v10 (n 335, 29 dias) | +0,0711 [−0,0464; +0,1793] p 0,2462 | +0,1264 [−0,0738; +0,3030] p 0,2208 | 0,4416 / 0,4416 |

**Nenhum dos dois testes é significativo em nenhum recorte, antes ou depois de Holm.** Todas as
estimativas pontuais estão do lado declarado (> 0) e todos os IC95 cruzam zero.

Leitura secundária com funding (`r_multiple`): agregado **+0,1076** [−0,0844; +0,2872] — o funding
custa **0,0006 R por decisão** nesta população, ou seja, nada perto dos 20 bps.

### 5. O controle secundário C2 — e o resultado mais informativo do dia

| recorte | Δ2 = R − C2 | **expectancy do próprio C2** |
|---|---|---|
| agregado | +0,1545 [−0,0489; +0,3493] p 0,1450 | **−0,0462** [−0,0765; −0,0159] p 0,0032 |
| v1 | +0,2653 [−0,1257; +0,7160] p 0,1228 | −0,1691 [−0,2969; −0,1163] p 0,0002 |
| v2 | +0,3265 [−0,0679; +0,9121] p 0,0816 | −0,1258 [−0,2449; −0,0398] p 0,0020 |
| v6 | +0,0929 [−0,1079; +0,3141] p 0,4356 | −0,0329 [−0,0703; −0,0005] p 0,0458 |
| v10 | +0,1408 [−0,0597; +0,3198] p 0,1766 | −0,0143 [−0,0386; +0,0072] p 0,2012 |

Pool efetivo: **19,4 sorteios por decisão** em média (mínimo 2, mediana 20, nenhuma decisão sem pool).
`Δ2` também **não** é significativo em nenhum recorte (Holm de sensibilidade sobre os três `p`:
agregado 0,4350 / 0,4500 / 0,4500 — nada muda). Mas a **segunda coluna** é: **o contrarian lag-1,
com a nossa geometria, a nossa saída e os nossos 20 bps, perde dinheiro** — −0,046 R por operação no
agregado, com IC que não cruza zero.

### 6. A afirmação do artigo replica no nosso perpétuo; o lucro não

Sobre **todos** os baldes de 15 min completos dos 56 mercados na janela (bloco de dia UTC):

```
P(próxima barra em alta | esta em baixa)  0,5128  IC95 [0,5033; 0,5225]   n 39 125
P(próxima barra em alta | esta em alta)   0,4907  IC95 [0,4813; 0,5006]   n 39 417
diferença                                +2,21 p.p.
```

(O `p` desse estimador testa "≠ 0" e é inútil aqui; o que se lê é o IC contra **0,50**.)

A reversão direcional de 15 min **existe** no nosso dado de perpétuos — a cláusula de refutação da
[[KB-0082]] ("se o nosso dado não mostrar reversão de sinal nem no controle") **não** dispara. E o
terceiro achado do artigo replica junto: **2,2 pontos percentuais de previsibilidade direcional não
pagam 20 bps** (§5, C2 negativo). As duas metades do artigo se sustentam aqui.

### 7. Coortes, separadas antes de agregar

| coorte | n | dias | expectancy | Δ2 |
|---|---|---|---|---|
| `replay` | 550 | 30 | +0,1063 [−0,1036; +0,3078] p 0,3370 | +0,1445 [−0,0759; +0,3657] p 0,2226 |
| `prospective` | 71 | **1** | +0,1234 | +0,2318 |

**O IC da coorte prospectiva é degenerado e não deve ser lido**: com **um** bloco de dia, toda
reamostragem devolve o mesmo dia e o IC colapsa no ponto (e o `p` cai no piso `2/B = 0,0002`). É
artefato do estimador, não evidência. Fica publicado com o aviso em vez de omitido.

### 8. Veredito

- **"O edge da `mean_reversion` é só reversão da última barra de 15 m" — refutada por descrição.**
  A família dispara depois de barra de baixa em **39,9 %** das vezes contra uma taxa-base de
  **49,8 %**: ela não é um contrarian lag-1 disfarçado, ela pende para o lado oposto.
- **"É uma forma cara de comprar reversão da última barra" — não sustentada.** O controle que compra
  essa reversão perde **−0,046 R** por operação; a família mede **+0,108 R**. A diferença (+0,155 R)
  está do lado certo em todos os recortes, mas **não é significativa** (p 0,145; Holm 0,435).
- **H-P1a: inconclusiva** (Δ1 +0,0735, p 0,2250; Holm 0,4500). **H-P1b: inconclusiva**
  (+0,1082 R, p 0,2798; Holm 0,4500). Falta de significância **não confirma** o contrário de nenhuma
  das duas.
- **Régua editorial:** como o pré-registro antecipou, ela morde. Nenhuma versão isolada tem
  ≥ 100 avaliáveis **e** ≥ 30 dias (`v10`: 335 e **29**; `v6`: 169 e 24; `v1`: 84 e 11; `v2`: 33 e 8).
  Só o agregado chega a 31 dias, e ele conta a mesma barra mais de uma vez.
  **`result: inconclusivo`.**

### 9. O que eu faria a seguir (não feito aqui)

1. Repetir com `v10` quando ela cruzar **30 dias distintos** — falta **um dia**. É a única versão
   perto da régua, e refazer é uma manivela (`q01` + `rodar.py`), não um desenho novo.
2. O tercil de fluxo (`|i| = |2·taker_buy/volume − 1|`) da [[KB-0082]] continua **não medido**;
   `taker_buy_volume` já está em `candles` com 100 % de cobertura, e o custo é carregá-lo no `Bar`
   da agregação.
3. `Δ2` é o número com mais sinal (+0,155 R, p 0,145). Vale medi-lo com `K` maior e com pool
   restrito a ±7 dias da decisão (regime mais próximo) — **como experimento novo**, nunca como uma
   segunda leitura deste.
