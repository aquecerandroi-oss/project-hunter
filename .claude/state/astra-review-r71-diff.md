**RESUMO**

Como `database-architect`: **sem MUST-FIX no diff final**. Parecer favorável na revisão estática; não certifico execução dos testes.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Comparação somente leitura em PowerShell, saída real: `6/6 mints exactly match; 6/6 costs fit scale 6 without rounding.`

Pytest/Alembic não executados nesta rodada.

**MUST-FIX**

Nenhum.

**NICE-TO-HAVE**

Acrescentar assert independente do mint literal de SLX: o teste fixa os outros cinco, mas verifica SLX apenas por tier/disabled ([teste:159](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0061.py:159)).

**O QUE EU FARIA DIFERENTE**

Nenhuma mudança funcional necessária.

**CONCORDO COM**

- Os seis mints coincidem exatamente com os informados. Custos em fração, convertidos para `Decimal`, cabem sem arredondamento em `numeric(9,6)` ([semente:73](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:73), [conversão:156](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:156), [coluna:89](C:/dev/project-hunter/infra/migrations/ddl/spot_desk.py:89)).
- NEAR como ponte; XRP/BIRB retidos por nome sem adulterar tier/custo; SLX desligado pela regra ([semente:73](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:73), [enabled:167](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:167)).
- INSERT parametrizado com `ON CONFLICT DO NOTHING`; downgrade com LOCK, guardas por `market_symbol`, escape das aspas no HINT e DELETE dos seis via `expanding=True` ([insert:138](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:138), [delete:187](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:187), [guarda:221](C:/dev/project-hunter/infra/migrations/ddl/spot_desk_r71.py:221)).
- Testes cobrem 56/38, valores/mints contra a constante, idempotência preservando edição operacional e downgrade bloqueado separadamente por ordem e posição ([contagem:176](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0061.py:176), [idempotência:220](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0061.py:220), [downgrade:265](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0061.py:265)).
- `HEAD_REVISION` aponta para `0061_spot_desk_r71` ([linha 43](C:/dev/project-hunter/packages/core/tests/integration/test_migrations.py:43)).

**OBSIDIAN**

- **Spot — a mesa `spot/1`**: registrar expansão para 56/38 na semente e retenções XRP/BIRB.
- **Revisões Astra — R71**: registrar parecer final sem bloqueadores e testes não executados nesta rodada.