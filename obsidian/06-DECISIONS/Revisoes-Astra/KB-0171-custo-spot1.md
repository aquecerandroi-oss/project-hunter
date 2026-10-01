---
tags: [revisao-astra, spot-1, custo, jupiter, aluguel, metodo]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: sexta-feira
decided_on: 2026-10-01
by: astra
tarefa: método da medição do custo real de ida-e-volta da spot/1 (KB-0171) e o achado da constante de aluguel
veredito: concorda com o método após 4 must-fix (absorvidos) e confirma o bug do aluguel pela leitura do código
---

# Revisão da Astra — custo real da `spot/1` (KB-0171)

**Pedido:** revisar o método (fontes, referência, aluguel, fechamento contábil, incerteza com n = 10) e o achado de que
o executor desconta 2 039 280 lamports de aluguel quando a rede cobra 1 488 440. Fonte bruta:
`.claude/state/astra-review-KB-0171-custo.md`. Ela não reproduziu os dados (o scratchpad está fora do repositório);
leu o código e a documentação da Solana.

**Bug do aluguel — confirmado pela leitura do código:** `spot_send_rules.py:27` (constante), `spot_send.py:298` e
`spot_reconcile.py:320` (atribuem a constante quando a ATA é criada), `spot_entry_writes.py:85` e `spot_settle.py:113`
(subtraem do gasto), `spot_settle.py:68` (PnL = recebido − gasto). 4 × 550 840 = 0,00220336 SOL de PnL a mais. Quando
2 039 280 estaria certo: só para uma ATA criada sob o parâmetro antigo (293 × 6 960); hoje 293 × 5 080 = 1 488 440. O
remédio é ler o depósito da própria transação, não trocar uma constante por outra.

**Must-fix de método, todos absorvidos na KB-0171:**

1. Aluguel lido do `createAccount` real e confirmado no saldo atual das 4 ATAs (1 488 440 cada, `getMultipleAccounts`).
2. Nome honesto: **déficit contra o último close 1 m da Binance perp** (mistura pool, impacto, base perp×spot e drift);
   minuto escolhido pelo `blockTime` on-chain — os 20 pousos caem no mesmo minuto que o `confirmed_at`, nada mudou.
3. Decomposição no **mesmo lote**, em SOL, sobre base comum (0,05 SOL); o fechamento PnL-sem-atrito − PnL-real é
   **identidade** (checa contas, não a referência). Resultado mantido: 0,493 %.
4. Incerteza por **posição** (pareada), não por perna; também por dia (6 dias: [0,33 %; 0,70 %]); deixar-um-de-fora
   0,445–0,538 %. Falhas que pousaram e pagaram taxa: 0 (nenhuma recusada tem assinatura).

**Correções de redação aceitas:** "0,033 SOL" → **0,0331 SOL** (0,033 ainda fica um pouco acima de 0,15 %/perna);
0,070 SOL dá **exatamente** 0,15 % no teto; "o proporcional não cai com a ficha" → **"sem evidência de diluição nesta
medição"**; "sem taxa de plataforma" → **"nenhuma identificada nas transações examinadas"**.

**Nice-to-have não feitos (e por quê):** referência contemporânea spot (bookTicker no segundo do pouso) — não temos esse
dado gravado para as 10; fica como "como mediríamos" na nota. Reprocessar o PnL das 4 posições — é escrita no banco,
fora do escopo desta pesquisa; fica no [[Open Bugs]].

**Onde concordou:** `meta.fee` como fonte; aluguel é depósito, não despesa; WSOL transitória; 0,001 SOL/perna ≈ 20× a
média medida; 0,15 %/perna abaixo dos ~0,247 %/perna observados nesta mesa e ficha — pede sensibilidade em R84/R85 sem
reescrever os vereditos históricos.

Ligações: [[KB-0171-custo-real-da-spot-1]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] ·
[[KB-0169-fibonacci-e-lta-diaria-no-dado]] · [[06-DECISIONS/Revisoes-Astra/Index|Index]]
