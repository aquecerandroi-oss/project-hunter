---
tags: [decisao, meme, pumpfun, execucao, dinheiro-real, teste-pequeno, m4]
titulo: Dinheiro real no executor de memecoins — autorização, escopo do teste pequeno, tetos e o que continua fora
data: 2026-09-12
updated: 2026-09-12
owner: sexta-feira
origem: Everton, 2026-09-12, 17:2x–17:4x BRT — "Autorização escrita — está autorizado"; "tem que fazer vários e vários testes e ir validando; lembrando que cria e morre rápido, e as mais promissoras é para fazer milhão"; "carteira própria do robô já está criada; máximo por SOL até 1000 dólares"
status: decidido
decided_on: 2026-09-12
by: everton
---

# Dinheiro real no executor de memecoins — autorização e escopo

## A decisão
O Everton autoriza por escrito (chat, 12/09/2026 17:2x BRT) ligar o executor real de memecoins
(`docs/ACTIVATION.md` §9b, item 2), sabendo que os Portões A (VM1–VM9 na VPS + 7 dias de papel) e B (EXP-M1: ≥ 100
operações e ≥ 30 dias) estão **vermelhos**: em papel, 12/09 fechou 17 apostas medidas a −3,37 R com 1 acerto. A carteira
dedicada do robô já existe (criada por ele às 17:4x BRT). O teto que ele fixou: **até US$ 1 000 por operação**
(≈ 9,8 SOL a US$ 102/SOL, cotação do heartbeat às 17:00 BRT).

## Em dois estágios — a proposta da Sexta-feira, para ele confirmar
O executor nunca assinou uma transação real; a prova é simulação na mainnet. Por isso a ordem proposta:

| Estágio | Escopo (`small_test_authorization` no `meme_gates.json`) | Objetivo |
|---|---|---|
| **1 — encanamento** | `max_sol_per_trade` **0,05 SOL** (≈ US$ 5), `max_total_sol` **0,25**, `max_trades` **5**, validade 2026-09-15 | provar fill real, `TradeEvent`, posição, venda real na curva, `sell_now`, kill switch — cinco compras e cinco vendas de verdade |
| **2 — o teto dele** | `max_sol_per_trade` **9,8 SOL** (US$ 1 000), `max_total_sol` e `max_trades` a fixar por ele, validade curta | as promissoras, uma a uma, cada compra aprovada por ele na mesa |

O estágio 2 só começa depois de o estágio 1 fechar cinco vendas reais sem recusa inesperada e com o PnL batendo ao
lamport com a cadeia (`meme_live_positions` × saldo da carteira). Ele assina o segundo `meme_gates.json` quando quiser.

Os cinco números de política do `.env` (só ele digita) para o **estágio 1** — sugeridos, ele pode apertar:
`MEME_WALLET_MAX_SOL=0.30` · `MEME_MAX_SOL_PER_TRADE=0.05` · `MEME_DAILY_LOSS_CAP_SOL=0.15` · `MEME_MAX_OPEN_POSITIONS=2`
· `MEME_COOLDOWN_S=60`. Saldo da carteira ≤ `MEME_WALLET_MAX_SOL` (acima disso o executor recusa entradas,
`wallet_over_max_sol`). No estágio 2 os cinco sobem junto com o escopo (o escopo é sempre o mínimo com a política).

## O que é dele e só dele (nenhum agente toca; o classificador de segurança bloqueia até a criação do arquivo de portões)
1. A carteira dedicada (feita) com saldo ≤ `MEME_WALLET_MAX_SOL`.
2. No `.env` da VPS: a flag ligada, `SOLANA_WALLET_SECRET_KEY` (base58 do Phantom **ou** o array JSON do
   `solana-keygen` — os dois formatos são aceitos, `hunter_core/execution/meme/signer.py`), `SOLANA_RPC_URL` (RPC próprio
   com chave — Helius/QuickNode/Triton; o endpoint público é recusado, `rpc_url_missing`), os cinco `MEME_*`,
   `MEME_GATES_FILE=/run/hunter/meme_gates.json`.
3. O arquivo `/opt/project-hunter/run/meme/meme_gates.json` (conteúdo pronto no chat de 17:4x BRT; formato em
   `packages/core/hunter_core/execution/meme/gates.py`).
4. Depois disso a Sexta-feira sobe com `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`, confere
   `hb:meme:executor` e `GET /meme/live`, e **cada compra real é aprovada por ele** na mesa ("Aprovar (REAL)", T4.17, dupla
   confirmação) ou por HTTP com `Idempotency-Key`. Nada compra sozinho em dinheiro real.
5. Desligar em 5 s: `touch /opt/project-hunter/run/meme/meme.kill`.

## O que continua fora (ele sabe antes de ligar)
- Venda **depois** da migração para a PumpSwap não existe: uma posição que migrar fica `open` com
  `blocked: pumpswap_sell_not_implemented` e sai só pelo site, à mão. Com `max_hold_s` curto o `time_stop` vende antes.
  **No estágio 2 isto pesa:** uma promissora que gradua com US$ 1 000 dentro só sai pelo Terminal — construir a venda na
  PumpSwap (T4.18) antes do estágio 2 é a recomendação.
- `holder_rewards` sempre 0 hoje e o piso de taxa é constante datada (decodificar `FeeConfig` depois — T4.8b).
- O rastreador ainda pode expulsar uma moeda com aposta aberta (T4.16b em curso); o executor lê a curva por RPC na hora
  de vender e não depende do rastreador para sair.

## O método que o Everton pediu e como ele se encaixa
"Vários e vários testes, validando; cria e morre rápido; as promissoras são para fazer milhão." O laboratório de papel
é isso: centenas de apostas pequenas por conjunto, régua de ≥ 100 apostas e 30 dias por regra
([[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|a régua]]), o fechamento diário escrevendo as lições
sozinho (T4.15), e os braços **moonshot** (alvo 10×/25×, trailing 50 % só após 3×, segurar pela migração —
[[05-EXPERIMENTS/EXP-M4-moonshot|EXP-M4]]) para a cauda. O dinheiro real grande entra **atrás** da regra que provar
vantagem; o estágio 1 garante que, no dia em que ela provar, o robô já esteja provado.

## Ligações
[[06-DECISIONS/2026-09-12-mesa-do-operador-e-caminho-inerte]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] ·
[[05-EXPERIMENTS/EXP-M4-moonshot]] · [[11-KNOWLEDGE/KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2|KB-0094]]
