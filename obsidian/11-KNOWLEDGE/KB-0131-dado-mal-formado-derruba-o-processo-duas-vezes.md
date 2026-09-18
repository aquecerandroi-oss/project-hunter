---
tags: [knowledge, nota, meme, pumpfun, incidente, robustez, worker, operacao, m5]
tema: memecoin / pump.fun / dado externo mal-formado derrubou o worker duas vezes em dois dias — byte nulo (T4.47) e decimal sem aspas (18/09)
fonte: logs do container hunter-meme-worker-1 (T4.47) + incidente operacional 18/09 14:19–14:29 BRT
fonte_url: ""
lido_em: 2026-09-16
evidencia: relato de diagnóstico e correção (T4.47, R45) + relato de incidente (diário 2026-09-18)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
---

# KB-0131 — Dado mal-formado derrubou o worker duas vezes em dois dias

## O que afirma
Dois incidentes do mesmo gênero — um dado de origem externa ou operacional, mal-formado, propaga sem
tratamento e derruba o processo inteiro em laço — em 48 h de intervalo.

## Número
- **T4.47 (17/09):** byte NUL embutido no `name` de um frame `create` do pump.fun
  (`"spaceX链游\x00"`) causou `CharacterNotInRepertoireError` no upsert de `meme_tokens`: **18
  restarts entre 00:07 e 00:13 UTC, 168 s de indisponibilidade acumulada** (R45). Corrigido com
  `clean_text()` em `TokenRow.__post_init__`.
- **Incidente 18/09 14:19–14:29 BRT:** `--set-param max_sol_per_bet=0.28` passado **sem aspas**
  gravou número em vez de string; o Lab recusa `float` ("params carry decimals as strings"),
  derrubando `lab_tick` **a cada tique por 10 min (17 reinícios)**. Corrigido com
  `'max_sol_per_bet="0.28"'` (texto).

## O que muda na operação
Dois incidentes do mesmo padrão em dois dias sugerem que o script de `--set-param` deveria **recusar**
`float` na entrada em vez de aceitar (item pequeno, planejado como T4.61, não implementado nesta
janela). Lição registrada no diário: todo decimal em `--set-param` vai entre aspas.

## Relacionados
`.claude/state/notes-T4.47.md` · `.claude/state/notes-R45.md` ·
[[09-OPERATIONS/Diario/2026-09-18]]
