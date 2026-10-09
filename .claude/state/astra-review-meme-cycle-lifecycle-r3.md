**RESUMO**

**REQUEST_CHANGES.** Encontrei três pontos a corrigir: falha mascarada como encerramento limpo, flusher sem supervisão efetiva e exclusão silenciosa de ciclos válidos pela consulta. Não encontrei ACK indevido no fluxo serial revisado.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei os sete arquivos indicados, usando o papel `code-reviewer` e a memória de **Meme / histórico de ciclos** e **meme-cycle-metrics**.

**TESTES**

Executei, com bytecode e cache do pytest desabilitados:

```text
uv run pytest services/meme-worker/tests/test_cycle_lifecycle.py services/meme-worker/tests/test_cycle_history_contract.py -q
14 passed in 14.43s
```

Reproduções adicionais em memória, chamando as funções reais e injetando falhas:

```text
crash_then_cancel_in_finally: clean= [True]
cancel_only_group: clean= [False]
flusher_failure: RuntimeError body_alive=True
flusher_failure: clean= [True] logs= ['meme_loop_failed']
external_cancel: writing= True abandoned= 0 queued= 1
drain_previous_pending: writing= True commits= 0
late_commit_retry: physical_rows= 2 queued= 0
```

Não executei a integração com PostgreSQL nesta revisão somente leitura.

**MUST-FIX**

1. **HIGH — Uma queda pode receber `clean=True`.**  
   [main.py:329](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:329) · [cycle_wiring.py:99](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:99).

   **Cenário:** o `TaskGroup` falha com `ExceptionGroup`; `_run` entra no `finally` e aguarda fechar clientes. Nesse intervalo chega SIGTERM, que cancela a tarefa — caminho existente em [runtime.py:196](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:196). O `CancelledError` substitui a exceção que estava propagando. `supervised()` recebe apenas o cancelamento e grava `clean=True`. Reproduzido com falha seguida de cancelamento no `finally`.

   **Correção:** preservar a informação de falha antes de começar a limpeza; um cancelamento posterior não pode apagá-la.

2. **MEDIUM — O flusher pode morrer e deixar o worker funcionando sem gravador.**  
   [cycle_wiring.py:93](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:93) · [collect.py:341](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:341).

   **Cenário:** uma exceção inesperada escapa do flush — por exemplo, falha do destino de logging ao registrar uma falha de escrita. `forever()` termina, mas ninguém monitora seu resultado durante o corpo supervisionado. A fila continua recebendo ciclos, eventualmente descartando-os. No encerramento, `asyncio.wait()` não propaga a exceção do flusher, e o fim ainda pode receber `clean=True`. A injeção de `RuntimeError` reproduziu esse comportamento.

   **Precisão sobre “silêncio”:** uma exceção comum normalmente deixa `meme_loop_failed`; portanto, não é necessariamente silêncio nos logs. É ausência de reação da supervisão. Cancelamento isolado do flusher também encerra sem esse log.

   **Correção:** observar a conclusão inesperada e propagá-la ou recuperar explicitamente o gravador.

3. **MEDIUM — O limite superior exclui dados válidos sem sinalizar incompletude.**  
   [cycle_history.py:118](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:118) · [test_cycle_history_integration.py:100](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history_integration.py:100).

   **Cenário:** Lab desligado, cadeia produzindo aproximadamente um ciclo por minuto, banco indisponível por 26 horas. Os aproximadamente 1.560 ciclos cabem na fila de 4.096; não precisa haver descarte. Após recuperação, ciclos de uma janela encerrada há mais de um dia são persistidos, mas desaparecem da consulta dessa janela. `dropped_total` pode continuar zero: ele conta transbordamento da fila, não exclusão pelo SQL ([cycle_queue.py:49](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_queue.py:49)).

   O teste atual **confirma a exclusão**, não a segurança da leitura. Ampliar `until` também muda a janela de ciclos analisada.

   **Correção:** separar a janela de persistência da janela de medição, ou detectar exclusões e devolver explicitamente “cobertura não comprovada”.

**NICE-TO-HAVE**

- **LOW — Abandono por cancelamento externo não incrementa `abandoned_total`.** Em [cycle_history.py:230](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:230), o chamador cancela a escrita e sai; se ela resistir ao cancelamento, continua em voo com contador zero. Reproduzido. Contabilizar esse caminho tornaria a telemetria fiel ao que permanece pendente.

**O QUE EU FARIA DIFERENTE**

Acrescentaria regressões para falha seguida de SIGTERM durante a limpeza, morte isolada do flusher e persistência tardia sem transbordamento. São os cenários que os testes atuais não fecham.

**CONCORDO COM**

- **ACK e duplicatas:** o ACK ocorre após sucesso observado e usa o token do lote ([cycle_history.py:168](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:168)). Commit tardio seguido de retry duplicou fisicamente a linha na reprodução; isso está dentro do contrato de deduplicação.
- **Escrita anterior pendente:** o drain espera dentro do orçamento e não abre outra escrita enquanto a anterior permanece pendente ([cycle_history.py:219](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:219)). A tarefa pode sobreviver ao drain; o prazo limita a espera, não garante sua terminação.
- **Outras exceções:** erro comum no `finally` resulta em `clean=False`. `KeyboardInterrupt` direto também. Um grupo contendo apenas cancelamentos recebe `False`, mas seria `BaseExceptionGroup`; não encontrei caminho atual que o produza naturalmente. Não o classifico como achado separado ([cycle_wiring.py:99](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:99)).

**OBSIDIAN**

- **Revisão da Astra — tempo de ciclo da cadeia e do Lab:** registrar os três bloqueantes e as reproduções desta conferência.
- **Meme / README:** esclarecer supervisão do gravador, preservação da causa de término e incompletude por persistência tardia.
- **Open Bugs:** registrar a queda mascarada por cancelamento durante a limpeza e o flusher encerrado sem reação do supervisor.