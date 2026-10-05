---
tags: [knowledge, leitura, perpetuos, funding, carry, basis, binance, hipotese]
tema: "carry de funding protegido (comprar à vista e vender o perpétuo do mesmo ativo na Binance para receber o funding): mecânica da liquidação, rentabilidade líquida publicada, encolhimento com o tempo e riscos de cauda (basis, liquidação da perna vendida, corretora/moeda estável)"
fonte: "He, Manela, Ross & von Wachter, 'Fundamentals of Perpetual Futures' (arXiv 2212.06888v5, jun/2024 — texto integral em HTML, tabelas 5 e 8 lidas); Schmeling, Schrimpf & Todorov, 'Crypto carry' (BIS WP 1087 — só os dois resumos, bis.org e RePEc); Binance — fórmula e juros já lidos em KB-0019 (documentação de 06/09/2026) e cadastro público `fapi/v1/fundingInfo` consultado em 05/10/2026; Gornall, Rinaldi & Xiao só pelo que KB-0021 registra (SSRN bloqueado ao robô)"
fonte_url: https://arxiv.org/html/2212.06888v5 · https://www.bis.org/publ/work1087.htm · https://ideas.repec.org/p/bis/biswps/1087.html · https://fapi.binance.com/fapi/v1/fundingInfo
lido_em: 2026-10-05
evidencia: "backtest do autor (He et al., cinco moedas, Binance, horário, 2020–2024) e resumo de working paper (BIS); cadastro da corretora consultado ao vivo; nenhuma medição nossa nesta nota (a medição está em KB-0181)"
hipotese_testavel: sim
astra: "propôs a ideia (n.º 1 em astra-review-astra-ideias-estrategias) e revisou o pré-registro: 7 must-fix aceitos como emenda antes do run (H-029-carry-prereg)"
status: vivo
owner: sexta-feira
updated: 2026-10-05
confiança: backtest do autor
tipo: leitura
hipotese: H-029
variavel: S7 (soma do funding liquidado de 7 dias) — contexto; nenhuma medição aqui
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "resultado do teste em [[KB-0181-carry-de-funding-no-dado]]"
classe_de_perda: —
mercado: cripto
---

# KB-0180 — Carry de funding: o que a literatura e a corretora dizem

> **Leitura curada, sem medição nossa.** O carry protegido recebe um pagamento contratual (o funding) com risco
> de preço quase zero — mas a literatura mostra que, na estratégia que deu Sharpe alto, **o funding é a parte
> menor e variável do retorno** (a maior é convergência de preço em horas) — **a parte do funding na estratégia
> deles** foi negativa no BTC em 2022–2023 e voltou a +6 % em 2024 (no mercado, a soma do funding do BTC foi +4,2 % e
> +7,9 % do nocional em 2022 e 2023, dado do R87) —, e que o capital que faz esse lado é escasso justamente porque
> **margem e liquidação o punem nas quedas e nos repiques**. Para nós, com ida e volta de 0,50 % do nocional e capital dobrado pela
> margem a 1×, o funding-base de 0,01 %/8 h rende ~5 % a.a. bruto sobre o capital total. Testado na
> [[Fila de Hipoteses#H-029 — Carry de funding protegido (à vista comprado + perpétuo USDT-M vendido, Binance, top-20)\|H-029]].

## Mecânica na Binance (o que importa para a conta)

- **Fórmula** (documentação lida em [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]): F = P + clamp(I − P,
  ±0,05 %), com P o índice de prêmio médio do período (preços de impacto amostrados a cada 5 s) e I = juros de
  **0,01 % por 8 h**. Quando o prêmio fica na faixa morta, a taxa é **exatamente 0,01 %/8 h** — o "funding-base".
  Anualizado sobre o **nocional**: 0,01 % × 3 × 365 ≈ 10,95 %; sobre o **capital total** de um carry a 1× (metade
  à vista, metade de margem): ≈ 5,5 % a.a. bruto.
- **Cadência e tetos hoje** (`fapi/v1/fundingInfo`, 05/10/2026, 801 contratos): **467 em 4 h, 333 em 8 h, 1 em
  1 h**; teto/piso ±2 % por liquidação em 706 contratos e ±0,30 % no BTC e no ETH. A cadência **muda por contrato
  ao longo do tempo** — somar "funding de 7 dias" é independente da cadência; supor 8 h fixo inventa ou esconde
  cobranças ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
- **Quem recebe:** só quem tem posição **no instante** da liquidação (a corretora processa com segundos de atraso).
  Entrar logo depois de 00:00 perde a liquidação de 00:00; sair logo depois a recebe. Essa fronteira mexe no
  resultado de operações curtas — a H-029 a congelou nas duas convenções.
- **Funding não é previsão** ([[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]],
  [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]): é o preço que equilibra demanda alavancada e
  capital de arbitragem. O carry não aposta em direção; aposta em **persistência** do pagamento.

## O que a literatura afirma (claim × evidência)

1. **He, Manela, Ross & von Wachter (v5, jun/2024)** — BTC, ETH, BNB, DOGE, ADA; preços de hora em hora e funding
   liquidado da Binance desde o início de cada perpétuo até 2024. Derivam limites de não-arbitragem com custo e
   uma estratégia "de vencimento aleatório" que abre quando o desvio passa do limite e fecha na convergência.
   Sharpe anual no custo "alto": BTC 1,80 (retorno 6,38 % a.a.), ETH 2,55 (9,59 %), BNB 4,84, DOGE 3,58, ADA 2,68
   (tabela 5). **Decomposição (tabela 8): a convergência de preço domina; o funding é menor e cai** — na estratégia
   deles (não é o funding do mercado), no BTC o funding contribuiu 7,68 % (2020), 15,31 % (2021), **−1,94 % (2022)**, **−0,94 % (2023)** e 6,03 % (2024) a.a.;
   no ETH 13,35 / 17,59 / −0,53 / −0,24 / 6,97. O custo "alto" deles é 6,75 bps à vista e 1,44 bps no perpétuo —
   **bem abaixo** da tarifa taker de varejo (0,10 % e 0,05 %) que usamos. Citação curta do resumo: *"These
   deviations comove across cryptocurrencies and diminish over time as crypto markets develop and become more
   efficient."*
2. **Schmeling, Schrimpf & Todorov (BIS WP 1087)** — o carry futuro − à vista pode chegar a **60 % a.a.** (resumo
   em bis.org; a versão RePEc diz "às vezes acima de 40 %"), varia muito no tempo e vem de (i) investidores
   menores perseguindo tendência com alavancagem e (ii) **capital de arbitragem escasso**, porque fazer o
   *cash-and-carry* "é arriscado por causa de picos de margem e liquidações nas quedas" (paráfrase do resumo).
   Só o resumo foi lido; os números de retorno da estratégia não foram conferidos.
3. **Gornall, Rinaldi & Xiao** — só pelo registro de [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]]:
   o desenho do perpétuo (pagamentos pequenos e frequentes) existe porque capital de arbitragem restrito e demanda
   volátil afastam o perpétuo do à vista. Página do SSRN bloqueada ao robô em 05/10.

## Síntese própria (o que pode matar o carry para nós)

- **Capital parado e margem:** o lucro tem de ser medido sobre **todo** o capital (à vista + margem + vagas
  desligadas), não sobre a margem. A 1× isso corta o retorno pela metade antes de qualquer custo.
- **Custo de ida e volta:** 0,50 % do nocional (0,15 %/lado à vista + 0,10 %/lado no perpétuo) = ~2,4 semanas de
  funding-base. Carry que entra e sai toda semana não se paga; só a posse longa paga.
- **Regime:** os dois estudos dizem que o carry alto é de fase de euforia e varia muito no tempo; na estratégia de
  He et al. a parte do funding ficou negativa em 2022–2023 e voltou em 2024. "Anualizar o funding excepcional" é o
  falso positivo que a Astra apontou. (No nosso dado, o carry ingênuo do top-20 recebeu funding negativo em 2023,
  2025 e 2026 por causa de algumas moedas com shorts lotados — [[KB-0181-carry-de-funding-no-dado]].)
- **Basis e liquidação:** o perpétuo não converge por vencimento (He et al.); um repique de +90 % numa semana
  liquida a perna vendida a 1× e deixa a comprada descoberta; o preço de **marca** governa a liquidação, não o
  último negociado.
- **Riscos não modelados em nenhum teste nosso:** quebra/congelamento da corretora, perda de paridade da moeda
  estável em que as duas pernas e a margem estão, mudança de regra de funding pela corretora.
- **Encolhimento (crowding):** desvios menores com o tempo (He et al.) — se houver vantagem, ela deve ser menor no
  trecho recente; por isso a H-029 exige sinal dos dois lados de 2023-01-01.

## Relacionados

[[KB-0181-carry-de-funding-no-dado]] (o teste) · [[Fila de Hipoteses]] (H-029) ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] · [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] · [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[Strategy Backlog]] (item 13 é outro objeto: prêmio contra
índice, só observação) · [[06-DECISIONS/Revisoes-Astra/H-029-carry-prereg|H-029-carry-prereg]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] §5
