## RESUMO

**Não encontrei bypass que permita desviar valor para terceiros.** Encontrei dois problemas de severidade **MEDIUM** na medição e na confirmação. Corrigiria ambos antes do `--apply`. Não há achado CRITICAL/HIGH demonstrado.

Revisão da árvore de trabalho como `security-reviewer`; nenhuma transação real executada.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisei os quatro scripts, os quatro arquivos de testes e as dependências de serialização, RPC, auditoria e confirmação.

## TESTES

Executei, com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest infra/scripts/tests/test_meme_close_atas.py infra/scripts/tests/test_meme_close_atas_plan.py infra/scripts/tests/test_meme_close_atas_send.py infra/scripts/tests/test_meme_close_atas_verify.py -q

68 passed in 1.15s
```

Sondas adicionais executadas em memória, com dados sintéticos:

```text
external_credit: reported= 106102840 actual_close_net= 6102840
processed_error: status= failed last_event= close_atas_failed
non_ata: is_ata= False verdict= close
commit_failure: signatures= 1 broadcasts= 0
```

Isso verifica o comportamento dos scripts; não substitui execução contra o runtime Solana.

## MUST-FIX

- [infra/scripts/meme_close_atas_send.py:241](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:241) — **MEDIUM** — `lamports_recovered` atribui ao fechamento todo movimento da carteira entre duas consultas — **cenário:** o lote recupera 6.102.840 lamports líquidos e chega um depósito externo de 100.000.000; a auditoria registra 106.102.840 como recuperados. Uma compra concorrente provoca o erro inverso. Usar `getTransaction(signature)` e `meta.postBalances[wallet_index] - meta.preBalances[wallet_index]`; se os metadados estiverem indisponíveis, manter a recuperação pendente.

- [infra/scripts/meme_close_atas_send.py:276](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:276), [treasury_rules.py:186](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury_rules.py:186) — **MEDIUM** — um erro em `processed` vira falha definitiva antes de alcançar `confirmed` — **cenário:** a transação falha num fork que depois é descartado; o script já gravou `close_atas_failed`, embora a assinatura ainda possa executar em outro fork enquanto válida. Exigir o nível de confirmação escolhido antes de concluir tanto sucesso quanto falha; até lá, continuar `submitted`.

## NICE-TO-HAVE

- [infra/scripts/meme_close_atas.py:184](C:/dev/project-hunter/infra/scripts/meme_close_atas.py:184) — **MEDIUM** — o kill switch é consultado apenas uma vez por execução — **cenário:** com vários lotes, o operador aciona `EMERGENCY` durante a confirmação do primeiro; o segundo ainda será assinado e enviado. O requisito literal “antes de carregar o signer” está cumprido; eu acrescentaria releitura antes de cada assinatura.

- [infra/scripts/meme_close_atas_plan.py:154](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:154) — **LOW**, condicionado ao escopo “somente ATAs” — contas não associadas também recebem `close` — **cenário:** uma conta token vazia, de endereço específico usado por outra integração, é fechada junto das ATAs e essa integração passa a falhar. Se o escopo for recuperar apenas ATAs, derivar o endereço com `(wallet, token_program, mint)` e emitir `skipped:not_ata`. Fechar uma conta não-ATA própria não constitui, por si só, desvio financeiro.

## O QUE EU FARIA DIFERENTE

**Para eventual extensão Token-2022**, manteria a recusa atual até decisão explícita do Everton. [meme_close_atas_plan.py:155](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:155) e [meme_close_atas_verify.py:99](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:99) hoje bloqueiam corretamente essa classe.

Exigiria:

1. **Decodificação completa da conta e das extensões.** Hoje [meme_close_atas_plan.py:117](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:117) extrai apenas campos básicos. Autorizar somente o conjunto explicitamente revisado `{ImmutableOwner}`; extensão desconhecida, bytes inválidos ou informação incompleta recusam. `amount=0` sozinho não demonstra ausência de saldo confidencial ou taxas retidas.
2. **Identidade vinculada ao plano:** endereço, mint, programa proprietário, autoridade e extensões; conta do tipo token account, nunca mint. Se limitado às 34 ATAs, exigir derivação ATA com **Token-2022** nas seeds.
3. **Mesmas restrições da mensagem:** exatamente `CloseAccount`, três contas, origem autorizada, destino e autoridade iguais à carteira, uma assinatura e teto de taxa. O programa permitido deve corresponder ao programa daquela origem.
4. **Prova no runtime**, além dos fakes: fechamento de conta com `ImmutableOwner`, rejeição das extensões fora da lista e comparação dos saldos e da taxa por transação. Após aprovação, primeiro fechamento real de uma conta, com reconciliação antes dos demais.

`ImmutableOwner` não impede esse fechamento. No processador Token-2022, `CloseAccount` valida autoridade, verifica condições de saldo/extensões e transfere os lamports ao destino; não executa um transfer hook. Também pode fechar **mints**, razão para validar o tipo da origem. [Implementação oficial Token-2022](https://github.com/solana-program/token-2022/blob/main/program/src/processor.rs#L1204).

Os números informados correspondem a **51.470.560 lamports = 0,051470560 SOL brutos**, antes das taxas. Não repeti a leitura da mainnet.

## CONCORDO COM

**(1) Verificador.** [meme_close_atas_verify.py:74](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:74) exige uma assinatura da carteira; [linha 93](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:93) restringe os programas; [linha 128](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:128) exige o opcode exato e valida origem, destino e autoridade. Não encontrei cenário executável de transferência externa permitido por essas verificações.

**(2) Simulação.** **Sim, desconta a taxa no post-state.** `sigVerify=false` apenas pula a verificação criptográfica; a execução simulada passa pela cobrança do pagador. [RPC Agave](https://github.com/anza-xyz/agave/blob/master/rpc/src/rpc.rs#L3872), [cobrança no account loader](https://github.com/anza-xyz/agave/blob/master/svm/src/account_loader.rs#L336).

A desigualdade de [meme_close_atas_send.py:195](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:195) está aritmeticamente correta **se o saldo anterior corresponde ao estado inicial simulado**. Hoje são consultas separadas: um débito concorrente pode causar recusa indevida; um crédito pode mascarar recuperação abaixo do esperado. Preferiria saldos inicial/final da própria simulação, quando disponíveis no RPC.

Não encontrei como **essa transação verificada** perder mais que a taxa. Se uma conta receber tokens entre simulação e execução, o fechamento clássico não nativo falha e o lote reverte; a taxa pode permanecer cobrada. Isso não garante que o saldo global da carteira não caia por outra transação. [Atomicidade e taxas Solana](https://solana.com/docs/core/transactions).

**(3) Assinatura → commit → envio.** A ordem está correta em [meme_close_atas_send.py:199](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:199), com commit aguardado na [linha 130](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:130). Reproduzi falha de commit: **uma assinatura, zero broadcasts**. Uma queda depois do commit e antes do envio deixa uma intenção durável sem broadcast; portanto `submitted` significa resultado ainda desconhecido, não prova de envio. Timeout de envio preserva a assinatura para reconciliação.

**(4) WSOL e autoridade.** O caso `amount=0` e `lamports==rentExemptReserve` é seguro: todos os lamports retornam à carteira. [meme_close_atas_plan.py:165](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:165) aceita esse caso; [linha 161](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:161) já aceita `closeAuthority == wallet`. Não falta esse veredito. O comportamento corresponde ao [processador SPL Token clássico](https://github.com/solana-program/token/blob/main/program/src/processor.rs#L615).

## OBSIDIAN

- **Revisoes-Astra — T4.77** — registrar os dois achados reproduzidos, os 68 testes e as condições para Token-2022.
- **KB-0146 — Trailing apertado e rent de ATA** — registrar que as 34 contas informadas são Token-2022 e permanecem excluídas da implementação atual.
- **Diário — 2026-09-19** — separar recuperação potencial, autorização e recuperação efetivamente confirmada por transação.