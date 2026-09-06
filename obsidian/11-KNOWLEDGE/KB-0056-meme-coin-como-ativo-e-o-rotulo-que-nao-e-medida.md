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

Uma meme coin não tem fluxo de caixa, protocolo com receita nem utilidade declarada: o preço é
inteiramente atenção precificada. A literatura aberta que eu consegui ler trata disso **na cadeia**
(criação de token, concentração de carteiras, difusão social) e **não** no perpétuo de corretora
centralizada, que é o único lugar onde o nosso Lab enxerga.

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

`H-KB0056`: gravar no envelope imutável de cada sinal a **marcação de universo** (`universe_tag`),
com o nome e a versão da lista (`meme_universe_v1`), a coorte (`A`, `B`, `cinza`, `btc`, `major`,
`resto`) e o `monitor_rank` do instante. Sem decidir nada com isso.

Motivo, e é o mesmo da [[KB-0030-o-regime-nao-chega-ao-sinal]] e do requisito de ranking da
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]]: reconstruir a marcação depois, pelo estado
**atual** de `markets`, atribui resultado à coorte errada quando a lista mudar — e ela vai mudar,
porque memes entram e saem do top 200. Uma estratificação por meme feita amanhã sobre a lista de
amanhã é irrecuperavelmente errada.

**O que a refutaria:** nada. Não é hipótese sobre o mercado, é sobre o nosso registro. O que a
tornaria desnecessária é alguém mostrar que a coorte de cada sinal é reconstruível sem ambiguidade a
partir do que já gravamos — e não é: o universo é reescrito a cada 900 s
(`packages/core/hunter_core/settings.py:140`) e o diff só vive em `outbox_events`, que na VPS
guarda **30 minutos** (medido: a tabela inteira ia de 18:15 a 18:46 às 18:46 UTC).

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

_(pendente — esta rodada revisa em bloco de três notas)_

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] · [[Index]]
