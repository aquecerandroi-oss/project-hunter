**RESUMO**

**REQUEST_CHANGES.** Encontrei dois defeitos de integridade reproduzíveis no leitor e duas lacunas de cobertura. Os **143 testes passaram**, mas não detectam esses casos. Revisão somente leitura; nenhum arquivo alterado, nenhum commit.

**ARQUIVOS**

Revisei os seis módulos solicitados, os testes e a proveniência das fixtures. Há também uma pendência formal: [test_program_logs.py:531](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:531) tem **531 linhas**, acima das 350 exigidas, e usa `float` sobre lamports na [linha 520](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:520).

**TESTES**

Executei, com sincronização do ambiente e escrita de bytecode/cache de pytest desativadas:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_pumpswap_buy_event.py packages/exchange-adapters/tests/unit/test_program_logs.py packages/exchange-adapters/tests/unit/test_program_logs_integrity.py packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py packages/exchange-adapters/tests/unit/test_t1a_provenance.py -q
143 passed in 3.35s

uv run python infra/scripts/check_file_size.py
scanned 1153 files; 0 over budget, 0 grandfathered
```

O gate de tamanho **exclui testes**, portanto não comprova o limite para o arquivo de 531 linhas: [check_file_size.py:42](C:/dev/project-hunter/infra/scripts/check_file_size.py:42).

As reproduções e mutações abaixo ocorreram exclusivamente em memória. Não reconsultei a RPC.

**MUST-FIX**

1. **P1 — Uma linha sem contexto não interrompe a atribuição posterior; o ordinal ainda pode colidir.**  
   Em [program_logs.py:181](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:181), `top is None` incrementa `unattributed_data_lines`, mas não ativa `blind`.

   **Cenário reproduzido:** na fixture `3gYx…`, preservei a primeira linha de evento sem seu frame e, depois, o frame completo da segunda venda. Resultado:

   ```text
   leitura limpa:    ordinal/token_atoms = [(0, 121423), (1, 976016)]
   leitura danificada:                    [(0, 976016)]
   gap=True; unattributed=1; stack_inconsistencies=0
   survivor collides with original first identity: True
   ```

   A segunda venda recebe a identidade da primeira; a recuperação completa encontra conteúdo conflitante sob a mesma identidade. **Discordo, portanto, de considerar encerrada a proteção geral dos ordinais em `wallets-1a.md`**: os casos `None`/`Log truncated` foram tratados, mas esse caminho residual continua aberto. Ao encontrar uma linha de dados sem atribuição possível, a leitura posterior também precisa ficar cega.

2. **P2 — Fim dos logs com pilha aberta retorna `gap=False`.**  
   [program_logs.py:238](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:238) retorna o resultado sem validar a pilha restante.

   **Cenário reproduzido:** cortei os logs da mesma fixture imediatamente antes do segundo `Program data:` — perda simulada de sufixo, sem marcador. A leitura completa tem duas vendas; a cortada retorna:

   ```text
   ordinals=[0]; gap=False
   stack_inconsistencies=0; truncated_logs=0
   ```

   O consumidor recebe uma transação aparentemente completa e não tem indicação para recuperar a segunda venda. O teste [test_program_logs.py:440](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:440) **cristaliza o erro**, exigindo leitura limpa para um `invoke [1]` sem retorno. Validar o encerramento da pilha e usar um frame completo no teste de “nenhum evento”.

**NICE-TO-HAVE**

- **Testar o valor da cauda, não apenas sua presença.** [test_pumpswap_buy_event.py:85](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpswap_buy_event.py:85) aceita qualquer inteiro. Forcei `trailing_u64=0` no construtor: **143 passed**. Isso apaga silenciosamente valores como `169685`, `65800174` e `4878771` das fixtures existentes. Fixar esses valores ou comparar com os oito bytes finais.
- **O teste de aluguel v1 não protege o valor contabilizado.** [test_rpc_v1_transactions.py:201](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py:201) aceita tudo `None`. Substituí as duas funções por retornos sempre ausentes: **1 passed**. A fixture de compra atualmente produz aluguel de **1.513.840 lamports**; uma regressão que perdesse esse custo passaria. A evidência atual demonstra ausência de exceção, não correção contábil.

**O QUE EU FARIA DIFERENTE**

Acrescentaria duas regressões distintas: evento sem contexto seguido de frame válido; e corte de sufixo com pilha aberta. Separaria os testes de normalização dos de integridade para cumprir 350 linhas. Substituiria a comparação com `0.9` por `10 * real_only < 9 * buy.sol_lamports`.

**CONCORDO COM**

A normalização por significado em [buy_event.py:125](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py:125) e a validação da cauda após os campos variáveis em [buy_event.py:208](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py:208) estão coerentes com as fixtures examinadas.

Não encontrei divergência interna de assinatura, slot, horário ou versão na proveniência; os testes dessas correspondências passaram: [test_t1a_provenance.py:38](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_t1a_provenance.py:38). Isso não equivale a uma nova autenticação dos dados contra a cadeia.

**OBSIDIAN**

- **wallets-1a** — acrescentar os dois casos residuais, as reproduções e os mutantes sobreviventes.
- **KB-0184 — O BuyEvent da PumpSwap e as armadilhas de ler eventos do programa inteiro** — registrar que linha sem contexto também invalida ordinais posteriores e que pilha aberta ao final indica lacuna.
- **Exchange Adapters** — condicionar o aceite do leitor ao fechamento dessas duas falhas de integridade.