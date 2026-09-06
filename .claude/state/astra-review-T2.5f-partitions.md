**RESUMO**

Concordo com o recorte, com uma correção de calendário. Revisão como `database-architect`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; análise estática em modo OPINIÃO.

**MUST-FIX**

Corrigir a expectativa “retenção de 30 dias ganha **só** o mês anterior”: em **01/03/2026**, o corte é **30/01**; janeiro ainda contém dados retidos. Portanto, janeiro **e** fevereiro devem ser provisionados. Não limite manualmente a um mês: deixe `is_expired` decidir pela borda superior, preservando o `<=` atual ([prune_partitions.py:119](C:/dev/project-hunter/infra/scripts/prune_partitions.py:119)).

**NICE-TO-HAVE**

Cobrir fevereiro, virada de ano, igualdade exata no corte, retenção `None` e configuração personalizada. Na extração, testar tanto execução direta quanto carregamento por caminho: os testes atuais usam `spec_from_file_location`, então um import relativo de módulo irmão pode quebrá-los ([test_create_partitions.py:48](C:/dev/project-hunter/infra/scripts/tests/test_create_partitions.py:48)).

**O QUE EU FARIA DIFERENTE**

Passaria o mesmo `now` UTC e a política resolvida ao planejador; consultaria retenção pelo **owner mensal** (`candles_1m`), não pela raiz (`candles`). A política já usa essa chave ([prune_partitions.py:101](C:/dev/project-hunter/infra/scripts/prune_partitions.py:101)).

**CONCORDO COM**

1. **`--months-behind=2` em todos os pais mensais.** `months_before()` já exclui o corrente e trata janeiro corretamente ([_partitions.py:92](C:/dev/project-hunter/packages/core/hunter_core/db/models/_partitions.py:92)).

2. **A guarda não esconde candles necessários aos últimos 7/30 dias com retenção de 90 dias.** Ela exclui somente meses inteiramente expirados. Se a retenção configurada for menor que o histórico solicitado, poderá excluir dados solicitados — coerentemente com o prune; recriá-los não resolve esse conflito de política ([prune_partitions.py:78](C:/dev/project-hunter/infra/scripts/prune_partitions.py:78), [prune_partitions.py:133](C:/dev/project-hunter/infra/scripts/prune_partitions.py:133)).

3. **As duas extrações fazem sentido.** Leve também os auxiliares de planejamento, preservando hardening e limites UTC; deixe execução/transações no script ([create_partitions.py:189](C:/dev/project-hunter/infra/scripts/create_partitions.py:189), [create_partitions.py:246](C:/dev/project-hunter/infra/scripts/create_partitions.py:246)).

4. **Funding/OI: nada a provisionar nesta tarefa.** Os modelos não são particionados ([market_data.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:90), [market_data.py:103](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:103)).

5. **Mantenha assinatura e `to_regclass`.** A existência real continua sendo a guarda necessária quando o provisionamento falha ou ainda não rodou ([partitions.py:191](C:/dev/project-hunter/services/market-worker/hunter_market_worker/partitions.py:191)). Ressalva: provisionar partições não amplia o limite atual de **sete dias por pedido** ([backfill_plan.py:33](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:33)).

**OBSIDIAN**

- **Infrastructure** — registrar provisionamento retroativo condicionado à retenção por pai mensal.
- **Market Collector** — atualizar a causa de `no_partition` e separar disponibilidade de partições do limite por pedido.