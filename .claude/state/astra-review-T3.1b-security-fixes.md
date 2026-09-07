**RESUMO**

Encontrei **três escapes reproduzíveis**: dois permitem criar um pico fictício como `hunter_app`; outro contorna a proibição de UPDATE por herança de papel. A afirmação de que a transição órfã fica ilegível também é falsa.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO; probes SQL com dados sintéticos e `ROLLBACK`.

**TESTES**

Comando solicitado, com cache e bytecode desativados:

```text
uv run pytest packages/core/tests/integration/test_schema_paper.py -q
69 passed in 179.63s (0:02:59)
```

Probes adicionais via `docker exec -i … psql`, no PostgreSQL 16 de teste:

```text
probe         initial_capital       peak_equity
skip_CTE      20000.0000000000       999999.0000000000

probe         peak_equity            equity_day_start
self_ceiling  999999.0000000000       999999.0000000000

UPDATE 1
current_user       peak_equity
astra_t31_probe    999999.0000000000

probe         count
orphan_read   1
```

Não executei downgrade/upgrade nem benchmark de desempenho.

**MUST-FIX**

1. **[P1 — ponto 3] O `NOT FOUND` permite escapar do teto sem violar a FK.**

   A trigger retorna antes da validação quando a carteira ainda não existe: [paper.py:423](C:/dev/project-hunter/infra/migrations/ddl/paper.py:423).

   Reproduzi esta ordem, com organização/workspace válidos e contexto de `hunter_app`:

   ```sql
   WITH child AS (
     INSERT INTO portfolio_risk_state
       (organization_id, portfolio_id, peak_equity, peak_equity_at)
     VALUES (:org, :pf, 999999, now())
     RETURNING portfolio_id
   )
   INSERT INTO portfolios
     (id, organization_id, workspace_id, name, type, initial_capital)
   SELECT portfolio_id, :org, :ws, 'probe', 'paper', 20000
   FROM child;
   ```

   No INSERT do filho, a carteira não existe e o teto é pulado. Ao verificar a FK no final do statement, a carteira **já existe**. Resultado: capital 20.000, pico 999.999, sem referência diária nem snapshot que o justifique.

   A âncora posterior exige que o estado de risco exista, mas não confronta seu pico com o capital: [paper.py:317](C:/dev/project-hunter/infra/migrations/ddl/paper.py:317).

   **Correção:** recusar carteira ausente nesse ponto, ou adiar a validação do teto e efetivamente executá-la depois. A FK não substitui essa validação.

2. **[P1 — ponto 3] Mesmo removendo o skip, o INSERT pode fabricar seu próprio teto.**

   `NEW.equity_day_start` participa do `greatest`: [paper.py:434](C:/dev/project-hunter/infra/migrations/ddl/paper.py:434).

   Reproduzi a sequência convencional: carteira primeiro, estado de risco depois. Enviei:

   ```text
   initial_capital = 20000
   peak_equity = 999999
   equity_day_start = 999999
   trading_day e respectivos timestamps preenchidos
   ```

   Passou como `hunter_app`. Nenhum snapshot foi necessário. A referência declarada pelo próprio INSERT legitima o pico declarado nesse mesmo INSERT.

   **Cenário de falha:** a carteira nasce com drawdown fictício próximo de 98%; a monotonicidade impede corrigir o pico para baixo.

   **Correção:** restringir o conteúdo inicial permitido ao app ou exigir evidência independente para a referência diária. Apenas retirar o skip não fecha esse caminho.

3. **[P1 condicionado ao login — ponto 2] Comparar o nome literal do papel não equivale a retirar o privilégio.**

   A comparação é `current_user = 'hunter_app'`: [paper.py:173](C:/dev/project-hunter/infra/migrations/ddl/paper.py:173), aplicada ao UPDATE em [paper.py:448](C:/dev/project-hunter/infra/migrations/ddl/paper.py:448).

   Criei, dentro da transação revertida, um papel sem privilégios próprios:

   ```sql
   CREATE ROLE astra_t31_probe NOLOGIN;
   GRANT hunter_app TO astra_t31_probe;
   SET LOCAL ROLE astra_t31_probe;
   ```

   Esse papel herdou UPDATE e conseguiu elevar referência diária e pico para 999.999. A trigger não o reconheceu como app.

   **Caminho equivalente com login real:** um login que herda `hunter_app` executa `SET ROLE NONE`; mantém os privilégios herdados, mas `current_user` passa a ser o login. Isso é comportamento documentado do [PostgreSQL — SET ROLE](https://www.postgresql.org/docs/16/sql-set-role.html). Não verifiquei a configuração dos logins de produção.

   Há uma alternativa mais estreita ao grant completo: **UPDATE em uma única coluna basta para `SELECT … FOR UPDATE`**. Portanto, considerar retirar UPDATE da tabela e conceder apenas `UPDATE(updated_at)`, mantendo a trigger, preserva o lock sem conceder alteração dos valores de risco. Referência: [PostgreSQL — SELECT](https://www.postgresql.org/docs/16/sql-select.html).

   Sobre os outros caminhos pedidos:

   - Uma `SECURITY DEFINER` pertencente ao dono poderia ultrapassar também um REVOKE do app; não é diferença exclusiva desta implementação. Não encontrei uma função dessas escrevendo esse estado nos caminhos examinados.
   - As FKs desse estado usam `ON DELETE CASCADE`, sem `ON UPDATE CASCADE`: [0006_paper_wallet.py:488](C:/dev/project-hunter/infra/migrations/versions/0006_paper_wallet.py:488). Não identifiquei uma ação referencial que reescreva diretamente pico ou referência diária. O escape por papel herdado já basta, independentemente de cascata.

4. **[P2 — ponto 4] Corrigir a garantia documental de “órfã ilegível por todo mundo”.**

   A política compara exclusivamente `organization_id` com a GUC: [_partitions.py:37](C:/dev/project-hunter/packages/core/hunter_core/db/models/_partitions.py:37) e [policies.py:88](C:/dev/project-hunter/infra/migrations/ddl/policies.py:88).

   Reproduzi: linha com organização inexistente, `SET LOCAL ROLE hunter_app`, contexto com aquele UUID, SELECT → **1 linha**. Uma requisição já autorizada antes do teardown também pode conservar esse contexto. Não é necessário recriar a organização; recriá-la com o mesmo UUID tampouco impediria a leitura.

   Isso contradiz [DATABASE.md:2381](C:/dev/project-hunter/docs/DATABASE.md:2381). O teste atual só verifica **outra organização**, não o contexto antigo: [test_schema_paper.py:2084](C:/dev/project-hunter/packages/core/tests/integration/test_schema_paper.py:2084).

   **Não encontrei quebra do CHECK:** apagar a organização não altera `scope` nem `organization_id`, e o CHECK continua válido: [risk.py:81](C:/dev/project-hunter/packages/core/hunter_core/db/models/risk.py:81).

   A guarda de órfãs é adequada para impedir restaurar essa FK sobre dados incompatíveis: [paper.py:982](C:/dev/project-hunter/infra/migrations/ddl/paper.py:982). Isso não constitui prova do round trip completo, que não executei.

**NICE-TO-HAVE**

- **Ponto 1 — recusa legítima adicional:** ordem de aquisição do lock não implica ordem dos timestamps. A captura/conversão de `now` precede o lock em [resume.py:102](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:102), e esse valor vira `created_at` em [transitions.py:173](C:/dev/project-hunter/packages/core/hunter_core/risk/transitions.py:173). Um pedido com instante anterior pode chegar à seção crítica depois de outro movimento e ser recusado mesmo escrevendo uma transição correta na própria transação. Você já documentou timestamp retroativo; esse é um mecanismo concreto pelo qual ele ocorre sem relógio defeituoso. Empates de timestamp também dependem da ordenação dos IDs.
- **Ponto 1 — destravamento ainda possível:** uma transição **nova**, com `actor_type='user'` e UUID inventado, seguida do UPDATE correspondente na mesma transação, satisfaz ambas as condições. O CHECK exige presença do UUID, não autenticação: [risk.py:93](C:/dev/project-hunter/packages/core/hunter_core/db/models/risk.py:93). É uma fronteira explicitamente delegada à API, não um replay antigo que `xmin` deixou escapar.
- **Custo do pico:** a consulta filtra apenas `portfolio_id`: [paper.py:367](C:/dev/project-hunter/infra/migrations/ddl/paper.py:367). Não restringe as chaves de particionamento nem dispõe, nesse modelo, de índice ordenado por equity: [portfolios.py:153](C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:153). Uma sequência de novas máximas executa a agregação repetidamente. Sem benchmark, não afirmo latência problemática; tampouco sustentaria “não está no caminho quente” apenas porque só roda quando sobe.

**O QUE EU FARIA DIFERENTE**

Primeiro fecharia os dois INSERTs reproduzidos e reduziria o grant para uma coluna sem efeito financeiro. Depois acrescentaria testes de papel herdado, CTE filho→pai e contexto do tenant removido. Para a auditoria, separaria explicitamente instante observado de ordenação dos movimentos serializados.

**CONCORDO COM**

A unicidade por organização fecha a segunda carteira principal via workspace: [0006_paper_wallet.py:988](C:/dev/project-hunter/infra/migrations/versions/0006_paper_wallet.py:988). Derivar o seed diretamente de `PAPER_V1` elimina a cópia divergente: [seed_reference.py:296](C:/dev/project-hunter/infra/scripts/seed_reference.py:296).

**OBSIDIAN**

- **Portfolio** — registrar os dois escapes de inicialização do pico e suas reproduções.
- **Risk Engine** — distinguir papel nominal, privilégio herdado e autorização de retomada.
- **Revisoes-Astra/Index** — vincular esta revisão T3.1b: 69 testes verdes, três escapes reproduzidos.
- **Architecture Decisions** — registrar que FK ao final do statement não valida uma invariante pulada por trigger BEFORE.