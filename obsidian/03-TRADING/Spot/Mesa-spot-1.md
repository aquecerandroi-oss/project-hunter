---
tags: [trading, spot, solana, jupiter, mesa-real, t4-74]
status: vivo
owner: sexta-feira
updated: 2026-09-19
---

# Mesa `spot/1` — placar

Ver [[03-TRADING/Spot/README|README da pasta Spot]] para o que esta mesa é e de onde vem o sinal.
Uma linha por posição, acrescentada por `infra/scripts/spot_ficha.py --write` (idempotente pelo
marcador `<id8>` — rodar duas vezes na mesma posição não duplica a linha). Vazio: a mesa ainda não
operou de verdade (`SPOT1_ENABLED=false`, `docs/ACTIVATION.md` §9j).

| data | mercado | id8 | status | R líquido | PnL (SOL) | ficha |
|---|---|---|---|---|---|---|
