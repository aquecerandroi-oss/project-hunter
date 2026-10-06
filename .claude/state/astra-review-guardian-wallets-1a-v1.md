## RESUMO

**DONE — concordo com o diff; nenhum must-fix identificado neste escopo.** Revisão como `risk-engine-guardian`, somente leitura.

1. **Consumidores de `getTransaction`: não encontrei condicionais ou asserts sobre `version`, `addressTableLookups` ou `transactionConfig` nos caminhos pesquisados.** Os decoders usam eventos, saldos e `accountKeys` + `loadedAddresses`: [fills.py:135](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/fills.py:135), [pumpswap_build.py:194](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:194), [spot_send_rules.py:195](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:195). Existe uma recusa de versão diferente de zero em [versioned_tx.py:93](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/jupiter/versioned_tx.py:93), mas ela valida **bytes da mensagem Jupiter**, não a resposta desse RPC.

2. **Legacy/v0 mantêm o comportamento de leitura.** A requisição conserva `encoding` e `commitment`; o cliente continua devolvendo o resultado sem transformação: [tx_rpc.py:184](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:184), [rpc_wallet.py:72](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_wallet.py:72). O teste live compara a igualdade dos JSONs recebidos com teto 0 e 1: [test_live_tx_version.py:82](C:/dev/project-hunter/packages/exchange-adapters/tests/live/test_live_tx_version.py:82). Eu escreveria **“JSONs iguais nas amostras verificadas”**, não uma garantia universal de bytes HTTP idênticos. A [documentação oficial](https://solana.com/docs/rpc/http/gettransaction) distingue configuração da consulta e versão retornada.

3. **Para nossas transações efetivamente legacy/v0, a reconciliação não muda. Para uma resposta v1 antes recusada, muda sim:** `-32015` virava exceção e `submitted_unconfirmed`; agora o conteúdo pode ser decodificado e registrado como `CONFIRMED`. Isso reconhece uma execução já ocorrida, sem reenviar ou reassinar: [submit.py:191](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:191), [submit.py:220](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:220). Também destrava, quando aplicável, o assentamento spot ([spot_reconcile.py:233](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:233)), a confirmação imediata ([spot_send.py:274](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:274)) e a tesouraria ([treasury_reconcile.py:118](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_reconcile.py:118)). **`send_path.py:154` tem outro efeito:** recuperar a taxa de uma transação que falhou on-chain; não transformá-la em compra/venda bem-sucedida ([send_path.py:146](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/send_path.py:146)).

4. **Não identifiquei enfraquecimento das saídas.** As decisões de stop/alvo/emergência permanecem no mesmo caminho ([spot_exits.py:133](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:133)); a venda meme continua sem o bloqueio de assinatura próprio das entradas ([exits.py:300](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:300)). Ler um fill antes inacessível pode concluir o fechamento; a ordem pendente continua sendo reconciliada antes de permitir outra venda ([exit_settle.py:78](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_settle.py:78)).

5. **Sim, o cursor ficava impedido de ultrapassar a assinatura que recebia `-32015`.** O `return cycle` ocorre antes da atualização do cursor; assinaturas anteriores já processadas podem ter avançado normalmente. Com a leitura v1 bem-sucedida, o processamento chega à atualização: [wallets.py:169](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:169), [wallets.py:214](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:214). Isso recupera histórico, posições observadas e comparações com o Lab. **Não encontrei essas tabelas alimentando disparos de entrada:** `lab_context_for` calcula uma anotação comparativa, depois gravada no histórico ([wallets_lab.py:116](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets_lab.py:116), [wallets.py:197](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:197)). Os indicadores compartilhados de saúde do RPC também mudam ([wallets.py:105](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:105)).

## ARQUIVOS

Nenhum arquivo criado ou modificado por mim. Revisei os quatro arquivos do diff, os dois testes novos e os consumidores citados.

## TESTES

- Executei `git diff --check -- <os quatro caminhos do diff>`: **exit code 0**; somente avisos de conversão CRLF → LF.
- Não executei pytest nesta revisão somente leitura. Os **2065 passed** e a equivalência dos decoders são resultados informados por você, não reexecutados por mim.
- Li os testes unitários e live; a prova live anterior também está registrada em [wallets-1a.md:35](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-1a.md:35).

## MUST-FIX

**Nenhum com cenário concreto de falha introduzida por este diff.**

## NICE-TO-HAVE

- Fixar como regressão no executor a sequência **erro de leitura → unconfirmed → resposta v1 válida → confirmado uma única vez**, incluindo fechamento. O comportamento está em [submit.py:191](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/submit.py:191); os testes novos exercitam diretamente o cliente em [test_rpc_v1_transactions.py:75](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py:75).
- Não generalizar “nenhum decoder muta a tx”: [trade_event.py:73](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:73) ainda altera `accountKeys` quando há endereços carregados. É dívida anterior, já registrada em [Open Bugs.md:1620](<C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:1620>); não bloqueia esta correção.

## O QUE EU FARIA DIFERENTE

Descreveria a mudança como **ampliação da leitura com efeitos possíveis na reconciliação e na coleta**, evitando “nenhum efeito operacional”. Ela pode transformar uma execução inacessível em fill reconhecido e permitir que o cursor prossiga, pelos caminhos acima.

## CONCORDO COM

O teto explícito em 1, a preservação dos erros como erros e a cópia de `accountKeys` em [sell_event.py:212](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:212). A correção é compatível com a orientação da [KB-0149](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md): corrigir infraestrutura e contabilidade sem alterar parâmetros de estratégia.

## OBSIDIAN

- **wallets-1a** — acrescentar este parecer: reconciliação própria, cursor e ausência de ligação encontrada com gatilhos de entrada.
- **Exchange Adapters** — distinguir compatibilidade legacy/v0 da ampliação operacional para v1.
- **KB-0184** — esclarecer que os leitores RPC já usados pelos workers mudam de comportamento, embora os novos leitores de logs permaneçam desacoplados.