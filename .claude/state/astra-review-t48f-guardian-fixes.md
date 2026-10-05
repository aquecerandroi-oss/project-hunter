**RESUMO**

**REQUEST_CHANGES.** O boot só-saídas resolve o problema principal, mas ainda há duas brechas na guarda: mudança durante a simulação e perda de divergência quando uma leitura posterior falha. Além disso, `spot/1` continua comprando: o rótulo “exits-only” precisa explicitar esse escopo.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhuma assinatura ou envio. Revisão como `code-reviewer`, considerando a memória de **T4.8f-pumpswap-guard**, **KB-0149** e **EXP-M18**.

**TESTES**

- `git diff --check -- services/meme-executor packages/exchange-adapters`: sem diagnóstico de whitespace; avisos de CRLF.
- Varredura estática: `exit_modules_checked=12; program_guard_references=0`.
- Os nove módulos do executor indicados na correção têm até 350 linhas; `main.py` e `heartbeat.py` estão exatamente no limite.
- **Não executei pytest, lint, typecheck ou simulações nesta revisão.** Não comprovo a sequência vermelho→verde de TDD pelo diff.

**MUST-FIX**

1. **HIGH — a checagem ainda antecede a simulação, não a assinatura efetiva.**  
   Depois de `signing_block`, os handlers chamam os submitters em outra thread ([entry_submit.py:61](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entry_submit.py:61), [launch_submit.py:67](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_submit.py:67)). Dentro dela, há acesso ao journal e simulação antes de `signer.sign`, sem nova checagem ([submit.py:106](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:106), [submit.py:128](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:128)).

   **Cenário:** entrada passa pela guarda → simulação demora → tique registra `program_divergence` → simulação responde sucesso → entrada é assinada apesar do bloqueio já conhecido.

   Exigir a guarda também imediatamente antes da assinatura, exclusivamente para entradas. O teste deve introduzir o bloqueio **durante a simulação**, usando um sentinela que detecte tentativa de assinatura sem assinar. Os testes novos cobrem bloqueio durante `kill.refresh`, mas substituem o caminho posterior ([test_signing_gate_wiring_t48f.py:46](C:/dev/project-hunter/services/meme-executor/tests/test_signing_gate_wiring_t48f.py:46), [test_signing_gate_wiring_t48f.py:174](C:/dev/project-hunter/services/meme-executor/tests/test_signing_gate_wiring_t48f.py:174)).

2. **HIGH — divergência parcialmente observada não fica pegajosa.**  
   No boot, a identidade só é comparada depois de `read_deploy_slots`; se esta falha, retorna sem registrar a divergência já disponível. O caminho completo de recuperação repete isso ([program_check.py:79](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:79), [program_check.py:125](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:125)).

   **Cenário:** leitura completa da identidade pump retorna hash divergente → leitura dos demais programas falha → uma leitura posterior volta ao hash esperado → `verified=True`, sem intervenção, embora uma divergência tenha sido observada.

   Registrar divergências assim que cada resultado validado estiver disponível; reservar a exigência de leitura completa para **liberar**, não para **bloquear**. Isso já constava do parecer anterior: “Preserve imediatamente qualquer divergência observada”.

3. **MEDIUM — “executor exits-only” promete mais que o comportamento implementado.**  
   O boot agenda `spot_entries`, e essa entrada verifica kill switch, sem consultar `program_block` ([main.py:325](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:325), [spot_entries.py:251](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:251)). Entretanto, o heartbeat publica `program_mode=exits_only` ([context.py:254](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/context.py:254)).

   **Cenário:** boot divergente, spot habilitada e sinal aprovado → nova compra spot enquanto o operador lê “exits-only”.

   Recomendo explicitar **“entradas pump/launch bloqueadas; spot independente”**, preservando a separação das mesas. Se a intenção for bloqueio global, falta implementá-lo e testá-lo.

**NICE-TO-HAVE**

- **Nomear o aluguel do acumulador.** Recomendo `account_rent_lamports`, com discriminação `user_volume_accumulator`. Não fixar `1.346.200`: reconhecer criação/financiamento comprovados pela transação. Manter `sell_net_lamports` pelo delta real; ajustar apenas a decomposição esperada do residual. Hoje o custo já reduz o líquido, mas aparece como inexplicado ([pumpswap_build.py:76](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:76)). Portanto, não encontrei erro de PnL apenas pela falta do nome.

- **Cashback: separar existência do acumulador e de seu ATA.** Nas duas fixtures, o ATA do acumulador já tem saldo prévio. O builder passa esse ATA, mas só cria explicitamente o ATA WSOL do usuário ([tx.py:137](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:137), [tx.py:228](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:228)). A simulação relatada sem acumulador é evidência relevante; registrar também se **o ATA dele estava ausente**, com pre/post das duas contas. Não afirmo que precise existir: isso ainda não está demonstrado pelas fixtures examinadas.

- **Precisar a promessa de paridade.** F2 compara os 24 bytes principais, contas e writable; não compara signer e admite a cauda de 26 bytes do roteador ([test_pumpfun_tx_parity_t48f.py:114](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48f.py:114)). Acrescentar signer e descrever essas exceções. O patch preparado também ainda diz que cashback sell não foi provado ([patch:85](C:/dev/project-hunter/.claude/state/tmp/t48f_pin_move.patch:85)).

**O QUE EU FARIA DIFERENTE**

Acrescentaria dois testes determinísticos: divergência seguida de falha parcial; e bloqueio surgindo dentro da simulação. Também exercitaria `event_exits` habilitado: o teste de boot atual o desativa e comprova agendamento dos demais loops, não execução de uma saída ([test_exits_only_boot_t48f.py:130](C:/dev/project-hunter/services/meme-executor/tests/test_exits_only_boot_t48f.py:130)).

**CONCORDO COM**

- Nascer não verificado e recuperar somente após leitura completa compatível é correto; divergência **já registrada** permanece bloqueante ([context.py:89](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/context.py:89), [program_check.py:171](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:171)).
- Não encontrei bloqueio direto das saídas pela nova guarda. `event_exits`, saídas spot e reconcile continuam sendo agendados independentemente dela ([main.py:302](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:302)).
- Heartbeat e status recebem o estado; a ressalva é o escopo do texto ([heartbeat.py:243](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/heartbeat.py:243), [main.py:252](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:252)).
- Sortear o recipient uma vez por intenção e persistir a escolha está correto ([pumpswap_build.py:225](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:225), [pumpswap_build.py:259](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:259)).

**OBSIDIAN**

- **T4.8f-pumpswap-guard** — registrar avanços F1–F6, as duas brechas restantes e o escopo independente da spot.
- **Open Bugs** — acompanhar checagem após simulação e preservação de divergência em leitura parcial.
- **KB-0171-custo-real-da-spot-1** — relacionar aluguel do acumulador à decomposição de custos, preservando o líquido real.