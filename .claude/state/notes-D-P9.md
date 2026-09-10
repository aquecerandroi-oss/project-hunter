# D-P9 — de onde vieram os −34 R da hora 21:00Z (18:00 BRT) de 09/09

**O que é isto:** diagnóstico **somente leitura** sobre a VPS (`hunter-vps`,
`hunter-postgres-1`). Nenhuma escrita, nenhuma mudança de versão viva, nenhuma
recomendação de mexer em estratégia. Toda consulta rodou dentro de
`begin transaction isolation level repeatable read read only; … commit;`.
Leitura de referência: `2026-09-10 03:47Z` (00:47 BRT), `TimeZone = UTC` no servidor.

Horários em **Brasília (UTC−3)** com o UTC ao lado. O dia "09/09" abaixo é o dia
de Brasília, salvo onde estiver escrito `UTC`.

SQL (todo em `infra/scripts/sql/research/`):

| arquivo | o que responde |
|---|---|
| `2026-09-10-dp9-q00-catalogo-e-fato.sql` | catálogo das versões; o fato por dia UTC nos três eixos |
| `2026-09-10-dp9-q01-dia-brt-e-hora.sql` | o dia em BRT; R por hora de decisão e de saída |
| `2026-09-10-dp9-q02-hora21z-mercado-versao.sql` | as 39 decisões das 21Z abertas por mercado, versão e **aposta única** |
| `2026-09-10-dp9-q03-saidas-e-duplicacao.sql` | stop/alvo/tempo/contexto; spot × perpétuo; hora a hora pooled × única |
| `2026-09-10-dp9-q04-caminho-de-preco.sql` | velas de 1 min das 5 piores apostas, em unidades de ATR |
| `2026-09-10-dp9-q05-btc-e-regime.sql` | BTC minuto a minuto, `regime_hourly_v1`, amplitude do universo |
| `2026-09-10-dp9-q06-dia-08-09-e-definicoes.sql` | 08/09 com a mesma decomposição + definições candidatas |
| `2026-09-10-dp9-q07-bruto-custo-funding-e-loo.sql` | bruto × custo × funding; decisão × entrada; leave-one-out |
| `2026-09-10-dp9-q08-minuto-da-saida.sql` | o minuto exato em que as posições morreram |

---

## 0. Qual número é qual (o brief não bate com nenhuma definição única)

Coorte = `signal_outcomes.meta->>'cohort' = 'prospective'`, `tracking_state='terminal'`.
`r_multiple` é o R **líquido com funding**; `meta.r_ex_funding` é o mesmo R sem funding
(`services/strategy-worker/hunter_strategy_worker/settle.py`).

| definição | 08/09 | 09/09 |
|---|---|---|
| A família do brief (8 versões + `h1 v1`) / decisão **BRT** | +14,25 R (109; 105 com R) | **−34,50 R** (423; 402 com R) |
| B mesma família / decisão **UTC** | +14,58 R (74) | −19,73 R (442) |
| C mesma família / **saída** UTC | +10,46 R (47) | −1,19 R (432) |
| D `mean_reversion*` inteira / decisão UTC | +19,99 R (80) | −16,97 R (452) |
| E `mean_reversion*` inteira / decisão **BRT** | +19,66 R (115) | **−31,74 R** (433; 412 com R) |
| F todas as famílias / decisão UTC | −430,35 R (1 989) | −408,02 R (1 865) |
| H família do brief, `r_ex_funding` / decisão UTC | +18,26 R (74) | −40,94 R (442) |

- O **−31,08 R em 420 desfechos** do brief é a definição **E** medida algumas horas
  antes (hoje: −31,74 R em 412 com R). Diferença = desfechos que liquidaram depois
  daquela leitura. **Assumo E como a origem do número e reporto A como a série
  principal** (é a família nomeada no brief).
- O **"+32 R" de 08/09 não se reproduz** em nenhuma das oito definições: o melhor
  recorte dá **+19,99 R**. Ou o número veio de outra população (portfólio paper,
  outra família, `agent_stats`), ou de um cálculo que não consigo nomear a partir de
  `signal_outcomes`. **Registro como divergência, não a explico.**
- Cuidado com F: o Lab inteiro está em −430/−408 R por dia. A `mean_reversion` é
  uma fatia pequena e comparativamente **boa** do conjunto.

---

## 1. A hora 21:00Z (18:00 BRT) de 09/09, decomposta

### 1.1 A hora existe e é de **decisão**, não de saída

R líquido por hora de **decisão** (dia 09/09 BRT, família do brief; `apostas` = pares
distintos (mercado, barra de 15 min da observação)):

| BRT | UTC | n pooled | com R | soma R pooled | média | acerto | stop | alvo | tempo | apostas | soma R por aposta |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 12 | 15 | 80 | 80 | **+21,24** | +0,27 | 62,5 % | 14 | 34 | 32 | 15 | +4,51 |
| 15 | 18 | 20 | 20 | **−20,13** | −1,01 | **0,0 %** | 18 | 0 | 2 | 3 | −3,03 |
| 17 | 20 | 25 | 25 | −8,72 | −0,35 | 32,0 % | 17 | 6 | 2 | 4 | −2,05 |
| **18** | **21** | **39** | **35** | **−34,02** | **−0,97** | **0,0 %** | **31** | **0** | **8** | **9** | **−7,53** |
| 19 | 22 | 53 | 53 | +14,30 | +0,27 | 52,8 % | 23 | 28 | 2 | 7 | +2,23 |
| 23 | 2 | 8 | 8 | −8,50 | −1,06 | 0,0 % | 8 | 0 | 0 | 1 | −1,06 |

(tabela completa das 21 horas no q03 bloco 4.)

- **Hora de entrada = hora de decisão em 100 % dos casos** (q07 bloco 2): o atraso
  decisão→entrada é de 11 a 57 s (máx. 59,6 s). Não há "stop de entrada anterior
  saindo nesta hora" no sentido de a hora ser um artefato de contabilidade — a hora
  21Z é onde as apostas **nasceram**.
- Das 39, apenas 15 **saíram** dentro da própria hora 21Z; as demais morreram em
  22:08–22:16Z e nas expirações de 01:31–01:32Z do dia 10.

### 1.2 Mercado × versão (as 39 decisões)

Por mercado:

| mercado | n pooled | versões | apostas únicas | soma R | média R | stop | alvo | tempo |
|---|---|---|---|---|---|---|---|---|
| ZKUSDT | 8 | 8 | 1 | −8,69 | −1,09 | 8 | 0 | 0 |
| XVGUSDT | 8 | 8 | 1 | −8,43 | −1,05 | 8 | 0 | 0 |
| NEARUSDT | 12 | 8 | 3 (2 barras × spot+perp) | −7,45 | −0,93 | 10 | 0 | 2 |
| PHAUSDT | 8 | 8 | 1 | −6,90 | −0,86 | 3 | 0 | 5 |
| DOTUSDT | 1 | 1 | 1 | −1,07 | −1,07 | 1 | 0 | 0 |
| LITUSDT | 1 | 1 | 1 | −1,06 | −1,06 | 1 | 0 | 0 |
| ZECUSDT | 1 | 1 | 1 | −0,42 | −0,42 | 0 | 0 | 1 |

Por versão (todas perdem; nenhuma escapa):

| versão | n | mercados | soma R | média R | stop | alvo | tempo |
|---|---|---|---|---|---|---|---|
| `mean_reversion v1` | 5 | 5 | −4,34 | −1,09 | 5 | 0 | 0 |
| `mean_reversion v3` | 5 | 5 | −4,34 | −1,09 | 5 | 0 | 0 |
| `mean_reversion v2` | 5 | 5 | −4,34 | −1,09 | 5 | 0 | 0 |
| `mean_reversion v6` | 4 | 4 | −4,06 | −1,01 | 3 | 0 | 1 |
| `mean_reversion v8` | 4 | 4 | −4,06 | −1,01 | 3 | 0 | 1 |
| `mean_reversion v14` | 5 | 5 | −4,06 | −1,01 | 4 | 0 | 1 |
| `mean_reversion v7` | 5 | 5 | −3,71 | −0,74 | 2 | 0 | 3 |
| `mean_reversion v10` | 4 | 4 | −2,98 | −0,75 | 2 | 0 | 2 |
| `mean_reversion_h1 v1` | 2 | 2 | −2,13 | −1,07 | 2 | 0 | 0 |

### 1.3 Pooled × aposta única — **o −34 R são 9 apostas, não 39**

| | valor |
|---|---|
| decisões (pooled) | 39 |
| soma R pooled | **−34,02** |
| apostas únicas (mercado, barra de 15 min) | **9** |
| soma R por aposta (média entre versões) | **−7,53** |
| versões por aposta | **4,33** |

Duas barras de 15 min concentram tudo: **21:00Z** (XVG, NEAR, DOT, LIT) e **21:30Z**
(ZK, NEAR, PHA, ZEC). Uma aposta (ZK 21:30Z) foi tomada por **8 versões** e sozinha
vale −8,69 R pooled — que são **uma** decisão econômica de −1,09 R repetida oito vezes.
Fundindo spot e perpétuo do mesmo símbolo são **8** apostas.

**Detalhe estrutural encontrado no caminho:** há duas linhas de `markets` por símbolo
(`spot` e `perpetual`, ambas monitoradas para NEAR/ZEC/BTC…), e a família apostou nas
duas no mesmo minuto. As 4 linhas de **spot** das 21Z têm `r_multiple = NULL` com
`r_net_reason = funding_schedule_unknown` — funding cobrado (ou melhor, não resolvido)
num mercado à vista. Os −34,02 R vêm **inteiramente** das 35 linhas perpétuas.
Não é escopo do D-P9 consertar isso; fica registrado.

### 1.4 Bruto × custo × funding

| recorte | n | bruto | ex-funding | líquido | custo total (R) | funding total (R) | custo médio |
|---|---|---|---|---|---|---|---|
| 08/09 (dia BRT) | 109 | +28,68 | +17,96 | **+14,25** | 10,72 | 0,18 | 0,098 R |
| 09/09 **sem** a hora 21Z | 384 | +13,52 | −17,29 | **−0,48** | **30,81** | 0,21 | 0,080 R |
| 09/09 **hora 21Z** | 39 | **−35,85** | −38,46 | **−34,02** | 2,61 | −0,03 | 0,067 R |

Duas leituras diferentes no mesmo dia:

- **fora** da hora 21Z, o dia é o pedágio: bruto +13,5 R virando líquido −0,48 R,
  com 30,8 R de custo (4+2+5 bps por perna, `meta.assumed_costs`). É a régua da
  KB-0076 outra vez, não um evento;
- **dentro** da hora 21Z, o bruto já é **−35,8 R**. Ali o custo (2,6 R) e o funding
  (≈ 0) são irrelevantes: é preço.

---

## 2. O que foram as saídas, e o caminho de preço

### 2.1 Saídas

Hora 21Z: **31 stop, 8 tempo (expired, 240 min), 0 alvo, 0 invalidação (contexto perdido)**.
Dia 09/09 BRT inteiro: 195 stop (−190,63 R), 128 alvo (+158,66 R), 100 tempo (−2,53 R),
**zero invalidação**. As invalidações da família nunca dispararam neste dia.

Denominador escondido: **513 sinais do dia não entraram** (`no_entry`), 512 deles por
`late:delay` — o preço fugiu da zona antes dos 120 s de janela de entrada.

### 2.2 As 5 piores apostas únicas das 21Z, minuto a minuto

ATR = o que a própria decisão usou (`supporting_features.atr.value`, `wilder_v1`, 15 m,
janela terminando na barra da decisão). Velas `candles_1m` do **perpétuo**, só `is_final`.

| aposta | dec. | soma R | ATR % | velas | queda máx. | em ATR | pior corpo 1 min | pior amplitude | velas > 1 ATR | velas de baixa |
|---|---|---|---|---|---|---|---|---|---|---|
| ZKUSDT 18:30 | 8 | −8,69 | 1,21 % | 18 | −3,41 % | 2,82 | 0,84 ATR | 1,31 ATR | 0 corpo / 1 amplitude | 12 de 18 |
| XVGUSDT 18:00 | 8 | −8,43 | 1,97 % | 69 | −6,67 % | 3,39 | **1,54 ATR** | 1,95 ATR | 1 corpo / 2 amplitude | 33 de 69 |
| PHAUSDT 18:30 | 8 | −6,90 | 3,20 % | 241 | −4,74 % | 1,48 | 0,37 ATR | 0,60 ATR | 0 | 122 de 241 |
| NEARUSDT 18:30 | 6 | −5,27 | 1,49 % | 241 | −2,20 % | 1,47 | 0,54 ATR | 0,70 ATR | 0 | 114 de 241 |
| NEARUSDT 18:00 | 2 | −2,18 | 1,31 % | 36 | −2,26 % | 1,72 | 0,61 ATR | 0,79 ATR | 0 | 22 de 36 |

**Resposta: as duas coisas, em ordem.** Primeiro **deriva** — 12/18, 33/69, 122/241,
114/241 velas de baixa, corpos de 0,03 a 0,3 ATR, que já levam o preço a −1 a −1,5 ATR
e matam os stops apertados (v1/v2/v3, `stop_atr = 1`) entre 18:37 e 18:45 BRT. Depois um
**impulso**, que mata os stops largos:

- ZK: 18:48 BRT (21:48Z) — corpo −0,84 ATR, amplitude 1,31 ATR, volume 14,0 M contra
  ~300 k nos minutos anteriores (≈ 40×);
- XVG e PHA: **19:08 BRT (22:08Z)** — corpo −1,54 ATR e amplitude 1,95 ATR no XVG,
  volume 33 M; o único minuto do dia com uma vela de corpo maior que 1 ATR.
- NEAR: 18:36 BRT (21:36Z) — corpo −0,61 ATR.

### 2.3 O minuto em que morreram

Das 39 decisões das 21Z: **15 saíram em 19:08–19:09 BRT (22:08–22:09Z)**, somando
−14,77 R — **43 % da hora em dois minutos**. Outras 15 saíram entre 18:22 e 18:49 BRT
(−13,09 R), 8 expiraram às 22:31–22:32 BRT (−5,10 R) e 1 às 19:16 BRT.

No dia 09/09 inteiro, os dois minutos mais caros da família são exatamente
**19:08 BRT (−9,58 R, 9 stops)** e **19:09 BRT (−9,36 R, 10 stops)**.

---

## 3. O BTC e o regime nessa janela

**BTC não explica.** BTCUSDT perpétuo, hora a hora (09/09):

| hora UTC | BRT | abertura | mínima | fechamento | variação |
|---|---|---|---|---|---|
| 20:00 | 17:00 | 78 194,4 | 77 884,7 | 78 282,0 | +0,11 % |
| **21:00** | **18:00** | 78 281,9 | 77 946,9 | 78 109,8 | **−0,22 %** |
| **22:00** | **19:00** | 78 109,8 | 77 706,1 | 77 885,1 | **−0,29 %** |
| 23:00 | 20:00 | 77 885,2 | 77 880,0 | 78 264,1 | +0,49 % |

No minuto do estouro, **22:08Z**, o BTC caiu **−0,204 %** (amplitude 0,246 %) — com
volume 1 425 BTC contra ~50 típicos, ou seja, ele *sentiu*, mas não caiu.

**O universo caiu.** Amplitude sobre os 200 perpétuos monitorados (fração com vela de
1 min negativa):

| minuto UTC | BRT | caindo | média | mediana |
|---|---|---|---|---|
| 21:48 | 18:48 | 181/200 (90,5 %) | −0,28 % | −0,21 % |
| 21:49 | 18:49 | 184/200 (92,0 %) | −0,28 % | −0,22 % |
| 22:07 | 19:07 | 190/200 (95,0 %) | −0,44 % | −0,29 % |
| **22:08** | **19:08** | **194/200 (97,0 %)** | **−3,71 %** | **−1,76 %** |
| 22:09 | 19:09 | 36/200 (18,0 %) | **+1,53 %** | +0,54 % |

O minuto 22:08Z é uma **cascata de alts** com repique imediato: LABUSDT −35,8 %,
ESPORTSUSDT −30,6 %, VELVETUSDT −26,3 %, TUTUSDT −24,8 %, TACUSDT −24,2 % **em um
minuto**, com o BTC em −0,2 %. Assinatura de liquidação em cadeia nas pontas ilíquidas,
não de um choque macro.

**Regime.** `regime_hourly_v1` (`market_regimes`, `scope = btc`, `classifier_version =
'regime_hourly_v1'`, uma linha por hora, T3.43 / PIPELINE §4b) marcou **`BTC_BEAR`,
confiança 1,0000, em TODAS as horas** de 09/09 16:00Z a 10/09 01:00Z — inclusive a hora
anterior fechada à decisão (20:00Z) e a própria hora 21:00Z. O `regime_v0` (`scope =
global`, por transição) oscilou entre `SIDEWAYS` e `BTC_BEAR` no mesmo período
(0,7500 de confiança). A família só emite **LONG**
(`packages/core/hunter_core/strategies/mean_reversion_v1.py:315`) e emitiu 39 LONGs numa
hora rotulada `BTC_BEAR` com a amplitude do universo já negativa (58–76 % dos mercados
caindo entre 21:00 e 21:03Z, quando as primeiras 5 entraram).

---

## 4. O dia 08/09 (o dia "bom") com a mesma decomposição

Só há dado prospectivo a partir das 15:17 BRT (18:17Z) de 08/09 — o dia tem 10 horas, não 24.

| BRT | UTC | n pooled | soma R | média | acerto | stop | alvo | tempo | apostas | soma R por aposta |
|---|---|---|---|---|---|---|---|---|---|---|
| 14 | 17 | 2 | −2,21 | −1,11 | 0 % | 2 | 0 | 0 | 2 | −2,21 |
| 15 | 18 | 7 | +2,05 | +0,29 | 57 % | 3 | 3 | 1 | 7 | +2,05 |
| 16 | 19 | 7 | +0,38 | +0,06 | 43 % | 2 | 3 | 2 | 7 | +0,38 |
| 17 | 20 | 14 | +4,58 | +0,38 | 67 % | 3 | 7 | 4 | 14 | +4,58 |
| **18** | **21** | 18 | **+1,32** | +0,07 | 50 % | 6 | 7 | 5 | 11 | +0,18 |
| 19 | 22 | 12 | −4,95 | −0,41 | 33 % | 6 | 2 | 4 | 5 | −1,41 |
| 20 | 23 | 14 | +13,41 | +1,12 | 92 % | 0 | 12 | 2 | 4 | +2,95 |
| 21 | 0 | 12 | −3,96 | −0,33 | 58 % | 5 | 3 | 4 | 2 | −0,66 |
| 22 | 1 | 12 | +0,89 | +0,07 | 75 % | 3 | 0 | 9 | 2 | +0,15 |
| 23 | 2 | 11 | +2,73 | +0,25 | 64 % | 4 | 6 | 1 | 2 | +0,35 |

**A hora 21Z de 08/09 é positiva (+1,32 R, 50 % de acerto, 11 apostas únicas).** A pior
hora de 08/09 foi 22Z (−4,95 R) e a melhor foi 23Z (+13,41 R) — nenhuma das duas é 21Z.
Por mercado, 08/09 é largo e ganho por poucos (VET +6,82, PIEVERSE +5,89, INJ +4,30) e
perdido por PONS (−7,96) e NEAR (−4,32). Por versão, tudo positivo menos v8 (−0,51),
com v1 +4,45 em 52 decisões.

**Diferença estrutural entre os dois dias que muda a leitura de qualquer soma pooled:**
em 08/09 a maioria das apostas tinha **1 versão** (109 decisões / ~76 apostas); em 09/09
o número de versões vivas cresceu e a média é de **4 a 8 versões por aposta**. O R pooled
da família **escala com o número de versões**, não com o número de decisões econômicas.
Comparar "+14 R num dia" com "−34 R noutro" sem dividir por versões compara duas
populações diferentes.

**Sensibilidade leave-one-out (09/09 BRT, família do brief, dia = −34,50 R):**

| tirando | n do mercado | R do mercado | R do dia sem ele | média sem ele |
|---|---|---|---|---|
| ZECUSDT | 24 | **−18,04** | −16,47 | −0,043 |
| ALGOUSDT | 8 | −8,83 | −25,67 | −0,065 |
| ZKUSDT | 8 | −8,69 | −25,82 | −0,066 |
| UAIUSDT | 8 | −8,50 | −26,00 | −0,066 |
| TRUTHUSDT | 14 | **+16,67** | −51,17 | −0,132 |
| FFUSDT | 21 | **+15,05** | −49,56 | −0,130 |

ZEC sozinho é metade da perda do dia (5 apostas únicas, 2 tipos de mercado, 23 stops de
24), mas **tirar ZEC não torna o dia positivo** (−16,47 R) e tirar os dois maiores
vencedores piora tudo. Banir ZEC pela manchete continua proibido (Astra,
`astra-review-plantao-20260910-0045.md`).

---

## 5. Resposta em português (≤ 12 linhas)

1. Os −34,02 R da hora 21:00Z (18:00 BRT) de 09/09 são **9 apostas únicas**, não 39: sete mercados, duas barras (21:00Z e 21:30Z), 4,33 versões por aposta. Somando uma vez cada aposta, a hora vale **−7,53 R**.
2. Todas as 39 perderam (acerto 0 %): 31 stops, 8 expirações, nenhum alvo, nenhuma invalidação.
3. **Não foi um evento só, foram dois.** Primeiro uma deriva de dezenas de velas pequenas (nenhuma > 1 ATR) que matou os stops apertados entre 18:22 e 18:49 BRT; depois um estouro.
4. O estouro tem minuto e nome: **19:08 BRT / 22:08Z**, quando **194 dos 200 perpétuos** caíram no mesmo minuto (média −3,71 %, mediana −1,76 %, LABUSDT −35,8 %) e repicaram no minuto seguinte. Ali saíram 15 das 39 (−14,77 R, 43 % da hora) e ali está a única vela de 1 min > 1 ATR (XVGUSDT, −1,54 ATR).
5. **O BTC não caiu**: −0,204 % naquele minuto, −0,22 % na hora 21Z. Foi cascata de liquidação em alts, não macro.
6. **Não é o relógio.** A mesma hora 21Z em 08/09 deu **+1,32 R** com 50 % de acerto. Há dois dias de série prospectiva: isso é painel, não teste — H-P4 não pode ser confirmada com o dia que a inspirou.
7. **É o regime, mas o rótulo já dizia isso antes:** `regime_hourly_v1` marcou `BTC_BEAR` com confiança 1,0000 em **todas** as horas de 09/09 16:00Z a 10/09 01:00Z, e a família só compra. O rótulo não separa 21Z das outras horas — ele apenas mostra que 39 LONGs nasceram num rótulo de baixa.
8. **O dia sem aquela hora não tem perda de preço, tem pedágio:** bruto +13,5 R, custo 30,8 R, líquido −0,48 R. Dentro da hora, o bruto já é −35,8 R. São dois problemas diferentes.
9. ZEC vale −18,04 R do dia; sem ZEC o dia ainda é −16,47 R. Tirar os vencedores (TRUTH +16,67, FF +15,05) piora muito mais. Nada aqui autoriza banir mercado.
10. **Para o funil, uma hipótese a pré-registrar (nunca uma mudança em versão viva): H-P7 — "correlação de barra".** A família concentra 4–8 versões e vários mercados na mesma barra de 15 min; medir a exposição por barra (apostas × versões) e testar se o R por **aposta única** é diferente do R pooled, com blocos de dia. Se for, o problema é de *dimensionamento e contagem*, não de horário.
11. Segunda a pré-registrar: **H-P8 — "amplitude do universo como estado"**: fração de perpétuos monitorados caindo nos 5 min antes da decisão, em tercis fixados em janela anterior; a pergunta é se comprar reversão com 70 % do universo caindo tem expectancy diferente. Célula, não filtro.
12. Duas coisas para o instrumento, sem edge: o Lab aposta em **spot e perpétuo do mesmo símbolo** como se fossem mercados independentes (NEAR, 09/09 21:30Z), e as linhas de spot saem com `r_multiple = NULL` por `funding_schedule_unknown`. Isso contamina qualquer contagem de "apostas únicas" por `market_id`.

---

## 6. Ressalvas honestas

- **Não reproduzi o "+32 R" de 08/09** sob nenhuma das oito definições testadas (máximo
  +19,99 R). O leitor precisa saber disso antes de comparar os dois dias.
- O "−31,08 R / 420" do brief bate com a definição E (`mean_reversion*` inteira, dia BRT)
  medida antes de alguns desfechos liquidarem; hoje ela dá −31,74 R sobre 412 com R.
- 2 dias de série prospectiva. Nada aqui é teste de hipótese; é descrição de dois dias.
  A hora 21Z de 09/09 é **descoberta**.
- `r_multiple` é nulo em 21 dos 423 desfechos de 09/09 (funding não estabelecido), então
  toda soma "com R" tem denominador menor que `n`. As duas colunas estão sempre expostas.
- A chave de "aposta única" usada é (`market_id`, barra de 15 min de `observation_ts`).
  Versões de 1 h (`v10`, `h1 v1`) leem barra de 1 h; agrupá-las na barra de 15 min é uma
  escolha minha, declarada, e é conservadora (separa mais apostas do que fundir por hora).
