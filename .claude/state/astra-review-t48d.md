## RESUMO

**Sim: considero defensável atualizar o pin para `(c7ca9566…, 449734335)` e recomendar a reabertura do escopo atual da mesa. A venda Mayhem ausente não obriga, sozinha, a manter tudo fechado.** Isso é um parecer de compatibilidade; a reautorização de dinheiro real continua sendo tua.

O motivo decisivo: **Mayhem permanece recusado pela admissão atual**, inclusive na pista de lançamento. Os contextos não concedem aprovação Mayhem, os defaults são falsos e a checagem permanece aplicada. Portanto, essa lacuna não cobre uma nova entrada atualmente permitida. Referências: [admission.py:222](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/admission.py:222), [launch_admission.py:126](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_admission.py:126), [inputs.py:118](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/inputs.py:118), [checks.py:290](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/checks.py:290).

**Não estenderia esse aceite para habilitar Mayhem.** `_validate_recipients` comprova nossa seleção de contas; não comprova que o binário novo executará todos os ramos da venda. [tx.py:174](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:174)

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit, acesso ao VPS, assinatura ou envio de transação.

## TESTES

Executei verificações offline por scripts em stdin, com `.venv/Scripts/python.exe -B -`, sobre as fixtures e os builders/decoders reais. Resultados:

```text
IDL canônica T4.8c = T4.8d:
c7ca9566370b9351df9472adb7667dcc77695c49d0b1cc21b953f77567e2dc12
Bytes integrais da conta IDL: hashes iguais
Deploy: 447228373 → 449734335
Autoridade: igual

buy normal em moeda Mayhem: 18 contas, 24 bytes, data_equal True, diffs []
sell clássico:             16 contas, 24 bytes, data_equal True, diffs []

Nos dois trades:
quote_sol_diff 0 protocol_diff 0 creator_diff 0
```

Confirmei também a derivação das duas PDAs sob o programa Mayhem.

**Não executei pytest nem novas simulações mainnet.** Os resultados `89601 / 91801 / 56042 CU` são das capturas fornecidas, que li; não são execuções desta revisão.

Duas correções documentais:

- Os trades dos slots `449773176/77` são de **17:38:03Z**, aproximadamente **2h53 após o deploy**, não uma hora. [fixture:4](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48d_rpc_tx_buy_nonmayhem_raw.json:4)
- `t48d_rpc_tx_sell_mayhem_raw.json` contém **`SellV2`**, não venda legacy. É evidência adicional favorável ao evento e à economia de Mayhem, mas não fecha a lacuna do nosso builder. [fixture:55](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48d_rpc_tx_sell_mayhem_raw.json:55)

## MUST-FIX

**Não encontrei incompatibilidade comprovada que impeça o novo pin.** Encontrei dois problemas operacionais concretos, distintos desse aceite:

1. **Versão 1 pode travar a coleta de uma carteira acompanhada.** O leitor assíncrono também limita `getTransaction` à versão 0; quando recebe erro, o coletor retorna antes de avançar o cursor. **Cenário:** uma carteira acompanhada faz uma transação v1; aquela assinatura passa a impedir a coleta das posteriores. Corrigir suporte de leitura com fixture v1 e teste do consumidor — simplesmente mudar o parâmetro sem validar a interpretação não basta. [rpc_wallet.py:82](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_wallet.py:82), [wallets.py:177](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/wallets.py:177)

2. **O bloqueio no boot também elimina as saídas.** **Cenário:** existe posição aberta, ocorre upgrade e o processo reinicia; ele morre antes de iniciar proteção e reconciliação. Isso merece correção própria para preservar recuperação/saídas sob os guardas previstos, mantendo novas entradas bloqueadas. Não é motivo para contornar o detector nem prova de incompatibilidade do upgrade. Não verifiquei se existem posições abertas agora. [program_check.py:60](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:60), [main.py:268](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:268), [main.py:326](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:326)

## NICE-TO-HAVE

Os pontos cegos mais úteis para completar a prova são:

- **Venda integral com fechamento da ATA.** A simulação clássica tem `closes_ata=false`; o executor acrescenta `CloseAccount` quando vende todo o saldo. Uma alteração que deixasse resíduo poderia fazer essa transação inteira reverter. [fixture:278](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48d_simulation_proof_mainnet_raw.json:278), [build.py:238](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/build.py:238)
- **Cashback e holder rewards não-zero.** Cashback tem ramo próprio de contas restantes; holder rewards não-zero continua fora da aritmética estabelecida do evento. As amostras atuais não exercitam esses casos. [tx.py:198](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:198), [trade_event.py:25](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:25)
- **Limiares econômicos negativos.** Repetiria o teste de compra abaixo do custo permitido e venda acima do recebimento possível. Simulação positiva com folga demonstra execução, mas não demonstra que o programa continua respeitando exatamente nossos limites de slippage.

## O QUE EU FARIA DIFERENTE

**Sobre (a): concordo com a distinção entre os caminhos; moderaria a explicação causal.** As PDAs derivadas e a paridade normal sustentam “comportamento específico do caminho do agente”. Não demonstram, isoladamente, qual condição interna concede essa exceção. A documentação oficial confirma que o agente Mayhem não paga taxa de protocolo. [Mayhem Mode](https://pump.fun/docs/mayhem-mode)

Para refutar a hipótese, compararia o caminho normal e o caminho do agente **na mesma moeda**, incluindo signer, pilha de CPI, dados e contas. Há ainda uma diferença adicional na fixture do agente: o buy tem **25 bytes**, contra 24 no buy normal; o builder permite esse byte opcional. [tx.py:183](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:183)

**Sobre (b): correto para esse evento específico.** O discriminador diferente é ignorado, e o caminho estruturado verifica o programa emissor. Entretanto, o fallback de logs **não autentica o emissor**: discriminar o formato não equivale a verificar sua origem. Eu manteria uma regressão com a transação contendo ambos os eventos. [trade_event.py:247](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:247)

**Sobre (c): hipótese econômica forte; exclusão de layout ainda não demonstrada.** Todos os tamanhos continuam exigindo muito mais que um lamport. Além disso, um erro anterior pode impedir que a execução alcance a validação da PDA. O controle adequado é uma curva Mayhem solvente, com detentor normal, venda pequena e duas variantes de PDA. A possibilidade de faltar liquidez em Mayhem também está documentada oficialmente. [Mayhem Mode](https://pump.fun/docs/mayhem-mode)

**Sobre (d): confirmado, mas pertence à versão da transação, não ao layout Pump.** A compra normal capturada declara `version: 1`; nosso cliente síncrono pede no máximo 0. Isso afeta a leitura dessa transação de terceiro. **Não implica que nossas ordens legacy passaram a exigir v1.** [fixture:385](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48d_rpc_tx_buy_nonmayhem_raw.json:385), [tx_rpc.py:191](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:191), [solana_codec.py:277](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/solana_codec.py:277). A API distingue explicitamente a versão retornada da opção de suporte do cliente. [Solana getTransaction](https://solana.com/docs/rpc/http/gettransaction)

## CONCORDO COM

**Manter os dois campos é necessário.** O detector corretamente diverge se **qualquer um** mudar. A T4.8d é precisamente a regressão que deve impedir alguém de aceitar “hash igual ⇒ programa aprovado”. Já existe teste isolando alteração de slot; acrescentaria o par real T4.8c/T4.8d e preservaria ambos no histórico. [program_identity.py:237](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:237), [test_pumpfun_program_identity.py:140](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py:140)

O SHA identifica a **descrição IDL**; o slot identifica a **fronteira de deploy observada**. Nenhum deles certifica sozinho a semântica do bytecode. Concordo com apoiar o re-registo na combinação de paridade, execução simulada e reconciliação — registrando explicitamente os ramos não exercitados.

## OBSIDIAN

- **Revisões-Astra — T4.8d**: registrar aceite técnico limitado ao escopo atual, provas reproduzidas e lacunas.
- **KB-0094 — upgrade de 12/09/2026**: acrescentar o segundo caso comprovado de deploy com IDL inalterada.
- **KB-0096 — segundo deploy de 15/09/2026**: ligar à nova fronteira `449734335`, preservando o registro anterior.
- **Diário de 2026-09-23**: registrar crash loop, decisão do Everton sobre reabertura e pendências de versão RPC/proteção após restart.