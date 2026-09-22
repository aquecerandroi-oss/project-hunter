# R66 — Sair da pump.fun para operar DEPOIS da graduação (PumpSwap): a conta não fecha

**Pergunta (Everton, 22/09/2026 18:1x BRT):** "e se sairmos da pump.fun? para lucrar" — existe vantagem negociável **depois da graduação**, onde o ida-e-volta custaria ~0,5 % em vez dos 4,09 % que pagamos na curva (R65)?

**Método:** leitura read-only da VPS (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `SELECT`/`COPY TO STDOUT`; nada foi escrito). Análise local em `.claude/state/r66/`. Dinheiro em `Decimal`. Taxas lidas da **tabela real do `FeeConfig` do PumpSwap** que o nosso próprio repositório decodificou da mainnet, não de um número solto.

## Resposta curta

**Não. A premissa dos 0,5 % está errada por ~5×, e o que há depois da graduação não é melhor.**

1. **Custo.** A faixa de taxa do pool canônico, escolhida pelo market cap em SOL do instante, nas 4 400 graduações observadas: **mediana 1,20 % por perna** (p10 0,65 %, p90 1,25 %). O custo de taxa **realizado** (entrada + saída, cada perna na sua faixa) nas 3 171 operações simuladas: **mediana 2,40 %, média 2,26 %**, mais 0,13 % de rede = **~2,4–2,5 % ida-e-volta**. Na curva, o R65 mediu **2,23 %** ida-e-volta sem o rent. **Depois da graduação é igual ou ligeiramente mais caro.** Os 0,30 % da tabela pública só valem a partir de **98 240 SOL** de market cap — só 256 das 4 400 entradas (5,8 %) chegam lá, e a mediana de um recém-graduado é 708 SOL.
2. **O rent da ATA é o mesmo nas duas praças** (0,00151384 SOL = 2,16 % de um ticket de 0,07) e recuperável nas duas. **A economia identificada no R65 não exige mudar de praça.**
3. **A forma do movimento é hostil.** A mediana de um token graduado é **−79,9 % em 15 minutos** e **−95,1 % em 1 hora** desde a primeira leitura pós-graduação. 86,8 % caem ≥ 30 % dentro de 1 h. A graduação é o evento de liquidez de saída de quem estava na curva.
4. **A regra da mesa aplicada lá perde**: −0,003691 SOL por operação (**−5,27 % do ticket**) em 3 171 entradas decidíveis, **0 dias verdes em 8**. A variante lenta perde mais (−8,80 %); entrar no pullback perde um pouco menos (−4,83 %) e também nunca fecha um dia no verde.
5. **A seleção não encontra nada.** Onze variáveis observáveis no instante da entrada, baldes por terços, permutação estratificada por dia, bootstrap por dia, Benjamini-Hochberg a 10 %: **nenhuma sobrevive** (p mais baixo 0,073, limiar BH 0,0091). Exatamente como no R65. O melhor de 16 cortes retrospectivos que fica positivo tem **n = 39** — é ruído.
6. **E nem seria executável hoje:** `docs/RISK_ENGINE_MEME.md` §1 e `hunter_exchanges/pumpswap/__init__.py` — **PumpSwap é só saída**; não existe `build_buy_instruction` e comprar lá é a recusa nomeada `pumpswap_buy_not_allowed`.

**Veredito (formulação acordada com a Astra):** *o R66 não dá evidência que justifique abrir uma frente de entradas pós-graduação. A suposta grande economia de taxas não se sustenta; os resultados exploratórios disponíveis são desfavoráveis. Manter o P0 do R65 — recuperar o rent das ATAs elegíveis, que não exige mudar de praça — e não priorizar esta implementação. **Isto não demonstra superioridade da curva nem exclui outras estratégias pós-graduação** (§6, §8).*

## 1. População e cobertura — e o que **não** dá para medir

| item | valor |
|---|---|
| tokens com `migrated_at` nos últimos 7 dias | **6 384** (`meme_tokens`) — 15/09 311, 16/09 1 027, 17/09 1 133, 18/09 1 005, 19/09 1 058, 20/09 1 099, 21/09 600, 22/09 156 (dia do corte) |
| **fita do pool** (`meme_trades`, `program='pump_amm'`, depois de `migrated_at`) | **1 002 mints = 15,7 %**, mediana de **57 s** de fita; só 17 mints têm algum trade em +5 min, 1 em +1 h, **0 em +4 h**. Fonte única `swap_api`: o poller só segue mints na watchlist do radar, e larga o mint logo depois da graduação |
| **board `graduated`** (`meme_board_observations`) | **4 400 mints = 68,9 %**, cadência 60 s, primeira leitura em mediana **+29 s** depois de `migrated_at` (p10 +4 s, p90 +54 s), 195 658 observações |
| pares válidos por janela (leitura **estritamente posterior** à entrada, a ±90 s do alvo, contada a partir da 1ª leitura e não de `migrated_at`) | +1 min **4 077** (92,7 %); +5 min **3 276** (74,5 %); +15 min **2 714** (61,7 %); +1 h **1 964** (44,6 %); **+4 h: 0** |
| `meme_curve_snapshots` depois da migração | 5 233 linhas — inúteis: a curva está drenada, o preço passou a ser o do pool |

**Por que o board e não a fita.** A fita morre a 57 s; o board é o único feed que atravessa a primeira hora. Preço = `market_cap_usd` (a supply da pump.fun é fixa em 1 000 000 000, logo qualquer razão de market caps do mesmo mint é a razão de preços), convertido para SOL pela série global `volume_usd / volume_sol` (mediana por minuto de parede sobre todos os mints daquele minuto) para tirar a deriva SOL/USD.

**Essa conversão é uma reconstrução retrospectiva e está declarada como tal** (a Astra apontou-a): o minuto de câmbio usa linhas do minuto inteiro, incluindo posteriores ao instante da decisão, e cai numa mediana global quando o minuto está vazio. **Não move um retorno dentro do mesmo mint** — a razão de market caps do mesmo mint é a razão de preços com ou sem câmbio, e o SOL/USD não anda 1 % numa hora enquanto a distribuição de retornos é de ±80 %. O que ela pode mover é a **atribuição de faixa de taxa** perto de um limiar; o efeito é da ordem de 0,05 pp por perna e não muda nenhuma conclusão da §5.

**Validação do board contra a fita** (`stats.py`): nos **834 mints** com um trade do pool a ≤ 30 s da primeira leitura, a razão `(market cap do board) / (preço da fita × 1e9)` tem **mediana 1,002** (p10 0,852, p90 1,212) e **só 68,2 % ficam dentro de ±10 %**. O intervalo p10–p90 é **−14,8 % a +21,2 %** — ruído da **mesma ordem do alvo de +15 %**. A frase honesta é: **há concordância central nesta subamostra** (que é ela própria selecionada: são os mints que ainda tinham fita), **não ausência de viés** nos retornos, nos extremos ou nas saídas. É a ressalva nº 1 deste relatório (§6).

**Sobrevivência, declarada:** só medimos o que o radar viu. O board `graduated` tem **30 posições** (`position` 0..29) e o token cai fora depois de ~1 h (span p50 3 488 s, p90 5 277 s; última posição vista p50 = 28). Direção do viés **desconhecida** — não sei a ordenação do board. O que sei medir: o retorno mediano a +15 min de quem fica pouco tempo é **−66,5 %** e de quem fica muito é **−88,3 %**, ou seja quem some cedo do board **não** é o que caiu mais. **+4 h não é estimável com esta coleta** e não é reportado.

**Não-antecipação:** o instante da decisão é o `observed_at` da primeira leitura em ou depois de `migrated_at`; todas as janelas contam **a partir dessa leitura**; nenhuma estatística e nenhuma saída simulada usa leitura posterior ao instante julgado (`load.py: entry_point/value_at/window`, `sim.py: MAX_GAP_S` e `censurado_fim`). A única exceção conhecida é a série global SOL/USD, declarada acima.

## 2. A forma do movimento depois da graduação

Retorno bruto (%) desde a 1ª leitura pós-graduação (`metrics.txt`):

| janela | n | p10 | p25 | **mediana** | p75 | p90 | ≥ +15 % | ≤ −30 % |
|---|---|---|---|---|---|---|---|---|
| +1 min | 4 077 | −35,6 | −9,6 | **+0,9** | +5,7 | +23,6 | 14,6 % | 11,9 % |
| +5 min | 3 276 | −79,7 | −54,4 | **+1,2** | +22,1 | +68,6 | 29,5 % | 35,3 % |
| +15 min | 2 714 | −95,8 | −94,8 | **−79,9** | +5,1 | +66,3 | 20,6 % | 64,8 % |
| +1 h | 1 964 | −99,7 | −99,4 | **−95,1** | −86,9 | +4,6 | 5,2 % | 86,8 % |
| +4 h | 0 | — | — | — | — | — | — | — |

MFE/MAE dentro da janela (só fecho de barra de 60 s — o extremo intra-minuto **não existe** nestes dados):

| janela | n | MFE med | MFE p75 | MFE p90 | MAE p10 | MAE med | toca +15 % | toca −10 % |
|---|---|---|---|---|---|---|---|---|
| +1 min | 2 264 | +1,0 | +4,8 | +20,6 | −31,7 | 0,0 | 12,8 % | 21,6 % |
| +5 min | 4 102 | +5,4 | +26,1 | +70,2 | −76,9 | −0,0 | 34,2 % | 43,3 % |
| +15 min | 4 133 | +12,3 | +49,5 | +133,0 | −95,8 | −46,7 | 47,8 % | 59,9 % |
| +1 h | 4 275 | +12,3 | +55,9 | +159,2 | −99,6 | −92,8 | 47,8 % | 75,3 % |

**Leitura:** os primeiros 5 minutos são quase simétricos (mediana +1,2 %, mas p25 −54 % e p75 +22 %); a partir daí a distribuição desaba. A cauda de cima é real (p90 de MFE +133 % em 15 min), mas o MFE aqui é medido em fechos de 60 s e não é tocável por uma regra que decide a cada segundo (§6.3).

**Comparação com a curva (R64/R65).** Não é par a par — aqui é população (4 400 graduações), lá são 87 apostas já filtradas por 25 checks de admissão. O que dá para dizer: nas 87 reais da curva o **MFE mediano em 300 s foi +7,6 % nas saídas por trailing e +46,7 % nas por alvo**; aqui o MFE mediano em 5 min é **+5,4 %** sobre a população inteira e o MAE mediano em 15 min é **−46,7 %**. Os números lado a lado: 64,8 % dos graduados perdem ≥ 30 % em 15 min; no dia do R64, 12 de 24 posições reais estavam abaixo de −40 % aos 300 s. **Não afirmo com isto que a distribuição pós-graduação seja pior** — populações, janelas e filtros são diferentes; afirmo que a população pós-graduação, sem filtro, é hostil em valor absoluto.

## 3. A nossa regra aplicada lá (`sim.py`, `sim.txt`)

**Custos usados** — todos do nosso código ou do R65, nenhum inventado:
- **taxa do pool:** as **25 faixas reais** do `FeeConfig` do PumpSwap decodificadas da mainnet em 16/09 (`packages/exchange-adapters/tests/unit/test_pumpfun_fee_config.py`, fixture `t429c_rpc_fee_config_amm_raw.json`, idênticas a `POOL_FEE_TIERS_SOL` de `packages/indicators/hunter_indicators/meme/pool.py`): faixa 0 (mcap < 420 SOL) = lp 2 + protocolo 93 + criador 30 bps = **1,25 %**; 420–1 470 SOL = **1,20 %**; … ; **≥ 98 240 SOL = 0,30 %**. A faixa é recalculada **na entrada e na saída**, cada uma pelo market cap do seu instante;
- **rede:** 0,000091 SOL por operação (R65: 0,007919 / 87);
- **rent de ATA:** 0,00151384 SOL, cobrado quando o mint é novo (é sempre novo aqui) e zero quando a conta é fechada na venda — reporto os dois;
- **impacto:** 0,10 % por perna. **É a única suposição numérica que fiz** (§7).

**Distribuição da faixa nas 4 400 entradas:** 1,25 % em 954, 1,20 % em 1 522, 1,00 % em 754, 1,05 % em 242, 1,10 % em 160 … e **0,30 % em apenas 256 (5,8 %)**. Mediana **1,20 %/perna**, p10 0,65 %, p90 1,25 %.
**Custo de taxa REALIZADO (entrada + saída) nas operações decididas: mediana 2,40 %, média 2,26 %.**

**Censura, separada do resultado** (correção pedida pela Astra): uma leitura que chega depois de uma lacuna maior que **150 s** (2,5× a cadência) não decide nada — atribuir a saída de uma regra de 300 s a uma leitura que chegou 7 minutos depois não é "monitorização a 60 s". E quando a série acaba sem gatilho, **vender na última leitura seria antecipação** (naquele instante ninguém sabia que era a última). Ambos os casos são marcados `censurado_lacuna` / `censurado_fim` e **excluídos do PnL**.

| cenário | decidíveis | censuradas | total SOL | por operação | % do ticket | alvos | hold med. | pior | melhor | dias verdes |
|---|---|---|---|---|---|---|---|---|---|---|
| graduação + regra da mesa (1,15× / trail 10 % / 300 s), rent devolvido | 3 171 | 1 229 (27,9 %) | **−11,70** | −0,003691 | **−5,27 %** | 36,2 % | 73 s | −0,0701 | +1,1815 | **0/8** |
| idem, rent perdido | 3 171 | 1 229 | −16,50 | −0,005205 | −7,44 % | 36,2 % | 73 s | −0,0716 | +1,1800 | 0/8 |
| graduação + regra lenta (1,30× / trail 15 % / 3 600 s), rent devolvido | 2 763 | 1 637 (37,2 %) | −17,03 | −0,006163 | −8,80 % | 34,2 % | 120 s | −0,0701 | +1,1815 | 0/8 |
| **pullback** (−10 % do máximo pós-graduação, até +15 min) + regra da mesa | 2 602 | 111 (4,1 %) | −8,79 | −0,003379 | **−4,83 %** | 44,0 % | 60 s | −0,0701 | +0,3694 | **0/8** |
| pullback + regra lenta | 2 519 | 194 (7,2 %) | −12,43 | −0,004935 | −7,05 % | 36,0 % | 120 s | −0,0701 | +0,3694 | 0/8 |

Por dia (regra da mesa na graduação, SOL): 15/09 −0,426 · 16/09 −1,568 · 17/09 −2,103 · 18/09 −1,614 · 19/09 −2,018 · 20/09 −3,131 · 21/09 −0,837 · 22/09 −0,007. **Oito dias, oito negativos.**

**O que esta simulação NÃO é.** A série é de **snapshots a ~60 s, não barras OHLC**. O pico e o vale intra-minuto não existem. Perder um pico pode ter evitado uma perda; perder um stop pode ter salvado uma recuperação. **O viés líquido tem direção indeterminada** — isto não é limite superior nem inferior, é monitorização discreta, e o `melhor = +1,1815 SOL` num ticket de 0,07 prova-o: é uma barra que saltou ~17× e a regra "saiu no alvo" a 17×, coisa que a execução real a cada segundo nunca faria. **Trate a §3 como exploratória.**

**Só 61,7 % dos mints chegam a mostrar um pullback de −10 % dentro de 15 min.** Quem entra neles perde menos (−4,83 % contra −5,27 %) porque entra depois da primeira perna de queda — e mesmo assim nenhum dos 8 dias fecha no verde.

## 4. Seleção: **nada sobrevive** — a mesma resposta do R65

Método (`stats.py`), com os ajustes que a Astra pediu: há **uma entrada por mint**, logo o bootstrap por cluster de mint degenera — o cluster é o **dia** (8 dias, reamostrados inteiros); a **permutação (10 000) é estratificada por dia**, para um p pequeno não poder ser só "esta variável identifica uma hora boa"; **Benjamini-Hochberg a 10 %** sobre a família. Só entram variáveis observáveis **no instante da entrada** ou antes dele. Desfecho = PnL da regra da mesa, **sobre as 3 171 decidíveis** (as censuradas não têm desfecho observável).

| variável (terços) | n baixo / alto | PnL baixo | PnL alto | diferença | IC 95 % (cluster = dia) | p perm. |
|---|---|---|---|---|---|---|
| market cap na entrada (SOL) | 1 058 / 1 058 | −0,002608 | −0,004817 | −0,002210 | [−0,004019, −0,000557] | 0,0734 |
| volume 5 min (SOL) | 1 058 / 1 058 | −0,005008 | −0,002390 | +0,002617 | [−0,000612, +0,005353] | 0,0986 |
| volume acumulado da curva (SOL) | 1 058 / 1 058 | −0,004894 | −0,002522 | +0,002373 | [−0,001311, +0,006080] | 0,1408 |
| holders | 1 065 / 1 061 | −0,004721 | −0,002685 | +0,002037 | [−0,001576, +0,005359] | 0,2152 |
| snipers | 1 112 / 1 073 | −0,003531 | −0,005025 | −0,001494 | [−0,003801, +0,001202] | 0,2501 |
| idade da criação até a graduação (s) | 1 057 / 1 057 | −0,003584 | −0,001882 | +0,001702 | [−0,003356, +0,005042] | 0,3066 |
| vendas / compras | 1 058 / 1 058 | −0,004114 | −0,003062 | +0,001052 | [−0,004692, +0,005549] | 0,5423 |
| compras | 1 064 / 1 060 | −0,003776 | −0,002808 | +0,000968 | [−0,003996, +0,004966] | 0,5851 |
| vendas | 1 074 / 1 058 | −0,003983 | −0,003231 | +0,000752 | [−0,004143, +0,004564] | 0,6669 |
| top-10 share | 1 058 / 1 058 | −0,003555 | −0,004282 | −0,000728 | [−0,005163, +0,001869] | 0,6770 |
| transações | 1 064 / 1 059 | −0,003916 | −0,003231 | +0,000685 | [−0,003878, +0,004730] | 0,6933 |

`participantes`, `dev share` e `KOLs` vêm constantes no board `graduated` (terços iguais) — excluídas por falta de variância, como `holders_rising` no R65.

**Benjamini-Hochberg a 10 %: nenhuma sobrevive.** O p mais baixo é 0,0734 contra um limiar de 0,0091. **Dizer "não achei nada" é o resultado.**

> **Correção importante, e é uma lição:** na primeira volta desta análise — que vendia na última leitura e aceitava lacunas de minutos — **9 de 11 contrastes "sobreviviam" ao Benjamini-Hochberg** com p = 0,0001. Depois de tirar a antecipação (venda retrospectiva) e de separar a censura, **o sinal desapareceu por inteiro**. O "sinal" era o artefacto: os mints com lacuna e fim de série não são um sorteio, e as variáveis que "separavam" separavam **quem tinha série boa**, não quem dava lucro.

Cortes retrospectivos (`best.txt`, 16 cortes de 1–3 variáveis mais o universo, **escolhidos olhando estes mesmos dados**): o melhor tercil isolado é `idade ≥ p67` com **−0,001882 SOL/op**; o único corte que fica positivo é `compras ≥ p67 & top-10 ≥ p67` com **+0,001630 SOL/op e n = 39** — com 39 pontos entre 16 cortes explorados, **o valor honesto a atribuir-lhe é zero**. Nenhum outro é positivo.

## 5. Veredito: curva vs pós-graduação, lado a lado

| | **curva (pump.fun)** | **pós-graduação (PumpSwap canônico)** |
|---|---|---|
| taxa de protocolo + criador | 1,25 %/perna (config da curva, faixa única, confirmada na mainnet) | **1,20 %/perna na mediana** (p10 0,65 %, p90 1,25 %); 0,30 % só em 5,8 % das entradas |
| rede | 0,13 % ida-e-volta | 0,13 % ida-e-volta |
| **custo ida-e-volta sem rent** | **2,23 %** (medido em 87 operações reais, R65) | **~2,4–2,5 %** (taxa realizada: mediana 2,40 %, média 2,26 %; mais 0,13 % de rede) |
| rent de ATA | 0,00151384 SOL = 2,16 % do ticket, **recuperável** | idêntico, **recuperável** — e o mint é sempre novo |
| custo ida-e-volta com rent perdido | 4,09 % (medido) | ~4,6–4,7 % |
| **acerto de equilíbrio** (alvo +15 %, stop −10 %: `p = (10+c)/25`) | **48,9 %** sem rent · 56,4 % com rent | **~50,5 %** sem rent · ~58,6 % com rent |
| idem na convenção simples do R65 (`p = c/15`) | 14,9 % sem rent · 27,3 % com rent | ~16,9 % sem rent · ~31 % com rent |
| resultado por operação | −0,00399 SOL **real** (−5,7 % do ticket, 87 operações) | −0,00369 SOL **simulado** (−5,27 % do ticket, 3 171 operações) |
| dias verdes | 0 de 6 (real) | 0 de 8 (simulado) |
| executável hoje? | sim | **não** — `pumpswap_buy_not_allowed`; PumpSwap é só saída |

**Resposta à pergunta do Everton: a economia que ele procurava não existe nesta rota.** Os "0,5 %" só aparecem a partir de **98 240 SOL** de market cap, e a mediana de um recém-graduado é **708 SOL**. O custo é **igual ou ligeiramente pior**, e o resultado simulado por operação é **indistinguível** do real da curva (−5,27 % contra −5,7 % do ticket) — com a diferença de que o da curva é dinheiro real medido e o de lá é uma simulação exploratória sobre preços esparsos. **A recuperação de rent identificada no R65 não exige mudar de praça.**

## 6. Ressalvas, por ordem de importância

1. **(a nº 1, na formulação da Astra) Este estudo não identifica a diferença de rentabilidade *executável* entre curva e pós-graduação:** observa uma amostra incompleta do board e simula saídas sobre preços esparsos. O que está sólido é a **conta do custo** (§5) e a **mediana da distribuição** (§2); o PnL da §3 é exploratório.
2. **O preço do board tem ruído da ordem do alvo.** Mediana 1,002 contra a fita, mas p10–p90 de −14,8 % a +21,2 % e só 68,2 % dentro de ±10 %, **numa subamostra ela própria selecionada** (só os mints que ainda tinham fita). Com um alvo de +15 %, parte dos "alvos" e dos "trailings" simulados é ruído de medição. Um erro no preço de **entrada** também pode fabricar associação entre "market cap menor" e retorno posterior maior — mais uma razão para não creditar a §4.
3. **Snapshots a 60 s não são barras.** Sem extremo intra-minuto, a regra de alvo/trailing não é reproduzível e o viés não tem direção garantida.
4. **Censura: 27,9 % das entradas não são decidíveis** (825 por lacuna > 150 s, 404 por fim de série) e estão fora do PnL. Se as censuradas não forem um sorteio — e provavelmente não são — o PnL das decidíveis é enviesado numa direção que não sei nomear.
5. **Cobertura e sobrevivência.** 68,9 % dos graduados têm série; o board tem 30 posições e o token cai fora em ~1 h; a ordenação do board é desconhecida, logo a direção do viés também. **+4 h não foi medido** (0 pares válidos) e não deve ser inferido dos 72 mints que aparecem nessa janela.
6. **7 dias, um regime, 8 datas.** "Muitos mints" não é "muita informação": permutar dentro do dia não elimina dependência intradiária e o bootstrap por dia não cria regimes novos. **Não escrevo "há poder a sério"** — escrevo que não encontrei nada.
7. **Os cortes da §4 foram escolhidos nestes dados**, e o único positivo tem n = 39.
8. **A fita do pool cobre 15,7 % dos mints e morre a 57 s.** Serviu para validar o board, não para medir retorno.
9. **A conversão SOL/USD é uma reconstrução retrospectiva** (§1) — não move retornos dentro do mesmo mint, pode mover a faixa de taxa perto de um limiar.

## 7. Suposição numérica declarada

**Impacto de 0,10 % por perna.** Um ticket de 0,07 SOL contra a reserva de ~79 SOL que a graduação deposita no pool dá ~0,09 %; arredondei para 0,10 % e apliquei nas duas pernas. **Não foi cotado contra um pool real** — não temos `build_buy_instruction` para o PumpSwap e nenhuma venda real no pool foi sequer simulada na mainnet (`docs/RISK_ENGINE_MEME.md` §1, T4.29a "o que não está provado"). Se o impacto real for 1 % por perna em vez de 0,1 %, o custo pós-graduação sobe de ~2,5 % para ~4,3 % — **a conclusão fica mais forte, nunca mais fraca**. Nenhuma outra suposição numérica foi feita: taxas, rede e rent vêm do código e do R65.

## 8. Segunda opinião (Astra) — ela mudou o resultado, não só a redação

Duas chamadas: `bash infra/scripts/astra.sh ask r66 "..."` (método, antes de medir) → `.claude/state/astra-review-r66.md`, e `... ask r66-veredito "..."` (veredito e código) → `.claude/state/astra-review-r66-veredito.md`.

**Ronda 1 — método, corrigido antes de medir:**
1. **Eu somava a rede duas vezes.** Os 2,23 % da curva **já incluem** os 0,13 % de rede. Corrigido em toda a §5.
2. **O rent é 0,00151384 SOL, não 0,00204** (o 0,00204 é a sobra da venda por Jupiter da mesa spot). Corrigido.
3. **"Recém-graduado" não garante a faixa de 1,25 %** — a faixa é do market cap do instante. Passei a escolhê-la linha a linha: mediana 1,20 %.
4. **O relógio da entrada** é a primeira leitura observável (+29 s), não `migrated_at`.
5. **`volume_usd/volume_sol` não é câmbio spot.** Por isso a validação é feita contra a **fita em SOL**, que não passa por câmbio nenhum.
6. **Bootstrap por mint degenera** com uma entrada por mint; permutação irrestrita pode devolver p pequeno para uma variável que só identifica uma hora boa. Refiz com **cluster e permutação por dia**.

**Ronda 2 — três bugs reais no meu código, todos corrigidos e todos mudaram números:**
1. **A minha tabela de taxas estava truncada em 0,80 %** (dez faixas em vez de 25). 466 entradas estavam acima do primeiro limiar omitido e levavam 0,80 % quando a tabela manda até 0,30 %. **Completei as 25 faixas e recalculei tudo.**
2. **A simulação aceitava lacunas arbitrárias e vendia retrospectivamente na última leitura** (721 operações "de 300 s" duravam mais de 390 s; 295 eram vendas no fim da série). Isto é **antecipação**. Passei a censurar (`MAX_GAP_S = 150`) e a excluir as censuradas do PnL: **o prejuízo por operação caiu de −14,12 % para −5,27 % do ticket** — o número anterior estava **inflacionado pelo próprio artefacto**.
3. **`value_at` aceitava a própria leitura de entrada** como retorno de +1 min, fabricando 100 % de cobertura e zeros artificiais. Corrigido (leitura estritamente posterior): a cobertura a +1 min passou de 4 400 para **4 077**.

**E a correção que mais importa:** com (2) resolvido, **os "9 de 11 contrastes que sobreviviam ao Benjamini-Hochberg" passaram a ZERO** (§4). O sinal era o artefacto. Tinha eu escrito "com n = 4 288 há poder a sério" — a Astra pediu para retirar a frase, e ela estava certa por um motivo ainda mais forte do que o que apresentou.

**Onde ajustei a redação a pedido dela:** "não é melhor / a distribuição é pior / o board é não-enviesado" excediam a evidência e foram reescritos (§1, §5, §6); "a única economia real" passou a **"a recuperação de rent identificada no R65 não exige mudar de praça"**; o veredito passou a dizer explicitamente que **isto não demonstra superioridade da curva nem exclui outras estratégias pós-graduação**.

**Onde discordo, e escrevo porquê:** ela propôs terminar em "ainda não sabemos se a população pós-graduação oferece retorno líquido melhor". Aceito a formulação para o **veredito**, mas registo que já sabemos mais do que "não sabemos": a mediana a +15 min é −79,9 % em 2 714 pares e a regra perde em 8 de 8 dias em 3 171 entradas decidíveis. Isso não prova impossibilidade — prova que **a versão simples da ideia (entrar na graduação com a regra atual) está medida e é desfavorável**.

**Hipóteses que estes dados NÃO testam** (ficam como nota, sem prioridade de implementação): (a) entrar **a partir de +1 h**, condicionado a liquidez e atividade observáveis *naquele instante* — escolher retrospectivamente quem sobreviveu e dar-lhe entrada na graduação seria antecipação, e "continuar no board" também não é "sobreviver economicamente"; (b) horizontes de **horas ou dias** — o nosso feed morre em 1 h; (c) pools **não canônicos** a 0,30 %, que existem na tabela pública mas sem garantia de liquidez ou preço executável por mint.

## 9. Arquivos

`.claude/state/r66/`:
- consultas: `q1_board.sql`, `q2_tokens.sql`, `q3_pregrad.sql`, `q4_amm.sql` (só `SELECT`/`COPY TO STDOUT`)
- dados: `board.csv` (195 658), `tokens.csv` (6 384), `pregrad.csv` (2 330), `amm.csv` (79 620)
- código: `load.py` (série de preço pós-graduação), `metrics.py` → `metrics.txt` (Q1/Q2), `sim.py` → `sim.txt` (Q3), `stats.py` → `stats.txt` (validação + Q4), `best.py` → `best.txt` (cortes)

Astra: `.claude/state/astra-review-r66.md`, `.claude/state/astra-review-r66-veredito.md`.
KB: `obsidian/11-KNOWLEDGE/KB-0148-a-graduacao-nao-e-a-saida-barata.md`.
**Nenhum EXP foi aberto:** não emergiu regra testável — o que emergiu foi uma refutação.

## 10. Proposta de linha de diário (22/09)

> **22/09 R66 — "e se sairmos da pump.fun?" Resposta: a economia que procurávamos não existe nessa rota.** A taxa do pool canônico do PumpSwap num recém-graduado é **1,20 % por perna na mediana** (p10 0,65 %, p90 1,25 %): os 0,30 % da tabela pública só começam em **98 240 SOL** de market cap e só 5,8 % das 4 400 graduações observadas chegam lá — a mediana é 708 SOL. Custo de taxa **realizado** ida-e-volta **2,40 % mediano lá contra 2,23 % na curva**, e o rent de ATA é idêntico e recuperável nas duas praças: **a recuperação de rent do R65 não exige mudar de praça**. Em 6 384 graduações de 7 dias (4 400 com série do board de 60 s), a mediana de um token graduado é **−79,9 % em 15 min** e **−95,1 % em 1 h**; a regra da mesa aplicada lá perde **−0,003691 SOL por operação (−5,27 % do ticket)** em 3 171 entradas decidíveis, **0 dias verdes em 8**; entrar no pullback de −10 % perde −4,83 % e também 0/8. Das 11 variáveis observáveis na entrada, **nenhuma sobrevive ao Benjamini-Hochberg** — como no R65. **E a lição do dia é minha:** a primeira volta desta análise dizia "9 de 11 sobrevivem" e "−14,1 % do ticket"; os dois números eram **artefacto de antecipação** (vendia na última leitura da série e aceitava lacunas de minutos) que a Astra apanhou — corrigido, o sinal desapareceu e o prejuízo caiu para metade. **Decisão: não abrir frente pós-graduação; o P0 continua a ser fechar a ATA.** Ressalva nº 1: este estudo não identifica a diferença de rentabilidade **executável** entre as duas praças — o preço do board só bate com a fita dentro de ±10 % em 68 % dos casos, ruído da mesma ordem do alvo de +15 %.
