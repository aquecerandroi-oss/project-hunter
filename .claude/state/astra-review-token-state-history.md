**MUST-FIX**

**O must-fix 2 não está integralmente fechado.** O contraexemplo original — `LEAST` ou migração registrados em L+10min — está corrigido pelo filtro `registrado_em <= L`. Resta a diferença entre escrita e visibilidade após commit ([estado_token.py:63](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:63)).

**1. O resíduo pode durar minutos no caminho real do worker.**

`run_board` executa todos os upserts de um lote dentro da mesma transação; essas linhas podem preencher `completed_at` ([wiring.py:182](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wiring.py:182), [boards.py:301](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/boards.py:301)). O histórico recebe `clock_timestamp()` durante o gatilho, antes do commit ([DDL:73](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:73)).

Cenário concreto, **não medido em produção**:

1. O primeiro token do lote recebe uma conclusão retroativa em L−1s.
2. Os próximos 30 upserts levam 5s cada, todos terminando com sucesso.
3. O lote commita perto de L+150s.
4. Um export em L não enxerga a conclusão; outro em L+3min enxerga seu histórico com `recorded_at < L`. A mesma venda passa de A para C.

O timeout padrão de 15s é aplicado **por comando**, não à transação inteira; portanto, não impede esse cenário ([settings.py:64](C:/dev/project-hunter/packages/core/hunter_core/settings.py:64), [session.py:200](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:200), [documentação PostgreSQL](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-STATEMENT-TIMEOUT)).

**Resposta a (b): não aceitaria esse resíduo como cumprimento da garantia estrita “disponível em L”.** A afirmação de que ele fica limitado a segundos precisa ser corrigida ([DATABASE.md:8672](C:/dev/project-hunter/docs/DATABASE.md:8672)). Exigiria uma prova de visibilidade em L e uma regressão com duas conexões, mantendo a transação escritora aberta durante o primeiro export.

**NICE-TO-HAVE**

- **Fallback — (c): correto sob as invariantes declaradas:** histórico completo, gatilhos continuamente ativos e implantação anterior à população. O `antes` da primeira mudança posterior recupera o estado anterior; ausência de mudanças permite usar a linha corrente nessas condições ([estado_token.py:66](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:66)). Porém, **valor do evento ≤ L não prova escrita ≤ L**. Se o gatilho estiver desligado e chegar em L+10min uma conclusão de L−1h, `current_row_pre_history` aceita esse valor e pode censurar a venda. Como essa via é declarada impossível na população prospectiva, eu a recusaria nessa população, em vez de apenas contá-la ([classes.py:44](C:/dev/project-hunter/infra/research/exp_m26/classes.py:44), [DATABASE.md:8718](C:/dev/project-hunter/docs/DATABASE.md:8718)). Não considero isso outro bloqueio sob implantação íntegra.

- **Precisão dos privilégios:** “somente pelo gatilho” descreve uma convenção, não uma restrição do banco. O worker tem `INSERT` direto, inclusive possibilidade de fornecer `recorded_at`; os privilégios garantem ausência de `UPDATE`/`DELETE` direto ([DDL:127](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:127)). Renomearia o teste que promete exclusividade do gatilho, pois ele não testa essa propriedade ([test_migration_0067.py:218](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:218)).

**O QUE FARIA DIFERENTE**

Para fechar a garantia estrita, preservaria um snapshot consistente em L ou informação durável que permita determinar quais transações estavam visíveis naquele instante. **`xid` sozinho não fornece o horário do commit.** Também não exigiria especificamente `track_commit_timestamp`: depende de configuração e suas informações são removidas ao longo da manutenção; precisaria de uma política de preservação, não apenas de uma consulta futura ([documentação PostgreSQL](https://www.postgresql.org/docs/16/functions-info.html#FUNCTIONS-COMMIT-TIMESTAMP)).

Transações menores reduziriam a exposição, mas não eliminariam a diferença entre gatilho e commit.

**CONCORDO COM**

- **(a) Correção do caso original:** a resolução ignora mudanças registradas depois de L. A regressão compara o relatório inteiro para as 168 vendas, além do controle com conclusão anterior a L ([test_leitura.py:192](C:/dev/project-hunter/infra/research/exp_m26/tests/test_leitura.py:192)).

- **(c) Token ausente → C:** tratamento conservador correto; ausência de evidência não vira “não concluiu” ([estado_token.py:74](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:74), [classes.py:86](C:/dev/project-hunter/infra/research/exp_m26/classes.py:86)).

- **(d) Retenção por cascata:** não encontrei bloqueio. O índice começa por `mint`, atendendo à busca dos filhos; cada lote de poda tem sua própria transação ([DDL:86](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:86), [collect.py:312](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:312)). Há custo adicional de locks/WAL proporcional aos filhos, portanto 5.000 tokens não limitam a quantidade de linhas apagadas no histórico. O teste existente verifica uma cascata, não desempenho do lote ([test_migration_0067.py:233](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:233)). A FK no `AFTER INSERT` pode enxergar o pai inserido pela própria transação ([PostgreSQL: visibilidade em gatilhos](https://www.postgresql.org/docs/16/trigger-datachanges.html)).

- **(e) Locks e `WHEN`:** a ordem token → histórico bloqueia os escritores antes da contagem e acompanha o caminho do upsert. O `WHEN ... IS DISTINCT FROM` filtra mudanças efetivas sem depender da lista de colunas do comando ([DDL:115](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:115), [DDL:140](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:140)). Não identifiquei dependência nova de estado de sessão incompatível com pooler transacional.

- **(f) Pares H/L:** ambos passam por `_em_l` e pela mesma função de censura; não encontrei regressão específica no pareamento ([leitura.py:226](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:226), [pacote.py:66](C:/dev/project-hunter/infra/research/exp_m26/pacote.py:66)). O bloqueio temporal acima também os afeta.

**Verificação:** revisão estática; nenhum arquivo modificado. Não executei pytest, migrações ou `alembic check`; li os testes, inclusive recusa e ida/volta do downgrade. A contagem dos 12 módulos Python indicados ficou entre 51 e 344 linhas.

**OBSIDIAN**

- **EXP-M26 — gráfico em moedas maduras:** registrar correção do atraso após L e pendência da visibilidade no commit.
- **Revisões-Astra — EXP-M26/J:** acrescentar esta rodada e o cenário da transação em lote.
- **Diálogo — EXP-M26:** definir explicitamente se “conhecido em L” significa escrita iniciada ou informação já visível no banco.