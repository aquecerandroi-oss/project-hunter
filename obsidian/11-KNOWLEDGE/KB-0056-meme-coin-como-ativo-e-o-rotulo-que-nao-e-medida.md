---
tags: [knowledge, nota, memecoins]
tema: meme coins / definição e método
fonte: Mancino, "The Memecoin Phenomenon" (arXiv 2512.11850); Xiang et al., "Measuring Memecoin Fragility" (arXiv 2512.00377); universo monitorado da VPS
fonte_url: https://arxiv.org/abs/2512.11850 · https://arxiv.org/abs/2512.00377
lido_em: 2026-09-06
evidencia: preprint (dois) + medição própria
hipotese_testavel: sim
astra: pendente
---

# Meme coin como ativo — e o rótulo que não é uma medida

## O que afirma

Uma meme coin é um ativo cuja **origem e tração são culturais**, e cujo preço é atenção precificada.
A literatura aberta que eu consegui ler trata disso **na cadeia** (criação de token, concentração de
carteiras, difusão social) e **não** no perpétuo de corretora centralizada, que é o único lugar onde
o nosso Lab enxerga.

**Correção da minha primeira definição, exigida pela revisão da Astra.** Eu tinha escrito "sem
fluxo de caixa, protocolo com receita nem utilidade declarada". Isso é **falso como critério
universal** e ela apontou os contraexemplos dentro da minha própria lista: a página oficial do
[Dogecoin](https://dogecoin.com/) declara finalidade de moeda e pagamentos; a do
[FLOKI](https://floki.com/) declara utilidade em jogos e DeFi. São memes pela origem cultural, não
pela ausência de utilidade declarada. Então o critério vira **três eixos separados**, e só o
primeiro define a lista:

1. **Origem cultural** — o ativo existe por causa de uma referência (cão, sapo, político, piada).
   É este eixo, e só ele, que define `meme_universe_v1`.
2. **Utilidade declarada** — o que o projeto diz fazer. Varia dentro da lista, e não é critério.
3. **Direito a fluxo de caixa** — nenhum dos 21 tem. Mas isso também vale para a maioria das
   altcoins do universo, então **não separa** meme de não-meme.

E há um problema anterior a qualquer hipótese: **"meme" não é um dado, é um rótulo que eu escolho.**
Escolher a lista depois de olhar o resultado é o grau de liberdade mais barato que existe para
fabricar um achado. Por isso esta rodada começa congelando a lista.

## Onde foi mostrado

- **Mancino (arXiv 2512.11850, dez/2025)** — Solana, 4º trimestre de 2024, dados on-chain da
  Pump.fun. Reporta que a plataforma chegou a **71,1%** de todos os tokens cunhados na Solana no
  período, contribuiu com **40 a 67,4%** das transações de DEX, e que **menos de 2%** dos tokens
  chegaram a uma DEX principal. Usuários ativos diários entre 60 mil e picos de 260 mil.
  **Não estuda perpétuos de corretora centralizada** — confirmei isso ao ler o resumo.
- **Xiang, Fu, Li, Wang, Yuen & Yu (arXiv 2512.00377, nov/2025)** — arcabouço "ME2F" com três
  dimensões (dinâmica de volatilidade, dominância de baleias, amplificação por sentimento) sobre
  tokens representativos com mais de 65% de participação de mercado. Ordena o risco assim: tokens
  **de tema político** (TRUMP, MELANIA, LIBRA) no topo; memes estabelecidas (DOGE, SHIB, PEPE) em
  faixa **intermediária**; ETH e SOL resilientes por liquidez mais profunda. **Também não usa dado
  de perpétuo.**
- **O que não achei:** nenhum estudo aberto que meça retorno, volatilidade ou funding de meme coins
  **em perpétuos da Binance**. A busca por "listing effect" em perpétuos devolveu só material de
  divulgação de corretora. Registrado na tabela de fontes que não abriram.

O ponto de contato entre a literatura e nós é fraco de propósito: os dois trabalhos descrevem a
população de tokens que **nunca chega** a ter perpétuo. O nosso universo é o outro extremo — só
entra quem já sobreviveu a ponto de a Binance listar um contrato perpétuo e o volume ser alto o
bastante para caber no top 200. Isso é **viés de sobrevivência por construção**, e qualquer número
nosso sobre "meme coins" descreve as sobreviventes.

## Como mediríamos aqui

Não dá para medir nada antes de decidir quem é meme. Congelei em 2026-09-06, **antes de rodar
qualquer consulta desta rodada**, a lista `meme_universe_v1`, com um critério declarado: token cuja
proposta de valor pública é a própria referência cultural, sem protocolo com receita associada.

**`meme_universe_v1` — coorte A (21 símbolos, alta confiança):**

```
DOGEUSDT, 1000SHIBUSDT, 1000PEPEUSDT, 1000BONKUSDT, 1000FLOKIUSDT, WIFUSDT, BOMEUSDT,
FARTCOINUSDT, PENGUUSDT, TRUMPUSDT, MOODENGUSDT, CHILLGUYUSDT, PNUTUSDT, NEIROUSDT,
1000CATUSDT, 1000000BOBUSDT, SPXUSDT, USELESSUSDT, MUBARAKUSDT, BROCCOLI714USDT, TSTUSDT
```

**Coorte B (5 símbolos) — definida por regra sintática, não por julgamento meu:** todo símbolo
monitorado que **não** casa com `^[A-Za-z0-9]+$`. Hoje são 牛来USDT, 哈基米USDT, 龙虾USDT,
币安人生USDT e 我踏马来了USDT. Escolhi uma regra mecânica de propósito: ela é reproduzível por
qualquer um, não depende de eu saber chinês, e o conjunto que ela seleciona coincide com listagens
recentes de meme da Binance. **A coerção "não-ASCII ⇒ meme" é uma suposição minha, não um fato.**

**Zona cinzenta, deliberadamente fora das duas coortes** (para que ninguém a use depois para
melhorar um resultado): PEOPLEUSDT, CATIUSDT, GIGGLEUSDT, 4USDT, DOODUSDT, PUMPUSDT, MARSCOINUSDT,
BULLAUSDT, RAYSOLUSDT, GRAMUSDT, TRADOORUSDT, SKYAIUSDT.

**Grupos de comparação, também congelados:** `C_btc` = BTCUSDT sozinho; `D_majors` = 23 símbolos
(ETH, SOL, XRP, BNB, ADA, AVAX, LINK, LTC, DOT, TRX, XLM, BCH, ATOM, ETC, HBAR, XMR, FIL, ICP,
NEAR, APT, SUI, UNI, AAVE); `E_resto` = os outros 150 monitorados.

Conferi que a lista cobre o universo: dos 200 monitorados na VPS em 2026-09-06,
21 + 5 + 1 + 23 + 150 = 200.

## Hipótese testável no Lab

**Não é uma estratégia — é um requisito de proveniência, e é o item 0 desta rodada.**

`H-KB0056`: gravar no envelope imutável de cada sinal o **`monitor_rank` do instante** e o **tamanho
e a regra do universo vigente**, e junto o nome e a versão da lista de marcação
(`meme_universe_v1`). Sem decidir nada com isso.

**Correção importante que a Astra impôs, e que muda o motivo da hipótese.** Eu tinha escrito que sem
o carimbo "nenhuma estratificação por meme é possível". Isso mistura duas coisas:

- **A classificação cultural É reconstruível.** Uma lista estática versionada, aplicada à identidade
  do mercado que o registro já guarda (`services/strategy-worker/hunter_strategy_worker/record.py:188`
  grava exchange e símbolo), pode ser aplicada retrospectivamente a qualquer sinal antigo. Nada se
  perde aqui.
- **O que É irrecuperável é a composição e o ranking históricos do top 200.** O universo é reescrito
  a cada 900 s (`packages/core/hunter_core/settings.py:140`), o diff só existe no evento
  `market.universe.changed`, e a `outbox_events` na VPS guarda **cerca de 30 minutos** (medido: às
  18:46 UTC a tabela inteira ia de 18:15 a 18:46, e **zero** eventos de universo sobreviviam). Sem
  isso não há **denominador** — não dá para dizer quantas memes estavam elegíveis num dia passado,
  nem qual era o rank de cada uma.

E o efeito disso já é mensurável. Medido na VPS em 2026-09-06:

```
 total_sinais | em_mercado_monitorado | em_mercado_nao_monitorado | mercados_que_sairam
--------------+-----------------------+---------------------------+---------------------
         1009 |                   982 |                        27 |                  14
```

Vinte e sete sinais, em quatorze mercados, foram emitidos por mercados que **já saíram** do universo
em menos de um dia — com **GOATUSDT** (uma meme, hoje no rank 249) liderando com 5 sinais. Toda
consulta que agrupa por `is_monitored` — inclusive as minhas desta rodada — descarta esses 27 em
silêncio. Isso é viés de sobrevivência acontecendo em quinze horas.

**O que a refutaria:** nada; não é hipótese sobre o mercado. O que a tornaria parcialmente
desnecessária é passar a persistir o diff de universo em tabela própria, em vez de só na outbox
efêmera — aí o rank histórico deixaria de ser perdido e o carimbo no sinal viraria conveniência, não
necessidade.

## Por que pode falhar

- **A lista é minha.** Vinte e um símbolos escolhidos por julgamento cultural. Qualquer resultado
  desta rodada muda se eu tiver classificado PENGU (NFT), SPX (referência a índice) ou TST (token de
  teste que virou meme) de outro jeito. Por isso a lista está escrita aqui, datada, e a zona
  cinzenta está fora **por escrito**.
- **A coorte B confunde duas coisas ao mesmo tempo:** ser meme e ser listagem recente. Tudo que eu
  medir nela pode ser efeito de idade do contrato, não de natureza do ativo — e a
  [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] mostra que não temos a data de listagem para
  separar os dois.
- **Sobrevivência dupla:** só entram memes com perpétuo *e* dentro do top 200 por volume. As que
  morreram não estão aqui, e as que caíram do top 200 desaparecem do universo sem deixar registro.
- **A literatura que citei é de outra população** (tokens on-chain, a maioria sem perpétuo). Usá-la
  para prever comportamento de DOGE na Binance é extrapolação, e está declarada como tal.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0056-0058-memecoins.md`). Quatro correções
entraram no texto acima:

1. **A definição estava errada.** "Sem utilidade declarada" é falso para DOGE e FLOKI, que declaram
   utilidade nas suas páginas oficiais. Ela pediu para **corrigir a definição preservando a lista
   v1**, exatamente para não reclassificar depois de ver resultado — e é o que fiz: três eixos
   separados, só o primeiro define a lista.
2. **Eu confundi reconstruir a classificação com reconstruir o universo.** A lista estática é
   aplicável retrospectivamente pela identidade do mercado; o que se perde é composição e ranking
   históricos. Cenário de falha dela: declarar tudo irrecuperável bloqueia uma análise válida,
   enquanto carimbar só o sinal é vendido como solução para um denominador que continua ausente.
3. **A regra sintática não identifica idade nem natureza econômica.** Ela identifica caracteres fora
   do ASCII alfanumérico, e nada mais. Cenário de falha: cinco contratos recentes e pouco líquidos
   concentram ATR alto, e o efeito é atribuído a "meme" quando idade, seleção por volume ou desenho
   do tick explicam. Isso **invalida a interpretação causal**, não as estatísticas dos cinco
   símbolos. Está escrito na seção "Por que pode falhar".
4. **Concordou** em congelar a lista antes das consultas, em declarar a zona cinzenta, e em tratar a
   dupla seleção (ter perpétuo + estar no top 200) como limite de generalização.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] · [[Index]]
