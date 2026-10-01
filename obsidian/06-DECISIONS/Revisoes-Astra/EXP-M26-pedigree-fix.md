---
tags: [astra, revisao, pesquisa, exp-m26, h-022, instrumento, pedigree, meme-worker]
date: 2026-10-01
updated: 2026-10-01
status: fechada
owner: backend-specialist
decided_on: 2026-10-01
by: Astra + backend-specialist
---

# Revisão da Astra — conserto da leitura de pedigree do minuto (EXP-M26 F, 01/10/2026)

**Por que existe:** o funil F de [[EXP-M26-grafico-em-moedas-maduras]] reprovou por instrumento: a leitura de
pedigree do minuto levava 6–14 s para ~385 mints e o laço a corta aos 8 s, o que vira `pedigree_unknown` em todas as
linhas do minuto. O remédio foi acordado antes ([[06-DECISIONS/Revisoes-Astra/EXP-M26-F|EXP-M26-F]]): na via de 1 min,
ler só as duas contagens de `PEDIGREE_V1` quando nenhum conjunto do relógio pede `pedigree_repeat_dumper`; os campos
não lidos ficam ausentes, nunca zero; a pista de 15 s não muda; nada de filtrar pela porta pura. Aqui a Astra
revisou o diff que o implementa. O bruto está em `.claude/state/astra-review-exp-m26-pedigree-fix.md`.

**O que estava em jogo:**
- **Código:** `lab_repo_pedigree.py` (novo, extraído de `lab_repo_fast.py`), `lab_repo_e2b.lineage_for`, e os testes
  `test_pedigree_light.py` e `test_pedigree_light_integration.py`.
- **Medido na VPS (só leitura, minuto fechado de 387 mints):** leitura completa 6,93–7,69 s (5 rodadas) e `EXPLAIN
  ANALYZE` 9 154 ms; só as duas contagens 46,8–68,7 ms e `EXPLAIN ANALYZE` 39 ms; mesmas somas nas colunas comuns.
  Números e correção da §69 em `docs/DATABASE.md` ("Correção de 2026-10-01").

**O que ela disse e o que foi feito:**

| achado | decisão |
|---|---|
| **APPROVE_WITH_NITS, sem must-fix.** A leitura leve preserva as decisões da pista de 1 min; os diagnósticos omitidos viram `None` | absorvido |
| Consumidores que passam a ver `None`: só os **registros** (`proposals_reasons` e `lab_opportunities._pedigree`), nenhuma recusa nova; `scale_step` não recebe o pedigree; a sonda de recusados usa o da pista de 15 s, que segue completo | absorvido; escrito em [[EXP-M26-grafico-em-moedas-maduras]] como obrigação do F repetido (os dois campos ficam `null` em `meme_mature_opportunities.pedigree`) |
| O critério "todo conjunto é `1m` e nenhum pede o dumper" protege os consumidores de hoje: o chamador de 15 s só passa conjuntos `15s`; basta um conjunto `1m` com a chave ligada para todos receberem a completa | absorvido |
| `None` não elimina uma recusa de dump: com a chave desligada `evaluate_repeat_dumper` nem é chamado | absorvido; teste de equivalência das decisões (`evaluate_gate` com e sem os dois campos, cinco combinações das duas contagens) |
| O fallback "qualquer relógio que não seja `1m` recebe a leitura completa" é conservador para um relógio novo; não garante desempenho | absorvido; linha `refused` na matriz de `lineage_for` |
| Nice-to-have (LOW): a doc de `PedigreeFeatures` dizia que `creator_prior_dump_count` é `None` só com identidade desconhecida | **corrigido**: agora diz "ou quando a leitura não o pediu; `None` é 'não sabido', nunca zero" |
| Nice-to-have: teste de persistência via `mature_gate_step` com `null` nos diagnósticos | já coberto pelo teste existente `test_the_first_pass_is_recorded_once_with_the_inputs_of_its_tick`, que roda `_gate_step` → `lineage_for` real → `meme_mature_opportunities`; a asserção de `pedigree` mudou de `0, 0` para `None, None`, e o comentário diz por quê |
| Ela confirmou, com `git show HEAD`, que o SQL antigo e o novo são idênticos (3 218 caracteres, SHA-256 `6b42935c…b74d`) | coincide com o pin do teste |

**Sem divergência.** Limite da aprovação, dito por ela: foi revisão estática; os testes e o F repetido são a prova.
O F continua **a repetir** antes de J/S.

**Aprendizado de medição (vale para quem cronometrar leituras de colunas):** embrulhar a consulta em `SELECT … FROM
(consulta) q` e referenciar só as colunas baratas faz o Postgres podar as colunas caras da subconsulta; a primeira
cronometragem da leitura "completa" deu ~40 ms por isso. O externo precisa referenciar todas as colunas que a
consulta devolve.

**Depois:** as revisões do code-reviewer, do database-architect e do quant-engineer (todas aprovam com correções, sem
bloqueio) estão em [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix-revisoes|EXP-M26-pedigree-fix-revisoes]].

Relacionado: [[EXP-M26-grafico-em-moedas-maduras]] (conserto de 2026-10-01) · [[Open Bugs]] ·
[[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]] · [[06-DECISIONS/Revisoes-Astra/EXP-M26-F|EXP-M26-F]]
