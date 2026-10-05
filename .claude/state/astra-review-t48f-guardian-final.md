**RESUMO**

**REQUEST_CHANGES: dois MUST-FIX.** O gate está restrito às entradas e a recusa normal não assina. Restam a exceção do callback derrubando as saídas e a perda de evidência parcial dentro do leitor de programas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão estática como `risk-engine-guardian`.

**TESTES**

Li os três testes indicados; não executei comandos de teste nesta rodada. Não afirmo aprovação das suítes.

**MUST-FIX**

1. **ALTA — exceção no gate derruba o executor inteiro.** Em [submit.py:149](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:149), o callback está fora de qualquer tratamento de exceção. Se levantar `RuntimeError`, por exemplo:

   - Nada é assinado: `sign()` vem depois.
   - A linha permanece **`admitted`**, com assinaturas vazias; o `finally` libera `signing_at`, deixando-o **NULL**, supondo sucesso do journal. `_LOCK` não altera o status e `_UNLOCK` somente libera a trava — [journal_db.py:49](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/journal_db.py:49).
   - A exceção atravessa `entry_submit`/`launch_submit`, que só capturam `MemeLiveTradingDisabled` e `SigningLocked` — [entry_submit.py:62](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entry_submit.py:62), [launch_submit.py:68](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_submit.py:68).
   - `forever` re-levanta; o `TaskGroup` cancela os demais loops, inclusive saídas e reconciliação — [main.py:116](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:116), [main.py:301](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:301).

   **Cenário:** há posição aberta; o callback de uma nova compra falha; a compra não assina, mas a posição perde seus loops de proteção até o executor reiniciar.

   **Correção:** capturar `Exception` especificamente na chamada do gate e concluir `failed` com motivo próprio, antes da assinatura. Testar callback que levanta e continuidade dos loops. Não transformar isso em `submitted_unconfirmed`.

2. **MÉDIA — leitura parcialmente decodificada pode perder um upgrade observado.** [program_watch.py:95](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_watch.py:95) acumula slots localmente, mas descarta todos se uma conta posterior vier ausente ou inválida. `program_check_once` recebe somente a exceção, incrementa falhas e não registra divergência — [program_check.py:159](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:159).

   **Cenário:** identidade previamente verificada; resposta contém pump compatível, **PumpSwap com slot diferente**, e fee program `None`. O slot divergente é decodificado, mas perdido quando a terceira conta falha. Na primeira e segunda ocorrências, entradas continuam liberadas; uma leitura seguinte totalmente compatível zera o contador sem tornar aquela divergência persistente.

   **Correção:** preservar os resultados válidos da leitura parcial e registrar suas divergências imediatamente; exigir leitura completa apenas para liberar entradas.

**NICE**

Adicionar prova com journal PostgreSQL para recusa e exceção do callback. O teste atual de recusa verifica `FAILED` e assinaturas vazias usando `InMemoryOrderJournal`, sem provar `_LOCK/_UNLOCK/_STATE` — [test_meme_submit_pre_sign_gate.py:61](C:/dev/project-hunter/packages/core/tests/unit/execution/meme/test_meme_submit_pre_sign_gate.py:61). Cenário protegido: regressão no SQL deixa a ordem admitida ou travada apesar do teste em memória passar.

**O QUE EU FARIA DIFERENTE**

Concentraria as correções nesses dois limites: exceção do callback vira falha terminal sem assinatura; leitor parcial conserva evidência válida. Não mudaria gates ou políticas de saída.

**CONCORDO COM**

- **(1) Saídas/default:** nenhum dos chamadores citados fornece `pre_sign_gate`: `exits.py:300`, `exit_settle.py:203`, `pumpswap_exit.py:157`, `pumpswap_settle.py:33`, `main.py:141` e `infra/scripts/meme_vm.py:169`. O default `None` preserva esse comportamento. Apenas as entradas o injetam, em `entry_submit.py:54` e `launch_submit.py:60`. A API permite recebê-lo; a separação é garantida pelo wiring atual, não pelo tipo da ordem.

- **(2) Recuperação:** não encontrei caminho automático que assine depois aquela compra órfã. Os candidatos excluem propostas com tentativa existente; `expire_orphan_buys` apenas muda a linha para **`refused:admitted_orphan_expired`**, após TTL + 300 s sem trava. Não assina nem reenvia — `repo.py:186`, `launch_repo.py:49`, [orphan_buys.py:49](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/orphan_buys.py:49). Depende de a reconciliação voltar a rodar.

- **(3) Recusa normal:** sim, fica **`failed` sem assinatura**, com motivo preservado e trava liberada; não cria `submitted_unconfirmed` órfão — `submit.py:149`, `submit.py:303`, `journal_db.py:69`.

- **(4) Boot só-saídas:** falhas de leitura e divergências de programa não encerram mais o boot antes dos loops — `program_check.py:107`, `main.py:276`. Não encontrei entrada pump/launch liberada com `program_identity_verified=False`: `context.py:96`, `entries.py:107`, `launch_entries.py:127` e `signing_gate.py:24` bloqueiam. Spot/1 permanece independente, explicitamente em `context.py:248`.

- **(5) Verificação:** não encontrei transição **False → True** sem leitura completa compatível. Divergência já registrada nunca é limpa; inclusive a identidade pump é registrada antes da leitura seguinte — `program_check.py:153`, `program_check.py:201`. A ressalva é o MUST-FIX 2, dentro do leitor, antes de essa evidência chegar ao estado.

**OBSIDIAN**

- **T4.8f — a simulação achou o que as fixtures não achavam:** acrescentar esta revisão, distinguindo recusa, exceção e perda de leitura parcial.
- **Open Bugs:** registrar os dois cenários pendentes e os testes exigidos para encerrá-los.