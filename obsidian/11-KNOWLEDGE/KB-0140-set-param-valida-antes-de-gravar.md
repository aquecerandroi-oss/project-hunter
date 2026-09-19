---
tags: [knowledge, nota, meme, operacao, worker, robustez, m5]
tema: dois incidentes de "--set-param" gravando um valor que o worker não conseguia carregar; o script agora valida antes de gravar (T4.64)
fonte: logs do container hunter-meme-worker-1 (18/09/2026) + infra/scripts/meme_rule_set.py
fonte_url: ""
lido_em: 2026-09-19
evidencia: relato de incidente (diário 2026-09-18) + correção implementada e testada (T4.64)
hipotese_testavel: não
astra: pendente
confiança: backtest do autor
owner: backend-specialist
updated: 2026-09-19
status: vivo
---

# KB-0140 — `--set-param` valida antes de gravar

## O que afirma
Um script auditado que grava parâmetros lidos por um worker crítico precisa carregar o documento
resultante pelo **mesmo código do worker** antes de gravar — não confiar que o operador digitou a
sintaxe certa (decimal como string entre aspas). Duas vezes em um único dia o mesmo tipo de erro
(um número JSON solto onde o Lab exige string) passou pela gravação e só foi descoberto quando o
worker já estava em loop de reinício.

## Número
- **18/09/2026 14:19 BRT:** `--set-param max_sol_per_bet=0.28` (sem aspas) gravou um número JSON;
  `RuleSetSpec.from_params` (`hunter_meme_worker/lab_models.py`) recusa com "a float is not an
  exact number; params carry decimals as strings" — **worker em loop de reinício por 10 minutos**.
- **18/09/2026 19:47 BRT:** `--set-param trailing_arm_x="1.0"` chegou a
  `ExitRules.__post_init__` ("trailing_arm_multiple must be greater than 1 when set") —
  **worker em loop de reinício por ~3,5 horas**, até a T4.65 tornar a *leitura* tolerante a um
  valor armado em 1× (dobrando como "sempre", nunca mais estrito).
- **T4.64 (19/09/2026):** `meme_rule_set.py --set-param` — em dry-run e em `--apply` — monta o
  `params` que resultaria da mudança e o carrega por `RuleSetSpec.from_params`, o portão
  (`_gate_from_params`) e as regras de saída (`effective_params(...).exit_rules()`), o mesmo
  caminho do worker (`meme_rule_set_validate.py`). Uma recusa aí é `WouldNotLoad`: imprime o erro
  exato, não grava nada, sai com código 2. Um número solto sobre uma chave que o documento vivo já
  guarda como string é pego antes disso, com a sintaxe certa: `decimals are strings: use
  'max_sol_per_bet="0.28"'`. `--validate NAME/VERSION` roda a mesma checagem, só leitura, sobre um
  conjunto já gravado.

## O que muda na operação
Um valor que o worker não conseguiria carregar nunca mais chega à tabela por este script — a
janela entre "gravado" e "descoberto em produção" fecha. Continua existindo espaço para o mesmo
erro por uma via não coberta por este script (uma migração, um `UPDATE` manual); a lição de
"todo decimal entre aspas" (KB-0131) continua valendo como segunda camada.

## Segunda opinião (Astra)
Pendente.

## Relacionados
[[KB-0131-dado-mal-formado-derruba-o-processo-duas-vezes]] · `.claude/state/notes-T4.64.md` ·
`infra/scripts/meme_rule_set.py` · `infra/scripts/meme_rule_set_validate.py`
