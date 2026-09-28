---
tags: [astra, revisao, banco, exp-m26, pesquisa]
date: 2026-09-28
updated: 2026-09-28
status: fechada
owner: sexta-feira
decided_on: 2026-09-28
by: Astra + database-architect
---

# Revisão da Astra — histórico de estado das moedas para a leitura do EXP-M26 (28/09/2026)

**Por que existe:** o must-fix 2 aberto na especificação J da H-022 ([[EXP-M26-grafico-em-moedas-maduras]]) — `completed_at`/`migrated_at` podem ser corrigidos depois, e uma correção chegando depois do corte L podia virar o veredito. Decisão da Sexta-feira: gravar o histórico e ler "o que se sabia em L".

**O que ficou (migração `0067_meme_token_state_history`):** tabela só de acréscimo alimentada por gatilhos **adiados para o commit** (`CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED`, carimbo `clock_timestamp()` no commit), função `SECURITY DEFINER` sem INSERT para nenhum papel; ordem por `id`; o export do J ganhou **prova de visibilidade** (nenhuma escritora aberta desde ≤ L, sem transação preparada, relógio sem recuo, papel que vê toda a atividade) e recusa sem ela; estado não comprovado pelo histórico vira censura, nunca "vendeu com a curva viva".

**Rodadas da Astra:** 1 — gatilho imediato carimbava minutos antes do commit ficar visível (corrigido com gatilhos adiados); 2 — margem de 60 s fazia dois exports lerem L diferente (removida; prova de visibilidade); 3 — furos da prova (`MEMBER`×`USAGE`, `track_activities`, 2PC, relógio) fechados; 4 — **"must-fix 2 fechado"**. Não feitos e declarados: teste real de 2PC (servidor de teste sem `max_prepared_transactions`) e dono `NOLOGIN` dedicado para a função.

**Pendente para o Everton/orquestrador:** o que fazer se a janela [L, L+1 h] fechar sem nenhum export com prova (hoje a leitura não roda).

Brutos: `.claude/state/astra-review-token-state-history{,-r2,-r3,-r4}.md`. Relacionado: [[2026-09-27]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
