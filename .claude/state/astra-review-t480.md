## RESUMO

**Código: APPROVE_WITH_NITS. Há uma correção obrigatória na orientação operacional:** aplicar o parâmetro aos conjuntos `operator` não constitui uma medição em sombra separada.

**1) COLOCAÇÃO — manteria por último e em módulo próprio.**  
`evaluate_entry` acumula as recusas; não interrompe na primeira. A trilha descarta casos com duas ou mais antes de acessar `refusals[0]`. Portanto, a ordem não muda aprovação, seleção da trilha ou seu motivo. Acrescentar o critério pode transformar uma recusa única em dupla e retirar aquela linha da trilha — independentemente da posição. [rules.py:311](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules.py:311), [gate_refusal_trail.py:87](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/gate_refusal_trail.py:87).

Não comprimiria `rules_criteria.py` para encaixar mais um critério: o módulo separado é pequeno e coeso. A proximidade conceitual com fluxo não exige compartilhar arquivo.

**2) DESCONHECIDO — manteria `buys_1m_unknown`, com diagnóstico separado.**  
O nome estável facilita contagem, mas **perde a causa específica no registro da recusa**. O bloco `flow` contém `tape_reason`, porém propostas recusadas não chegam à construção desse bloco. Portanto, ele não resolve sozinho o diagnóstico das recusas. Eu preservaria o código fixo e, quando necessário, registraria `tape_reason` como detalhe. [rules_buys.py:44](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_buys.py:44), [proposals.py:267](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:267), [proposals_reasons.py:109](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_reasons.py:109).

**3) LOOK-AHEAD — não identifiquei antecipação introduzida pela T4.80.**  
A dobra de trades exige `received_at <= end_time` e `start < block_time <= end_time`; a pista de evento reutiliza essa dobra com `as_of`. [features_tape.py:188](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/features_tape.py:188), [event_state.py:247](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_state.py:247).

**Ressalva importante:** minuto e 15 s priorizam `activity_1m`, cuja janela pode terminar antes do instante julgado. Logo, “contagem disponível na decisão” é correto; “os 60 segundos exatos terminados na decisão” não é universalmente correto. Uma janela antiga com 20 compras pode passar enquanto os 60 segundos imediatamente anteriores já contêm 30. Isso é defasagem, não antecipação. [fold.py:81](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/fold.py:81), [fast_lane.py:177](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/fast_lane.py:177), [features_tape.py:120](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/features_tape.py:120).

**4) TIPO — concordo com inteiro JSON puro.**  
Recusar `"25"`, `25.5` e `true` evita coerções e a armadilha descrita de `_check_decimal_convention`. Validar o tipo na entrada JSON e somente o domínio não negativo no objeto tipado é razoável. [lab_params.py:86](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:86), [meme_rule_set_validate.py:44](/C:/dev/project-hunter/infra/scripts/meme_rule_set_validate.py:44), [rules_validation.py:100](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_validation.py:100).

**5) LIGAR/DESLIGAR — a mecânica está correta, com estas ressalvas:**

- O comando precisa de `--reason` com pelo menos dez caracteres; sem isso é recusado. [meme_rule_set.py:163](/C:/dev/project-hunter/infra/scripts/meme_rule_set.py:163).
- `null` desliga semanticamente; não remove a chave do JSON. Ausente e `null` chegam como `None`. [meme_rule_set_params.py:51](/C:/dev/project-hunter/infra/scripts/meme_rule_set_params.py:51), [lab_gate_params.py:79](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_gate_params.py:79).
- Os documentos alterados são validados antes da escrita; alterações e histórico usam a transação do comando. [meme_rule_set_params.py:154](/C:/dev/project-hunter/infra/scripts/meme_rule_set_params.py:154), [meme_rule_set.py:277](/C:/dev/project-hunter/infra/scripts/meme_rule_set.py:277).
- Os contadores citados agregam por `spec.name`: `operator/5` e `/6` compartilham `operator`. Não servem, sozinhos, para comparar versões. [lab_fast.py:124](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:124).

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum comando de aplicação executado.

## TESTES

**Não executados**, para preservar a revisão estritamente sem escrita. Inspecionei os três arquivos de testes informados; não afirmo que passam.

## MUST-FIX

**HIGH — corrigir a instrução que apresenta alteração de `operator/5` e `/6` como “sombra”.**  
Cenário: alguém copia o exemplo acreditando apenas medir recusas; o parâmetro passa a bloquear propostas desses conjuntos. O caminho faz `continue` na recusa, sem braço paralelo de observação. Além disso, enquanto ausente, o critério não gera contadores contrafactuais. [docs/RISK_ENGINE_MEME.md:1123](/C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:1123), [proposals.py:267](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:267), [rules_buys.py:44](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_buys.py:44).

A própria memória já recomenda **não ligar** o filtro após R67. Atualizaria a orientação operacional antes de publicar esse exemplo. [KB-0147:111](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md:111).

Não encontrei must-fix no comparador novo.

## NICE-TO-HAVE

- Testar o ciclo `25 → null → 25` pelo CLI, com dois conjuntos.
- Testar trade ocorrido antes, mas recebido depois de `as_of`; o teste novo de antecipação usa trade ocorrido depois. [test_gate_buys_1m.py:184](/C:/dev/project-hunter/services/meme-worker/tests/test_gate_buys_1m.py:184).
- Documentar a defasagem de `activity_1m` e preservar sua procedência no diagnóstico.

## O QUE EU FARIA DIFERENTE

Manteria a implementação pequena. Corrigiria a descrição temporal e separaria explicitamente **ativar um filtro** de **medir uma hipótese em sombra**.

## CONCORDO COM

Ausência por padrão, teto inclusivo, falha fechada, inteiro estrito na fronteira JSON e extração de `as_parameters` sem alterar os parâmetros antigos.

## OBSIDIAN

- **KB-0147 — custo e compras por minuto:** corrigir o exemplo de sombra e alinhar a orientação ao resultado R67.
- **Meme — o que uma “estratégia” é aqui:** registrar a semântica opcional e as diferenças temporais entre as pistas.
- **Revisões-Astra — T4.80:** registrar este parecer, a ressalva operacional e os testes ainda não executados.