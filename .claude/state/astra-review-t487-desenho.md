**RESUMO**

Eu manteria a entrada única, mas **não congelaria esse veredito universal**. O desenho mistura protocolos com estimadores e testes diferentes. Parecer como `quant-engineer`: **NEEDS_CONTEXT** apenas quanto ao quinto estudo — foram identificados quatro: R65/R67/R68/R69.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão estática em modo OPINIÃO. Não validei numericamente a reprodução dos exports.

**MUST-FIX**

**a) Planalto deve ser diagnóstico obrigatório, não condição universal de CONFIRMA.** A regra vigente está na **emenda 1, item 5**, do R67: curva sem p ou IC decidindo o resultado ([preregistro.md:54](C:/dev/project-hunter/.claude/state/r67/preregistro.md:54)). “Virou teste padrão” na [KB-0149:64](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:64) não precisa significar portão inferencial.

Cenário: variável booleana ou efeito com descontinuidade real nunca satisfaz quatro limiares vizinhos, apesar de confirmar a previsão congelada. Se algum estudo exigir planalto, isso deve pertencer à política pré-registrada daquele estudo.

**b) `IC_sup < MRE` é defensável como “refuta vantagem ≥ MRE”, não “refuta qualquer efeito”.** É esse o escopo da E1.9c ([preregistro.md:195](C:/dev/project-hunter/.claude/state/r68/preregistro.md:195)). Efeito positivo pequeno pode ser corretamente refutado como **insuficiente**.

Mas pouca amostra **não garante IC largo**. Cenário: milhares de linhas provenientes de dois episódios, ou amostra pequena que não capturou ganhos raros; o IC estimado fica artificialmente estreito. Exija elegibilidade inferencial por **clusters/blocos independentes**, réplicas válidas e cobertura, além de `min_per_side`. IC inválido/NaN deve impedir veredito conclusivo. “Sem potência” também não é sinônimo matemático de `n` pequeno; prefiro motivo `amostra_insuficiente`.

**c) Sim, a guarda pode passar com antecipação ou viés.**

- **Relógio insuficiente:** no R69, `computed_at` representa início da transação, não disponibilidade após commit; atraso de 5 s é sensibilidade, não prova ([desenho.md:65](C:/dev/project-hunter/.claude/state/r69/desenho.md:65)).
- **Acesso contornável:** `Bars.take` verifica timestamps, mas os arrays continuam públicos e o chamador fornece `decision_idx` ([load68.py:54](C:/dev/project-hunter/.claude/state/r68/load68.py:54)). Cenário: fornecer também uma decisão futura. Vincule o corte ao contexto criado pelo executor e teste invariância do pipeline inteiro ao futuro.
- **Desfecho:** fita posterior à decisão é necessária; usar preços posteriores ao **fim do horizonte** muda o alvo. Separe horizonte, tempo dos eventos, disponibilidade e corte do export.
- **Censura:** remover perdas sem desfecho observado melhora artificialmente o resultado. Preserve população elegível, motivos e sensibilidades por lado; o R67 já exige isso ([preregistro.md:50](C:/dev/project-hunter/.claude/state/r67/preregistro.md:50)).
- **Ausência ≠ zero:** o bug SQL do R69 produzia percentil zero para sujeito sem valor, mesmo com timestamps válidos ([stats69.py:45](C:/dev/project-hunter/.claude/state/r69/stats69.py:45)). Porte também os testes de ausência e paridade SQL↔Python.

**d) Não aceito ±0,05 no p como prova principal.** Aceitaria 0,049 e 0,099 como equivalentes, embora mudem a decisão. ±0,01 no IC também depende da unidade.

Prefiro **mesmas reamostragens/permutacões**, comparando estatística por réplica e quantis, além dos resultados determinísticos. Seed sozinha não basta: R67 usa RNG global consumido sequencialmente ([stats67.py:4](C:/dev/project-hunter/.claude/state/r67/stats67.py:4)). Congele ordem, gerador, algoritmo de quantil e tratamento de réplicas inválidas. Com RNG diferente, use tolerância calibrada pelo erro Monte Carlo, específica por métrica.

**e) Faltam contratos essenciais para reproduzir os estudos:**

- **Estimando, comparador, unidade, custos e numerário.** R68 testa retorno líquido absoluto e diferença contra sempre-long; `selecionados − resto` não substitui ambos ([partb.py:112](C:/dev/project-hunter/.claude/state/r68/partb.py:112)). Cenário: selecionados perdem menos que o resto e recebem CONFIRMA apesar de prejuízo.
- **Plano de inferência:** método primário, construção/duração dos blocos, ponderação e família de testes com correção. R68 substituiu permutação por bootstrap temporal centrado e exige Holm ([preregistro.md:140](C:/dev/project-hunter/.claude/state/r68/preregistro.md:140), [185](C:/dev/project-hunter/.claude/state/r68/preregistro.md:185)). Permutação universal pode destruir dependência e confirmar ruído.
- **População e validação:** deduplicação, exclusão dos sujeitos da descoberta, censura, sensibilidades e walk-forward com seleção só no treino. Uma fronteira `treino_ate` não representa as dobras do R68 ([preregistro.md:82](C:/dev/project-hunter/.claude/state/r68/preregistro.md:82)).
- **Política de limiar e finalidade:** fixo, quantil amostral ou histórico; exploratório versus confirmatório. R69 adotou mediana amostral antes de consultar desfechos ([desenho.md:88](C:/dev/project-hunter/.claude/state/r69/desenho.md:88)). Texto em `Prediction` não comprova pré-registro; registre versão, momento e proveniência.

**NICE-TO-HAVE**

Hashes dos exports/protocolo, concentração por episódio, contagem de réplicas descartadas e relatório de exclusões.

**O QUE EU FARIA DIFERENTE**

Separaria `HypothesisSpec`, `InferencePlan` e `DecisionPolicy`, mantendo `run_hypothesis(spec)`. Waiver permite análise com limitação explícita; não certifica observabilidade.

**CONCORDO COM**

Offline, previsão obrigatória, orientação explícita de D, três rótulos com motivos e teste adversário de antecipação.

**OBSIDIAN**

- **KB-0149 — O que a mesa real ensinou:** esclarecer que planalto é diagnóstico padrão, sem portão universal.
- **Revisões Astra — T4.87 (nova):** registrar estimandos, políticas inferenciais, limites das guardas e critérios de fidelidade.