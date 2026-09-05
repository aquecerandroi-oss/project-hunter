**RESUMO**

**As correções resolvem os cenários originais, com uma ressalva no backfill e cobertura ainda parcial do aceite S0.** Revisei como `database-architect`. Não identifiquei regressão funcional nas alterações, mas não executei os testes de banco nesta rodada.

| Correção | Parecer |
|---|---|
| **1 — Decimal** | **Resolvida.** A montagem por `as_tuple()` preserva os dígitos sem operações sujeitas à precisão do contexto. Os novos testes cobrem arredondamento, colisão anterior e expoentes: [canonical.py:66](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:66), [testes:126](/C:/dev/project-hunter/packages/core/tests/unit/test_strategies_canonical.py:126). |
| **2 — Backfill** | **Resolve os casos legados coerentes**, incluindo encerrado e aberto com entrada. Não resolve o caso contraditório da pergunta **a**, detalhado abaixo: [migração:221](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:221). |
| **3 — Coorte** | **Resolvida.** `fullmatch()` elimina a aceitação do newline final; o vetor passa na execução desta rodada: [enums.py:328](/C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:328), [teste:151](/C:/dev/project-hunter/packages/core/tests/unit/test_domain_enums.py:151). |
| **4 — Episódio/outcome** | **Resolve existência do outcome e correspondência de versão/mercado.** A integridade completa permanece explicitamente parcial, sob responsabilidade de S2: [migração:148](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:148), [DATABASE.md:878](/C:/dev/project-hunter/docs/DATABASE.md:878). |
| **5 — Outbox** | **Contrato corrigido.** O docstring e o índice usam pendência por `dispatched_at IS NULL`: [modelo:131](/C:/dev/project-hunter/packages/core/hunter_core/db/models/agents_shadow.py:131), [migração:108](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:108). |

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executei com sincronização de dependências, bytecode e cache do pytest desabilitados:

```text
uv run pytest packages/core/tests/unit/test_strategies_canonical.py packages/core/tests/unit/test_domain_enums.py -q
38 passed in 1.22s
```

```text
uv run python infra/scripts/check_file_size.py
error   352 > 350  apps/api/hunter_api/realtime/endpoint.py
scanned 143 files; 1 over budget, 0 grandfathered
```

O gate global está vermelho em arquivo fora de S0. Não atribuo isso às cinco correções.

Os upgrades, downgrade/check e `350 passed` são **resultados informados por você**, não reexecutados por mim.

**MUST-FIX**

**a) O backfill não é semanticamente seguro para `result='open'`, `entry_ts=NULL`, `exit_ts` preenchido.**

Essa linha recebe `pending_entry` e passa pelo CHECK, porque ambos ignoram `exit_ts`: [migração:221](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:221), [CHECK:235](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:235).

**Cenário de falha:** uma linha com saída registrada passa a ser apresentada ao acompanhamento como aguardando entrada. O consumidor futuro pode tentar processá-la novamente. Com `entry_ts` preenchido, a mesma contradição vira `active`.

Não há informação suficiente para inferir `target`, `stop` ou outro resultado. **Minha recomendação é rejeitar explicitamente o upgrade diante de `result='open' AND exit_ts IS NOT NULL`, com mensagem clara**, até existir uma política de conversão aprovada. Acrescentar esse vetor ao teste: hoje ele verifica somente `resolved`, `entered` e `waiting` — [test_migrations.py:293](/C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:293). Não constatei que existam linhas assim no banco operacional.

**NICE-TO-HAVE**

**d) Ainda faltam provas relevantes:**

- **DELETE direto do outcome e DELETE do signal com cascata**, verificando vínculo nulo e preservação de versão/mercado/checkpoint do episódio. Os testes novos exercitam inserções: [test_schema_shadow.py:425](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:425).
- **Versão incorreta com mercado correto**, para proteger separadamente a segunda dimensão da FK composta; o vetor atual troca o mercado: [teste:425](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:425).
- **DELETE da estratégia-pai com versão ativada**; atualmente há prova de exclusão direta da versão: [teste:250](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:250).
- **Newline no CHECK PostgreSQL**, incluindo `replay:<uuid>\n`; os vetores SQL atuais não incluem newline: [teste:399](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:399).

Além disso, **não marcar integralmente o aceite S0 de isolamento por `run_id` e envelope nunca reescrito**. O round-trip do helper e prospective/replay em slots distintos não provam dois runs independentes nem preservação do envelope na reentrega: [helper:144](/C:/dev/project-hunter/packages/core/tests/unit/test_domain_enums.py:144), [slots:387](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_shadow.py:387), [aceite:48](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:48). Essas provas precisam acompanhar a persistência de S2.

**O QUE EU FARIA DIFERENTE**

**c) Sim, o UNIQUE acrescenta um índice logicamente redundante com a PK de `id`.** Porém ele sustenta a FK das três colunas; a PK simples não substitui esse alvo no PostgreSQL 16. A criação está corretamente antes da tabela filha: [migração:78](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:78). [Referência PostgreSQL](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-FK).

Eu manteria. Há custo adicional de armazenamento e escrita; chamá-lo de “caro” exige medição. Removê-lo exige redesenhar a garantia de integridade.

**CONCORDO COM**

**b) Não há conflito intrínseco entre essas duas ações de SET NULL.** Ambas anulam somente `open_outcome_signal_id`. Ao apagar o signal, o outcome é cascateado; qualquer caminho que execute primeiro deixa o vínculo nulo, válido para ambas as FKs sob `MATCH SIMPLE`. Versão e mercado permanecem preenchidos: [FKs:148](/C:/dev/project-hunter/infra/migrations/versions/0002_shadow_lab.py:148), [cascata:154](/C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:154). Isso decorre da semântica documentada; falta a prova operacional mencionada acima. [Referência PostgreSQL](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-FK).

**OBSIDIAN**

- **Strategies** — registrar canônico corrigido e testes executados nesta rodada.
- **Performance Overview** — documentar tratamento necessário de estados legados contraditórios.
- **Diálogo Claude ⇄ Astra — SHADOW** — explicitar provas de integridade e reentrega ainda atribuídas a S2.
- **Revisões Astra / S0-schema** — registrar segunda rodada, ressalva do backfill e lacunas de teste.