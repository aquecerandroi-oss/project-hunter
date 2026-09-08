**RESUMO**

Como `quant-engineer`: **(1)** falha no pool deixa shards sem merge; uma retomada pode apagá-los. **(2)** a igualdade com `bars_evaluated` não está garantida sob falhas. **(3)** uma barra é válida para comparar o mesmo instante, mas o teste atual é insuficiente.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Revisão estática; não executei testes, pois eles criam arquivos e usam banco, incompatível com esta sessão somente leitura.

**MUST-FIX**

- **Preservar diagnósticos entre tentativas.** Cenário: BTC termina, ETH falha; `gather` propaga a exceção e o merge não acontece ([run.py:171](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/run.py:171)). As linhas permanecem nos shards, mas executar novamente com o mesmo caminho os trunca em `"w"` ([explain.py:120](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/explain.py:120)). Usar identidade por tentativa/fatia e conservar os arquivos incompletos.

- **Não apagar shards antes de confirmar a gravação; validar a contagem.** Cenário: shard pequeno cabe no buffer do destino, é apagado, e o fechamento do destino falha por falta de espaço: perde-se a cópia recuperável. O merge também ignora shards ausentes ([explain.py:160](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/explain.py:160)); o pai apenas registra `lines` e `bars`, sem exigir igualdade ([run.py:220](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/run.py:220)). Confirmar escrita antes da limpeza e recusar resultado incompleto.

**NICE-TO-HAVE**

Fortalecer a prova temporal: a mutação começa em `TRIGGER_BAR + 5 min`, deixando os cinco minutos imediatamente posteriores intactos ([test_replay_explain.py:71](C:/dev/project-hunter/services/strategy-worker/tests/test_replay_explain.py:71)). O teste não-final também altera apenas esse futuro distante ([test_replay_explain.py:361](C:/dev/project-hunter/services/strategy-worker/tests/test_replay_explain.py:361)). Testar desde o corte, não-finais dentro do histórico e vários cortes de uma janela maior, comparando somente os prefixos anteriores à mutação.

**O QUE EU FARIA DIFERENTE**

Publicaria um artefato por tentativa/fatia, validando contagem e histograma antes de consolidá-lo. Acrescentaria testes de falha do worker, falha do merge e retomada.

**CONCORDO COM**

Reutilizar a mesma `Evaluation` para contador e diagnóstico preserva a correspondência no caminho sem falhas ([simulate.py:209](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/simulate.py:209)). A contrap prova com corte antecipado também é útil ([test_replay_explain.py:366](C:/dev/project-hunter/services/strategy-worker/tests/test_replay_explain.py:366)).

**OBSIDIAN**

- **Workers** — documentar recuperação de shards e garantia de completude do explain ledger.
- **Revisoes-Astra/Index** — registrar esta revisão e as lacunas da prova temporal.