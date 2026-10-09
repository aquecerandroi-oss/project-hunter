---
tags: [revisao-astra, meme, copiar-carteiras, h-037, exp-m28, papel, fronteira, guardiao, execucao]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: risk-engine-guardian
decided_on: 2026-10-09
by: astra
tarefa: revisão R4 do desenho do H-037, limitada à fronteira: algo que a pista de cópia em papel escreve (commit 0736023a) pode chegar a dinheiro real?
veredito: "REQUEST_CHANGES estreito, depois fechado. Nenhum caminho de ordem real: provado por sonda contra Postgres. Os dois acoplamentos indiretos com a mesa real (pedigree e pinos, F1/F2) foram corrigidos em a46bad1d e conferidos na re-revisão. F3 (claim da pista de lançamento sem escopo) foi corrigido na mesma tarefa, com teste. F4 segue aberto."
---

# Revisão do guardião: a fronteira da pista de cópia (R4 do H-037)

Pergunta única, do desenho §8: **algo que a pista de cópia escreve pode chegar a dinheiro real?** Escopo: o
commit `0736023a` (`services/meme-worker/hunter_meme_worker/copy_*.py` e os testes), mais o isolamento do Lab ainda
não commitado da tarefa I ([[copy-lab-isolation]]). Contexto: [[copy-lane]] · [[EXP-M28-copiar-carteiras-no-papel]] ·
[[Dialogos/copy-paper|copy-paper]] (DECISÃO CONJUNTA, rodada 4: "isolamento e fronteira ... não substitui a prova
integrada").

## O que foi lido antes (e o que mudou no plano)

- [[00-HOME]]: "nenhum agente executa ordens". Em 30/09 a mesa meme real estava pausada. Por isso F1 e F2 estão
  **latentes** hoje e viram acoplamento vivo quando a mesa voltar.
- [[KB-0149-o-que-a-mesa-real-ensinou]] item 28: ligar critério novo na mesa real não é sombra; sombra é braço
  `research_only`. F1 e F2 são exatamente um braço `research_only` vazando para a mesa real.
- O desenho §3.6 e §8 (MF6): os três escritores possíveis de `mode = 'live'` foram o roteiro da busca.
- `lab_repo_pedigree.py:150-163` (T4.85, T4.91, T4.95, EXP-M26, H-031b): todo braço de pesquisa com apostas em mints
  que a mesa não olha já foi subtraído do pedigree por id, porque "mudaria as recusas `creator_repeat_dumper` da
  mesa real". Esse precedente transformou a observação da Astra em F1.

## Veredito: nenhum caminho de ordem

- **Nascimento.** A única inserção é `copy_repo._draft` → `lab_repo.insert_proposals`, com status `approved`/`rejected`,
  `decided_by = 'rules:copy'` e `origin = 'rules'`. O `mode` nunca é escrito; vale o padrão `'paper'`
  (`infra/migrations/ddl/meme_live.py:223`).
- **Uma transação por escrita.** É `approved` + `mark_filled`, ou `approved` + `mark_unfilled` (`copy_exec_entry.py`).
  Linha de cópia commitada só existe como `filled`, `unfilled` ou `rejected`; `approved` só existe dentro da transação.
  Isso é **mais estrito que o desenho**, que previa a linha nascendo `approved` antes do preço.
- **Leitores que promovem ou executam:**

  | Leitor | Filtro | Linha de cópia passa? |
  |---|---|---|
  | `approval.py:57` (`DECIDE_PROPOSAL`) | `status = 'proposed'` | não |
  | `repo.py:111` (executor) | `mode = 'live'` | não |
  | `auto_approve.py:110` | `kind = 'operator'` e `status = 'proposed'` | não |
  | `launch_repo.py:43` | nome `launch_v0` e série em Python | não |

  A pista não publica em `meme:proposals:wake` e não escreve em `meme_live_orders`. O kill switch e o `risk-core` não
  leem `meme_paper_bets` nem `meme_proposals`.
- **Conjuntos.** O `copy_spec._LOAD` exige `kind = 'research_only'` e `clock = 'copy'`: semente com outro `kind` não
  carrega, e a pista falha fechada.
- **Saídas.** Só passam por `paper_engine.close_bet`/`close_bet_row`. Nada na pista importa o executor.
- **Sonda contra Postgres.** Linhas escritas pela pista real; depois foram chamados `live_candidates`,
  `launch_candidates`, `operator_proposals` e `decide_proposal(mode=live)`. Resultado: nenhuma linha devolvida,
  nenhuma movida, 0 ordens, modos `{'paper'}`. A mesma sonda mostrou F3.

## Achados

| # | Onde | Gravidade | Achado e cenário | Estado |
|---|---|---|---|---|
| F1 | `lab_repo_pedigree.py:81-87` com `creator_watch.py:70-72,81` | MÉDIA (dinheiro), ALTA (pesquisa) | O `creator_watch` carimba `creator_sold_seen_at` em toda aposta de papel aberta. O pedigree não subtrai os conjuntos de cópia. Cenário: um líder compra uma moeda do criador C que a mesa nunca olhou. C vende com a cópia aberta. A moeda seguinte de C recebe `REPEAT_DUMPER_REFUSAL` (`pedigree.py:177`) na linha real e nos braços de papel. A direção é só recusa: nenhuma entrada nasce disso | corrigido em `a46bad1d` (tarefa I), conferido; [[Open Bugs]] |
| F2 | `tracker_pins.py:69-77` | MÉDIA (dinheiro), ALTA (pesquisa) | As apostas de cópia abertas entram nos pinos comuns, até 2 × 100 mints por até 3 600 s. Cenário (o mesmo da T4.91): o pino mantém `meme_features_1m.creator_sold` sendo escrito (o caminho que nenhum id subtrai) e estreita o teto do rastreador para os candidatos da mesa. A pista não precisa dos pinos, porque precifica por leitura própria na cadeia | corrigido em `a46bad1d` (tarefa I), conferido; [[Open Bugs]] |
| F3 | `launch_repo.py` `_CLAIM` | BAIXA (endurecimento) | O claim escrevia `mode = 'live'` filtrando só pelo id. A sonda mostrou que reivindicaria linhas de cópia `filled`/`unfilled`/`approved` (em transação desfeita). Cenário: um chamador futuro que passe outro id manda uma cópia para o executor | **corrigido** nesta tarefa, ver abaixo |
| F4 | `test_copy_boundary_integration.py:38-39,86-92` | BAIXA (teste) | O gatilho grava só `status`. O "nunca live" lê `meme_paper_bets.mode`, que já tem `CHECK (mode = 'paper')`, então não pode falhar. Cenário: uma mudança que grave `mode = 'live'` na inserção da cópia passa no teste. Conserto: gravar `NEW.mode` no gatilho | aberto (tarefa C) |

**Re-revisão de F1/F2 (09/10, `a46bad1d`).** O filtro é por `params ->> 'clock' = 'copy'`, não por id, porque os ids
só nascem com a semente E.

- Ele está nos dois ramos de `meme_paper_bets` do `_DUMP_COUNT` e nos dois ramos do `_ORDINARY_PINNED_MINTS`.
- `test_lab_copy_pedigree_pins.py`, `test_pedigree_light.py` e `test_lab_copy_isolation.py`: `42 passed, 1 xfailed`.
  O teste do pedigree tem controle: a aposta comum conta, a de cópia não.
- O único outro leitor do carimbo é `creator_stats`, uma estatística sem decisão.
- **Resíduo, sem dinheiro:** a prioridade `TIER_OPEN_BET` do `repo_tape._OPEN_BETS` só ordena as leituras REST de mints
  já rastreados (`collect.py:185`). O `prune` não a lê, então ela não reabre o caminho do `creator_sold`. É o item 3 de
  [[copy-lab-isolation]].

**Ainda aberto, do desenho §8:** o ensaio automático que roda aprovação manual, aprovação automática, pista de
lançamento em `on`, *polling* e *wake* com linhas de cópia presentes. Ele fica com a E2E.

## F3: o que foi feito

- **Teste primeiro.** `services/meme-executor/tests/test_launch_claim_scope_integration.py` roda contra Postgres, como
  `hunter_worker`, com cada claim desfeito no fim. Cobre três linhas de cópia (`approved`/`filled`/`unfilled`), uma
  linha `launch_v0` sem o rótulo `series` e o controle: uma proposta de lançamento rotulada.
- **Antes do conserto:** `4 failed, 1 passed`, todos em `assert (True, 'live') == (False, 'paper')`.
- **O conserto.** Um fragmento `_LAUNCH_SCOPE` agora é compartilhado pelo `_CANDIDATES` e pelo `_CLAIM`, para os dois
  não divergirem. Ele cobre nome do conjunto, conjunto ativo, `origin`, `mode` e status. O `_CLAIM` também confere
  `reasons[0].series = LAUNCH_SERIES`, a regra do `is_launch`.
- **Depois do conserto:** 7 casos, incluindo os da Astra (conjunto aposentado; rótulo de série num conjunto de cópia;
  releitura externa depois de cada rollback). Os 6 negativos falham no SQL antigo com `(True, 'live')` e passam no novo.
  Com os testes de lançamento (`test_launch_integration.py` é o claim real de ponta a ponta): `39 passed`.
- **Suíte inteira do `meme-executor`:** `3 failed, 1211 passed`. As 3 falhas são de `test_live_persistence.py` (fase 1 da
  aprovação automática), recusadas por `curve_state_clock_skew` e **intermitentes**. Com o `launch_repo.py` do HEAD
  deram `1 failed, 2 passed`; com o conserto, `3 passed`. Não têm relação com F3.

## Segunda opinião (Astra)

Transcrição: `.claude/state/astra-review-guardian-copy-boundary.md`.

- A Astra não achou must-fix no caminho direto.
- Concordou que F3 é endurecimento e que o teste do gatilho é insuficiente (F4).
- No F3, aprovou o diff sem must-fix (`.claude/state/astra-review-guardian-f3-claim-scope.md`); as três coberturas
  que ela sugeriu entraram no teste.
- Levantou o carimbo do `creator_watch` no pedigree. Conferi no código e confirmei: é F1. A variante dos pinos (F2)
  eu achei na mesma linha de busca.
- **Gravidade de F1/F2.** A revisão [[copy-lab-isolation]] chamou os dois de ALTA, olhando a pesquisa. Aqui ficam
  MÉDIA do ponto de vista do dinheiro, porque só acrescentam recusas. As duas leituras valem, e o conserto é o mesmo.
- **Aviso registrado.** Durante a chamada, o `astra.sh` acusou mudanças na árvore em arquivos da tarefa A
  (`leader_source_*`, `rpc.py`). A Astra diz que não alterou nada; a causa provável é outro agente em voo, sem
  confirmação.

## Lição

Todo braço de papel novo que segura apostas em mints que a mesa não olha precisa entrar nas duas listas de exclusão:
o pedigree (`pedigree_params`) e os pinos (`tracker_pins`). Não basta tirá-lo do Lab. Já são cinco precedentes, e a
cópia seria o sexto esquecido.

## Relacionados

[[copy-lane]] · [[copy-lab-isolation]] · [[EXP-M28-copiar-carteiras-no-papel]] · [[Open Bugs]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]]
