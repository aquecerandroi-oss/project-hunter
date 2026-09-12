---
tags: [knowledge, nota, plantao, meme, pumpfun, ferramenta, dexscreener]
tema: memecoin / ferramentas / sinais pagos ("Dex paid", "Boost") / DEX Screener / Terminal do pump.fun
fonte: DEX Screener — marketplace (Enhanced Token Info) e docs (Boosting); Terminalpedia (guia dos Trenches do Terminal, terceiro); referência da API do DEX Screener (endpoint /orders/v1 apontado pela Astra)
fonte_url: https://marketplace.dexscreener.com/product/token-info
lido_em: 2026-09-12
evidencia: páginas do próprio vendedor (preço anunciado, prazo, regras) lidas em 2026-09-12 11:20–11:22 BRT (plantão T4.64, run 10, lane 2) + wiki de terceiro para o rótulo do Terminal; nenhuma medição própria; preços dos pacotes de Boost não publicados pelo vendedor
hipotese_testavel: sim
astra: ok (parecer 11:32 BRT, must-fix 3 — perfil ≠ pedido pago ≠ boost; preço "a partir de"; pagador desconhecido)
status: vivo
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# "Dex paid" e "Boost": o que custam e o que medem (DEX Screener, visto pelo Terminal do pump.fun)

> Nota do plantão T4.64 (run 10, lane 2). Rascunho com URLs e horas: `.claude/state/plantao-meme/2026-09-12-1116-lane2.md` (itens 2 e 8).
> `confiança: "?"` porque é a descrição do produto pelo vendedor, sem medição própria de quantas moedas pagam nem de quem paga.

## O fato estrutural (medido nas páginas do vendedor, 12/09/2026 11:20–11:22 BRT)

| rótulo no Terminal | produto do DEX Screener | preço anunciado | prazo | regras lidas |
|---|---|---|---|---|
| **"Paid" / "Dex paid"** | *Enhanced Token Info* (`https://marketplace.dexscreener.com/product/token-info`) | **"$299.00"** (riscado "$499.00") — "a partir de", não o desembolso de uma moeda específica | "Most orders are processed within just a few minutes, but please allow up to 12 hours" | logo, sociais, informação do projeto, **carteiras com supply bloqueado** (muda o mcap exibido); cripto ou cartão |
| **"Boost"** | *Boosts* (`https://docs.dexscreener.com/boosting`) | pacotes de pontos; **preços não publicados** nas docs nem no marketplace (estimativas de terceiro: ~US$ 100 a 1 500 — `openliquid.io`, sem data) | "Boosts last from 12 to 24 hours depending on the pack" | "temporarily increase a token's Trending Score" por multiplicador ("won't automatically rank at #1"); inelegível se inativo > 24 h ou com risco de segurança; só no navegador; **"non-refundable"**; removível se marcado malicioso; **Golden Ticker com "500 or more Boosts are active"** |

O Terminal (ex-Padre, `trade.padre.gg` = `terminal.pump.fun`) só **exibe** os dois rótulos: o toggle "Dex paid" dos Trenches é "evidence someone
purchased DEX Screener listing upgrade" (`https://terminalpedia.com/guides/trading/terminal-trenches-guide`, 11:22 BRT, terceiro). O pump.fun não
vende nenhum dos dois (`https://pump.fun/docs`, 11:19: só Termos e Privacidade; Telegram técnico sem post desde 20/07).

## O que cada endpoint público mede (sem chave; o nosso `received_at` é o relógio)

| estado | endpoint | o que comprova | o que **não** comprova |
|---|---|---|---|
| `perfil_observado` | `GET https://api.dexscreener.com/token-profiles/latest/v1` | que um perfil recente existe para o mint | pagamento, valor, pagador, data do pedido |
| `pedido_pago_observado` | `GET https://api.dexscreener.com/orders/v1/{chainId}/{tokenAddress}` (tipo, status, `paymentTimestamp` — referência oficial apontada pela Astra; não aberta pela lane) | que há pedido pago com carimbo | quem pagou (criador, comunidade, terceiro) |
| `boost_observado` | `GET https://api.dexscreener.com/token-boosts/latest/v1` e `/top/v1` (`amount`, `totalAmount`) | que houve boost aplicado | dólares gastos, boosts **ativos** (o Golden Ticker exige 500 ativos), pagador |

Regras de uso no radar: os três estados ficam **separados**; `totalAmount` não vira dinheiro; "não observado sob cobertura operacional" (poll
registrado: consultas previstas/realizadas, falhas, lacunas, itens devolvidos) é diferente de "cobertura insuficiente"; o endpoint `latest` não
promete enumeração completa; o perfil pode levar até 12 h — qualquer janela curta mede também rapidez de publicação e descoberta.

## Por que importa e o que testar

- Custo de visibilidade: US$ 299 é um piso anunciado, ordens de grandeza abaixo da mcap de graduação (≈ US$ 41,7 k, run 1); o boost de 12–24 h
  explica por que o ranking `token-boosts/top` mudou pouco entre 07:26 e 11:19 (mesmos 900/730/500 no topo).
- Hipótese na fila: **M-P30** ([[Hipoteses-do-plantao]]) — sinal pago conhecido até `L = t0 + 30 min` após a migração validada acrescenta
  informação a um modelo-base para retenção 24 h e resultado depois de `L`; preditivo, não causal.
- Para o censo de narrativa (M-P25), `token-boosts/top/v1` é **ranking pago**: seleção por pagamento, nunca criações.

## Ligações
[[README-meme|Meme (Conhecimento)]] · [[03-TRADING/Meme/Terminal-do-pumpfun|Terminal do pump.fun]] · [[02-MARKET/Meme/2026-09-12|Plantão MEME 2026-09-12]] · [[Hipoteses-do-plantao]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]
