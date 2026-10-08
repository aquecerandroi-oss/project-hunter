---
tags: [revisao-astra, meme, creator-dump, gemeo, migracao, banco, h-031b, exp-m26]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: database-architect
decided_on: 2026-10-07
by: astra
tarefa: revisão de banco da `0069_meme_absorb_semdump_arm` (gêmeo da H-031b) e linearização das duas cabeças sobre a `0068` (a semente retida do EXP-M26 virou `0070_meme_mature_chart_arms`)
veredito: "APPROVE da 0069 depois de três ajustes aplicados pelo database-architect (trava FOR NO KEY UPDATE, quinta guarda, teste da corrida sem sleep); uma cabeça só (0070); a 0070 fica fora do commit implantável até o J do EXP-M26 congelar"
---

# Revisão de banco — o gêmeo da H-031b e a linearização 0069/0070

**Pedido:** rever a migração que semeia `absorb_semdump_v0/1` ([[EXP-M27-gemeo-sem-creator-dump]], `docs/DATABASE.md`
§72): trava e corrida, idempotência, downgrade, RLS/grants, pós-checagem, se os testes exercitam as guardas; e
linearizar as duas filhas da `0068` (a gêmea e a semente retida do [[EXP-M26-grafico-em-moedas-maduras]]).
Transcrições: `.claude/state/astra-review-db-0069-twin.md` (rodada 1) e `astra-review-db-0069-twin-r2.md` (rodada 2).

## O que a Astra disse (rodada 1) e o que foi feito

- **Concordou:** copiar o `params` vivo, travar a origem antes das guardas, repetir o predicado válido na cópia e na
  pós-checagem, recusar identidade incompatível (o erro de PK num `…0022` de outro nome é desejável), nenhum grant
  novo (`meme_rule_sets` é global, §34.1).
- **Must-fix 1 (alinhar `HEAD_REVISION` e contagem com cada commit):** feito. Árvore com as duas: `0070` e 30 ativos.
  Commit só da gêmea: `HEAD = 0069_meme_absorb_semdump_arm` e 27, num patch pronto
  (`.claude/state/h031b/test_migrations.twin-only.patch`, `git apply --cached --check` passa).
- **Must-fix 2 (o teste da corrida podia passar sem a trava, por depender de `sleep(3)`):** aceito. O teste agora
  espera `pg_blocking_pids` conter o backend que segura a linha (até 30 s). Mutante "sem trava" (`AND false` no
  `_LOCK`): o teste falha.
- **Nice-to-have aceito:** a quinta guarda (`meme_mature_opportunities`, a quinta chave estrangeira para
  `meme_rule_sets`), com caso no teste; e a frase da §72 sobre `--set-param` corrigida: o que chega **depois** da
  trava espera e grava depois, sem ser julgado pela migração.
- **Nice-to-have não feito:** testar original ausente, colisão só de PK e reaplicação com gêmeo correto — os
  caminhos são `NOT EXISTS` e erro de PK do próprio Postgres; ficam registrados como lacuna de teste.

## Achado do database-architect que a Astra não levantou

**`FOR UPDATE` travaria as inserções do worker.** Toda checagem de chave estrangeira toma `FOR KEY SHARE` na linha
referenciada, e `FOR UPDATE` conflita com ela. Com `FOR UPDATE`, toda inserção de proposta, aposta ou recusa de
`absorb_v0/2` esperaria a transação inteira da migração, e a migração esperaria qualquer transação do worker aberta com
uma linha dessas. Medido num Postgres 16 descartável: inserção filha bloqueada com `FOR UPDATE` e livre com `FOR NO
KEY UPDATE`; o `UPDATE` de `params` (o `--set-param`) bloqueado nos dois. Trocado para `FOR NO KEY UPDATE`, com teste
novo (`test_the_lock_stops_an_edit_of_the_original_but_not_the_workers_inserts`); o mutante `FOR UPDATE` faz esse teste
falhar. Lição geral: para "congelar o conteúdo de uma linha" numa migração que roda com o sistema no ar, a trava certa
é `FOR NO KEY UPDATE`.

## Rodada 2

**Sem must-fix.** Ela confirmou que `FOR NO KEY UPDATE` segura `--set-param` (`UPDATE params`) e `--deprecate`
(`UPDATE status, retired_at`), e que mudar `id`/`name`/`version` também não escapa (esse `UPDATE` toma `FOR UPDATE`,
que conflita com a trava). Nice-to-have aceito: o teste da corrida confere que a thread terminou depois do `join`.
Nice-to-have não feito: identificar o backend da migração na consulta de bloqueio — o banco do teste é exclusivo do
arquivo, então não há terceiro cliente que produza um falso positivo. O docstring velho de
`lab_opportunities.py` ("`0068`'s seed") foi corrigido; o comentário igual em `lab_repo_pedigree.py` ficou, porque o
arquivo já estava no commit `3c056c3a` de outra tarefa.

**O que ela faria diferente, e foi feito:** validar o estado exato do commit da gêmea. Numa worktree isolada com HEAD
mais só os arquivos da gêmea e o patch `0069/27`: os testes de cabeça, de ids e de contagem (4 passed) e os dois
arquivos da `0069` (18 passed).

## Onde isto vive

[[EXP-M27-gemeo-sem-creator-dump]] · [[EXP-M26-grafico-em-moedas-maduras]] · [[H-031b-diff]] · [[H-031b-prereg]] ·
[[Fila de Hipoteses]] (H-031b) · [[Revisoes-Astra/Index|índice das revisões]]
