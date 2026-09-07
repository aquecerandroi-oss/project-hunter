Restam **dois MUST-FIX de severidade alta no item (1)**, reproduzidos em memória:

1. **Alvo bloqueado esconde stop válido posterior** — [triggers.py:204](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:204), [triggers.py:212](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:212).

   Watermark `99`, stop `95`, alvo `110`; lote `[100@100 não recebido até now+20s, 101@110 válido, 102@90 válido]`, todos com `ts=now`. O primeiro cruzamento é o alvo; bloqueá-lo retorna imediatamente `unavailable`, sem procurar o stop `102`. Após 11 segundos, os prints vencem: retorna `stale_trade`. **O stop nunca é publicado.** Quando o alvo ficar indecidido, ainda é necessário procurar um stop válido posterior.

2. **Só o primeiro defeito recebido participa da decisão** — [triggers.py:296](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:296), [triggers.py:288](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:288).

   Mesmo watermark e proteções; lote fora de ordem `[103@100 recebido em now+20s, 100@90 recebido em now+2s, 101@110 válido]`. Guarda apenas o defeito `103`; como ele está depois do alvo, publica `target/101` e avança o watermark. Após três segundos, o stop `100` ficou utilizável, mas é descartado em [triggers.py:291](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:291). **A falha original permanece.** Um defeito posterior com ID não numérico também é ignorado quando outro já ocupou `defect`. A verificação precisa considerar todos os defeitos potencialmente anteriores.

Executei `uv run pytest packages/core/tests/unit/execution -q`: **124 passed in 4.45s**. Esses dois cenários escapam da suíte. Nenhum arquivo modificado.

**OBSIDIAN**

- **Execution Engine** — registrar os dois caminhos restantes de perda de stop: alvo bloqueado e múltiplos defeitos.
- **Revisoes-Astra/T3.4b** — acrescentar os cenários reproduzidos desta rodada antes de encerrar o MUST-FIX 1.