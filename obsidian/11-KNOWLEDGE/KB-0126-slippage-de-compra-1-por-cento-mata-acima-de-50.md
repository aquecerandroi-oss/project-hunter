---
tags: [knowledge, nota, meme, pumpfun, slippage, compra, executor, m5]
tema: memecoin / pump.fun / slippage de compra fixo em 1 % mata compras acima de 50 % de progresso (6002); configurável, subiu para 3 %
fonte: código do executor (send_tuning.py, send_path.py) + duas compras reais falhas em 17–18/09/2026
fonte_url: ""
lido_em: 2026-09-18
evidencia: relato de construção e teste (T4.59 — .claude/state/notes-T4.59.md)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
tipo: leitura
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0126 — Slippage de compra fixo em 1 % mata compras acima de 50 %; subiu para 3 % (T4.59)

## O que afirma
Com a janela de progresso liberada até 100 % (T4.58, Proposta A), a tolerância fixa de compra
(`MemeLimits.max_slippage_pct = 0.01`) passou a recusar compras legítimas em curvas mais avançadas,
que se movem mais rápido por SOL de fluxo.

## Número
Duas compras reais morreram por `Custom 6002 = TooMuchSolRequired`: **EMRLD** (54,8 % de progresso,
`failed onchain_error` **depois** do envio — taxa de rede paga por nada) e **TIME** (52,3 %,
`simulation_failed` — taxa de rede poupada). A T4.55 só tinha tornado configurável a tolerância das
**vendas**; a compra continuava com 1 % fixo no código.

## O que muda na operação
`MEME_BUY_MAX_SLIPPAGE_PCT` (padrão 1 %, faixa `(0, 20]`, teto mais apertado que o das vendas por ser
dinheiro que pode sair a mais) — Everton subiu para **3 %**, cobrindo os dois casos vistos. Ressalva
aberta: o check 19 (`slippage_cap`) e o `max_sol_cost_sol` do *sizing* ainda julgam pelo 1 % do perfil
enquanto a instrução usa o valor configurado — com 20 % e 0,28 SOL/trade a carteira pode pagar até
0,336 SOL numa compra sem que a `MemeDecision` persistida mostre isso. Fechar exige o limite do perfil
ler o env (risk-core), fora do escopo desta tarefa.

## Relacionados
`.claude/state/notes-T4.58.md` · `.claude/state/notes-T4.59.md` · `docs/RISK_ENGINE_MEME.md` §3, §6
