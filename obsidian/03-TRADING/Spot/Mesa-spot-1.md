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

- 01/10/2026 — análise das 10 primeiras operações fechadas: placar verdadeiro Σ −0,003938 SOL (−4,40 R), 8 perdas e 2 ganhos (o registrado diz −0,001735 por causa do aluguel constante). Causas e hipóteses em [[KB-0172-perdas-da-spot-1]]; operação a operação em [[Perdas-spot-1]]; custo em [[KB-0171-custo-real-da-spot-1]]. (Linha fora da tabela de propósito: `spot_ficha.py --write` acrescenta linhas no fim do arquivo.)

| data | mercado | id8 | status | R líquido | PnL (SOL) | ficha |
|---|---|---|---|---|---|---|
