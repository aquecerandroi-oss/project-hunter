---
tags: [knowledge, leitura, cripto, tendencia, media-movel, filtro, comprar-e-segurar, serie-temporal, hipotese]
tema: "o que o filtro de tendência diário entrega de fato nos estudos com custo e fora da amostra — corta queda e risco, quase não acrescenta retorno nas altas; e o momentum de série temporal se parece com 'estar comprado quando a média histórica é positiva'"
fonte: "Deprez & Frömmel, 'Are simple technical trading rules profitable in bitcoin markets?' (International Review of Economics & Finance, 2024 — versão de autor de 01/05/2024 no repositório da Universidade de Ghent, lida na íntegra); Huang, Li, Wang & Zhou, 'Time series momentum: Is it there?' (JFE 135, 2020 — só o resumo, RePEc); Moskowitz, Ooi & Pedersen, 'Time series momentum' (JFE 104, 2012 — só o resumo); e a medição própria KB-0166 (H-024)"
fonte_url: https://biblio.ugent.be/publication/01HY3C3S169G1N6QNYR55NZMFB · https://doi.org/10.1016/j.iref.2024.05.003 · https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html · https://doi.org/10.1016/j.jfineco.2011.11.003
lido_em: 2026-10-01
evidencia: "mista — um estudo revisado lido na íntegra em versão de autor (Deprez & Frömmel), dois estudos revisados só pelo resumo (Huang et al.; Moskowitz et al.), e uma medição nossa já publicada (KB-0166)"
hipotese_testavel: não
astra: "discorda em parte — revisada junto da síntese KB-0179; as correções que atingem esta nota foram aceitas (ver KB-0179 §Segunda opinião)"
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: "?"
tipo: leitura
hipotese: H-027
variavel: razao_mm20d (contexto; nenhuma medição aqui)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "nenhum; alimenta a leitura do resultado da H-027 em KB-0179"
classe_de_perda: —
mercado: cripto
---

# KB-0174 — O filtro de tendência corta queda; não acrescenta alta

> **Leitura curada + uma medição nossa já publicada.** No estudo mais rigoroso que achei sobre regras técnicas
> simples no BTC (Deprez & Frömmel: 75.360 regras, custo, seleção por taxa de descobertas falsas, fora da amostra
> 2014–2021), o que sobra é **redução de queda e de risco**, não retorno a mais: as carteiras de regras **não**
> batem comprar e segurar em retorno de forma significativa, empatam nas altas e só se destacam nas quedas. Isso
> é coerente com o nosso [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta|H-024]] (sair para o caixa nas moedas
> em queda não bateu a cesta de forma confirmável — IC que ainda não exclui o MRE; segurar BTC foi melhor) e com Huang et al. (o momentum de série temporal rende quase o
> mesmo que uma regra que só olha a média histórica). **Para a C1 isso importa:** o canal pelo qual a tendência
> diária "funciona" na literatura é **ficar fora nas quedas**, e a H-027 só enxerga esse canal se os sinais com
> razão ≤ 0 perderem mais que os outros.

## O que afirma

1. **Deprez & Frömmel (lido inteiro, versão de autor).** BTC/USD na Bitstamp, 2012–2022, quatro frequências
   (diária e três intradiárias), seis classes de regra (média móvel, filtro, suporte/resistência, canal, OBV,
   RSI), só compra ou caixa. A cada mês escolhem as melhores regras do ano anterior **depois do custo** (custo
   médio de cerca de 0,14 p.p. por operação, com o spread do livro) e as seguram no mês seguinte — 2.922 dias fora
   da amostra (2014–2021).
   - Retorno: as carteiras rendem um pouco mais que comprar e segurar, **sem significância**; a melhor regra
     precisa de menos de 0,05 p.p. a mais de custo para empatar com o benchmark.
   - Risco: queda máxima, VaR e assimetria melhores; por isso batem o benchmark em medidas de risco-retorno.
   - Só 1,68 % das regras (retorno) e 2,95 % (Sharpe), em média, superavam o benchmark **dentro** da amostra.
   - Subperíodos de 2 anos: nas quedas (2014–15, 2018–19) todas as carteiras superam o benchmark (sem
     significância depois da correção de mineração); nas altas (2016–17, 2020–21), no máximo empatam. Em 2018–19
     a maioria só **perdeu menos**.
   - Intradiário rende mais que diário antes de custo, mas o diário é muito mais robusto a um aumento de custo.
   - O desempenho das regras muda com o tempo (as classes vencedoras trocam de período a período).
2. **Huang et al. (só o resumo).** Nos 55 ativos de Moskowitz et al., a regressão ativo por ativo quase não mostra
   momentum de série temporal; o t grande da regressão empilhada não passa dos valores críticos de bootstrap; e a
   estratégia rende praticamente o mesmo que uma regra baseada na **média histórica** do ativo, que não exige
   previsibilidade.
3. **Moskowitz, Ooi & Pedersen (só o resumo).** Momentum de série temporal de 1–12 meses em 58 futuros líquidos,
   com reversão parcial depois; a carteira diversificada vai melhor nos **mercados extremos**.
4. **Nossa medição (KB-0166).** Top-20 da Binance à vista, 2019–2026, com deslistados: D = +0,14 p.p./semana
   [−0,50; +0,86] contra a cesta, metade da exposição, queda máxima −71 % contra −96 %; BTC comprado rendeu mais
   que as duas.

## Onde foi mostrado

Diário e intradiário no BTC (Deprez & Frömmel); futuros mensais (Moskowitz; Huang); top-20 à vista semanal
(nossa). O padrão comum: **o valor econômico da tendência aparece como gestão de exposição** (sair nas quedas),
e o retorno a mais, quando existe, é pequeno e instável.

## Como mediríamos aqui

Não há medida nova — é chave de leitura da H-027 ([[Fila de Hipoteses]]):

- O mecanismo "cortar queda" vira, nos sinais do Lab, **"os sinais com razão ≤ 0 perdem mais"**. A H-027 testa a
  inclinação contínua de `razao_mm20d`; a secundária (grupo > 0 contra ≤ 0) e as médias brutas dos dois grupos
  são onde esse canal aparece.
- **Nível × diferença × benchmark são três coisas.** Lucrar em nível não é bater comprar e segurar: na própria
  H-024 a regra lucrou em nível e o ganho incremental não confirmou (e o IC não excluiu o MRE — não é prova de que
  "só corta queda"). Na H-027, a cláusula "grupo favorável lucrativo em nível" é uma exigência pontual; um grupo
  > 0 que perca menos e ainda perca é compatível com esta literatura, e um que lucre também é — só não demonstra
  alfa (correção da Astra, [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]]).

## Por que pode falhar (como transposição)

- O filtro da literatura decide a **posição inteira** por dias; a C1 só condiciona entradas que já passaram pelo
  gatilho da estratégia. Um estado diário ruim pode já estar refletido no ATR% e no `return_4h` (covariáveis da
  H-027).
- Huang et al. e Moskowitz et al. são mensais e multiativo, lidos só pelo resumo.
- A amostra de Deprez & Frömmel termina em 2021; não sei como as regras foram em 2022–2026.

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] ·
[[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] · [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] ·
[[Fila de Hipoteses]]
