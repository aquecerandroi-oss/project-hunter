---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-15
---

# Operações traçadas (meme) — índice

Uma página por conjunto de regras, um gráfico por aposta **fechada** (entrou, saiu, R apurado na linha de `meme_paper_bets`). Gerado por `meme_render_bets.py notes` — `docs/PIPELINE.md` §9c.

- [[03-TRADING/Meme/Apostas-tracadas/flow_v2-1]]
- [[03-TRADING/Meme/Apostas-tracadas/flow_v2-2]]
- [[03-TRADING/Meme/Apostas-tracadas/flow_v2-3]]
- [[03-TRADING/Meme/Apostas-tracadas/hype_probe_v0-2]]
- [[03-TRADING/Meme/Apostas-tracadas/moonshot_v0-1]]
- [[03-TRADING/Meme/Apostas-tracadas/moonshot_v0-2]]

As linhas destes gráficos são **features** calculadas pelo fold (`meme_features_v3`, `docs/DATABASE.md` §38.1), não desenho à mão: suporte pelos dois últimos fundos locais, máxima da janela anterior de 15 min, rompimento. Quem **lê** linha para decidir é o conjunto cujo portão a exige ([[EXP-M2-a-linha-manda]]); nos demais a linha é contexto.

Irmã de [[03-TRADING/Operacoes-tracadas/README|Operações traçadas (perps/spot)]] e de [[03-TRADING/Meme/README|Meme (Trading)]].
