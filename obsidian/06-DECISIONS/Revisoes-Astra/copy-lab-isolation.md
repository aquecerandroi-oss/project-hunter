---
tags: [revisao-astra, meme, copia, piloto, h-037, lab, isolamento, launch-lane]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: backend-specialist
decided_on: 2026-10-09
by: astra
tarefa: tarefa I do desenho do piloto de copiar carteiras no papel (H-037) - tirar as linhas da pista de cópia (params.clock = 'copy') do alcance do Lab (lab_repo.py, lab_repo_bets.py)
veredito: sem bloqueador nos filtros centrais; pedigree e pinos do rastreador corrigidos depois do pedido do guardião (F1/F2); três achados laterais entregues ao orquestrador; a corrida do launch_v0 confirmada e não alterada
---

# Revisão da Astra: o Lab não toca nas linhas da pista de cópia (09/10/2026)

Fonte citada (não substitui esta nota): `.claude/state/astra-review-copy-lab-isolation.md`. Experimento: [[EXP-M28-copiar-carteiras-no-papel]]. Desenho: `docs/design/copiar-carteiras-papel.md` §3.6 e tarefa I.

## O problema, medido antes do conserto

Um teste de integração contra Postgres (`services/meme-worker/tests/test_lab_copy_isolation.py`) virou um conjunto de regras para `params.clock = 'copy'` depois de as linhas existirem e rodou o `lab_tick` real. Antes do conserto, pelos motivos certos:

- a proposta `approved` da cópia saiu `unfilled/rule_set_inactive` (o `_RULE_SETS` não consegue montar um conjunto de relógio `copy`, porque `'copy'` não está em `CLOCKS`, então não há spec);
- a aposta aberta da cópia recebeu do Lab `exit_intent = target` na foto seguinte, sem a latência da pista;
- o contador `lab_bets_indeterminate_total` contava a cópia censurada;
- cada tick registrava `meme_rule_set_load_failed` e contava o erro para um conjunto saudável;
- um `cancel` do operador rejeitava a proposta da cópia, e uma linha `rejected` é lida na reinicialização da pista como "não admitida", liberando a chave (estrato, mint).

## O que mudou (só SQL; nenhuma coluna, nenhuma tabela)

| Onde | Mudança |
|---|---|
| `lab_repo._RULE_SETS` | `AND COALESCE(params ->> 'clock','') <> 'copy'` ao lado do `<> 'event'` |
| `lab_repo._APPROVED` | `NOT EXISTS` do conjunto de relógio `copy` |
| `lab_repo._CANCEL` | o mesmo `NOT EXISTS`; o comando é respondido `refused` por nome |
| `lab_repo_bets._OPEN_BETS` | o mesmo `NOT EXISTS` |
| `lab_repo_bets._INDETERMINATE` | o mesmo `NOT EXISTS` |
| `lab_repo_pedigree._DUMP_COUNT` (F1, guardião) | as duas fontes `meme_paper_bets` de `creator_prior_dump_count` ganham `NOT EXISTS (... prs.params ->> 'clock' = 'copy')`. **O texto SQL fixado por hash em `test_pedigree_light` mudou de propósito** (3 218 → 3 635 caracteres; sha256 antigo `6b42935c…ceb74d`, novo `378a7a44…45b67f`); sem conjunto de cópia no banco, as linhas devolvidas são as mesmas |
| `tracker_pins._ORDINARY_PINNED_MINTS` (F2, guardião) | apostas abertas e propostas `proposed` de conjuntos `clock = 'copy'` não fixam mint |

A pista de cópia lê as próprias apostas abertas (`copy_repo._OPEN_COPIES`), então o Lab perde a visão e a pista não perde nada. Uma chave `copy_lane=True` que eu tinha acrescentado a `load_open_bets` saiu: sem uso, seria código especulativo.

## Segunda opinião (Astra) e decisões

| # | Achado da Astra | Decisão |
|---|---|---|
| 1 | HIGH: `copy_repo` lia as apostas pelo `load_open_bets` e, com o filtro, recuperaria lista vazia na reinicialização | **Já resolvido pela pista:** `copy_repo.py` passou a ter leitura própria (`_OPEN_COPIES`, docstring cita a tarefa I). Conferido no arquivo. A chave `copy_lane` que eu havia criado foi removida |
| 2 | HIGH: o `creator_watch` ainda escreve `creator_sold_seen_at` nas apostas de cópia (por mint), e o pedigree do Lab usa esse carimbo como "o criador vendeu antes" (`lab_repo_pedigree.py:81-94`), então a cópia pode recusar um token novo do mesmo criador por `creator_repeat_dumper` | **Confirmado e corrigido (F1 do guardião, mesmo achado).** O precedente da casa (subtrair por id, [[EXP-M27-gemeo-sem-creator-dump]]) não serve porque os ids só existem na semente (tarefa E); a exclusão é pelo relógio, dentro do SQL, o que muda o hash fixado de propósito. Teste: `test_a_copy_bets_creator_sale_does_not_count_as_a_prior_dump` (controle ordinário = 1, cópia = 0) |
| 3 | HIGH: as apostas de cópia entram em `tracker_pins` (reduzem o teto efetivo do rastreador) e em `repo_tape._OPEN_BETS` (prioridade `TIER_OPEN_BET` na coleta compartilhada) | **`tracker_pins` corrigido (F2 do guardião)**, com testes para aposta aberta e proposta `proposed`. **`repo_tape._OPEN_BETS` segue aberto, sem alteração:** a prioridade na coleta compartilhada precisa de decisão do orquestrador (a pista de cópia lê a própria cadeia) |
| 4 | MEDIUM: `sell_now` do operador sobre uma cópia aberta recebe `refused/bet_not_open` do Lab (diagnóstico enganoso; nada é vendido) | **Registrado.** A mensagem certa nasce na API (`meme_desk_commands.py`), fora do escopo |
| 5 | HIGH, preexistente: corrida do `launch_v0` | Ver a seção seguinte |
| n | `events_repo.py:90` acrescenta `event_id` a qualquer proposta do mint, inclusive de cópia | **Registrado:** enriquecimento compartilhado, sem efeito em fill/marca/saída; se "dono único" quiser dizer nenhuma coluna alterada por terceiros, vira exclusão |
| n | `cancel` de proposta de cópia: o produtor atual insere proposta e fill na mesma transação, então a janela normal não é a de 1,65 s | **Aceito como endurecimento do contrato:** o filtro do `_CANCEL` existe e tem teste, sem afirmar que a corrida acontece com o produtor atual |

**Concordâncias:** os quatro filtros centrais corrigem os caminhos de cópia; a pista de pool e o resgate pontual só recebem a aposta que o `process_open_bets` selecionou, então herdam o filtro; carteira, exposição, sondas, escalas e oportunidades são delimitadas por `rule_set_id`. **Discordância:** nenhuma de fundo. Eu mantive o padrão restritivo (a visão do Lab exclui cópia) como ela recomendou.

## O achado lateral: `launch_v0` (`clock = 'event'`)

Confirmado por leitura e por um teste `xfail(strict)` (`test_the_lab_leaves_an_approved_launch_lane_proposal_alone`). **Nada foi alterado.**

- `launch_lane_entry.py:114` grava a proposta `approved` (conjunto de pesquisa); `launch_lane_eval.py` a persiste e só depois abre o watch; `launch_lane_bets.open_launch_bet` chama `mark_filled` quando chega o primeiro ponto em ou depois de `created_at + 1 s`.
- `lab_repo._RULE_SETS` já pula os conjuntos `event` (T4.67c), então o Lab não tem spec deles; `_APPROVED` não os exclui. Se um tick do Lab (a cada `lab_cycle_s` = 15 s) cai entre o commit da proposta e o `mark_filled`, o `fill_approved` (`lab_bets.py:101-106`) marca `unfilled/rule_set_inactive`.
- `mark_filled` insere a aposta primeiro e depois faz `UPDATE ... WHERE status = 'approved'` sem conferir quantas linhas mudaram. Resultado: **aposta aberta sem o vínculo `bet_id`, com a proposta `unfilled`**. A janela vai do commit ao `UPDATE` do fill e pode passar de 1 s sem ponto elegível. A frequência em produção **não foi medida**; contar propostas `launch_v0` `unfilled/rule_set_inactive` com aposta cujo `proposal_id` aponta para elas diz quantas já aconteceram.
- Separado: as apostas `event` abertas entram no `process_open_bets` e podem receber foto, `sell_now` ou saída por migração do Lab enquanto a pista as administra na memória. `launch_lane_bets.py:46` documenta a intenção de o Lab resgatar órfãs, mas o leitor não distingue órfã de aposta administrada. Não mexer em `event` sem decidir o resgate de órfãs.

## Relacionado

[[EXP-M28-copiar-carteiras-no-papel]] · [[copy-leader-selection]] · [[H-037-prereg]] · [[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[EXP-M18-sniper-de-lancamento]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Open Bugs]]
