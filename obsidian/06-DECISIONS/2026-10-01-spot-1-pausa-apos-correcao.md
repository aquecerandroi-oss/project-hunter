---
tags: [decisao, spot, dinheiro-real, mean-reversion]
status: decidida
owner: sexta-feira
updated: 2026-10-01
decided_on: 2026-10-01
by: Everton
---

# `spot/1`: pausar novas compras depois das correções (01/10/2026)

**Contexto.** A análise das perdas ([[KB-0172-perdas-da-spot-1]], [[Perdas-spot-1]]) e o custo real ([[KB-0171-custo-real-da-spot-1]]) mostraram:
- a `mean_reversion v14` não tem vantagem fora da amostra: 202 sinais no Lab somam −0,03 R; foi escolhida pela única semana boa (+19,2 R, semana de 14/09);
- o custo real é 0,28 R por operação (0,49 % ida e volta na ficha de 0,05 SOL), maior que a vantagem;
- perda real das 10 operações: **−0,0039 SOL (−4,40 R)**; o placar mostrava −0,0017 por um bug de aluguel de conta;
- dois defeitos de execução: aluguel de conta lido de uma constante antiga e stop/alvo decidido numa cotação só (UNI 29/09 vendeu num "stop" de −13,6 % que a Binance não mostrava) — ver [[Open Bugs]].

**Opções apresentadas pela Sexta-feira:** pausar já (recomendado) · manter ligada · pausar só depois da correção.

**Decisão do Everton:** **pausar só depois da correção** — a `spot/1` segue ligada (ficha 0,05 SOL, um aberto por vez) até as duas correções subirem num deploy; então a Sexta-feira pausa as novas compras pela ferramenta auditada (vendas e stops continuam) e o Everton decide o passo seguinte.

**Para voltar a comprar depois da pausa:** uma estratégia precisa passar no teste com o custo real da `spot/1` (proposta H-c em [[KB-0172-perdas-da-spot-1]]: a v14 paga 0,25 %/perna fora da semana de seleção?), e o Everton aprova.

## Relacionado

[[2026-09-30]] · [[Mapa de Estrategias]] · [[KB-0149-o-que-a-mesa-real-ensinou]]

## Mercados a desligar na pausa (lista lida em 01/10/2026, `spot_desk_markets.py --list`, `enabled = yes`)

A pausa é feita mercado a mercado pela ferramenta auditada `infra/scripts/spot_desk_markets.py --disable <símbolo> --note <esta nota> --apply` (o portão exige que esta nota cite cada símbolo). Desligar um mercado só tira ele das **entradas**; as posições abertas seguem com stop, alvo, saída por tempo e venda manual.

1000BONKUSDT · 1000PEPEUSDT · AAVEUSDT · ARBUSDT · BIOUSDT · BNBUSDT · BOMEUSDT · BTCUSDT · CHIPUSDT · DOGEUSDT · ETHUSDT · FARTCOINUSDT · HYPEUSDT · INJUSDT · JTOUSDT · JUPUSDT · LINKUSDT · LITUSDT · METUSDT · MONUSDT · NEARUSDT · ORCAUSDT · PENGUUSDT · PONSUSDT · PUMPUSDT · PYTHUSDT · RENDERUSDT · SKRUSDT · SPXUSDT · TAOUSDT · TRUMPUSDT · TRXUSDT · UNIUSDT · USELESSUSDT · WIFUSDT · WUSDT · XMRUSDT · ZECUSDT
