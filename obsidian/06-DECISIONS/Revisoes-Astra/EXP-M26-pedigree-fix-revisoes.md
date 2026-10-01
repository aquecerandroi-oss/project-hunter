---
tags: [astra, revisao, pesquisa, exp-m26, h-022, instrumento, pedigree, meme-worker]
date: 2026-10-01
updated: 2026-10-01
status: fechada
owner: backend-specialist
decided_on: 2026-10-01
by: code-reviewer + database-architect + quant-engineer (reconciliadas com a Astra)
---

# As três revisões do conserto de pedigree do minuto (EXP-M26 F, 01/10/2026)

**Por que existe:** depois da [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix|revisão da Astra]] (APPROVE_WITH_NITS), o
code-reviewer, o database-architect e o quant-engineer revisaram o mesmo diff. Os três aprovaram **com correções, sem
bloqueio**. Esta nota registra o que cada um achou e o que foi feito na mesma mudança. Os textos brutos das revisões
vivem nos relatórios dos agentes, não em arquivo; aqui consta só o que o coordenador repassou, nada além disso.

| revisor | achado | decisão |
|---|---|---|
| código | o bloco `pedigree` de `proposals_reasons.py` não dizia que `None` na via de 1 min é "não lido" | **feito**: comentário `# None on the light 1m read (EXP-M26 F): not read, never zero` |
| código | quando um conjunto `1m` liga `pedigree_repeat_dumper`, a pista volta à leitura de 6–14 s sem aviso | **feito**: `lineage_for` emite `meme_pedigree_full_read_on_1m_lane` (warning, com `sets` e `mints`); teste novo |
| código | o teste da leitura completa usava `<=` nas chaves de parâmetro | **feito**: o teste afirma o conjunto **exato** das 8 chaves |
| código | a docstring de `evaluate_repeat_dumper` ainda dizia que `None` é só identidade desconhecida | **feito**: agora diz "ou a leitura não pediu a contagem"; teste novo fixa que um conjunto com a chave nunca recebe a leitura leve (3 relógios × 3 composições de pista) |
| código | `ruff check .` vermelho no CI por `F811` em `opportunity/history.py` (commit `057a8f1b`) | **feito**: a definição de `sparse_history_policy` estava duplicada, e a constante `HISTORY_POLICY_V2` também; removi as cópias, os 1 451 testes de `packages/indicators` passam |
| banco | a §69 dizia que a §66 media "~320 mints sem as contagens de dump/dead"; falso: a §66 mediu 3,3 s frio / 2,9 s quente com 329 mints **sem** `symbol_dup_24h` e **com** dump/dead; o "~3 s com o índice" foi inferência; o salto para 6–14 s não foi decomposto | **corrigido** em `docs/DATABASE.md` §69 e em [[Open Bugs]] (acréscimo datado) |
| banco | `pedigree` ganhou um terceiro estado: objeto presente com os dois diagnósticos `null` = "não lidos"; identidade desconhecida é `creator_prior_mints_1h IS NULL` | **documentado** na §68 (e em `meme_proposals.reasons`) e no [[Dicionario de Variaveis]] |
| banco | ligar `pedigree_repeat_dumper` em qualquer conjunto `1m` põe a pista inteira na leitura completa, cortada aos 8 s na maioria dos minutos | **registrado** como condição de ativação (§69, docstring de `lineage_for`, [[Open Bugs]]): não ligar sem índice medido ou prova de carga |
| banco | **defeito já em produção, anterior ao conserto:** a leitura **completa** da pista de 15 s estoura o corte de 8 s 2–5 vezes por hora desde 30/09 ~15h (`57014`, ~127–133 mints; 3,09–3,24 s para 126 mints); ~1–2 % dos ticks, todos os conjuntos de 15 s recusam por `pedigree_unknown` | **aberto** em [[Open Bugs]]; hipótese **não medida**: índice parcial em `meme_features_1m (mint, end_time) WHERE creator_sold`; dono database-architect + backend-specialist. O conserto do F não mexe nisso de propósito |
| quant | com nenhum conjunto `1m` ativo antes da semente, o F repetido **não consegue exercitar a leitura leve** em produção | **registrado** como próxima tarefa (medidor de produção) na página [[EXP-M26-grafico-em-moedas-maduras]]; **não implementado aqui** |
| quant | a guarda do desenho "apostas abertas do EXP-M26 ≤ 10 em qualquer janela de 15 min" é ambígua | **registrado**: tem de ser corrigida por texto antes de semear (detalhe na página do EXP-M26) |

**Divergências:** nenhuma entre os três e a Astra. O que só um revisor achou (a falha da pista de 15 s, o medidor de
produção, a ambiguidade da guarda) entrou como registro em [[Open Bugs]] e na página do EXP, sem ser tratado como provado
além do que cada nota diz.

Relacionado: [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix|EXP-M26-pedigree-fix]] ·
[[EXP-M26-grafico-em-moedas-maduras]] · [[Open Bugs]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
