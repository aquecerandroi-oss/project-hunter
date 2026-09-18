---
tags: [knowledge, nota, meme, pumpfun, relogio, horario, atividade, m5]
tema: memecoin / pump.fun / relógio de atividade do pump.fun — pico 14–20 BRT, madrugada −75 %
fonte: banco da VPS (meme_tokens, meme_live_orders), 72 h retroativas (14–16/09/2026)
fonte_url: ""
lido_em: 2026-09-16
evidencia: medição própria (R53 — SQL `r53.sql` citado em .claude/state/notes-R53.md)
hipotese_testavel: sim
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
---

# KB-0125 — Relógio de atividade: pico 14–20 BRT, madrugada −75 %

## O que afirma
Distribuição horária de criação e graduação de moedas em 72 h, para responder "por que nenhum trade
num dado turno" e orientar quando a mesa deveria operar.

## Número
| Janela BRT | Moedas/h | Graduações/h | Graduações com vida | Nota |
|---|---:|---:|---:|---|
| 00–08 | 841 | 37 | 14 (1,9 %) | **Noite morta (−75 % vs. pico)** |
| 09–13 | 1 394 | 47 | 19 | Ramp matinal |
| **14–20** | **1 808** | **50** | **24** | **Pico orgânico** |
| 21–23 | 1 363 | 40 | 19 | Transição |

Recomendação registrada: janela viável 14–20 BRT, secundária 10–13 BRT, **nunca 00–07 BRT**
(atividade −75 %, vida −85 %).

## O que muda na operação
A mesa real ignorou a recomendação: as compras do estágio 1 (R54) entraram entre 03:08 e 06:29 BRT —
exatamente a janela morta. Confirma que a diretriz "análise contínua" (memória do Everton) precisa
incluir suspensão ou peso menor de madrugada; decisão de operar 24 h ou não continua sendo do Everton
(não implementada como corte automático).

## Relacionados
[[03-TRADING/Meme/Balanco-2026-09-17-estagio-1]] · `.claude/state/notes-R53.md`
