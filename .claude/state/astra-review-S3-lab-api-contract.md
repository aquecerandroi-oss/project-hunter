**RESUMO**

**REQUEST_CHANGES.** Aceito a limitação de persistência e a regex como solução provisória. A população financeira e os motivos de PF estão corretos, mas o contrato ainda mistura cobertura de avaliações com cobertura de outcomes e omite regras temporais acordadas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executados: revisão estática do contrato, das decisões e dos caminhos de persistência. Não consultei dados operacionais.

**MUST-FIX**

1. **HIGH — Contagens de sinais não representam avaliações; censuras não representam avaliações indisponíveis.**  
   O contrato redefine `decisions` e apresenta `coverage.unavailable.gap` como observável ([contrato:14](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:14)). Porém, até `TRIGGERED` pode **não emitir sinal** quando o episódio está desarmado ou já acompanha uma entrada ([episodes.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:62)).

   **Cenário:** cem avaliações falham por gap antes de qualquer sinal; não existe outcome para censurar. A resposta informa `gap: 0`, apesar da indisponibilidade. Analogamente, dez avaliações `TRIGGERED` podem produzir apenas um sinal.

   **Correção:** manter `signals_emitted`; contagens por `Evaluation.state` ficam nulas com motivo, **inclusive gap**. Contar gaps de acompanhamento exclusivamente em `censored`. `markets_evaluated` também precisa de fonte e definição: mercados com sinais devem chamar-se `markets_with_signals`; não comprovam o universo avaliado ([contrato:122](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:122)). Não encontrei fonte durável que reconstrua as avaliações completas por versão/coorte/janela.

2. **HIGH — `as_of` e horizonte maturado não estão aplicados à população financeira.**  
   O contrato limita `decision_at`, mas define avaliáveis apenas como `terminal AND r_multiple IS NOT NULL` ([contrato:68](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:68), [contrato:137](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:137)). A decisão conjunta exige também horizonte maturado para evitar seleção de saídas rápidas ([diálogo:308](C:/dev/project-hunter/.claude/state/dialogue-SHADOW.md:308)).

   **Cenários:** consultar `as_of=12:00` amanhã inclui uma saída das 14:00; ou uma coorte recente mostra apenas stops rápidos enquanto entradas que podem expirar após quatro horas continuam abertas.

   **Correção:** explicitar corte de saída `exit_ts <= as_of` e maturação pelo horizonte congelado, independentemente de ter encerrado cedo. A fonte existe: `entry_plan.entry_bar_open` e `meta.horizon_s` ([record.py:164](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:164)). Separar contagens operacionais da população maturada. Definir também se estados históricos são reconstruídos ou indisponíveis: filtrar decisões não transforma o estado atual em fotografia histórica.

3. **MEDIUM — Faltam denominador explícito do PF e metadados completos de excursão.**  
   PF contém somente `value/reason` ([contrato:106](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:106)), embora o aceite exija denominador explícito ([plano:64](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:64)). O exemplo de excursões omite unidade, método, parciais e referência de normalização ([contrato:185](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:185)).

   **Cenário:** o consumidor não distingue PF baseado em perda mínima de PF sustentado por perdas substanciais; interpreta `mae=0.8` como R, embora a implementação declare unidade `price` ([excursions.py:49](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:49)).

   **Correção:** expor soma positiva, módulo da soma negativa e tamanho da amostra nos dois blocos financeiros; preservar `meta.excursions` completo, incluindo parciais, unidade, método, janelas, risco inicial e referência ([excursions.py:139](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:139)).

**NICE-TO-HAVE**

- Fixar `distinct_days` como dias UTC de decisão da população correspondente; declarar separadamente cobertura e maturidade.
- Especificar `blocked:*` no agrupamento de censuras, preservando o prefixo `gap:` também nos motivos conhecidos ([contrato:146](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:146)).
- Corrigir “funding inaplicável” para “funding não apurável”. Ausência comprovada de liquidação pode produzir funding zero e R válido ([settle.py:11](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:11)).
- Definir soma sem amostra, limites/direção do cursor e resolver a contradição entre envelope “omitido” e presente como `null` ([contrato:157](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:157), [contrato:195](C:/dev/project-hunter/.claude/state/contract-S3-lab.md:195)).

**O QUE EU FARIA DIFERENTE**

Preservaria os nomes pedidos no brief com nulidade explícita quando indisponíveis, sem redefinir `decisions` como sinais. Registraria essa entrega como cobertura parcial do requisito, acompanhada da pendência de persistência.

Para `superseded_by`, usaria a regex provisoriamente, identificando a origem como inferida do changelog. Não exigiria migração nesta tarefa.

**CONCORDO COM**

- **(a) Persistência:** o diagnóstico está correto. As avaliações alimentam métricas, e a emissão passa por outra decisão do episódio ([decide.py:122](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:122), [decide.py:155](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:155)). Aceito nulos; rejeito substituir avaliações por contagens de outcomes.
- **(a) Sucessão:** a regex corresponde ao prefixo escrito pelo script ([activate_strategy_version.py:234](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:234)). `system_events` também recebe texto, sem IDs estruturados da relação ([activate_strategy_version.py:79](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:79), [activate_strategy_version.py:265](C:/dev/project-hunter/infra/scripts/activate_strategy_version.py:265)). Não é fonte melhor. O changelog permanece mutável, portanto a relação não deve ser apresentada como garantida por FK ([DATABASE.md:786](C:/dev/project-hunter/docs/DATABASE.md:786)).
- **(b) População:** `terminal AND r_multiple IS NOT NULL` é a base correta, incluindo expired/invalidated; faltam os cortes temporais do item 2. `r_ex_funding` deve selecionar seus próprios terminais com valor conhecido, sem exigir R líquido disponível.
- **(c) PF:** `no_sample` para população vazia; `no_losses` para população não vazia sem soma negativa. Isso cobre também amostra composta só por zeros. Só perdas produz PF zero, não nulo. Avaliar essas condições antes de arredondar.
- **(d) Brief:** os principais campos estão contemplados; permanecem incompletos avaliações por estado, cobertura real e excursões completas. O denominador explícito e a maturação são exigências adicionais do plano incorporado pelo brief.

**OBSIDIAN**

- **Diálogo Claude ⇄ Astra — SHADOW:** registrar os ajustes necessários em cobertura, maturação e `as_of`.
- **Strategy Performance:** documentar populações, denominadores e distinção entre R líquido e R sem funding.
- **Strategies:** registrar sucessão inferida do changelog e sua limitação.
- **Revisões da Astra — Index:** vincular esta revisão quando o orquestrador a registrar.