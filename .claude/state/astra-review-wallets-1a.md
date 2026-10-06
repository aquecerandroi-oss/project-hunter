**RESUMO**

**Eu devolveria a onda 1a para correção.** A contabilidade dos swaps está coerente; os bloqueios estão na informação perdida das reservas, na estabilidade do ordinal e na validação de atribuição/unidade.

Revisão como `exchange-integration-specialist`, considerando a memória de **KB-0149**, **KB-0183**, **wallet-tape-storage** e **wallets-engine**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit, worker ou configuração ativado.

**TESTES**

Não executei pytest, Ruff, Pyright nem mutação. Fiz leitura do código, `git diff` da Parte B e inspeção de bytes das fixtures em memória via PowerShell.

A inspeção de `t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json` produziu:

```text
event_pool_quote=141161932418
virtual_quote=25730818627
wsol_pre_balance=141161932418
```

Portanto, os achados de testes abaixo são análise estática, não resultados de execução.

**MUST-FIX**

1. **ALTA — O `SwapRecord` perde informação necessária para precificar a PumpSwap.**

   As conversões preservam reservas **anteriores**, mas descartam `virtual_quote_reserves` e a parcela LP da taxa. O `Fill.Reserves` exige estado **posterior**. Além disso, o próprio adapter calcula quote efetivo como saldo do vault **mais reserva virtual**. Referências: [swap_record.py:146](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:146), [swap_record.py:181](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:181), [tape.py:54](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:54), [quote.py:73](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/quote.py:73).

   **Cenário concreto:** na fixture acima, usar `sol_reserves` diretamente ignora **25.730.818.627** de reserva virtual. Mesmo corrigindo isso, transformar a compra em estado posterior exige acrescentar `net_quote_in + lp_fee`; o registro guarda somente a taxa total, que não permite recuperar LP separadamente.

   **Correção:** preservar reservas reais/efetivas e o movimento exato do vault, ou produzir explicitamente estados anterior e posterior antes de descartar o evento. A ponte para `Fill` precisa de teste real. O motor também reconstrói o estado anterior desfazendo apenas `sol_lamports`, sem LP: [pricing.py:130](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:130). **Não basta mudar o rótulo para `after_trade`.**

2. **ALTA — Base64 inválido ou payload curto desloca a identidade dos eventos seguintes.**

   O ordinal avança somente depois dessas validações: [program_logs.py:169](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:169).

   **Cenário concreto:** uma transação contém eventos A e B do mesmo programa. Na primeira leitura, A chega inválido: B recebe ordinal **0**. Na recuperação completa, A recebe **0** e B recebe **1**. Isso cria conflito entre A e B e permite contar B novamente. Marcar `gap` não conserta as identidades já emitidas.

   **Correção:** reservar ordinal para toda linha `Program data:` atribuída ao programa, antes de decodificar. Se faltar a própria linha ou o contexto impedir determinar o ordinal, não emitir identidades aparentemente definitivas após essa perda.

3. **MÉDIA — A pilha aceita retornos e profundidades incoerentes sem marcar lacuna.**

   Qualquer linha que corresponda a `_RETURN` remove o topo, sem conferir o programa; `invoke [n]` também aceita saltos de profundidade. Referência: [program_logs.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:152).

   **Cenário concreto, entrada malformada:** Pump invoca um programa estrangeiro; aparece `Program Outro success`; o leitor remove o estrangeiro. Uma linha seguinte desse estrangeiro, contendo discriminador de `TradeEvent`, passa a ser atribuída ao Pump. Pode virar swap com `gap=False`.

   **Correção:** validar programa do retorno e continuidade da profundidade; inconsistência deve invalidar o contexto e ser contada. Não encontrei esse defeito nas fixtures reais; ele viola o contrato declarado de tratamento de logs malformados.

4. **MÉDIA — Igualdade de quantidades não comprova que a quote é SOL.**

   `_curve` aceita mint diferente de SOL quando `quote_amount == sol_amount > 0`, e então grava `quote_is_sol=True`: [swap_record.py:118](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:118).

   **Cenário concreto:** evento com quote USDC e os dois campos numéricos iguais entra como lamports. O teste atual muda **mint e quantidade simultaneamente**, deixando esse caso passar: [test_program_logs.py:371](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:371).

   **Correção:** validar identidade da quote por conjunto explícito de representações comprovadas. Se essa igualdade é compatibilidade necessária de algum layout, restringi-la ao layout e comprová-la com fixture.

**NICE-TO-HAVE**

- **Evitar mutação da transação recebida.** `keys += ...` altera o próprio `message.accountKeys`; chamadas repetidas em v0 com ALT acumulam endereços. Copiar a lista elimina esse efeito. O padrão também existe nos leitores antigos: [buy_event.py:265](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py:265), [trade_event.py:73](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:73), [sell_event.py:212](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/sell_event.py:212).
- **Distinguir evento desconhecido de não-swap conhecido.** Hoje qualquer discriminador desconhecido vira `non_swap_events`, sem lacuna. Há contador, mas um novo tipo de swap pode desaparecer da população sem alerta específico: [program_logs.py:192](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:192).
- **Ampliar a prova v1 até a contabilidade.** Os testes exercitam eventos e `WalletFill`, mas não assertam valores de rent, `decode_pumpswap_fills` ou `spot_send_rules.fill_from_transaction`: [test_rpc_v1_transactions.py:147](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py:147).

**O QUE EU FARIA DIFERENTE**

Faria primeiro testes de fronteira, com estes casos:

| Caso | O que deve provar |
|---|---|
| A inválido, B válido; depois recuperação completa | B mantém identidade; A recupera sem colisão |
| Retorno de programa errado e salto de profundidade | Contexto não fabrica atribuição; há lacuna |
| Quote não-SOL com quantidades iguais | Não vira lamports |
| Fixture PumpSwap com reserva virtual e LP | Estado utilizado pelo motor corresponde à cadeia |
| Duas leituras do mesmo objeto v0 | Entrada permanece idêntica |

**Mutação:** pela leitura, sobreviveriam alterações como zerar `virtual_quote_reserves` no `BuyEvent`, trocar seu i128 para leitura sem sinal nas fixtures positivas e remover cashback da taxa de **compra**, já que nenhuma compra testada tem cashback. Os testes verificam conservação, mas vários esperados são derivados do próprio decoder: [test_pumpswap_buy_event.py:88](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpswap_buy_event.py:88).

Em contrapartida, há provas fortes contra trocar campos de conta, quantidade de base, quote recebido pelo vault e interpretação de `buy_exact`: [test_pumpswap_buy_event.py:61](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpswap_buy_event.py:61). A comparação **byte a byte** entre logs e self-CPI também é melhor que comparar apenas contagens: [test_program_logs.py:105](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:105).

**CONCORDO COM**

- **Semântica monetária:** curva usa `sol_amount`; compra PumpSwap usa `quote_amount_in_with_lp_fee - lp_fee`; venda usa `quote_amount_out`. Somar taxas na compra e subtrair na venda corresponde ao `Fill`, inclusive cashback na venda. Não há arredondamento novo nessa normalização: são operações inteiras sobre valores declarados. Referências: [swap_record.py:118](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:118), [tape.py:11](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:11).
- **Recusar caudas não comprovadas**, validar depois dos campos variáveis e não somar a cauda desconhecida: [buy_event.py:188](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py:188).
- **Parte B: mudar para máximo 1.** É ampliação da versão aceita, sem conversão de legacy/v0; a documentação oficial descreve o parâmetro como teto. [Documentação Solana](https://solana.com/pl/developers/guides/advanced/versions). O diff mantém encoding e commitment: [tx_rpc.py:184](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/tx_rpc.py:184), [rpc_wallet.py:72](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rpc_wallet.py:72).

  Não encontrei quebra estrutural v1 nos consumidores citados: eles leem chaves, instruções e saldos, sem exigir `addressTableLookups` ou rejeitar `version=1`. Referências: [rent.py:45](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/rent.py:45), [wallet_fills.py:126](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/wallet_fills.py:126), [pumpswap_build.py:136](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/pumpswap_build.py:136), [spot_send_rules.py:195](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send_rules.py:195). Isso é conclusão de leitura, não prova executada de reconciliação.

**DISCORDO DE**

- **“Compatível com `Fill`” sem qualificar reservas.** Dinheiro: sim. Estado de preço: ainda não.
- **“Não conta duas vezes” como garantia do leitor isolado.** Ele fornece identidades; deduplicação entre notificações continua sendo responsabilidade do consumidor. `tape.dedupe` faz isso, desde que os ordinais sejam estáveis: [tape.py:144](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:144).
- **“Legacy/v0 byte-idênticos” como resultado provado pelos testes.** O mock devolve o mesmo objeto por construção; comprova o comportamento local do cliente, não uma comparação de respostas RPC com os dois parâmetros: [test_rpc_v1_transactions.py:46](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py:46).

**OBSIDIAN**

Nenhuma página alterada. Deveriam receber atualização:

- **Exchange Adapters** — registrar BuyEvent e suporte RPC v1, com os bloqueios de identidade e reservas.
- **wallets-engine** — documentar a incompatibilidade entre reservas PumpSwap e a reconstrução de estados do motor.
- **KB-0183** — separar cobertura de decodificação de suficiência contábil dos registros.
- **Revisão Astra — H-030 onda 1a** — registrar estes achados, cenários e testes exigidos antes do aceite.