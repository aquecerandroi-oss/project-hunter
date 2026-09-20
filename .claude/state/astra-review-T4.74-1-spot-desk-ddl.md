**RESUMO**

**DONE_WITH_CONCERNS.** A estrutura atende ao fluxo descrito de compra, múltiplas tentativas de venda e reconciliação. Não identifiquei drift causado pelo ciclo de FKs. Há dois pontos a corrigir antes do aceite: concorrência na guarda de downgrade e integração ao teste geral de grants.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `database-architect`, em modo OPINIÃO.

**TESTES**

Executei uma comparação somente leitura, em PowerShell, entre a semente e R63 §2a:

```text
R63 rows after exclusions: 50
Seed rows: 50; enabled: 35
Mismatches (symbol/mint/tier/liquidity/cost): 0
```

Não executei pytest, upgrade/downgrade ou `alembic check`: esta revisão não criou banco nem arquivos. Portanto, a concordância DDL/ORM abaixo é estática, não certificação de execução.

**MUST-FIX**

1. **A guarda de downgrade tem uma janela de concorrência.**  
   A contagem de assinaturas ocorre antes do `ALTER TABLE` que começa a desmontagem: [spot_desk.py:297](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:297) e [spot_desk.py:286](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:286).

   **Cenário:** a guarda conta zero; o executor confirma a gravação de uma assinatura; o downgrade adquire o lock e elimina as tabelas. A transação da migração, sozinha, não impede essa intercalação.

   **Correção:** adquirir locks transacionais que bloqueiem os escritores **antes da contagem**, mantendo-os até terminar o downgrade. Isso é compatível com pooler de transação. Uma proibição operacional explícita de downgrade com escritores ativos também precisa existir, mas não substitui uma guarda que promete preservar o livro.

2. **As três tabelas precisam entrar na classificação geral de privilégios.**  
   A união não inclui as listas spot e termina comparando igualdade com todas as tabelas existentes: [test_schema_privileges.py:548](C:/dev/project-hunter/packages/core/tests/integration/test_schema_privileges.py:548) e [linha 590](C:/dev/project-hunter/packages/core/tests/integration/test_schema_privileges.py:590).

   **Cenário:** banco atualizado até `0057`; a consulta encontra as três tabelas, a união não, e o teste falha. A pendência já está declarada em [DATABASE.md:7994](C:/dev/project-hunter/docs/DATABASE.md:7994); documentá-la não fecha o aceite. A ausência anterior de `meme_treasury_swaps` deve ser distinguida da regressão acrescentada aqui.

**NICE-TO-HAVE**

- Acrescentar um teste completo com duas vendas falhadas, uma `submitted_unconfirmed`, reconciliação e confirmação repetida. Hoje o teste insere somente uma venda e não exercita esse ciclo: [test_migration_0057.py:260](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0057.py:260).
- Antes desse teste, ajustar a limpeza: ela apaga vendas antes das posições; uma posição fechada que referencie a venda por `exit_order_id` impedirá esse DELETE. Referências: [test_migration_0057.py:58](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0057.py:58), [spot_desk.py:199](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:199).
- Corrigir a ordem descrita no desenho §5 para coincidir com a implementação; a divergência já está explicada em [DATABASE.md:7978](C:/dev/project-hunter/docs/DATABASE.md:7978).

**O QUE EU FARIA DIFERENTE**

**Sobre a pergunta 3:** eu contaria também `spot_positions`, independentemente de assinatura. O schema permite posição apontando para ordem `admitted` sem assinatura; o próprio teste constrói esse estado em [test_migration_0057.py:247](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0057.py:247). Portanto, “existe posição ⇒ existe assinatura” é uma obrigação futura do executor, não uma garantia do banco.

A perda de `refused`/`failed` sem assinatura é **explicitamente aceita pelo desenho §5 e pela §63**, então não a classifico como implementação divergente. Mas essa aceitação é mais permissiva que §17.7: decisões de admissão não são necessariamente recomputáveis. [DATABASE.md:1617](C:/dev/project-hunter/docs/DATABASE.md:1617), [DATABASE.md:7975](C:/dev/project-hunter/docs/DATABASE.md:7975).

Minha preferência seria proteger qualquer ordem e qualquer posição. Se mantiverem a fronteira atual, preservaria pelo menos posições e evidência em `signatures`, além de `tx_signature`, com a exceção de retenção documentada claramente.

**CONCORDO COM**

1. **Ciclo de FKs — pergunta 1.**  
   O `use_alter=True` está na FK nomeada que o DDL acrescenta depois; o downgrade remove essa FK e derruba posições → ordens → mapa. Não vejo falha de dependência nem motivo de drift **por esse ciclo**. [ORM:164](C:/dev/project-hunter/packages/core/hunter_core/db/models/spot_desk.py:164), [DDL:227](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:227), [DDL:284](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:284). A ressalva é a concorrência apontada acima.

2. **CHECK e UNIQUE — pergunta 2.**  
   Não bloqueiam o caminho contratado: compra sem `position_id`; posição ligada por `entry_order_id`; N vendas com IDs próprios apontando para a mesma posição. O UNIQUE restringe posições por compra, não vendas por posição. [DDL:153](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:153), [DDL:193](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:193).

   `pending` não deve ser persistido literalmente: o contrato manda convertê-lo em `submitted_unconfirmed`, com assinatura. Reconcile deve atualizar/reutilizar a ordem existente; criar outra com a mesma assinatura será corretamente recusado. [Desenho:105](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:105), [DDL:235](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:235).

3. **Percentuais — pergunta 4.**  
   `0.00193 = 0,193%` está correto. **Não existe CHECK SQL `<= 0.004`**: é uma regra de habilitação da semente, permitindo posterior decisão do operador. [spot_desk_seed.py:110](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_seed.py:110). Um CHECK permanente excluiria inclusive linhas desabilitadas exigidas pelo contrato.

   O risco de fator 100 aparece se o executor tratar essa fração como pontos percentuais. Recomendo teste explícito da conversão; não há consumidor implementado entre os arquivos revisados que demonstre esse erro.

4. **Pooler e grants — pergunta 5.**  
   Não identifiquei estado de sessão introduzido pelo DDL. Os grants concedem exatamente SELECT, as duas colunas de pedido de venda para app e SELECT/INSERT/UPDATE para worker, sem DELETE: [spot_desk.py:266](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:266).

   A ausência de RLS corresponde à exceção global expressa no desenho, não constitui isolamento entre tenants: [desenho:128](C:/dev/project-hunter/docs/design/spot1-lab-solana.md:128). E o Alembic do projeto continua previsto para conexão direta, conforme [env.py:1](C:/dev/project-hunter/infra/migrations/env.py:1); este parecer não valida sua execução pelo endpoint pooled.

**OBSIDIAN**

- **Revisões Astra — 0057 spot/1**: registrar os dois must-fix, a comparação da semente e a ausência de validação dinâmica.
- **Execution Engine**: registrar o contrato de tentativas, reconciliação idempotente e unidade dos percentuais da pista spot.
- **System Overview**: documentar a exceção global das três tabelas e sua matriz de privilégios.