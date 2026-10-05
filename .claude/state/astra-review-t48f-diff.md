**RESUMO**

**REQUEST_CHANGES antes de mover o pino.** A correção atende às vendas clássicas verificadas, mas há problemas no caminho cashback e na guarda de entradas/saídas. O patch continua não aplicado.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `code-reviewer`, considerando a memória da T4.8e, KB-0149 e EXP-M18.

**TESTES**

Executei com sincronização, downloads, bytecode e cache do pytest desabilitados:

| Comando | Saída real |
|---|---|
| `uv run pytest packages/exchange-adapters/tests/unit/test_pumpswap_tx_t48f.py packages/exchange-adapters/tests/unit/test_pumpfun_program_watch.py packages/exchange-adapters/tests/unit/test_pumpfun_trade_event_t48e.py -q` | `41 passed in 1.07s` |
| `uv run pytest services/meme-executor/tests/test_program_check.py services/meme-executor/tests/test_program_check_t48f.py services/meme-executor/tests/test_pumpswap_build_t48f.py services/meme-executor/tests/test_pumpswap_unexplained_t48f.py -q` | `23 passed in 1.77s` |
| `uv run pytest services/meme-worker/tests/test_logs_trades_t48e.py -q` | `14 passed in 1.70s` |
| `uv run python infra/scripts/check_file_size.py` | `scanned 1123 files; 0 over budget, 0 grandfathered` |
| `git apply --check .claude/state/tmp/t48f_pin_move.patch` | Saída vazia, código `0` |

Não executei os testes de fechamento: o teste puro **assina com chave sintética**, embora envie somente ao fake ([teste:214](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_t48f.py:214)). Respeitei sua restrição literal de nenhuma assinatura. Não rodei Postgres, novas simulações mainnet, lint ou typecheck. O histórico RED→GREEN do TDD não foi comprovado nesta revisão.

**MUST-FIX**

1. **HIGH — A lista fixa de remaining accounts não cobre cashback.**  
   O builder sempre acrescenta `[pool_v2, recipient, ATA]`, sem consultar `is_cashback_coin` ([tx.py:148](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:148)). O SDK oficial 1.20.0 acrescenta, no sell cashback, **ATA do accumulator e accumulator**, ambos writable, antes de `pool_v2` e buyback. [Fonte: SDK oficial](https://cdn.jsdelivr.net/npm/@pump-fun/pump-swap-sdk@1.20.0/dist/index.js).

   **Cenário:** compra cashback na curva, migração e tentativa de saída PumpSwap. As três contas ocupam posições incompatíveis com a variante cashback; a simulação pode recusar a saída repetidamente. Os testes atuais não demonstram essa variante: constroem todas as pools com cashback/Mayhem `False` ([teste:103](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpswap_tx_t48f.py:103)). Corrigir a montagem condicional e provar com venda cashback pós-upgrade.

2. **HIGH — Bloqueio detectado durante a admissão não impede a compra em andamento.**  
   A consulta a `program_block` ocorre no início ([entries.py:106](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:106)). Depois dos vários `await`s, a última verificação examina somente o kill switch e chama o submit ([entries.py:251](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:251)). O lançamento repete esse padrão ([launch_entries.py:291](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_entries.py:291)).

   **Cenário:** entrada passa pela guarda; enquanto aguarda RPC/banco, o terceiro erro ou um upgrade define o bloqueio; a entrada retoma e assina mesmo assim. Revalidar a guarda na fronteira de assinatura e testar essa intercalação. A janela já existia para divergência e agora também afeta `program_unreadable`.

3. **HIGH — “Saídas nunca travadas” não vale após restart.**  
   No boot live, identidade ilegível ou divergente lança exceção ([program_check.py:78](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:78)). O processo encerra antes de criar os loops, inclusive saídas spot, meme e reconciliação ([main.py:273](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:273), [main.py:330](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:330)).

   **Cenário:** há posição aberta; executor reinicia; somente `getMultipleAccounts` falha ou PumpSwap divergiu. Nenhuma saída volta a funcionar, mesmo que sua simulação fosse aceita. É comportamento herdado, ampliado pela nova leitura no boot. Para cumprir a regra declarada, o boot precisa preservar reconciliação/saídas com entradas bloqueadas.

4. **MEDIUM — A prova preparada para mover o pino está incompleta e contém uma afirmação incorreta.**  
   O novo teste “IDL não mudou” lê apenas a fixture antiga e compara constantes; não compara uma captura T4.8f com os bytes anteriores ([patch:110](C:/dev/project-hunter/.claude/state/tmp/t48f_pin_move.patch:110)). Além disso, o comentário afirma `unexplained_lamports == 0` para todas as simulações, contrariando o cashback com aluguel residual informado no brief ([patch:76](C:/dev/project-hunter/.claude/state/tmp/t48f_pin_move.patch:76)).

   **Cenário:** captura nova ausente/incorreta, teste verde e aprovação baseada numa prova que ele não executou. Incluir a captura verificável ou reformular o teste como verificação apenas do histórico; registrar separadamente a exceção cashback. O patch depende também das fixtures T4.8f já presentes fora dele: não é um pacote autossuficiente.

**NICE-TO-HAVE**

- **Recipient `[0]`: aceitável funcionalmente.** Escolher sempre um membro válido não altera a taxa; distribuir entre os oito reduz concentração de escrita no ATA. A escolha atual está em [pumpswap_build.py:250](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:250); o SDK oficial sorteia o recipient.

- **Mayhem não está coberto:** o builder escolhe sempre `protocol_fee_recipients[0]` ([pumpswap_build.py:249](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:249)), enquanto o SDK usa a lista reservada em Mayhem. Não declarar suporte com base nas três fixtures clássicas. A política de admissão Mayhem é uma proteção separada ([checks.py:290](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/checks.py:290)).

- **Boost/6063 é disponibilidade de reserva real, não mais uma conta faltante.** A cotação mantém apenas a reserva efetiva e não verifica o teto do cofre real ([quote.py:60](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/quote.py:60), [quote.py:137](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/quote.py:137)). Com reserva virtual positiva, uma venda pode cotar acima do que o cofre paga e falhar com 6063. A [IDL oficial](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump_amm.json) identifica exatamente esse limite. Acrescentar diagnóstico/teste; reduzir apenas `min_out` não resolve falta de liquidez.

- **O `finally` não garante execução imediata em `break`/exceção do consumidor.** Minha reprodução, mantendo referência ao gerador, retornou:
  ```text
  after break, retained generator: []
  after explicit close: ['T1']
  ```
  `close()` após iniciar executa o `finally`; antes de iniciar, não. Os consumidores atuais esgotam o gerador sem `await` dentro do loop ([event_gate_eval.py:101](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_eval.py:101), [launch_lane_eval.py:70](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/launch_lane_eval.py:70)). Não vi regressão nesses caminhos, mas a promessa da docstring é excessiva: finalização tardia pode marcar um gap antigo depois de eventos novos. Usaria `contextlib.closing` nos consumidores e teste com referência retida.

- **Fechamento único: cobertura parcial.** O puro cobre ambas as praças, repair, stream replay e segundo reconcile; porém, em PumpSwap, o cenário remove os saldos e termina em `trade_event_missing`, não em exceção de decoder ([teste:80](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_t48f.py:80), [teste:247](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_t48f.py:247)). A idempotência do banco é implementada pelo fake. O teste Postgres cobre apenas curva, sem `on_stream_event` ([integração:45](C:/dev/project-hunter/services/meme-executor/tests/test_exit_decode_failure_integration_t48f.py:45)). Falta essa prova persistente para PumpSwap.

**O QUE EU FARIA DIFERENTE**

Manteria o pino parado até corrigir os bloqueantes e completar as provas. Acrescentaria testes de cashback, bloqueio surgindo durante admissão e restart com posição aberta.

O limiar **3** é razoável para tolerar erros transitórios, mas não significa um teto de 30 segundos: o intervalo é 10 s, o RPC tem timeout de 15 s e o loop dorme depois do trabalho ([config.py:91](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/config.py:91), [tx_rpc.py:84](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:84), [main.py:125](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:125)). Mediria também a idade da última leitura bem-sucedida.

**CONCORDO COM**

- **Contabilidade WSOL:** para a transação canônica, `delta − pre` exclui corretamente aluguel e WSOL anteriores. ATA criada e fechada na mesma transação tem `pre=0`; o aluguel faz ida e volta. O builder fixa `payer=user` e fecha sua ATA ([pumpswap_build.py:252](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:252), [tx.py:178](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:178)). Não generalizar a fórmula para conta não-ATA, ATA não fechada ou outro financiador: o decoder pressupõe a nossa ordem ([pumpswap_build.py:155](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:155)).

- **Stack dos logs:** reconhece os formatos normais de invoke/retorno; texto emitido como `Program log: Program ...` não casa com a regex ancorada. Truncamento não recupera eventos perdidos. Sem contexto, uma linha válida também pode virar trade, não apenas perda: isso é fallback de atribuição, não prova de origem ([trade_event.py:129](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:129)).

- **Guarda em runtime:** divergência permanece bloqueante; leitura boa limpa somente a ilegibilidade. Não encontrei consulta direta a esses bloqueios nos caminhos de saída; a exceção importante é o boot descrito acima ([program_check.py:132](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:132)).

- **Nome da próxima tarefa:** depois de fixar `EXPECTED_PUMP_PROGRAM.task="T4.8f"`, **`regravar T4.8g` está correto**. A indicação do orquestrador para T4.8f deve ser corrigida. O patch aplica em check e seus três arquivos permanecem abaixo de 350 linhas.

**OBSIDIAN**

- **T4.8f — revisão de builder e guarda:** registrar bloqueantes, 78 testes executados e limites das provas.
- **T4.8e-decoders:** atualizar a cobertura de recuperação, mantendo explícita a pendência Postgres/PumpSwap.
- **T4.8e-upgrade-02-10:** corrigir a próxima tarefa para T4.8g e a ressalva contábil da simulação cashback.
- **Open Bugs:** registrar cashback no builder, janela antes da assinatura e bloqueio de saídas no restart.