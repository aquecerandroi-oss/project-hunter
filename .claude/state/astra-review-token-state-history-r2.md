## MUST-FIX

**O must-fix 2 ainda não está fechado.** O adiamento corrige o lote que **começa a executar o commit depois de L**, mas a margem não garante a mesma classificação entre exports.

**Cenário concreto, com apenas dois segundos entre carimbo e visibilidade:**

1. O token está visível com os dois campos nulos, sem histórico.
2. O gatilho adiado registra uma conclusão retroativa em **L−1s**.
3. O primeiro export, em **L**, ainda não enxerga a transação: `em(...)` retorna `history`, campos nulos; uma venda que satisfaz os demais critérios é **A**.
4. O commit fica visível em **L+1s**.
5. O segundo export, em **L+2s**, enxerga a mudança carimbada em L−1s: `em(...)` retorna `incerto_em_l`; a mesma venda vira **C**.

Esse resultado decorre diretamente do fallback nulo em [estado_token.py:85](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:85), da margem em [estado_token.py:106](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:106) e da censura em [classes.py:87](C:/dev/project-hunter/infra/research/exp_m26/classes.py:87). **Classificar conservadoramente depois não preserva a leitura anterior.**

A regressão nova termina o primeiro export **antes de chamar `commit()`**; portanto, cobre o lote aberto, mas não o commit já em processamento enquanto o export tira seu snapshot ([test_migration_0067.py:318](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:318)). O teste dos 0,3s também espera **antes** do commit ([test_migration_0067.py:232](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:232)).

**(b) Não aceitaria o resíduo como cumprimento da garantia estrita “conhecido em L”.** Além do contraexemplo acima, carimbo em L−61s e visibilidade em L+1s faz uma informação indisponível em L entrar como `history`. O intervalo posterior ao primeiro carimbo inclui os demais gatilhos adiados, suas inserções e verificações referenciais, além da finalização do commit; não apenas WAL. A descrição do resíduo precisa refletir isso ([DDL:99](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:99), [DATABASE.md:8739](C:/dev/project-hunter/docs/DATABASE.md:8739)). O PostgreSQL define esses gatilhos como execução ao final da transação, não como callbacks posteriores à visibilidade ([documentação](https://www.postgresql.org/docs/16/sql-createtrigger.html)).

## NICE-TO-HAVE

**(c) Gatilhos adiados: há limites concretos que merecem testes e documentação.**

- **`SET CONSTRAINTS`:** antecipar esses gatilhos e continuar a transação reabre o problema original; voltar para `DEFERRED` não desfaz os carimbos já escritos. Não encontrei chamada executável disso nos caminhos pesquisados, portanto não acrescento outro bloqueio ao fluxo atual ([DDL:131](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:131); [PostgreSQL](https://www.postgresql.org/docs/16/sql-set-constraints.html)).
- **Alteração e poda do mesmo mint na mesma transação:** atualizar um campo observado, apagar o token e commitar deixa um evento pendente tentando inserir histórico cujo pai já não existe. A FK faz o commit falhar; `ON DELETE CASCADE` não elimina uma inserção que ainda não aconteceu ([DDL:79](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:79), [DDL:105](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:105)). A poda atual abre transação própria, por isso não classifico isso como regressão do caminho existente ([collect.py:312](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:312)). O teste atual também insere e poda em transações separadas ([test_migration_0067.py:269](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:269)).
- **Várias mudanças do mesmo mint:** acrescentaria uma regressão com nascimento e dois recuos na mesma transação. O teste de upsert atual usa uma transação por linha ([test_migration_0067.py:94](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:94)). Sob adiamento uniforme, espero a sequência correta; os estados intermediários não foram individualmente visíveis.
- **Dono superusuário:** preferiria dono dedicado, `NOLOGIN`, com privilégios mínimos. É endurecimento, não uma exploração identificada neste corpo estático ([DDL:99](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:99), [DDL:120](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:120)).
- **`db_role`:** representa o papel configurado quando o gatilho executa. Se houver `RESET ROLE` ou troca de papel entre a alteração e o commit, não identifica necessariamente o autor daquela alteração. O caminho atual mantém o contexto durante a transação ([DDL:94](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:94), [session.py:232](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:232)).

**(d) `historico_diverge`: não vejo falso positivo causado apenas por concorrência normal neste export.** Há um único `SELECT ... UNION ALL`, incluindo linha corrente e histórico, logo ambos compartilham o snapshot ([export_h022.sql:18](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:18), [export_h022.sql:69](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:69)). `READ ONLY` sozinho não garantiria isso entre comandos distintos em `READ COMMITTED` ([PostgreSQL](https://www.postgresql.org/docs/16/transaction-iso.html)).

Entretanto, “divergência prova escrita sem gatilho” é forte demais: a ordenação prioriza o relógio, usando `id` apenas no empate. Se o relógio do servidor recuar entre duas mudanças, uma mudança antiga pode ser escolhida como última e produzir divergência com histórico íntegro ([estado_token.py:75](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:75), [estado_token.py:104](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:104)). `clock_timestamp()` mede o relógio corrente, não uma sequência monotônica ([PostgreSQL](https://www.postgresql.org/docs/16/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT)).

## O QUE FARIA DIFERENTE

Manteria o histórico e os privilégios novos, mas fecharia a garantia usando **evidência preservada de visibilidade no snapshot de L**. Aumentar a margem não resolve o contraexemplo.

Antes disso, acrescentaria uma regressão que bloqueia controladamente a transação **depois do carimbo e antes da visibilidade**, executa o primeiro export, libera o commit e compara a classificação completa com o segundo export. Essa é a fronteira ainda não exercitada.

## CONCORDO COM

- **`SECURITY DEFINER`:** o `search_path` fixo, o destino qualificado, a ausência de SQL dinâmico e a revogação de `EXECUTE` fecham os vetores usuais neste corpo. Não identifiquei escalada concreta; uma função `RETURNS trigger` não vira uma API comum invocável por `SELECT` ([DDL:99](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:99), [DDL:120](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:120); [PostgreSQL](https://www.postgresql.org/docs/16/sql-createfunction.html)).
- **`WHEN` e `ON CONFLICT DO UPDATE`:** a comparação captura mudanças efetivas. Não identifiquei duplicação indevida de nascimento no ramo de conflito atualizado; os gatilhos por linha seguem a operação efetivamente realizada ([DDL:124](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:124); [PostgreSQL](https://www.postgresql.org/docs/16/sql-createtrigger.html)).
- **Vias desconhecidas → C:** tratamento coerente para histórico anterior, divergência e ausência do token ([classes.py:44](C:/dev/project-hunter/infra/research/exp_m26/classes.py:44)).
- **(e) Pooler transacional:** não identifiquei incompatibilidade nova. A fila adiada pertence à transação, e `SET LOCAL ROLE` permanece nela até a conclusão ([session.py:158](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:158), [DDL:131](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:131)). O backend permanece atribuído durante a transação ([PgBouncer](https://www.pgbouncer.org/features.html)).

**Verificação:** revisão estática; não executei testes ou migrações. Nenhum arquivo modificado, nenhum commit e nenhuma leitura de `.env`.

## OBSIDIAN

- **EXP-M26 — gráfico em moedas maduras:** registrar que o lote aberto foi corrigido, mas a estabilidade entre exports ainda falha durante o commit.
- **Revisões-Astra — EXP-M26/J:** registrar esta rodada e a regressão necessária entre carimbo e visibilidade.
- **Diálogo — EXP-M26:** consolidar a exigência de visibilidade em L e os limites de qualquer aproximação temporal.