**MUST-FIX**

Nenhum cenário concreto restante identificado. **must-fix 2 fechado**, sob a premissa declarada de que o relógio não recua e a convenção “carimbado até L”.

**NICE-TO-HAVE**

Acrescentar regressão real de `PREPARE TRANSACTION` → export recusado → `COMMIT PREPARED` → export aceito, cobrindo a guarda de [estado_token.py:75](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:75). A [finalização no PostgreSQL 16](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/access/transam/twophase.c) mantém a preparada registrada até sua saída do ProcArray.

**CONCORDO COM**

As observações ampliadas e as recusas cobrem os contraexemplos da rodada 3: [export_h022.sql:27](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:27) e [estado_token.py:68](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:68). A distinção entre carimbo e visibilidade está explícita em [protocolo_h022.txt:85](C:/dev/project-hunter/infra/research/exp_m26/protocolo_h022.txt:85).

Revisão estática; não executei testes nem modifiquei arquivos.

**OBSIDIAN**

- **EXP-M26 — gráfico em moedas maduras:** registrar o fechamento condicionado do must-fix 2.
- **Revisões-Astra — token-state-history, rodada 4:** registrar este parecer e a regressão 2PC sugerida.