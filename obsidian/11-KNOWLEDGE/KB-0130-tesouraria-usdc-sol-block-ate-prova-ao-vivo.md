---
tags: [knowledge, nota, meme, pumpfun, tesouraria, jupiter, revisao-de-risco, dinheiro-real, m5]
tema: memecoin / pump.fun / tesouraria USDC→SOL — revisão BLOCK (3 txs hostis aceitas em teste) até consertos e prova ao vivo com 1 e 3,2 USDC
fonte: revisão de risco (review-T4.54.md) + código (T4.54, T4.54b) + duas trocas reais na VPS, 18/09/2026
fonte_url: ""
lido_em: 2026-09-18
evidencia: relato de revisão adversarial e correção com dinheiro real (T4.54, review-T4.54, T4.54b)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
---

# KB-0130 — Tesouraria USDC→SOL: BLOCK na revisão até prova ao vivo de 1 e 3,2 USDC

## O que afirma
A primeira versão da tesouraria (T4.54, troca automática de USDC por SOL via Jupiter quando o SOL cai
abaixo de um piso) verificava só o `program_id` de cada instrução, sem decodificar valores — a
revisão de risco achou que isso não bastava.

## Número
Prova adversarial da revisão: **3 transações hostis foram aceitas** pelo verificador original —
`SystemProgram.Transfer` da carteira inteira, `Token.Transfer` de todo o USDC, e uma `route` com
`in_amount` 1000× o pedido. Veredito: **BLOCK** até A–E corrigidos (verificação instrução a instrução,
validação da cotação, teto diário somando `submitted`, flag antes de qualquer leitura, alvo com teto
do `wallet_max_sol`). T4.54b implementou as cinco e acrescentou um invariante pós-simulação
(`check_simulated_balances`). Prova ao vivo em 18/09: **1 USDC → 0,009465 SOL** (10:08 BRT) e depois
**3,2 USDC → 0,0303 SOL** (10:19 BRT), as duas confirmadas na cadeia.

## O que muda na operação
Mostra o ciclo completo que todo código que assina dinheiro real deveria seguir: revisão adversarial
**antes** de ligar, não depois. A tesouraria está ligada em produção com os consertos aplicados; o
bug que ela expôs no cap diário (KB-0129) só apareceu **depois** de ligada — a revisão de segurança de
uma peça não previu a interação com outra peça já existente.

## Relacionados
`.claude/state/notes-T4.54.md` · `.claude/state/review-T4.54.md` ·
[[11-KNOWLEDGE/KB-0129-cap-diario-cego-a-entrada-da-tesouraria|KB-0129]] ·
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] adendo 18/09 10:1x
