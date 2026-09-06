**RESUMO**

`DONE_WITH_CONCERNS`: corrigiria o teste dependente do calendário e a documentação antes de reportar.

**ARQUIVOS**

Nenhum arquivo alterado.

**TESTES**

Não executei pytest nem migrações neste modo somente leitura. Conferência aritmética em PowerShell: agosto com retenção de 14 dias passa de `expired=False` em 14/09 23:59:59 UTC para `True` em 15/09 00:00:00 UTC.

**MUST-FIX**

- **Teste quebra a partir de 15/09:** usa `datetime.now(UTC)` e exige passado para todos os pais; `feature_snapshots` legitimamente não terá nenhum. Fixar datas e cobrir ambos os lados da expiração, permitindo passado vazio conforme a política. [test_create_partitions_integration.py:154](/C:/dev/project-hunter/infra/scripts/tests/test_create_partitions_integration.py:154), [linha 170](/C:/dev/project-hunter/infra/scripts/tests/test_create_partitions_integration.py:170).
- **§1.3 contém afirmações incorretas:** 01/03/2027 − 30 dias = **30/01**, portanto um mês anterior não basta sempre; **90 dias não são ≥ três meses**; “hash/LIST” contradiz LIST → RANGE descrito anteriormente. Corrigir [DATABASE.md:121](/C:/dev/project-hunter/docs/DATABASE.md:121), [123](/C:/dev/project-hunter/docs/DATABASE.md:123) e [127](/C:/dev/project-hunter/docs/DATABASE.md:127). O cenário de março reforça a escolha de **dois** meses.

**NICE-TO-HAVE**

O invariante vale **no mesmo instante e com a mesma configuração**. Com retenção inteira em dias, a expiração ocorre à meia-noite UTC: **04:07 → 04:12 UTC não cruza a borda**, mas **23:59 → 00:01 cruza**. Um plano atrasado pode criar algo que o prune seguinte remove; não elimina linhas ainda retidas. Qualificar a promessa absoluta. [partition_retention.py:90](/C:/dev/project-hunter/infra/scripts/partition_retention.py:90), [partition_plan.py:139](/C:/dev/project-hunter/infra/scripts/partition_plan.py:139).

**O QUE EU FARIA DIFERENTE**

Acrescentaria casos determinísticos para março e para a virada de expiração, mantendo a política compartilhada.

**CONCORDO COM**

Não identifiquei quebra nos consumidores citados: o loader existente adiciona `infra/scripts` ao caminho; Docker copia a pasta inteira; entrypoint executa por caminho; migrations usam helpers de `hunter_core`. [loader:83](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_seed_and_partitions.py:83), [Dockerfile:89](/C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:89), [entrypoint:47](/C:/dev/project-hunter/infra/docker/entrypoint.sh:47), [ddl:35](/C:/dev/project-hunter/infra/migrations/ddl/partitions.py:35).

**OBSIDIAN**

- **Infrastructure** — registrar horizonte retroativo condicionado à retenção e limite temporal do invariante.
- **Market Collector** — registrar cobertura de backfill e preservação da consulta às partições existentes.