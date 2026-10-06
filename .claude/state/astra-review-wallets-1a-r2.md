## RESUMO

**Ainda devolveria a 1a para uma correção de identidade após perda de linha.** Os consertos de reservas, base64 inválido, pilha incoerente e quote por mint estão presentes. O diagnóstico sobre o motor 1c continua correto e também afeta a **compra**, não apenas a venda.

Revisão como `exchange-integration-specialist`, considerando **KB-0149**, **KB-0183**, **wallet-tape-storage** e **wallets-engine**.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Executei com bytecode e cache do pytest desativados, sem sincronizar dependências:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_program_logs.py packages/exchange-adapters/tests/unit/test_program_logs_integrity.py packages/exchange-adapters/tests/unit/test_pumpswap_buy_event.py packages/exchange-adapters/tests/unit/test_rpc_v1_transactions.py -q -p no:cacheprovider
112 passed in 4.47s

uv run pytest packages/indicators/tests/meme/test_wallets_pricing.py -q -p no:cacheprovider
11 passed in 1.51s
```

Com `HUNTER_LIVE_TESTS=1`:

```text
uv run pytest packages/exchange-adapters/tests/live/test_live_tx_version.py -m live -q -p no:cacheprovider
3 passed in 3.42s
```

Inspeções adicionais em memória:

- **29 fixtures de transações bem-sucedidas:** nenhuma inconsistência de pilha; sequências completas de payloads por programa idênticas entre logs e self-CPI, incluindo eventos não-swap.
- **Dez fixtures com trade único por pool:** reservas pós-trade de base e quote iguais aos saldos finais dos vaults.
- Reproduções sintéticas abaixo.

Não reexecutei os 13 mutantes nem os gates gerais de lint/typecheck.

## MUST-FIX

### 1. ALTA — Após perda de linha, o ordinal ainda pode colidir na recuperação

Em [_Scan.line:141](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:141), `malformed_lines` e `truncated_logs` apenas incrementam contadores. A leitura continua com os ordinais anteriores.

**Cenário reproduzido:** substituir por `None` a primeira linha de evento da fixture com duas vendas cashback. O segundo swap passa a ter a identidade do primeiro:

```text
null_line gap= True ordinals= [0]
collides_with_first= True is_second_trade= True
```

Há também um cenário sustentado pelo runtime: o **Agave pode descartar uma mensagem grande, emitir `Log truncated` e conservar mensagens menores posteriores**. O contador de bytes não avança pela mensagem descartada. [Código do LogCollector](https://github.com/anza-xyz/agave/blob/master/svm-log-collector/src/lib.rs#L24).

Reproduzi esse algoritmo em memória, com um evento sintético grande seguido de um payload real:

```text
full_ordinal= 1 limited_ordinal= 0
truncated= 1 stack_inconsistencies= 0
```

Portanto, **pilha coerente não basta para preservar ordinal depois de truncamento**. Marcar `gap` também não desfaz a identidade errada já emitida.

**Correção pedida:** após `Log truncated` ou entrada não textual, interromper a atribuição dos eventos posteriores; preservar somente o prefixo confiável. Não adivinhar quantos eventos desapareceram. Acrescentar testes que comparem as identidades com a recuperação completa. O teste atual de lixo antes dos logs exige continuar emitindo e precisará ser revisto: [test_program_logs.py:426](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:426).

### 2. ALTA para a integração — O motor 1c ainda perde virtual quote e LP

Isso **não invalida a nova derivação da 1a**, mas impede declarar a integração com `Fill` pronta.

`Reserves` não representa a reserva virtual separada da pool, e `Fill` não preserva LP: [tape.py:54](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:54), [tape.py:78](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:78). As duas cotações usam diretamente `state.sol_lamports`: [pricing.py:93](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:93), [pricing.py:126](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:126).

**Cenários confirmados:**

- Na compra `5Smr…`, precificar a quantidade comprada usando somente a reserva real dá **32.468.690**, contra **38.387.041 lamports** usando a efetiva — o valor da cadeia.
- Ao construir `Fill` com o registro atual, `_pre_state` reconstrói quote anterior **76.775 lamports acima** do evento na compra e **364.066 acima** na venda: exatamente LP. A causa é [pricing.py:130](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:130).

## NICE-TO-HAVE

- **Transformar os 61 pares em regressão executável ou identificar a medição externa.** O teste cita 61, mas seu laço verifica dois pares; há ainda a cadeia das duas vendas cashback. [test_program_logs.py:194](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:194).
- Trocar `if first.pool == second.pool` por uma asserção explícita: confirmei que a fixture tem a mesma pool; hoje uma troca acidental poderia esvaziar a verificação. [test_program_logs.py:224](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_program_logs.py:224).
- No live, distinguir resposta RPC com `error` de `result: null`; hoje ambas podem virar “histórico podado”. Não afetou esta execução, que passou. [test_live_tx_version.py:72](C:/dev/project-hunter/packages/exchange-adapters/tests/live/test_live_tx_version.py:72).

## O QUE EU FARIA DIFERENTE

Para quem corrigir o **1c**, pediria este contrato e seus testes antes da implementação:

1. Preservar **quote real, virtual quote assinada e LP**, ou informações equivalentes sem perda. A reserva virtual pode ser negativa; isso é documentado pelo próprio programa. [Documentação Pump](https://github.com/pump-fun/pump-public-docs/blob/main/docs/NEGATIVE_VIRTUAL_QUOTE_RESERVES.md).
2. Precificar **compra e venda** com `Q_efetiva = Q_real + V`, mantendo a disponibilidade real do vault distinguível.
3. Desfazer o movimento exato:

   | Trade | Quote real anterior | Base anterior |
   |---|---|---|
   | Compra | `Q_pós − (sol_lamports + LP)` | `B_pós + token_atoms` |
   | Venda | `Q_pós + (sol_lamports − LP)` | `B_pós − token_atoms` |

4. Testar a ponte **evento real → SwapRecord → Fill → pré-estado/cotação**, comparando com reservas e movimentos da cadeia. Cobrir virtual positiva, zero e negativa; LP não zero; cashback; sem criador; `buy_exact_quote_in`. Preservar as regras temporais e provar ausência de regressão na curva.

## CONCORDO COM

**(a) Pilha estrita:** não encontrei padrão legítimo de **logs completos** de transação bem-sucedida que exija aceitar salto de profundidade ou retorno de outro programa. O runtime registra a profundidade corrente e o retorno do programa executado; a implementação atual corresponde a isso. [Agave](https://github.com/anza-xyz/agave/blob/master/program-runtime/src/invoke_context.rs#L579), [program_logs.py:158](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_logs.py:158).

Uma transação bem-sucedida pode ter **logs truncados** e, por isso, uma pilha observada incoerente. Nesse caso, a lacuna é real na observação; não é motivo para relaxar a pilha.

**(b) Reservas pós-trade:** concordo com as fórmulas dos casos perguntados. Compra acrescenta o fluxo efetivo recebido pelo vault; venda retira bruto menos LP. Cashback e creator fee não justificam retirar LP novamente. A inversão dos nomes em `buy_exact_quote_in` não afeta esses campos. [swap_record.py:165](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:165), [swap_record.py:208](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_record.py:208).

As dez comparações independentes com saldos finais e a cadeia cashback sustentam essa conclusão. **Não apresentaria isso como prova universal de qualquer layout futuro.**

**(d) `Fill`:** mantenho a concordância monetária da rodada 1: compra custa `sol + fee`; venda recebe `sol − fee`. A 1a agora também entrega corretamente as reservas reais posteriores e preserva os campos necessários. A incompatibilidade restante está no contrato e nas fórmulas do 1c.

## DISCORDO DE

**(c) “Ordinal por `Program data:` equivale sempre ao ordinal de `emit_cpi`.”** Isso não é garantia do protocolo: `Program data:` é saída genérica de dados; Anchor distingue emissão em logs de emissão por CPI. [Runtime](https://github.com/anza-xyz/agave/blob/master/program-runtime/src/stable_log.rs#L42), [Anchor](https://www.anchor-lang.com/docs/features/events).

**Não encontrei uma linha extra desse tipo nos dois programas nas 29 fixtures examinadas.** Logo, não abro outro MUST-FIX por uma possibilidade não observada. Mas a recuperação deve contar **todos os eventos do programa**, inclusive não-swap, antes de filtrar; comparar somente swaps não prova equivalência de ordinal. O helper atual filtra por discriminador: [t1a_chain.py:60](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/t1a_chain.py:60).

Também retiro a objeção anterior de que a compatibilidade legacy/v0 só tinha prova por mock: **agora executei e confirmei a comparação RPC real**.

## OBSIDIAN

Nenhuma página alterada. Deveriam ser atualizadas:

- **Revisão Astra — H-030 onda 1a** — registrar os consertos confirmados e o bloqueio residual de identidade após perda de linha.
- **wallets-engine** — registrar virtual quote nas duas cotações e LP na reconstrução do pré-estado.
- **KB-0183** — acrescentar a comparação integral logs/self-CPI e a verificação live de versões RPC.
- **Exchange Adapters** — documentar reservas posteriores e o limite da garantia de ordinal.