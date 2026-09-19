---
tags: [experimento, meme, evento, retencao, snipers, m4]
status: pre-registrado
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 00:4x BRT — "se está subindo, vendas rápidas e mudanças rápidas de subida: compra assim que tiver alta, dá para perceber" / "então está precisando melhorar, não?"
---

# EXP-M19 — Subida com gente atrás (retenção dos snipers + carteiras novas − vendas rápidas)

## Hipótese
A subida que paga é a que tem compradores novos entrando e os primeiros compradores (snipers, bloco 1–3) **segurando**; a que não paga é a distribuição (os primeiros vendendo para os que chegam). Um critério de porta lido do feed por trade — retenção dos snipers ≥ 70 % por ≥ 60 s, ≥ N carteiras novas nos últimos 30 s, vendas rápidas (compra e venda em < 20 s) ≤ 20 % dos trades — separa as duas com vantagem.

## Por que agora
O feed por evento (T4.52b, 3 000 trades/min) traz **quem** compra e vende; a porta atual só lê números de uma foto (snipers, holders, progresso). O teto de snipers (10) barra 45 moedas/30 min de madrugada sem saber se os snipers ficaram.

## Método (T4.66, papel primeiro)
Estado em memória por moeda: carteiras dos 3 primeiros blocos e seus saldos (via trades), carteiras novas por janela, trades "rápidos". Critério novo na porta de evento; braço `flow_v2/10` (`research_only`) = `flow_v2/6` + critério; controle `flow_v2/6`. Medir 3 dias: R médio, acerto, concentração, e a mesma leitura nas moedas que a mesa real comprou (teria vetado YOU/CITIZEN?).

## Regra de decisão
Vira mesa se R médio do braço > controle com ≥ 60 apostas e vetar ≥ 2 dos 3 rugs reais sem vetar a única vencedora (PS).

Ligações: [[KB-0119-entrada-depois-da-queda]] · [[KB-0120-piso-de-snipers]] · [[KB-0128-cadeia-vence-fita]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[EXP-M18-sniper-de-lancamento]]
