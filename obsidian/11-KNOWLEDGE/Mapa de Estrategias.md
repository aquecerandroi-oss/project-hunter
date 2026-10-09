---
tags: [knowledge, indice, estrategias, mapa]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-28
---

# Mapa de Estratégias

Uma página, três estados, para toda ideia testada em meme ou cripto: **Vivas** (rodando ou em
teste agora), **Pistas** (inconclusiva mas com sinal que vale acompanhar) e **Cemitério** (refutada
ou não confirmada, com o porquê em uma linha e o número). Construída com consultas Dataview sobre o
frontmatter novo (`tipo`, `hipotese`, `veredito`, `efeito`, `mercado` — ver
[[_TEMPLATE-NOTE|_TEMPLATE-NOTE]] "como preencher") **e** uma tabela estática logo abaixo de cada
consulta, para quem lê sem o plugin instalado. As duas devem concordar; se divergirem, a tabela
estática é a mentirosa (foi editada e a nota não) — corrija a nota, nunca só a tabela.

> Requer o plugin **Dataview** (Everton confirmou instalado e ativo em 2026-09-25). Sem ele, os
> blocos ```dataview``` abaixo aparecem como texto puro — as tabelas estáticas continuam legíveis.

## Vivas — rodando ou coletando agora

```dataview
TABLE mercado AS "mercado", hipotese AS "hipótese", veredito AS "estado", proximo_passo AS "próximo passo"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "em_curso"
SORT mercado ASC, hipotese ASC
```

| item | mercado | o que é | estado em 2026-09-25 |
|---|---|---|---|
| [[Fila de Hipoteses#H-001 — Absorção de uma venda grande (EXP-M22)\|H-001]] — absorção de venda | meme | braços `absorb_v0/1` e `absorb_v0/2` em papel | **em_curso** — 14 apostas medidas em 23/09 (mínimo 20/lado); ficha de 25/09 mostra 72+84 entradas acumuladas nos dois braços, ainda sem novo julgamento ([[Ficha-2026-09-25]]) |
| [[Fila de Hipoteses#H-002 — Retenção dos primeiros compradores (EXP-M19)\|H-002]] — retenção dos primeiros 20 | meme | braço `flow_v2/10` | **em_curso** — 0 apostas no corte de 23/09; sem sinal de ter começado a produzir |
| [[Fila de Hipoteses#H-036 — `mean_reversion v14` em coorte futura, ao custo Binance medido (a v14 tem vantagem fora da amostra?)|H-036]] — `mean_reversion v14` em coorte futura ao custo medido | cripto (Lab/Shadow) | teste de nível pré-registrado, sinais emitidos desde T0 = 2026-10-07 12:00Z, custo todo a mercado medido no `market_snapshots` ([[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]]) | **coletando** — consultas fixas em 06/01, 07/04 e 07/07/2027; nada a ler antes; export cego semanal |
| `spot/1` (Jupiter/Binance, `mean_reversion v14`) | cripto | primeira mesa de cripto normal em dinheiro real (23/09) | viva — primeira posição real 25/09 11:30 BRT, `TAOUSDT`, alvo/stop declarados ([[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]) |
| mesa real de memes (`operator/5`, `operator/6`) | meme | operadores em produção | vivos — 148 operações acumuladas até 25/09, acumulado **−0,4707 SOL**, primeiro dia verde em 25/09 (+0,0356 até 12:00 BRT) |
| `mean_reversion v1/v2/v3/v6/v7/v8/v10` + `momentum v3` (paper) + `momentum v8` | cripto (Lab/Shadow) | roster do Shadow Lab depois da poda T3.56 (2026-09-09) | vivos na última leitura registrada (2026-09-09); **esta página não confirmou estado mais recente** — conferir [[Estratégias.base]] antes de citar como atual |
| [[Fila de Hipoteses#H-022 — Estrutura do gráfico em moedas maduras (15–120 min, ainda na curva)\|H-022]] — gráfico em moedas maduras | meme | três braços de papel `grafico_ctrl_v1/1`/`grafico_v1/1`/`grafico_v1/2` ([[EXP-M26-grafico-em-moedas-maduras]]) | **em construção** — desenho congelado 26/09 (decisão conjunta com a Astra); I1/I2/L1/R1/C1 no ar desde 27/09; **F não aprovado por instrumento em 01/10** (leitura de pedigree do minuto acima do corte de 8 s); nada semeado, nenhuma proposta |

## Pistas — inconclusivas, mas com sinal que vale acompanhar

Nada aqui é `CONFIRMA` (vocabulário de `docs/RESEARCH.md`) — é o que ficou de interessante depois de
uma hipótese fechar sem confirmar, e que só vira hipótese nova em população futura. Entra aqui também o
que parou por **limite de dado** sem sinal nenhum (a consulta lê `limite_de_dado`), como a H-021.

```dataview
TABLE mercado AS "mercado", hipotese AS "hipótese", efeito AS "efeito descritivo"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "limite_de_dado"
SORT mercado ASC
```

| pista | origem | o que apareceu | por que não é confirmação |
|---|---|---|---|
| Vender o primeiro repique e não voltar (alvo, não giro) | H-009 (nao_confirma) | +3,44 pp em 62 % das posições reais, contra a regra atual, no fragmento não condicionado ao futuro | virou hipótese própria (H-011) e **refutou** — o fragmento evapora quando testado sem olhar o resultado (−0,31 pp reais, +0,34 pp papel) — [[KB-0152-a-oscilacao-existe-o-giro-nao-paga]] → [[KB-0154-subir-o-alvo-nao-paga]] |
| `buys_1m ≤ 25` (fluxo baixo no minuto) | R65 → R67 | tercil favorável na amostra original (34 % de alvos, MFE +28,1 %) | **não confirmou fora da amostra**: 473 moedas independentes, D=+0,036, IC [−0,058,+0,136], p=0,43, curva **pico** — [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] |
| Percentil de `sells/buys` dentro da coorte viva (`p_sb`) | R69 → H-004 | sobrevivente isolado em família de 17 (p=0,014) | reproduziu (D=+0,106, p=0,0145) mas a curva é **pico**: só 1 de 7 limiares exclui zero — [[KB-0154-subir-o-alvo-nao-paga]] não se aplica aqui, ver [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] |
| Célula `P3_vol_surge`, h=120 (cripto) | R68 → H-003 | D=+0,25 % líquido, IC de cluster [+0,16 %,+0,34 %] (aperta) | IC de **permutação** é largo (p=0,1478) — carregado por poucas barras extremas — [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] |
| Longe da mínima de 24 h (`distance_from_24h_low`, cripto) | secundária da [[Fila de Hipoteses#H-023 — Proximidade da máxima de 24 h nos sinais do Lab de cripto (segunda frente, custo baixo)\|H-023]] (nao_confirma) | tercil longe − perto da mínima **+0,207 R** [+0,121,+0,284], Holm 0,0004, patamar 7/7, nos 9 187 sinais de continuação | sem sinal pré-registrado; o melhor tercil **perde −0,097 R** em nível; anda com ATR% (ρ 0,77) e retorno 4 h (0,70); só volta em coorte nova, com a feature no envelope e teste incremental conjunto — [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] |
| Rompimento do topo depois do teste da LTA diária (braço B, cripto à vista) | [[Fila de Hipoteses#H-026 — Linha de tendência de alta (LTA) diária em cripto grande: retorno na LTA (A) e rompimento do topo (B)\|H-026]] B (nao_confirma) | **+1,09 p.p.** por 10 d [−0,76; +2,89] contra as moedas do mesmo dia com LTA confirmada, Holm 0,22; patamar nas 3 tolerâncias e os dois períodos positivos | IC cruza zero; o controle não separa a linha de um rompimento de topo qualquer (momentum); H = 20 d (+3,72) é sensibilidade, não troca de horizonte; só volta em coorte prospectiva com contraste contra rompimento sem LTA — [[KB-0169-fibonacci-e-lta-diaria-no-dado]] |
| `mean_reversion` do Lab (v1–v14, um só conjunto de entradas com saídas diferentes) sob custo Binance real (cripto) | diagnóstico de custo, **não hipótese** ([[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]]) | única família bruto-positiva no prospectivo: +0,05 a +0,09 R, k* +6 a +19 bp; com taker 5 bp/perna (só taxa, custo assumido) as de custo em R menor (v6/v7/v10/v14) ficam em +0,02 a +0,04 R | IC por dia contém zero em todas; outubro negativo em todas; desfechos **expostos** — só uma coorte futura com pré-registro novo pode confirmar; a `momentum` e a `volume_anomaly` **não** são problema de custo (bruto ≤ 0 / ≈ 0) |
| Estrutura do gráfico na compra (distância do suporte, fundos mais altos, rompimento) | [[Fila de Hipoteses#H-021 — Estrutura do gráfico na hora da compra (distância do suporte, fundos mais altos, rompimento)\|H-021]] | **nada de desempenho** — desfechos não abertos; o achado é estrutural: a porta compra com 1,6 min de vida (`max_age_s = 300`), só 1 de 885 decisões tem 5 min de fita | **limite_de_dado** (estrutural): o bloco pede 150; o arquivo de trocas não reconstrói a estrutura; volta só como H-021b prospectiva com o preço marginal gravado na fita da decisão — [[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]] |

O que a literatura de análise gráfica diz que merece virar pista depois do EXP-M26 (três candidatas, nenhuma
registrada, e o que **não** vale testar): [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] e
[[Proximas Hipoteses]] (seção de 28/09).

## Cemitério — refutadas ou não confirmadas

Uma linha, o porquê, o número. `nao_confirma` = ignorância (não sabemos), nunca reaberta com o
mesmo desenho; `refuta` = evidência contra uma vantagem **desse tamanho** (docs/RESEARCH.md).

```dataview
TABLE mercado AS "mercado", veredito AS "veredito", efeito AS "número"
FROM "11-KNOWLEDGE" OR "05-EXPERIMENTS"
WHERE veredito = "refuta" OR veredito = "nao_confirma"
SORT veredito ASC, mercado ASC
```

### Meme

| hipótese | o que testou | veredito | número |
|---|---|---|---|
| [[Fila de Hipoteses#H-009 — Giro rápido na oscilação (comprar a queda, vender o repique, repetir)\|H-009]] | política de giro (comprar queda, vender repique, repetir) | **nao_confirma** | 0 de 12 células confirmam; melhor IC superior +0,103, previsão pedia +0,05 ([[KB-0152-a-oscilacao-existe-o-giro-nao-paga]]) |
| [[Fila de Hipoteses#H-011 — Onde deve ficar o alvo (vender o primeiro repique e não voltar)\|H-011]] | alvo diferente de 1,15× | **refuta** | melhor alvo 1,08× é a **borda** da grade; D=+3,05 pp reais mas 5 moedas concentram o ganho e inverte com a cobertura da fita ([[KB-0154-subir-o-alvo-nao-paga]]) |
| [[Fila de Hipoteses#H-012 — Tempo máximo curto ("o que não sobe logo não sobe mais")\|H-012]] | `max_hold` < 300 s | **refuta** | maior IC inferior −1,16 pp (reais); a 30 s cortam-se 14 de 23 vitórias reais ([[KB-0154-subir-o-alvo-nao-paga]]) |
| [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | financiador comum entre vendedoras do despejo | **nao_confirma** | D=+0,054, IC [−0,005,+0,116]; nos 4 casos de origem, rede 0–1,4 % ([[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]]) |
| [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] | SOL comprado no slot de criação como filtro | **refuta** | teto no tercil alto mataria **36,5 %** das vencedoras (limite 30 %) ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) |
| [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] | esperar recuo grande antes de comprar | **refuta** | maior IC inferior −3,60 pp; as moedas que não recuam são as vencedoras (X=12 %/W=20 s perde 25 de 30 vitórias reais) ([[KB-0157-esperar-o-recuo-nao-paga]]) |
| [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]] | recuo pequeno (3 %/60 s) como melhora do preço de entrada, braço `recuo_v1/1` contra o controle de entrada imediata `recuo_ctrl_v1/1` ([[EXP-M24-entrada-no-recuo]], [[EXP-M25-controle-do-recuo]]) | **nao_confirma** | 151 pares no papel: D=+0,0077, IC [−0,027,+0,041] (previa ≥ +2 pp); braço contra "nada" −0,0385 [−0,078,+0,002]; 74 de 124 entradas na mesma foto do controle; os braços podem ser aposentados ([[KB-0162-o-recuo-pequeno-empata-com-comprar-na-hora]]) |
| [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | prever `comprou_no_topo` pela forma do minuto | **refuta** | piso no tercil baixo mataria 34,7 % das vencedoras; sinal saiu ao contrário da tese ([[KB-0159-a-desaceleracao-nao-avisa-o-topo]]) |
| [[Fila de Hipoteses#H-020 — Identidade social reciclada (o mesmo X/Twitter em várias moedas)\|H-020]] | barrar moedas que reciclam o link de X/Twitter de outras das 24 h anteriores | **nao_confirma** | D=−0,0525, IC [−0,123,+0,016]; golpe 1,02× (previa 2×); filtro mataria 24,5 % das vencedoras reais; some com o que a base sabia em T ([[KB-0160-o-link-reciclado-nao-avisa-o-golpe]]) |
| [[Fila de Hipoteses#H-031 — Concentração do maior comprador no preenchimento (`top_buyer_share`) como aviso de golpe\|H-031]] | excluir a concentração do maior comprador (fatia do SOL da curva) | **nao_confirma** | `decision_tape` D_adj=−0,0023, IC [−0,043,+0,037]; `creator_dump` 2,11× no braço alto sem pior retorno ([[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]]); 07/10: a rota (2) do Defensor virou a **H-031b**, gêmeo de papel `absorb_semdump_v0/1` sem `creator_dump`, pré-registrada e aguardando deploy ([[EXP-M27-gemeo-sem-creator-dump]]) |
| [[Fila de Hipoteses#H-032 — Moeda Mayhem depois da entrada (o agente de SOL virtual muda o desfecho?)\|H-032]] | moeda Mayhem × não-Mayhem depois da entrada (a exclusão por padrão paga?), na sonda de recusadas | **nao_confirma** (instrumento) | papel D_adj=+0,535 [+0,48,+0,58] contra Mayhem, mas o teto de SOL real cortou 63 % das saídas Mayhem; nenhuma conclusão econômica sobre Mayhem; a mesa nunca comprou Mayhem e nada muda ([[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]]) |
| [[Fila de Hipoteses#H-034 — `holders_rising` e `progress_rising` isolados na hora da decisão (os dois "subindo" separam o retorno do papel?)\|H-034]] | `holders_rising` e `progress_rising` isolados, como a porta os gravou na decisão (a H-013 só tinha a conjunção) | **nao_confirma** | holders D_adj=+0,027, IC [−0,030,+0,085], braço verdadeiro perde em nível; progresso +0,133 [−0,041,+0,315] em 130 apostas; reais da `operator/5` +0,082 [−0,011,+0,173], descritivo ([[KB-0190-os-dois-subindo-nao-separam-o-retorno]]) |
| 13 variáveis de decisão (R65) | snipers, dev share, compradores únicos, progresso, fluxo do criador, idade, volume 1 m, sells/buys, holders, top10, retenção, carteiras novas, flip rápido | **nao_confirma** (todas) | nenhuma sobrevive Benjamini-Hochberg; p mais baixo 0,046 contra limiar 0,0077 ([[KB-0149-o-que-a-mesa-real-ensinou]] item 11) |
| Sniper de lançamento | entrar cedo no lançamento | **nao_confirma** (tratada como descartada) | 18/18 células negativas, não era latência ([[KB-0141-sniper-de-lancamento]]) |
| Rajada de compradores | pico súbito de compradores como gatilho | **nao_confirma** (tratada como descartada) | negativa em 54 células (R58/[[KB-0138-explosao-de-compradores-nao-tem-vantagem]]) |
| Seguir carteira vencedora | copiar quem já ganhou | **nao_confirma** (tratada como descartada) | não é gatilho (R57/KB-0136); piloto em papel pré-registrado em 09/10 ([[EXP-M28-copiar-carteiras-no-papel]], H-037) |
| `momentum v2/v4/v6/v10`, `volume_anomaly v2`, `session_orb v1`, `trendline_breakout v1` (Shadow Lab) | variantes de parâmetro/família | aposentadas | negativas em toda coorte que tiveram (T3.56, roster 16→9) |

### Cripto

| item | o que testou | veredito | número |
|---|---|---|---|
| [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] | 5 preditores em h∈{60,120,240} | **nao_confirma** | 0 de 15 células confirmam; menor Holm ajustado = 1,0000 |
| [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] | `p_sb` | **nao_confirma** | curva é pico: só 1 de 7 limiares exclui zero |
| [[Fila de Hipoteses#H-005 — Piso de impulso recente (momentum_15m ≤ 2,0)\|H-005]] | `momentum_15m ≤ 2,0` | **nao_confirma** | 0 sinais com a variável no envelope verbatim; braço selecionado perde em nível |
| [[Fila de Hipoteses#H-006 — Desequilíbrio agressor na barra do sinal\|H-006]] | `taker_imbalance_5m` | **nao_confirma** | D=+0,09 % líquido, 1 ponto-base abaixo do MRE de +0,10 % |
| [[Fila de Hipoteses#H-007 — Teto de volume relativo (exaustão)\|H-007]] | teto de `volume_ratio_5m` em 12 | **refuta** | limite superior do IC (+0,0155) abaixo do MRE de +0,10 R |
| [[Fila de Hipoteses#H-023 — Proximidade da máxima de 24 h nos sinais do Lab de cripto (segunda frente, custo baixo)\|H-023]] | perto da máxima de 24 h nos sinais de continuação do Lab (`distance_from_24h_high`, tercis) | **nao_confirma** | D=−0,032 R, IC [−0,113,+0,038] em 9 187 sinais; curva sem nenhum corte positivo; momentum +0,097 × volume_anomaly −0,231 (descritivo) ([[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]) |
| [[Fila de Hipoteses#H-024 — Momentum semanal de série temporal em cripto grande (à vista, só compra)\|H-024]] | momentum semanal de série temporal, só compra, à vista: top-20 da Binance por volume com deslistados, fica nas moedas de retorno de 14 d > 0 e o resto em caixa, contra a mesma cesta sempre comprada (secundária: terço de maior retorno) | **nao_confirma** | 395 semanas 2019–2026: D_ts **+0,14 p.p./sem [−0,50; +0,86]** (previa ≥ +0,25); patamar 7 d negativo, antes de 2022 negativo; D_cs +0,35 [−0,08; +0,70] é pico (7 e 28 d negativos); BTC comprado-e-segurado (bruto) teve Sharpe 0,98 contra 0,59 da regra ([[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]) |
| [[Fila de Hipoteses#H-025 — Retração de Fibonacci (50–61,8 %) em cripto grande no diário (à vista, só compra)\|H-025]] | comprar o 1.º fechamento na retração de 50–61,8 % da última perna de alta confirmada (pivô k = 5), top-20 à vista da Binance, 10 d, contra as moedas do mesmo dia sem recuo; secundária com alvo 1,618 e stop abaixo do fundo | **nao_confirma** | 360 eventos 2019–2026: D **+0,69 p.p. [−1,43; +2,95]** (previa ≥ +1,0); vizinhas 45 % e 55 % negativas (pico); Fibonacci não especial (+1,28 [−0,11; +2,63] sobre as vizinhas); estrutural +0,18 [−3,17; +3,59] ([[KB-0169-fibonacci-e-lta-diaria-no-dado]]) |
| [[Fila de Hipoteses#H-026 — Linha de tendência de alta (LTA) diária em cripto grande: retorno na LTA (A) e rompimento do topo (B)\|H-026]] A | comprar o toque (3.º ou depois) numa LTA diária confirmada, contra as moedas do mesmo dia com LTA confirmada longe da linha | **refuta** | 1 529 eventos: D **−1,09 p.p. [−2,08; −0,02]**, negativo nas 3 tolerâncias, nos dois períodos e em todos os blocos; o mesmo repique perdeu no 15 min ([[EXP-0016-trendline-breakout]]) ([[KB-0169-fibonacci-e-lta-diaria-no-dado]]) |
| [[Fila de Hipoteses#H-027 — Tendência diária (razão à média de 20 dias) como estado dos sinais de continuação do Lab de cripto\|H-027]] | razão à média de 20 fechamentos diários como estado dos sinais de continuação do Lab, teste incremental conjunto com `distance_from_24h_low`, ATR% e retorno 4 h (análise **retrospectiva**; coorte futura não feita) | **nao_confirma** (momentum **refuta** o tamanho) | momentum, 874 unidades em 16 mercados: β **−0,026 R/desvio [−0,083; +0,029]** (dia), [−0,072; +0,014] (mercado), previa ≥ +0,05; os dois grupos perdem −0,19 R; com FE de dia o IC sup chega a +0,058; volume_anomaly limite de dado ([[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]]) |
| [[Fila de Hipoteses#H-029 — Carry de funding protegido (à vista comprado + perpétuo USDT-M vendido, Binance, top-20)\|H-029]] | carry de funding protegido: à vista comprado + perpétuo USDT-M vendido a 1× no top-20 da Binance com deslistados, semanal, três braços (sempre ligado; entra com funding de 7 d ≥ 0,125 %; excepcional ≥ 0,65 %) | **nao_confirma** (A2 limite de dado) | 340 semanas 2020–2026: A1 **+5,3 a +5,9 % a.a.** sobre o capital, Holm 0,15–0,175; antes de 2023 +11,6 %, **desde 2023 +0,6 %**; A0 −4,4 % desde 2023; sem 2021 o A1 dá +1,4 % ([[KB-0181-carry-de-funding-no-dado]]) |
| [[Fila de Hipoteses#H-033 — Open interest em nível (lotação relativa à própria semana) como estado dos sinais de continuação do Lab de cripto\|H-033]] | open interest relativo à mediana semanal (`open_interest_history`, folga de 15 min) como estado dos sinais de continuação do Lab, teste incremental conjunto com `distance_from_24h_low`, ATR% e retorno 4 h (análise **retrospectiva**, condicionada à folga) | **nao_confirma** (momentum não confirma; volume_anomaly limite de dado) | 869 unidades da momentum v3: β +0,003 R/desvio, IC dia [−0,047; +0,059], mercado [−0,038; +0,035] — o +0,05 previsto não fica excluído no IC de dia; grupo "menos lotado" −0,25 R ([[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]]) |
| `return_4h > 0` como gate de tendência | redundância lógica com a própria entrada | descartada antes de testar | gate não filtraria nada, exceto por indisponibilidade da feature ([[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]]) |
| `orderbook_imbalance_20 ≥ 0` como filtro de book | profundidade do livro | descartada antes de testar | a feature é razão invariante a escala, não mede profundidade ([[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]]) |
| Funding como filtro direcional de entrada | funding prevê retorno | nunca entrou na fila | evidência direta aponta poder preditivo ~zero por ativo ([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]) |
| `derivatives_v1` (reversão de funding, Shadow Lab) | comprar depois de funding liquidado negativo | morreu na pré-checagem | 5 liquidações negativas em 31 d × 4 mercados; módulo nunca escrito |
| Escalar exposição pelo inverso da volatilidade (Barroso & Santa-Clara) | vol-scaling | adiada, não testada | o Shadow Lab não dimensiona posição; PnL de carteira não aplicável |

## Fontes e como manter isto atualizado

O que alimenta as consultas Dataview é o frontmatter de cada nota — `tipo`, `hipotese`, `veredito`,
`efeito`, `ic`, `proximo_passo`, `mercado` (ver [[_TEMPLATE-NOTE]]). Ao fechar uma hipótese nova:

1. Escreva o veredito na [[Fila de Hipoteses]] (campo já existente, não mexer no que já está lá).
2. Escreva/atualize a nota `KB-0xxx` correspondente com o frontmatter completo.
3. **Não edite esta página à mão para mover uma linha entre seções** — edite o `veredito` da nota;
   as consultas Dataview já refletem a mudança. As tabelas estáticas abaixo de cada consulta são
   para quem lê sem o plugin, e devem ser atualizadas juntas para não divergirem.

## Relacionado

[[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Proximas Hipoteses]] · [[Strategy Backlog]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0168-fibonacci-elliott-e-lta-diaria]] · [[KB-0169-fibonacci-e-lta-diaria-no-dado]] ·
[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] · [[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]] · [[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]] · [[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]] · [[Perdas/Index|Perdas]] · [[Estratégias.base]] ·
[[Experimentos.base]] · `docs/RESEARCH.md`
