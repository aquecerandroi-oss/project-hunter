## RESUMO

**REQUEST_CHANGES.** Como `risk-engine-guardian`, encontrei um caminho que ainda perde stop e uma lacuna na idempotência após restart. O guard de replay exige um contrato de reconstrução mais explícito. A assimetria da banda é coerente, mas sua evidência publicada está incompleta.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisei os diffs solicitados e li integralmente `idempotency.py` e `test_pricing.py`.

## TESTES

Executei com bytecode, cache do pytest e sincronização do ambiente desabilitados:

```text
uv run pytest packages/core/tests/unit/execution -q
119 passed in 1.77s
```

Também executei sondas sintéticas em memória via `uv run python -`, sem criar arquivos. Resultados relevantes:

```text
A1 triggered target 101 trade_not_yet_received
A2 unavailable already_reported 101
B ValueError ... terminal (superseded)
C ReplayMismatch original 0.8 reconstructed 0.4
C_json_roundtrip True
C_missing_identity returned_old_fill 3 requested 2
D rejected price_band filled 0 base_delta 0 quote_delta 0
  reported_reference 125 last_spot_trade:100
```

Não executei integração com Postgres, lint ou typecheck nesta revisão.

## MUST-FIX

**1. ALTA — (a) O watermark pode ultrapassar um stop ainda indecidido.**

Em [triggers.py:200](/C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:200), o watermark avança até o cruzamento encontrado mesmo quando existe defeito anterior. Depois, [triggers.py:270](/C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:270) descarta aquele print anterior.

Cenário reproduzido:

- Watermark inicial `99`, stop `95`, alvo `110`.
- Print `100@90`, com `received_at=now+2s`; print `101@110`, válido.
- Primeiro ciclo: `triggered/target`, watermark `101`, resto indecidido.
- Dois segundos depois: o print `100@90` ficou utilizável, mas é descartado por estar abaixo de `101`. Retorna `already_reported` pelo alvo; **o stop nunca é reportado**.

Publicar `undecided_reason` não preserva a possibilidade de recuperação. É necessário distinguir o avanço contínuo da leitura dos cruzamentos já publicados, ou conservar explicitamente os prints pendentes sem duplicar o alvo.

**Falta testar:** defeito **antes** do cruzamento, recuperação no ciclo seguinte e ausência de repetição do alvo. Os testes adicionados usam o defeito depois do stop.

**2. ALTA — (b) `fills.execution_key` não reconstrói tentativas aplicadas sem fill.**

[Idempotency.py:113](/C:/dev/project-hunter/packages/core/hunter_core/execution/idempotency.py:113) recupera somente os IDs fornecidos pelas chaves dos fills. Entretanto, [intents.py:288](/C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:288) registra também tentativas de preenchimento zero como aplicadas.

Cenário reproduzido: tentativa A sem livro → relatório `pending_degraded`, zero fill → aplicação → intenção substituída → restart → reconstrução a partir dos fills → reentrega de A. Como A desapareceu do conjunto, [intents.py:279](/C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:279) levanta `ValueError` pela intenção terminal. Antes do restart, a mesma reentrega seria no-op.

Não fabrica quantidade, mas quebra a promessa de reentrega inofensiva e pode interromper o consumidor. O próprio helper de persistência só grava fill quando há quantidade positiva: [test_execution_intents.py:303](/C:/dev/project-hunter/packages/core/tests/integration/test_execution_intents.py:303).

**Correção:** autoridade durável de *tentativas aplicadas*, incluindo zero fill, escrita atomicamente com o estado. Apenas acrescentar uma coluna “na transação do fill” não cobre esse caso.

**Falta testar:** zero fill → substituição/void → restart → reentrega; e zero fill antigo reaplicado depois de uma tentativa posterior ter removido a degradação.

**3. MÉDIA — (c) A garantia de divergência desaparece se a identidade não for persistida.**

[Idempotency.py:96](/C:/dev/project-hunter/packages/core/hunter_core/execution/idempotency.py:96) aceita qualquer quantidade quando `submitted_qty=None`, e qualquer decisão quando o fingerprint está vazio. A orientação de que esses campos não precisam ser gravados em [notes-T3.4.md:247](/C:/dev/project-hunter/.claude/state/notes-T3.4.md:247) precisa distinguir unicidade de fill de detecção de divergência.

Reproduzi: relatório original de `3`, reconstruído sem os dois campos; pedido divergente de `2` com outra decisão recebe o fill antigo de `3`, sem exceção. A chave única impede outro INSERT, mas não resolve essa resposta incorreta.

**Falta testar:** round-trip persistido do relatório seguido de replay igual e divergente. Para registros novos, identidade ausente não deveria significar “igual”.

## NICE-TO-HAVE

- **(c) Reentrega legítima reconstruída pelo saldo atual:** reproduzi `0,8 → fill 0,4 → for_intent(... mesmo attempt_id ...) → qty 0,4 → ReplayMismatch`. O recálculo ocorre em [intents.py:188](/C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:188). O guard está certo ao detectar outra quantidade; o consumidor deve recuperar a tentativa original **antes** de recalcular saldo. Testar esse fluxo completo, inclusive intenção já terminal. O hash da decisão testada sobreviveu ao round-trip JSON.
- **(d) Publicar a referência efetivamente usada pela banda:** [pricing.py:242](/C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:242) prefere o último trade, enquanto a banda usa `avg_price`. Reproduzi compra a `125`, média `100`, teto `120`: rejeição correta segundo a política, mas relatório informa referência `125`. Registrar média, limites e VWAP recusado permitiria explicar a decisão.
- **(d) Testar limites exatos, média ausente/inválida e movimento real rápido.** [Pricing.py:203](/C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:203) trata média ausente como ausência de breach; não distingue banda indisponível de banda aprovada.

## O QUE EU FARIA DIFERENTE

Separaria três contratos: **print processado**, **gatilho publicado** e **tentativa aplicada**. Um watermark único e um conjunto derivado apenas de fills não representam todos esses fatos, como mostram os cenários acima.

Para T3.5, exigiria reconstrução da tentativa imutável, consulta idempotente antes de recalcular quantidade e persistência conjunta de efeitos e identidade.

## CONCORDO COM

- **(b)** Para fills positivos persistidos atomicamente com a intenção, a deduplicação antes da checagem terminal resolve a repetição parcial: [intents.py:277](/C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:277). A lacuna é a cobertura de tentativas sem fill.
- **(d)** A banda não bloqueia a proteção: [paper.py:218](/C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:218). A entrada recusada retorna zero fill e zero deltas; portanto, **não encontrei criação de posição desprotegida por esse ramo**, em [paper.py:122](/C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:122). Uma alta real além da banda pode ser recusada pela política; isso não prova corrupção do book.
- Centralizar a validade em `usable_trade` e conferir níveis construídos sem validação são correções adequadas: [pricing.py:179](/C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:179), [book_walk.py:104](/C:/dev/project-hunter/packages/core/hunter_core/execution/book_walk.py:104).

## OBSIDIAN

- **Execution Engine** — registrar watermark com pendências, identidade imutável e recuperação de tentativas sem fill.
- **Paper Trading** — documentar assimetria da banda e evidência necessária para explicar recusas.
- **Revisoes-Astra/T3.4b** — registrar os cenários reproduzidos, os 119 testes aprovados e as lacunas ainda abertas.