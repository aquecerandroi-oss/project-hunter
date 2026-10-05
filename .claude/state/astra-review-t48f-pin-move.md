**RESUMO**

**O pino está coerente com as fixtures; não aprovo este diff como liberação irrestrita de entradas live.** Não encontrei regressão direta nas saídas nos três arquivos. Há uma pendência de validação já exigida pelo checklist.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão somente leitura como `code-reviewer`.

**TESTES**

Não executei pytest, lint ou typecheck nesta rodada. Executei verificações somente leitura:

- `git diff --check -- <os três arquivos>`: saída vazia, código **0**.
- Decodificação do cabeçalho bruto: tag **3**, slot **452654932**.
- Conversão do timestamp da fixture: **2026-10-02T15:47:21Z**.
- Comparação das IDLs: base64 T4.8f **idêntico** ao T4.8c; contexto **453633942**.
- **12 fixtures T4.8f** presentes e versionadas; os seis trades usados na paridade pump têm slot posterior ao upgrade e `meta.err == null`.

**MUST-FIX**

1. **ALTA — concluir a prova de fechamento único com persistência real antes de permitir novas entradas.**

   A versão Postgres cobre somente a curva e declara não ter sido executada — [test_exit_decode_failure_integration_t48f.py:1](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_integration_t48f.py:1). O teste das duas praças usa uma implementação falsa de `close_position` que já garante fechamento único; portanto, não prova essa garantia no SQL — [test_exit_decode_failure_t48f.py:165](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_t48f.py:165).

   **Cenário:** após liberar entradas, uma posição migra, a venda confirma, o decode falha e o executor reinicia. Uma divergência entre o fake e a persistência real pode deixar a posição aberta indevidamente ou repetir efeitos contábeis; os testes em memória continuariam verdes.

   **Para encerrar:** executar a integração da curva e acrescentar/executar a variante PumpSwap. A exigência está registrada em [T4.8f-pumpswap-guard.md:120](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/T4.8f-pumpswap-guard.md:120).

   **Distinção importante:** a aprovação final do guardião admite mover o pino mantendo o escopo esgotado; ela própria conserva a integração e a revisão de cashback como condições para aumentar esse escopo. Não equivale a aprovar religamento irrestrito — [T4.8f-pumpswap-guard.md:179](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/T4.8f-pumpswap-guard.md:179).

**NICE-TO-HAVE**

- **Preservar a simulação como evidência executável.** Há relato datado das simulações, mas não encontrei nas fixtures T4.8f um artefato equivalente ao `t48d_simulation_proof_mainnet_raw.json`, carregado pelo teste anterior — [test_pumpfun_tx_parity_t48d.py:277](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48d.py:277). Paridade de trades não demonstra, sozinha, todas as afirmações de simulação e `unexplained` da nova [docstring:167](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:167).
- **Eliminar a circularidade do teste positivo de boot:** `FakeRpc` usa o slot de `EXPECTED_PUMP_PROGRAM` e sobrescreve o cabeçalho bruto. Esse teste pode passar com um pino errado; os testes independentes do adapter compensam isso — [test_program_check.py:48](C:/dev/project-hunter/services/meme-executor/tests/test_program_check.py:48), [test_program_check.py:79](C:/dev/project-hunter/services/meme-executor/tests/test_program_check.py:79).
- Atualizar a docstring antiga que ainda descreve T4.8d como atual e histórico de três deploys — [test_pumpfun_program_identity.py:4](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py:4).

**O QUE EU FARIA DIFERENTE**

Fecharia o registro de aceite distinguindo: pino validado, deploy sem novas entradas e autorização para retomar compras. Também falta localizar a avaliação datada da cobertura das EXP afetadas e a execução completa do gate final exigido pela [T4.8e:84](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/T4.8e-decoders.md:84). O primeiro fill real com `unexplained_lamports == 0` é verificação posterior à retomada controlada, não prova já disponível antes dela.

**CONCORDO COM**

- **(2) Saídas:** o diff não acrescenta bloqueio às saídas. Os submitters de saída continuam sem `pre_sign_gate`, enquanto o callback permanece opcional — [exits.py:300](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:300), [pumpswap_exit.py:157](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_exit.py:157), [submit.py:91](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:91). Isso preserva a permissão de tentar sair; não garante aceitação pelo programa externo.
- **(3) Fixtures:** sim, as capturas de identidade são carregadas e confrontadas com endereço, bytes, hash e slot — [test_pumpfun_program_identity.py:67](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py:67), [linha 108](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py:108). A paridade pump e cashback PumpSwap também carrega transações reais — [test_pumpfun_tx_parity_t48f.py:96](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48f.py:96), [test_pumpswap_tx_t48f.py:321](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpswap_tx_t48f.py:321).
- **(4) Upgrade futuro:** sim, uma divergência detectada de qualquer dos três programas continua bloqueando entradas, persistindo no estado e sendo consultada antes da assinatura — [program_check.py:187](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:187), [context.py:89](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/context.py:89), [submit.py:149](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:149). **Não é detecção instantânea:** há polling; uma leitura parcial pode descartar slots válidos e só bloquear após três falhas. É limitação preexistente, já registrada — [program_watch.py:95](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_watch.py:95), [program_check.py:172](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:172).
- **(5) Slot/hash:** não encontrei inconsistência. Manter o hash e mudar o slot é correto diante das capturas. O hash identifica a **IDL**, não o bytecode; por isso preservar as duas comparações é essencial — [program_identity.py:302](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:302). Não fiz consulta RPC atual.

**OBSIDIAN**

- **T4.8f — a simulação achou o que as fixtures não achavam:** registrar este parecer e separar aprovação do pino de retomada live.
- **Open Bugs:** manter aberta a integração de fechamento único até haver execução nas duas praças.
- **EXP-M18 e demais EXP da pista de eventos:** acrescentar avaliação datada da cobertura perdida entre o upgrade e o deploy do conserto.