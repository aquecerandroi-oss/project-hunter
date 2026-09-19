---
tags: [trading, spot, solana, jupiter, mesa-real, t4-74]
status: vivo
owner: sexta-feira
updated: 2026-09-19
---

# Spot — a mesa `spot/1` (sinal do Lab, execução na Solana)

Irmã de [[03-TRADING/Meme/README|Meme]], não uma extensão dela. A mesa `spot/1` não negocia pump.fun
nem curva de bonding: ela lê um sinal do Lab de mercado (a estratégia `mean_reversion` da Binance,
`docs/DATABASE.md` §33/§55) e compra o par equivalente na Solana pela Jupiter, com a carteira do
robô do executor de memes (mesmo processo, mesmo kill switch, mesma âncora do dia — desenho
`docs/design/spot1-lab-solana.md` §1). Origem: decisão do Everton de 19/09/2026,
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real|adendo em teste-pequeno-meme-real]]: "quero ir no
dinheiro real e testar no real mesmo".

Schema `0057_spot_desk` (`docs/DATABASE.md` §63): `spot_desk_markets` (o mapa Binance → Solana,
editado só por `infra/scripts/spot_desk_markets.py`), `spot_orders`, `spot_positions`. Perfil de risco
`docs/RISK_ENGINE_MEME.md` §19. **Nada liga sozinho:** `SPOT1_ENABLED` nasce `false`
(`docs/ACTIVATION.md` §9j).

## O que esta pasta guarda

- **[[03-TRADING/Spot/Mesa-spot-1|Mesa-spot-1.md]]** — o placar da mesa: uma linha por posição fechada (ou aberta), acrescentada por
  `infra/scripts/spot_ficha.py --write`, idempotente pelo marcador `<!-- <id8> -->` (design §7).
  Começa vazio — a mesa ainda não operou de verdade.
- **`Ficha-<AAAA-MM-DD>-<SÍMBOLO>-<id8>.md`** — uma por operação real, gerada pelo mesmo script:
  sinal e geometria, cotações de entrada/saída, as duas assinaturas on-chain, a paridade Jupiter ×
  Binance na decisão, SOL/USD na entrada e na saída, custo em R, R bruto/líquido e um campo "Lição"
  para o Everton preencher à mão. Regra dele (18/09/2026): toda compra real vira ficha no mesmo dia.

## O que não é uma "estratégia" pré-registrada aqui

Ao contrário de [[03-TRADING/Meme/README|Meme]], a mesa `spot/1` não é um conjunto de regras
pré-registrado que se aposenta por `--deprecate`: é a saída de papel da `mean_reversion/v14` (já
avaliada, `Σ R +14,90` em 23 sinais, R63) levada à Solana por uma pista fixa (ficha 0,05 SOL, 1,5 R /
4 h, sizing "ficha ou nada"). A parada é uma regra de código, não uma troca de conjunto: 20 operações
com expectância líquida ≤ 0 R, ou perda acumulada ≥ 0,15 SOL, e a pista entra em `refuted`
(desenho §8) até uma linha nova do Everton no `.env`.
