---
tags: [knowledge, nota, meme, pumpfun, radar, cobertura, graduacao, m5]
tema: memecoin / pump.fun / 45,9 % das graduações nascem cheias (não-rastreáveis por desenho); o radar só perde 0,4 %
fonte: banco da VPS (meme_tokens), 24 h retroativas em 16/09/2026
fonte_url: ""
lido_em: 2026-09-16
evidencia: medição própria (R50 — SQL em .claude/state/notes-R50.md)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
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

# KB-0123 — 45,9 % das graduações nascem cheias; a perda real do radar é 0,4 %

## O que afirma
Classificação de 1 058 graduações em 24 h (`completed_at` ou `graduated_board_seen_at` não-nulo):
quanto é falha do radar vs. limite físico do desenho do pump.fun.

## Número
| Categoria | Contagem | % | Vida média |
|---|---:|---:|---|
| WATCHED (rastreadas antes de completar) | 568 | 53,7 % | ~3 h |
| **BORN_FULL** (cria + migra sub-segundo) | **486** | **45,9 %** | **1,3 s** |
| MISSED_ORGANIC (vida ≥ 60 s, perdida de verdade) | **4** | **0,4 %** | ~57 h |

Todas as 486 BORN_FULL são non-Mayhem, origem `pumpportal_ws` (evento de migração), atraso do radar
= 0 s — o radar vê a migração antes de ter chance de rastrear. Das 4 MISSED_ORGANIC, 3 foram vistas só
pelo board (`trenches_ws`), nunca pelo `create` do PumpPortal.

## O que muda na operação
Confirma que quase metade do universo de graduações é **estruturalmente intradável** (latência de
design do pump.fun), não um defeito do radar — a perda evitável real é pequena. Aponta
`services/meme-worker/hunter_meme_worker/boards.py` como o lugar certo para tornar o rastreamento mais
agressivo em moedas novas vistas primeiro pelo board (item de manutenção, não implementado).

## Relacionados
[[11-KNOWLEDGE/KB-0117-o-progresso-da-serie-de-15s-esta-atrasado|KB-0117]] ·
`.claude/state/notes-R50.md`
