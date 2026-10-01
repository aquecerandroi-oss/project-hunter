---
tags: [knowledge, leitura, cripto, tendencia, media-movel, serie-temporal, diario, hipotese]
tema: "tendência diária em cripto (razão preço/média móvel, canal, momentum de série temporal) — que tamanho de efeito a literatura publica, em que amostra, com que custo, e quanto disso sobrevive fora da amostra; a base de evidência por trás da C1/H-027"
fonte: "Detzel, Liu, Strauss, Zhou & Zhu (Financial Management 50, 2021 — só o resumo); Zarattini, Pagani & Barbon (SSRN 5209907, 2025, preprint — só o resumo e o desenho descrito pela CXO Advisory); Fieberg, Liedtke, Poddig, Walker & Zaremba (JFQA 60, 2025 — só o resumo); Rozario, Holt, West & Ng (arXiv 2009.12155, 2020, preprint — lido na íntegra); e, já curados na base, Hudson & Urquhart 2021, Grobys, Ahmed & Sapkota 2020, Gerritsen et al. 2020 (KB-0167) e Liu & Tsyvinski NBER 2018 (KB-0164)"
fonte_url: https://doi.org/10.1111/fima.12310 · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907 · https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/ · https://doi.org/10.1017/S0022109024000747 · https://arxiv.org/abs/2009.12155
lido_em: 2026-10-01
evidencia: "mista — resumos de estudos revisados (Detzel et al.; Fieberg et al.), resumo de um preprint com backtest do autor (Zarattini et al.), um preprint lido na íntegra sem custo e com parâmetros otimizados (Rozario et al.), e números de estudos revisados já conferidos em KB-0164/KB-0167; nenhuma medição nossa"
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

# KB-0173 — Tendência diária em cripto: o tamanho publicado

> **Leitura curada, sem medição nossa.** A literatura sobre tendência diária em cripto mostra efeito **bruto**
> grande até 2017–2018, quase sempre como estratégia de **estar dentro ou fora** de uma moeda (não como filtro de
> sinais de horas), medido contra comprar e segurar, com custo tratado como custo de equilíbrio ou ignorado. O que
> há depois de 2020 com custo é **backtest do autor** num preprint (Zarattini et al.) ou fator transversal com
> aprendizado de máquina (Fieberg et al.). Nenhum estudo que achei mede o que a [[Fila de Hipoteses|H-027]] mede:
> a expectativa de um sinal de continuação de 5–15 min **condicionada** ao estado diário.

## O que afirma (claim × evidência, estudo por estudo)

| estudo | o que afirma | evidência que eu vi | custo | amostra |
|---|---|---|---|---|
| Detzel et al. 2021 | razões preço/média móvel (5–100 d) preveem o retorno **diário** do BTC dentro e fora da amostra; estratégias com essas razões dão alfa e ganho de Sharpe contra comprar e segurar | **só o resumo** (Semantic Scholar/Wiley); o texto não abriu (SSRN 403) | o resumo não fala de custo | BTC; segundo a revisão de Deprez & Frömmel ([[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]), dados até 2018 e desempenho melhor antes de 2014 — leitura de segunda mão |
| Hudson & Urquhart 2021 | ~15 mil regras, cinco classes, todas com previsibilidade; custo de equilíbrio alto | já conferido em [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]: média móvel no CoinDesk 54,86 bps, 32,04 % das regras acima de 50 bps; **a melhor regra do BTC perdeu fora da amostra (1.º sem. 2018)** | custo de equilíbrio | BTC, LTC, XRP, ETH até 2017 |
| Grobys, Ahmed & Sapkota 2020 | média móvel de 20 dias, só compra, bate comprar e segurar | KB-0167: 45,63 % a.a. contra 36,87 % nas 10 moedas sem o BTC (+8,76 p.p.), bruto | nenhum | 11 maiores, 2016–2018 |
| Gerritsen et al. 2020 | rompimento de faixa de 50–200 d acima de comprar e segurar; médias móveis quase nunca diferentes | KB-0167 | nenhum | BTC 2011–2019 |
| Liu & Tsyvinski (NBER 2018) | momentum de série temporal forte no **semanal**; no **diário** o coeficiente de 1 dia não passa no bootstrap | [[KB-0164-momentum-semanal-em-cripto-grande]] (t 1,22 com bootstrap no diário) | nenhum | BTC 2011–05/2018 |
| Zarattini, Pagani & Barbon 2025 | conjunto de canais de Donchian de 5 a 360 dias, alvo de volatilidade, carteira rotativa das 20 mais líquidas: Sharpe acima de 1,5 e alfa de 10,8 % a.a. contra o BTC, **líquido de taxa** | **só o resumo** (via índice do buscador; SSRN devolveu 403) e o desenho descrito pela CXO (taxas de 0,10/0,25/0,50 %, alvo de 25 % de volatilidade, universo sem sobrevivência desde 2015) | sim, no backtest do autor | todas as criptos desde 2015 com volume mínimo; até mar/2025 |
| Fieberg et al. 2025 (CTREND) | um fator de tendência que agrega preço e volume em vários horizontes, por aprendizado de máquina, prevê o **corte transversal** de mais de 3.000 moedas; robusto a subperíodos, estados de mercado e custo | **só o resumo** (OpenAlex; o PDF aberto da Cambridge devolveu 429) | o resumo diz que sobrevive | >3.000 moedas |
| Rozario et al. 2020 (arXiv) | seguir tendência no BTC rende 255 % a.a. em "walk-forward" | lido inteiro: janelas **otimizadas para o Sharpe** a cada fatia de 1 ano, custo, spread e derrapagem assumidos **desprezíveis**; os próprios autores dizem que pequenas perturbações em torno do ótimo mudam muito o Sharpe | não | BTC/USD Bitstamp, set/2011–dez/2019, barras horárias |

## Onde foi mostrado — o que isso diz e o que não diz

- **Mercado/horizonte:** BTC e as maiores, **diário**, posição de dias a semanas; a "tendência" é a própria
  regra de entrada e saída. Na C1 a tendência é um **estado** sobre sinais que duram no máximo 4 h
  (`horizon_s` 14 400 da `momentum_v1`) com 1 R = 1,5 ATR de 15 min.
- **Regime:** quase toda a evidência favorável vem de 2011–2018, um período com duas bolhas e uma queda de mais
  de 80 %; o único resultado líquido depois de 2020 (Zarattini et al.) é preprint com backtest do autor, carteira
  com alvo de volatilidade e nove janelas — não a razão de 20 dias isolada.
- **Custo:** os estudos revisados que olham custo usam custo de **equilíbrio** de regras diárias que trocam
  de posição poucas vezes por ano; o nosso pedágio é por operação de horas (~20 bps ida e volta,
  [[KB-0076-por-que-perdemos-2026-09-08]]). As bases não são comparáveis sem conta própria.
- **Escala:** a fração de bons resultados num universo de milhares de regras diz pouco sobre **uma** regra
  pré-escolhida — ver [[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]].

## Como mediríamos aqui

Já pré-registrado como H-027 na [[Fila de Hipoteses]] (não editada por esta nota): `razao_mm20d` do último dia
UTC fechado, contínua, no modelo conjunto com `distance_from_24h_low`, ATR% e `return_4h`, por estratégia,
coorte prospectiva até 01/10/2026 (análise retrospectiva pré-especificada, pela emenda). O que esta leitura
acrescenta é uma **ilustração**: só o canal da deriva diária, convertido para um sinal de horas e para R, tende a
centésimos de R sob hipóteses declaradas — o que **não** é tamanho esperado nem teto do β ajustado (correção da
Astra; a conta e seus limites estão em [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]]).

## Por que pode falhar (como evidência para a C1)

- **Objeto diferente.** Estar dentro/fora por dias ≠ filtrar entradas de 15 min; a literatura não testa a
  transferência.
- **Decaimento** (BTC fora da amostra em 2018; [[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]]).
- **Resultado favorável = resumo ou preprint.** Detzel, Zarattini e Fieberg só pelo resumo; Rozario et al. é o
  exemplo do que não fazer (otimização sem custo).
- **Sobrevivência:** Hudson & Urquhart e Grobys et al. usam as moedas que já eram grandes; só Zarattini et al.
  declara universo sem sobrevivência, e não li o texto.

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0164-momentum-semanal-em-cripto-grande]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] ·
[[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] · [[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] ·
[[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] · [[Fila de Hipoteses]] · [[Strategy Backlog]]
