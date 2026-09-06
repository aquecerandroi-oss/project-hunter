**RESUMO**

Como `database-architect`: **não reportaria DONE ainda**. A ordem do downgrade foi corrigida, mas restam quatro must-fix: sobrescrita dos pesos, promoção baseada numa leitura anterior ao INSERT, protocolo de retenção incompleto e downgrade que pode apagar pendências/evidências.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão restrita ao conjunto indicado; S2 e T2.2 não foram revisados.

**TESTES**

- `git diff --check`, restrito aos arquivos modificados indicados: **exit 0**, apenas avisos de CRLF → LF.
- Não executei pytest, migrações ou seed neste modo OPINIÃO. Portanto, **não atesto aprovação dos testes nem atomicidade observada em PostgreSQL**.

**MUST-FIX**

1. **O seed continua sobrescrevendo o conteúdo de versões existentes.**

   O conflito ainda executa `weights = excluded.weights`; preservar `is_active` não preserva a versão quantitativa. [seed.py:305](C:/dev/project-hunter/infra/scripts/seed.py:305)

   **Cenário:** T2.4 ratifica v2, conforme permitido na documentação, e registra `components_frozen=true`. Reexecutar este seed restaura o payload com `false`. Se o conteúdo quantitativo existente divergir, ele também será substituído sob o mesmo identificador. [DATABASE.md:1266](C:/dev/project-hunter/docs/DATABASE.md:1266), [seed_reference.py:241](C:/dev/project-hunter/infra/scripts/seed_reference.py:241)

   **Correção:** inserir versões ausentes; para existentes, validar igualdade do conteúdo e recusar divergência sem sobrescrever. Mudança quantitativa exige nova versão. Ajustar também o teste que ainda exige “refresh” do vetor. [test_schema_seed_and_partitions.py:309](C:/dev/project-hunter/packages/core/tests/integration/test_schema_seed_and_partitions.py:309)

2. **A promoção não está vinculada à execução que efetivamente criou v2.**

   `already_present` vem de um SELECT separado. Depois, tanto INSERT quanto UPDATE por conflito retornam um ID, e a promoção depende exclusivamente daquela leitura anterior. [seed.py:289](C:/dev/project-hunter/infra/scripts/seed.py:289), [seed.py:304](C:/dev/project-hunter/infra/scripts/seed.py:304)

   **Cenário:** o seed lê “v2 ausente” e pausa; um operador cria v2 inativa, mantendo v1 ativa deliberadamente; o seed retoma, encontra conflito, atualiza a linha e promove v2. Essa execução **não criou v2**, mas altera a escolha operacional. [seed.py:263](C:/dev/project-hunter/infra/scripts/seed.py:263), [seed.py:314](C:/dev/project-hunter/infra/scripts/seed.py:314)

   **Correção:** decidir a promoção pelo resultado de `INSERT … ON CONFLICT DO NOTHING RETURNING`, juntamente com a validação do conteúdo do item anterior. Somente quem inseriu a linha pode executar a promoção inicial.

   O teste decisivo precisa intercalar **seed e operador com duas conexões e barreiras**, sem depender de sleeps.

3. **O protocolo escrito de retenção ainda não resolve a corrida.**

   A seção determina uma condição de idade e uma ordem relativa à retenção do histórico, mas não define exclusão mútua entre criação de referências e exclusão de baselines. [DATABASE.md:1086](C:/dev/project-hunter/docs/DATABASE.md:1086)

   **Cenário:** o job verifica que B não tem referências; o scorer mantém B em cache e grava um envelope; o job apaga B. Fazer isso antes de avançar a janela do histórico não impede a intercalação. Além disso, uma baseline antiga pode estar referenciada numa amostra recente: idade de `available_at` não prova ausência de dependência.

   O trigger apenas verifica o marcador; não verifica referências. [analysis.py:128](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:128)

   **Correção nesta tarefa:** fechar o contrato, sem implementar o job inteiro. Por exemplo: escritor e retenção usam o mesmo lock transacional por baseline; escritor revalida a existência após adquirir o lock; retenção reconsulta todas as referências preservadas antes de apagar. Incluir referências nos envelopes atuais, não apenas no histórico.

4. **A guarda do downgrade protege rótulos, mas não pendências nem evidências.**

   O downgrade consulta os rótulos adicionados e depois remove envelopes, baselines e outbox sem outra guarda. [0003_analysis.py:100](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:100), [0003_analysis.py:307](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:307), [0003_analysis.py:372](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:372)

   **Cenários:**
   - Há um evento com `dispatched_at IS NULL`, mas nenhum rótulo novo em uso: downgrade termina com sucesso e perde a obrigação de publicação.
   - Uma oportunidade `HOT` referencia B em `feature_snapshot`: a guarda passa, B é apagada e a oportunidade preservada perde sua evidência. Esse campo permanece no modelo. [analysis.py:241](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:241)

   **Correção:** recusar antes de qualquer remoção quando houver pendências ou evidência M2 que precise ser preservada, até existir um procedimento explícito de exportação/conversão. Não basta exigir ausência de `EXTENDED`/`UNKNOWN`.

**NICE-TO-HAVE**

Os testes adicionais de maior valor seriam:

- **Downgrade com dados compatíveis em duas partições**, seguido de upgrade; conferir linhas, default `NORMAL`, índices e tipos das filhas. O teste de ciclo atual não monta esse cenário. [test_migrations.py:409](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:409)
- **Falha depois das remoções, durante a reconstrução dos tipos**, verificando rollback de tabelas, dados, grants e trigger. O teste atual provoca recusa logo na primeira guarda e verifica a revisão; não demonstra rollback de alterações já executadas. [test_migrations.py:569](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:569)
- Parametrizar **EXTENDED somente no histórico**, `UNKNOWN` em regimes e os dois novos tipos de anomalia; testar também cada uma das três guardas de upgrade. [analysis.py:167](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:167), [analysis.py:202](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:202)
- Testar promoção partindo de **v1 já ativa**, falha entre desativação e ativação, divergência do payload e a intercalação do MF2.
- Testar o marcador de retenção na transação seguinte, na mesma conexão. `SET LOCAL` termina com a transação; o teste deve provar esse uso. [PostgreSQL 16 — SET](https://www.postgresql.org/docs/16/sql-set.html)

**O QUE EU FARIA DIFERENTE**

Usaria duas garantias explícitas: **versão quantitativa inserida e validada, nunca atualizada pelo seed**; **downgrade recusado enquanto houver estado durável sem conversão definida**.

Não considero `components_frozen=false` aprovação dos números provisórios. Aceito o registro do desvio como pendência de T2.4, condicionado a não produzir scores antes do congelamento; essa condição está documentada, mas o payload sozinho não a impõe. [DATABASE.md:1258](C:/dev/project-hunter/docs/DATABASE.md:1258)

**CONCORDO COM**

- **Ordem do downgrade:** CHECK e índice novos saem antes da reconstrução; o índice antigo volta depois. O default de `opportunities.status` é removido e restaurado. Não identifiquei outra dependência problemática nos arquivos revisados. [0003_analysis.py:100](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:100), [analysis.py:230](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:230)
- **Partições e índices simples:** o ALTER sem `ONLY` alcança descendentes; índices simples sobre a coluna são reconstruídos pelo PostgreSQL. Isso cobre o desenho mostrado, mas não certifica views ou defaults particulares existentes no banco implantado. Uma dependência esquecida deve causar erro, pois o `DROP TYPE` não usa `CASCADE`. [analysis.py:245](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:245), [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/16/sql-altertable.html), [DROP TYPE](https://www.postgresql.org/docs/16/sql-droptype.html)
- **Atomicidade:** o corpo é compatível com uma transação única. A garantia efetiva depende do executor Alembic manter essa transação; não certifiquei isso executando o ciclo. Atomicidade também não impede a perda **intencionalmente commitada** descrita no MF4.
- **Guardas de upgrade:** correspondem aos três invariantes e não recusam excessivamente dentro desse contrato. Não inventam expiração nem escolhem arbitrariamente uma duplicata. [analysis.py:175](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:175)
- **Baselines e legado:** aprovo fingerprint na unicidade, CHECKs locais e anomalias anteriores marcadas `unknown`. [0003_analysis.py:182](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:182), [0003_analysis.py:244](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:244)
- **Decimal/UTC/tenancy/pooler:** não encontrei violação adicional no escopo. O DDL usa `NUMERIC(28,10)` e timestamps com timezone; a API recebe apenas leitura nas tabelas novas; o trigger trata GUC ausente/vazio. A causalidade da seleção ainda será responsabilidade do consumidor, conforme o contrato. [0003_analysis.py:155](C:/dev/project-hunter/infra/migrations/versions/0003_analysis.py:155), [analysis.py:254](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:254), [analysis_baselines.py:45](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis_baselines.py:45)

**OBSIDIAN**

- **Features (Feature Engine)** — registrar sincronização obrigatória entre referências e retenção de baselines.
- **Architecture Decisions** — registrar promoção pela inserção efetiva, conteúdo imutável dos pesos e proteção de dados no downgrade.
- **Diálogo Claude ⇄ Astra — M2** — manter explícita a pendência de congelamento quantitativo antes dos scores.
- **Revisões Astra / T2.1 — diff da 0003_analysis** — guardar os quatro achados e vincular os testes que os encerrarem.