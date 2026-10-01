**RESUMO**

**Sim: restam dois must-fix antes de congelar.** Revisão como `quant-engineer`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Revisão estática; não executei testes nem detecção.

**MUST-FIX**

1. **Acrescentar uma classificação pode substituir a anterior.** O hash protege o prefixo, mas o dicionário usa a última ocorrência da base. Cenário: `NEW` estava com `excluded:true`; acrescentar `NEW` com `excluded:false` preserva o prefixo e muda o universo sem erro. Recusar classificações conflitantes da mesma base, com teste desse acréscimo. [guards.py:145](C:/dev/project-hunter/.claude/state/h026b-forward/guards.py:145), [guards.py:147](C:/dev/project-hunter/.claude/state/h026b-forward/guards.py:147).

2. **Ausência por estar fora de `TRADING` não fica documentada.** A guarda dispensa esses símbolos, mas o registro guarda somente `api_missing` e aceitações manuais, sem a lista das ausências dispensadas por status. Cenário: moeda pausada devolve série sem a vela do dia, sem erro `−1121`; o dia é concluído sem preservar a justificativa. Gravar símbolo, dia e motivo/status observado para cada ausência dispensada. [guards.py:74](C:/dev/project-hunter/.claude/state/h026b-forward/guards.py:74), [detect_daily.py:167](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:167), [detect_daily.py:180](C:/dev/project-hunter/.claude/state/h026b-forward/detect_daily.py:180).

**NICE-TO-HAVE**

Nenhum adicional nesta rodada.

**O QUE EU FARIA DIFERENTE**

Fecharia esses dois pontos antes do congelamento, sem reabrir o desenho.

**CONCORDO COM**

A validação do CSV e a parada dura atendem aos cenários apontados anteriormente. [archive.py:93](C:/dev/project-hunter/.claude/state/h026b-forward/archive.py:93), [guards.py:99](C:/dev/project-hunter/.claude/state/h026b-forward/guards.py:99).

**OBSIDIAN**

- **H-028-forward-prereg** — registrar estes dois bloqueios residuais e, depois, as respectivas correções.