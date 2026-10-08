## RESUMO

**Aprovo os ajustes na revisão estática. Não encontrei must-fix remanescente.** Há duas melhorias pequenas no teste concorrente e uma referência documental antiga.

**1. `FOR NO KEY UPDATE` protege os caminhos citados.**

`--set-param` executa `UPDATE params`; `--deprecate` executa `UPDATE status, retired_at`. Ambos conflitam com a trava escolhida. Ela precede as guardas e permanece na transação da migração. [Parâmetros](C:/dev/project-hunter/infra/scripts/meme_rule_set_params.py:53), [aposentadoria](C:/dev/project-hunter/infra/scripts/meme_rule_set.py:128), [ordem das operações](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:141), [transação](C:/dev/project-hunter/infra/migrations/env.py:136).

Alterar `id` ou valores de `name/version` também **não escapa**: o `FOR UPDATE` adquirido nessa atualização conflita com `FOR NO KEY UPDATE`. Precisão: existe PK em `id` e unicidade **composta** em `(name, version)`. [Constraints](C:/dev/project-hunter/infra/migrations/ddl/meme_lab.py:95). A compatibilidade com `FOR KEY SHARE` permite a checagem de FK sem liberar atualizações da linha. [PostgreSQL 16 — conflitos entre locks](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS).

Isso protege a cópia durante a transação; uma edição que chegou depois pode executar após o commit, como o pré-registro agora explica. [EXP-M27](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M27-gemeo-sem-creator-dump.md:54).

**2. `pg_blocking_pids`: avanço suficiente, com uma ressalva de precisão.**

A consulta pergunta se **algum backend** está bloqueado pelo segurador; não fixa o PID da migração. `worker.is_alive()` também não estabelece essa identidade. [Consulta](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:42), [espera](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:203).

Um falso positivo exigiria outro cliente bloqueado pelo segurador enquanto a migração ainda estivesse atrasada antes das guardas. **Não identifiquei esse terceiro cliente na fixture atual**, que usa banco próprio; portanto, não classifico a possibilidade como must-fix. [Fixture](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:52).

Pode haver falso negativo se a migração demorar mais que a janela de espera para alcançar a trava. Além disso, “30 s” é aproximado: são 120 iterações, somadas ao tempo das consultas. [Loop](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:206).

**3. Patch e linearização estão coerentes.**

- A `0070` desce da gêmea `0069`; seu teste usa os mesmos identificadores. [Migração](C:/dev/project-hunter/infra/migrations/versions/0070_meme_mature_chart_arms.py:36), [teste](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0070.py:40).
- A árvore completa espera `0070/30`; o patch prepara `0069/27` e **aplica no índice atual**. Ele é relativo à base `0068`, não um patch para aplicar sobre o arquivo de trabalho já em `0070`. [HEAD](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:43), [contagem](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:4544), [patch](C:/dev/project-hunter/.claude/state/h031b/test_migrations.twin-only.patch:4).
- O teste de wallet aponta para a gêmea. Sua referência antiga a `0068_meme_mature_chart_arms.py` verifica justamente que esse arquivo **não existe**; está correta. [Teste](C:/dev/project-hunter/packages/core/tests/integration/test_migration_wallet_exceptions.py:115).
- O `0068` de `lab_opportunities.py` é apenas docstring desatualizado, sem efeito na execução. [Referência](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_opportunities.py:87).

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit.

## TESTES

Verificações executadas:

- `git apply --check --cached .claude/state/h031b/test_migrations.twin-only.patch` → saída vazia, **exit 0**.
- `git diff --check -- infra/migrations packages/core/tests/integration/test_migrations.py packages/core/tests/integration/test_migration_wallet_exceptions.py docs/DATABASE.md` → saída vazia, **exit 0**.

**Não executei pytest, migrations ou mutantes.** Os resultados de PG16 e mutação informados no pedido não são uma execução minha.

## MUST-FIX

Nenhum identificado nesta rodada.

## NICE-TO-HAVE

- Identificar explicitamente o backend da migração na consulta de bloqueio. [Consulta atual](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:42).
- Guardar a thread retornada e verificar `not worker.is_alive()` após `join(timeout=120)`. [Join atual](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:219).
- Trocar `0068` por `0070` no [docstring](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_opportunities.py:87).

## O QUE EU FARIA DIFERENTE

Validaria a suíte sobre o conteúdo exato do commit da gêmea antes da entrega. O patch passou na checagem de aplicação; isso ainda não prova a suíte no estado intermediário `0069/27`, previsto no [contrato de entrega](C:/dev/project-hunter/docs/DATABASE.md:8924).

## CONCORDO COM

A troca da trava, o teste que distingue bloqueio de edição de bloqueio de FK e a quinta guarda com mensagem específica. [Trava](C:/dev/project-hunter/infra/migrations/ddl/meme_absorb_semdump_arm.py:77), [teste concorrente adicional](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069_guards.py:231), [teste da quinta guarda](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0069.py:302).

## OBSIDIAN

- **H-031b-db-review** — registrar aprovação estática da rodada 2 e a ressalva sobre identificar o backend bloqueado.
- **EXP-M27-gemeo-sem-creator-dump** — acrescentar o fechamento da revisão, distinguindo-o da validação executada do commit `0069/27`.