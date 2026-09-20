## RESUMO

**Encontrei um MUST-FIX MEDIUM antes da prova de uma conta:** a ausência de extensões no `jsonParsed` está sendo tratada como prova de ausência. O item 3 da revisão anterior foi atendido; o item 1 ainda está incompleto.

Não demonstrei bypass para outro opcode ou reembolso a terceiros, nem achado CRITICAL/HIGH.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisei o diff dos quatro scripts, o novo teste Token-2022 e os itens 1–4 da revisão anterior.

## TESTES

Executei com sincronização, cache e bytecode desabilitados:

```text
uv run pytest infra/scripts/tests/test_meme_close_atas.py infra/scripts/tests/test_meme_close_atas_plan.py infra/scripts/tests/test_meme_close_atas_send.py infra/scripts/tests/test_meme_close_atas_verify.py infra/scripts/tests/test_meme_close_atas_token_2022.py -q

124 passed in 1.50s
```

Sondas adicionais em memória, com fixtures sintéticas:

```text
missing: extensions=() classify=close verifies=True
empty: extensions=() classify=close verifies=True
malformed_dict: extensions=() classify=close verifies=True
```

Não executei transações nem prova contra o runtime Solana.

## MUST-FIX

- [infra/scripts/meme_close_atas_plan.py:161](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:161) — **MEDIUM** — informação ausente ou incompleta sobre extensões autoriza o fechamento — **cenário concreto:** uma ATA Token-2022 vazia contém uma extensão desconhecida pela versão do decoder do RPC. A enumeração falha, o decoder devolve extensões vazias/omitidas e o script interpreta `extensions=()`, atribui `close` e permite assinar. Se a extensão não impedir `CloseAccount`, uma conta fora do conjunto autorizado será fechada, inclusive no modo-prova.

Esse caminho não exige RPC malicioso: o [parser oficial do Agave](https://github.com/anza-xyz/agave/blob/master/account-decoder/src/parse_token.rs) usa `get_extension_types().unwrap_or_default()`. A [enumeração TLV](https://github.com/solana-program/token-2022/blob/main/interface/src/extension/mod.rs) pode falhar ao converter um tipo desconhecido. Portanto, não é garantido que toda extensão desconhecida apareça como `unparseableExtension`.

**Correção:** validar os bytes brutos da conta e enumerar integralmente o TLV; recusar tipo desconhecido, estrutura inválida ou decodificação incompleta. A lista vazia só deve ser aceita quando comprovada pelos bytes. Exigir apenas a presença da chave `extensions` não resolve respostas com `[]`.

O impacto demonstrado é **violação da seleção autorizada**, não roubo nem perda demonstrada de saldo confidencial.

## NICE-TO-HAVE

Nenhum achado adicional com cenário que justifique elevar a prioridade nesta re-revisão.

## O QUE EU FARIA DIFERENTE

Fecharia a lacuna acima com testes de bytes reais/sintéticos do formato Token-2022, incluindo extensão desconhecida e TLV truncado. O teste atual aceita explicitamente a representação sem extensões em [test_meme_close_atas_token_2022.py:122](C:/dev/project-hunter/infra/scripts/tests/test_meme_close_atas_token_2022.py:122), mas isso não demonstra que o RPC inspecionou todos os bytes.

Depois, faria a prova de uma conta e reconciliaria a assinatura antes dos lotes. `--i-know-2022` é uma declaração do operador: não consulta histórico de prova confirmada, conforme [_proof_run](C:/dev/project-hunter/infra/scripts/meme_close_atas.py:172).

## CONCORDO COM

**1. Instrução diferente, mint/multisig ou reembolso externo?**

- **Outro opcode ou reembolso externo:** não encontrei caminho. A validação exige `data == b"\x09"`, três contas, destino igual à carteira e autoridade igual à carteira assinante em [verify.py:147](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:147). A assinatura única está em [verify.py:82](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:82); o teto de prioridade, em [verify.py:118](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:118).
- **Mint/multisig:** o verificador isolado **não conhece o tipo da origem**; se receber um endereço desses no mapa autorizado, pode aceitar a mensagem. No fluxo revisado, o plano recusa `kind != "account"` e exige ATA derivada com o programa correto em [plan.py:186](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:186) e [plan.py:203](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:203). Não encontrei caminho normal que contorne essas guardas. No [processador oficial](https://github.com/solana-program/token-2022/blob/main/program/src/processor.rs), mint com autoridade de fechamento e supply zero pode ser fechado; multisig não é uma origem suportada.

**2. O casamento programa×plano fecha o item 3?**

**Sim.** [verify.py:160](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:160) compara o programa da instrução com o registrado para aquela origem. O mapa vem do lote em [send.py:198](C:/dev/project-hunter/infra/scripts/meme_close_atas_send.py:198). Trocar clássico por Token-2022, ou o inverso, é recusado; misturar ambos também, em [verify.py:114](C:/dev/project-hunter/infra/scripts/meme_close_atas_verify.py:114).

**3. Extensões que o runtime aceita, mas devemos recusar?**

**Sim:** por exemplo, `MemoTransfer`, `TransferHookAccount`, `CpiGuard` neste fechamento direto para o próprio dono, e `TransferFeeAmount` com retenção zerada. O runtime não limita fechamento a `ImmutableOwner`; manter a lista restrita é coerente com o escopo aprovado. `CloseAccount` não executa transfer hook. [Processador oficial Token-2022](https://github.com/solana-program/token-2022/blob/main/program/src/processor.rs).

Extensões do **mint**, como `PermanentDelegate`, também não aparecem na listagem das contas token; isso não significa erro de parsing da conta. A omissão relevante para o bloqueio é a falha silenciosa na enumeração das extensões **da própria origem**.

**4. Prova de uma conta?**

O plano limita a seleção a **no máximo uma Token-2022**, adiando as clássicas, em [plan.py:230](C:/dev/project-hunter/infra/scripts/meme_close_atas_plan.py:230). Corrigiria o MUST-FIX antes do `--apply`. Os testes verdes não substituem essa correção nem a prova no runtime.

## OBSIDIAN

- **Revisoes-Astra — T4.77b** — registrar o item 3 atendido, o bloqueio por extensões incompletas e os 124 testes.
- **KB-0146 — Trailing apertado e rent de ATA** — distinguir rent potencialmente recuperável de contas cuja elegibilidade foi comprovada por bytes.
- **Diário — 2026-09-19** — registrar a re-revisão e que nenhuma prova real foi executada nesta sessão.