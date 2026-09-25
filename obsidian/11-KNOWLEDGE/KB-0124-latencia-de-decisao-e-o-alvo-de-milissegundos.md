---
tags: [knowledge, nota, meme, pumpfun, latencia, executor, radar, entrada-instantanea, m5]
tema: memecoin / pump.fun / latência ponta a ponta de 6,6 s; o gargalo é proposta→executor (4,8 s), e o que T4.52a/b fazem
fonte: banco da VPS (meme_live_orders, meme_proposals), 24 h em 17/09/2026 + código de T4.52a/T4.52b
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R55) + relato de construção (T4.52a, plan-T4.52b, T4.52b-1/2/3, review-T4.52a/b)
hipotese_testavel: sim
astra: não consultada nesta nota
confiança: backtest do autor (medição) e relato de implementação (correções)
owner: sexta-feira
updated: 2026-09-18
status: vivo
tipo: pesquisa
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

# KB-0124 — Latência ponta a ponta 6,6 s; o gargalo é o poll do executor (4,8 s)

## O que afirma
Resposta à diretriz "entrada instantânea" (memória do Everton, 10/09): onde está o tempo entre o
evento de mercado e a ordem liquidada, e o que os pacotes T4.52a/b mudam.

## Número
R55 (5 compras + 24 h de ordens): **6,6 s p50** ponta a ponta = **4,8 s (76 %) Proposal→Received**
(o executor faz *poll* de 1 s na tabela) + 0,4 s admissão/RPC + 1,3–1,4 s piso da Solana (assinar,
enviar, `confirmed`). T4.52a (Redis pub/sub `meme:proposals:wake`, commit `51914d02`, revisão
SAFE_WITH_FLAG → conserto de uma linha aplicado): publicação → evento ligado em < 200 ms testado.
T4.52b (plano em 5 partes): radar por WS do RPC (`logsSubscribe`+`accountSubscribe` na PDA da curva),
alvo evento→proposta **0,6–1,6 s p50**; T4.52b-1 mediu ao vivo lag `confirmed` p50 0,58 s.

## O que muda na operação
Corta a fila estrutural entre "proposta escrita" e "executor pegou" (T4.52a, já em produção) e depois
entre "evento na cadeia" e "proposta escrita" (T4.52b). T4.52b passou por revisão adversarial em duas
rodadas (BLOCK para shadow/on → consertos F1–F7 → shadow liberada, corrida residual em `on`) antes de
ser ligado em produção às 14:3x BRT de 18/09 (`MEME_EVENT_GATE=on`, decisão do Everton "se achou
oportunidade eu quero que ela entre já").

## Relacionados
`.claude/state/notes-R55.md` · `.claude/state/notes-T4.52a.md` · `.claude/state/plan-T4.52b.md` ·
`.claude/state/notes-T4.52b-1.md` · `.claude/state/review-T4.52a.md` · `.claude/state/review-T4.52b.md` ·
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]]
