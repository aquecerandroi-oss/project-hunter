## 1. População e cobertura

| recorte | mints | com fita desde o nascimento (R73) | compradoras pré-decisão | resolvidas antes da decisão | cobertura agregada | mediana por mint | mints ≥ 60 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| uma por mint (todas) | 591 | 291 | 32219 | 22150 | 68.7% | 97.5% | 368 de 533 |
| reais | 84 | 45 | 3994 | 3965 | 99.3% | 100.0% | 69 de 69 |
| papel | 507 | 246 | 28225 | 18185 | 64.4% | 95.9% | 299 de 464 |
| **elegíveis** | 291 | 291 | 14649 | 14350 | 98.0% | 100.0% | 288 de 291 |

Desfecho nas elegíveis: {'None': 272, 'gap>60s': 11, 'not_resolvable': 8} (`None` = resolvido). Compradoras no mesmo segundo da decisão (ambíguas, contadas): 106 de 14649.

## 2. A variável

`rede_financiadora_pct` nas 291 elegíveis: zeros 100 (34.4%); quantis 1/3 0.0000, mediana 0.0364, 2/3 0.0520, p90 0.1515, máx 0.8000.

| caso | via | fita nasce/reconcilia | compradoras | resolvidas | maior grupo | rede (congelada) | rede ÷ todas | s1 | s2 | criador | despejo (máx. vendedoras/slot) | PnL realizado |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| SIMFTR | live | True/False | 78 | 78 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | True (73) | -0.0283607920 |
| CITIZEN | live | False/False | 333 | 333 | 2 | 0.6% | 0.6% | 0.6% | 0.6% | 0.0% | True (154) | -0.0573418300 |
| WAVECOREE | live | True/True | 75 | 75 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | True (76) | -0.0368884810 |
| RHOS | live | False/False | 365 | 365 | 5 | 1.4% | 1.4% | 0.0% | 1.4% | 0.0% | True (262) | -0.0062708330 |

## 3. Tercis (D = baixo − alto; previsão D ≥ +0,05)

| recorte | n | baixo / alto | cortes | média baixo / alto | D (baixo − alto) | IC 95 % (mint) | despejo baixo vs alto |
|---|---:|---:|---|---|---:|---|---|
| **principal** (simulador, censura 60 s) | 272 | 91 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0427 / -0.0963 | **+0.0535** | [-0.0050, +0.1162] | 12/91 vs 8/91 |
| sem censura por buraco | 283 | 95 / 95 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0404 / -0.0948 | **+0.0544** | [-0.0037, +0.1129] | 12/95 vs 8/95 |
| censura ≤ 30 s | 264 | 88 / 86 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0469 / -0.0984 | **+0.0514** | [-0.0115, +0.1155] | 12/88 vs 8/86 |
| s1 (exclui desconhecidos) | 272 | 220 / 52 | ≤ q⅓ 0.0000 / > q⅔ 0.0000 | -0.0745 / -0.0509 | **-0.0236** | [-0.0810, +0.0350] | 29/220 vs 7/52 |
| s2 (só identidade) | 272 | 89 / 89 | ≤ q⅓ 0.0164 / > q⅔ 0.0556 | -0.0434 / -0.0875 | **+0.0441** | [-0.0172, +0.1071] | 12/89 vs 9/89 |
| maior grupo ÷ todas | 272 | 91 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0427 / -0.0963 | **+0.0535** | [-0.0066, +0.1153] | 12/91 vs 8/91 |
| só reais | 44 | — / — | — | — | — | sem potência | — |
| só reais, PnL realizado | 45 | — / — | — | — | — | sem potência | — |
| só papel | 228 | 75 / 76 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0396 / -0.1017 | **+0.0621** | [+0.0037, +0.1254] | 8/75 vs 5/76 |
| cobertura por mint ≥ 60 % | 270 | 89 / 91 | ≤ q⅓ 0.0000 / > q⅔ 0.0520 | -0.0442 / -0.0963 | **+0.0521** | [-0.0096, +0.1146] | 12/89 vs 8/91 |

Por dia (D e n; descritivo):

- 2026-09-12: n = 1 (sem potência)
- 2026-09-13: n = 22 (sem potência)
- 2026-09-14: n = 16 (sem potência)
- 2026-09-15: n = 18 (sem potência)
- 2026-09-16: n = 18 (sem potência)
- 2026-09-17: n = 38 (sem potência)
- 2026-09-18: n = 51 (sem potência)
- 2026-09-19: n = 45 (sem potência)
- 2026-09-20: n = 33 (sem potência)
- 2026-09-21: n = 22 (sem potência)
- 2026-09-23: n = 8 (sem potência)

## 4. Despejo coordenado (≥ 10 vendedoras distintas num slot, até 300 s da entrada)

| tercil | n | despejo coordenado [Wilson] | perda ≥ 50 % |
|---|---:|---|---:|
| baixo | 91 | 13.2% [7.7%–21.6%] | 3 |
| alto | 91 | 8.8% [4.5%–16.4%] | 5 |

Razão alto ÷ baixo = **0.67×** (a previsão pede ≥ 2×). Diferença de taxas (alto − baixo) -0.044, IC 95 % bootstrap por mint [-0.135, +0.047].

## 5. Moinho — primária e secundária

# H-014 primária — rede_financiadora_pct (baixo × alto) — NÃO CONFIRMA

> Origem: perda real SIMFTR 23/09/2026 (73 vendedoras num slot)  ·  impressão digital do pré-registo: `2f6294373725`
> Limiar congelado: **0**  ·  efeito mínimo relevante (MRE): **+0.0500**

## Pré-registo (escrito antes de correr)

- **Previsão:** o tercil alto de rede_financiadora_pct rende menos −0,05 por SOL que o baixo (IC 95 % bootstrap por mint inteiramente abaixo de zero) e tem taxa de despejo coordenado ≥ 2× a do tercil baixo; patamar em dois limiares vizinhos; no contrafactual das reais, um teto bloqueia ≥ 3 das 6 piores e mata ≤ 20 % das vencedoras
- **Refutação:** limite superior do IC acima de −0,01 por SOL; ou a curva é pico e não patamar; ou o teto que bloqueia as piores mata > 30 % das vencedoras; ou financiador resolvido em < 60 % das compradoras pré-decisão (limite de dado, não resultado). ERRATA (Astra, antes do contraste): a cláusula (a) literal só não-confirma; refutação pelo intervalo = limite superior de D(baixo−alto) < +0,01
- **Regra de decisão:** moinho sobre os tercis extremos: CONFIRMA com D(baixo−alto)>0, D≥MRE 0,05, IC inferior>0, p<0,05, braço baixo lucrativo em nível, planalto; rótulo final pela regra das notas §0.4b-4
- **Política de limiar:** limiar = máximo do tercil baixo (quantil 1/3, empates juntos), fixado antes dos desfechos
- **Congelado em:** 2026-09-23

## Os números

| # | o quê | valor |
|---|---|---|
| 1 | população usada (de 182 linhas lidas) | **182** em 182 clusters |
| 2 | selecionados / resto no limiar congelado | 91 / 91 |
| 3 | média do desfecho: selecionados / resto | -0.0427 / -0.0963 |
| 4 | **D = média(selecionados) − média(resto)** | **+0.0535** |
| 5 | IC 95 % de D (bootstrap de cluster por `mint`) | [-0.0050, +0.1162]  P(D≤0) = 0.037 |
| 6 | IC 95 % de D (bootstrap de blocos) | [-0.0042, +0.1141] em 113 blocos |
| 7 | p de permutação (estratificada por `dia`) | 0.0830 |

Censura: 0 linhas sem desfecho, 0 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: NÃO CONFIRMA

- IC 95 % inferior -0.0050 não está acima de zero
- p de permutação 0.0830 não é < 0,05
- o braço selecionado perde em nível (-0.0427); perder menos que o resto não é vantagem
- há dependência temporal declarada e o IC 95 % por blocos [-0.0042, +0.1141] cobre zero

## Curva de limiares — planalto ou pico?

Diagnóstico: **pico** (1 limiares avaliáveis; maior corrida positiva 1 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|
| 0 | 91/91 | +0.0535 | [-0.0050, +0.1162] |

## Baldes por tercis (descritivo, não decide nada)

| balde | n | média | mediana |
|---|---|---|---|
| -0 | 91 | -0.0427 | -0.0827 |
| 0-0.0757576 | 31 | -0.1121 | -0.1111 |
| 0.0757576-inf | 60 | -0.0881 | -0.1079 |

## A ressalva que mais importa

a guarda não correu (dispensa declarada: variável = compradoras com block_time < decisão (oráculo retrospetivo de meme_trades, R73) e financiamento com block_time < decisão (Helius); a guarda de chegada não se aplica ao oráculo) — causalidade é afirmação do operador, não do moinho

Outras ressalvas:

- sem fatia de teste reservada: o resultado é dentro da amostra

## Suposições numéricas declaradas

- desfecho = simulate_current do R72 (1,15×/10 %/300 s, 2,23 %, pouso +1,6 s)
- censura: buraco > 60 s até ao pouso; uma decisão por mint, real > papel > mais antiga
- patamar avaliado fora do moinho (grelha de quantis, partições distintas)

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.


# H-014 secundária — financiado_pelo_criador_pct — NÃO CONFIRMA

> Origem: perda real SIMFTR 23/09/2026 (73 vendedoras num slot)  ·  impressão digital do pré-registo: `2b3b12cce594`
> Limiar congelado: **0**  ·  efeito mínimo relevante (MRE): **+0.0500**

## Pré-registo (escrito antes de correr)

- **Previsão:** o tercil alto de rede_financiadora_pct rende menos −0,05 por SOL que o baixo (IC 95 % bootstrap por mint inteiramente abaixo de zero) e tem taxa de despejo coordenado ≥ 2× a do tercil baixo; patamar em dois limiares vizinhos; no contrafactual das reais, um teto bloqueia ≥ 3 das 6 piores e mata ≤ 20 % das vencedoras
- **Refutação:** limite superior do IC acima de −0,01 por SOL; ou a curva é pico e não patamar; ou o teto que bloqueia as piores mata > 30 % das vencedoras; ou financiador resolvido em < 60 % das compradoras pré-decisão (limite de dado, não resultado). ERRATA (Astra, antes do contraste): a cláusula (a) literal só não-confirma; refutação pelo intervalo = limite superior de D(baixo−alto) < +0,01
- **Regra de decisão:** moinho sobre os tercis extremos: CONFIRMA com D(baixo−alto)>0, D≥MRE 0,05, IC inferior>0, p<0,05, braço baixo lucrativo em nível, planalto; rótulo final pela regra das notas §0.4b-4
- **Política de limiar:** limiar = máximo do tercil baixo (quantil 1/3, empates juntos), fixado antes dos desfechos
- **Congelado em:** 2026-09-23

## Os números

| # | o quê | valor |
|---|---|---|
| 1 | população usada (de 238 linhas lidas) | **238** em 238 clusters |
| 2 | selecionados / resto no limiar congelado | 149 / 89 |
| 3 | média do desfecho: selecionados / resto | -0.0608 / -0.1087 |
| 4 | **D = média(selecionados) − média(resto)** | **+0.0479** |
| 5 | IC 95 % de D (bootstrap de cluster por `mint`) | [-0.0099, +0.1079]  P(D≤0) = 0.054 |
| 6 | IC 95 % de D (bootstrap de blocos) | [-0.0113, +0.1092] em 132 blocos |
| 7 | p de permutação (estratificada por `dia`) | 0.1042 |

Censura: 0 linhas sem desfecho, 0 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: NÃO CONFIRMA

- D = +0.0479 abaixo do MRE +0.0500
- IC 95 % inferior -0.0099 não está acima de zero
- p de permutação 0.1042 não é < 0,05
- o braço selecionado perde em nível (-0.0608); perder menos que o resto não é vantagem
- há dependência temporal declarada e o IC 95 % por blocos [-0.0113, +0.1092] cobre zero

## Curva de limiares — planalto ou pico?

Diagnóstico: **pico** (1 limiares avaliáveis; maior corrida positiva 1 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|
| 0 | 149/89 | +0.0479 | [-0.0099, +0.1079] |

## Baldes por tercis (descritivo, não decide nada)

| balde | n | média | mediana |
|---|---|---|---|
| -0 | 149 | -0.0608 | -0.1158 |
| 0-0.05 | 10 | -0.1048 | -0.0728 |
| 0.05-inf | 79 | -0.1092 | -0.1266 |

## A ressalva que mais importa

a guarda não correu (dispensa declarada: variável = compradoras com block_time < decisão (oráculo retrospetivo de meme_trades, R73) e financiamento com block_time < decisão (Helius); a guarda de chegada não se aplica ao oráculo) — causalidade é afirmação do operador, não do moinho

Outras ressalvas:

- sem fatia de teste reservada: o resultado é dentro da amostra

## Suposições numéricas declaradas

- desfecho = simulate_current do R72 (1,15×/10 %/300 s, 2,23 %, pouso +1,6 s)
- censura: buraco > 60 s até ao pouso; uma decisão por mint, real > papel > mais antiga
- patamar avaliado fora do moinho (grelha de quantis, partições distintas)

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.


Holm na família {primária, secundária}: p brutos [0.083, 0.1042] → Family(p=(0.08299170082991701, 0.10418958104189581), bh_threshold=(0.05, 0.1), bh_adjusted=(0.10418958104189581, 0.10418958104189581), bh_survives=(False, False), holm_adjusted=(0.16598340165983402, 0.16598340165983402), holm_survives=(False, False))

## 6. Patamar (população elegível inteira, direção low)

Grelha pedida: quantis [0.2, 0.25, 0.333, 0.4, 0.5] → limiares com partições distintas: [0.0, 0.0254, 0.0364]

| limiar (≤) | n sel | n resto | D (sel − resto) | IC 95 % |
|---:|---:|---:|---:|---|
| 0.0000 | 91 | 181 | +0.0409 | [-0.0107, +0.0926] |
| 0.0254 | 107 | 165 | +0.0503 | [-0.0009, +0.1016] |
| 0.0364 | 136 | 136 | +0.0310 | [-0.0197, +0.0830] |

Forma (regra do moinho): **pico** — 3 limiares avaliáveis; maior corrida positiva 3 (0 com IC acima de zero)

## 7. Contrafactual nas 95 decisões reais (cada uma no seu instante; PnL realizado)

Base: 95 posições, 29 vencedoras, PnL **-0.3870 SOL**. As 6 piores: `CITIZEN` -0.0573 (rede 0.6%, fita nasce False), `AIRAA` -0.0556 (rede 15.2%, fita nasce True), `SNORP` -0.0441 (rede 0.0%, fita nasce True), `YOU` -0.0395 (rede 0.0%, fita nasce True), `WAVECOREE` -0.0369 (rede 0.0%, fita nasce True), `SIMFTR` -0.0284 (rede 0.0%, fita nasce True).

| regra | bloqueia | das 6 piores | vencedoras mortas | Δ PnL |
|---|---:|---|---|---:|
| rede > 5% | 23 | 1 ['AIRAA'] | 7 de 29 (24%) ['WIFTIGRINO', 'ANT', 'WEENY', 'DOGPHIL', 'RESERVED', 'SENTHOS', 'MMKT'] | +0.0441 |
| rede > 10% | 12 | 1 ['AIRAA'] | 3 de 29 (10%) ['ANT', 'WEENY', 'RESERVED'] | +0.0634 |
| rede > 15% | 4 | 1 ['AIRAA'] | 2 de 29 (7%) ['WEENY', 'RESERVED'] | +0.0317 |
| rede > 20% | 1 | 0 [] | 1 de 29 (3%) ['WEENY'] | -0.0207 |
| rede > 30% | 0 | 0 [] | 0 de 29 (0%) [] | +0.0000 |
| criador > 0% | 39 | 2 ['AIRAA', 'YOU'] | 14 de 29 (48%) ['WIFTIGRINO', 'NOOP', 'PROCK', 'ANT', 'WEENY', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'TANK', 'RIGBY', 'SENTHOS', 'MMKT', 'EDEN'] | +0.0945 |
| criador > 5% | 31 | 2 ['AIRAA', 'YOU'] | 11 de 29 (38%) ['WIFTIGRINO', 'NOOP', 'ANT', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'RIGBY', 'SENTHOS', 'MMKT', 'EDEN'] | +0.1067 |
| criador > 10% | 25 | 2 ['AIRAA', 'YOU'] | 9 de 29 (31%) ['WIFTIGRINO', 'NOOP', 'DOGPHIL', 'Aura', 'Paidichi', 'PHIL67', 'SENTHOS', 'MMKT', 'EDEN'] | +0.1035 |

Sem valor (nenhuma compradora resolvida): 15. Sem fita desde o nascimento: 46 de 95 (valores dessas são exploratórios).

## 8. Proxy barato ao vivo (descritivo, fora do veredito)

n = 291 elegíveis. Alvo 1: tercil alto de rede (> 0.0520). Alvo 2: despejo coordenado.

| proxy | mediana | Spearman com rede | AUC tercil alto de rede | AUC despejo | AUC perda ≥ 50 % (sim) |
|---|---:|---:|---:|---:|---:|
| `p_buyers` | 44.000 | -0.092 | 0.305 | 0.515 | 0.409 |
| `p_holders` | 26.000 | -0.042 | 0.379 | 0.580 | 0.495 |
| `p_holders_frac` | 0.657 | +0.088 | 0.621 | 0.573 | 0.659 |
| `p_cv` | 1.248 | +0.122 | 0.559 | 0.463 | 0.478 |
| `p_drip_frac` | 0.472 | +0.130 | 0.557 | 0.352 | 0.419 |
| `p_bundle` | 2.000 | -0.104 | 0.444 | 0.641 | 0.519 |
| `p_bundle_sol` | 3.148 | +0.103 | 0.585 | 0.672 | 0.740 |
| `p_single_nosell_frac` | 0.606 | +0.030 | 0.588 | 0.569 | 0.614 |
| (a própria rede) | 0.036 | 1 | — | 0.468 | 0.581 |