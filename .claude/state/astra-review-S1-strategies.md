**RESUMO**

Concordo com a estrutura geral, com `evaluate() -> Decision | None`, com as duas invalidações propostas e com confidence constante explicitamente não calibrada. Antes de congelar a v1, eu corrigiria os contratos de canonicalização, ATR, contexto e resultado da avaliação.

Atuei como `quant-engineer`. Esta é uma opinião sobre o desenho, não aprovação da implementação.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

A premissa sobre `canonical.py` mudou durante a leitura: já existe uma implementação na árvore que aceita float, usa `ensure_ascii=False` e calcula o hash sem o envelope `{"format":1,"params":...}` — diferenças em relação à proposta. S0 e S1 precisam convergir antes de fixar os vetores: [canonical.py:69](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:69), [canonical.py:116](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:116), [canonical.py:127](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:127).

**TESTES**

Não executei testes, lint ou typecheck nesta revisão em modo OPINIÃO. Os cenários abaixo são critérios propostos, não resultados obtidos.

**MUST-FIX**

1. **Canonicalização não pode arredondar nem depender do contexto Decimal ambiente.**

   `normalize()` aplica arredondamento antes de remover zeros. Com precisão ambiente 3, `Decimal("1.234")` pode virar `"1.23"`; com precisão 28, permanece `"1.234"`. O mesmo parâmetro produziria hashes diferentes, ou parâmetros diferentes colidiriam por arredondamento. Isso é comportamento documentado de [Decimal.normalize](https://docs.python.org/3/library/decimal.html#decimal.Decimal.normalize).

   **Correção:** para Decimal finito, usar `format(value, "f")` e remover zeros **somente da parte fracionária**, tratando zero separadamente. Rejeitar não finitos, floats e chaves não string. Fixar também UTF-8 e o tipo de retorno de `canonical_json`.

   Concordo com incluir o formato no digest. Mas S0 e S1 precisam usar exatamente os mesmos bytes; a identidade durável depende desse hash ([SHADOW-LAB.md:16](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:16)).

2. **Separar fechamento da decisão e fechamento do ATR.**

   **Cenário:** volume avalia às 12:05. Passar esse corte diretamente ao agregador de 15 minutos produz `misaligned`; arredondar para 12:15 introduz futuro. Isso eliminaria duas de cada três avaliações ou causaria look-ahead.

   **Correção:** manter `source_bar_close=12:05`, mas calcular ATR com `atr_bar_close=12:00`, último fechamento de 15 minutos ≤ corte. O `atr_pct` usa o fechamento dessa barra de **15 minutos**, e a evidência registra esse horário. Às 12:15, já usa a barra encerrada às 12:15. O contrato exige ATR de 15 minutos também no volume ([SHADOW-LAB.md:17](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:17)).

3. **Congelar origem, extensão e gate do ATR — a fórmula sozinha não basta.**

   **Cenário:** execução contínua conserva Wilder desde uma origem antiga; bootstrap reinicializa nas últimas 97 barras. Após um pico antigo de volatilidade, os ATRs diferem e podem cair em lados opostos do limite de 5%.

   `bars_needed=max(janelas)` resolve dependências finitas, mas não define a origem de uma recorrência. Minha preferência, pela compatibilidade com M2, é origem recuperável ou checkpoint explícito passado como dado à função pura. Recalcular numa janela móvel também é determinístico **se ambos os caminhos fizerem exatamente isso**, mas precisa ser declarado como política própria, sem alegar equivalência ao Wilder contínuo.

   Há ainda uma divergência documental real: seu mínimo de `period+1` barras entrega a seed; o diálogo M2 acordou um gate adicional, liberando após a atualização pelo 15º TR. Não chame esses comportamentos de idênticos. Fixe separadamente `seed` e primeira leitura elegível ([dialogue-M2.md:111](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:111), [dialogue-M2.md:184](/C:/dev/project-hunter/.claude/state/dialogue-M2.md:184)).

4. **Contexto precisa garantir identidade do mercado e duração das velas.**

   **Cenário:** uma consulta mistura minutos de BTC e ETH sem repetir horários. A sequência proposta passa como crescente e completa, mas gera OHLC agregado de dois ativos.

   Acrescentaria identidade explícita `(exchange, symbol)` e validação de candles, funding e OI contra ela. Também exigiria `close_time == open_time + 1 min`. O modelo atual valida fechamento posterior e alinhamento da abertura, mas não duração exata ([market.py:282](/C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:282)).

   Validaria preços positivos e volumes não negativos na fronteira apropriada: `stop < reference < target` sozinho aceita três preços negativos. Esses campos atualmente não têm tais limites declarados ([market.py:259](/C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:259)).

5. **“Sem decisão” precisa distinguir condição falsa de avaliação indisponível.**

   **Cenário:** episódio termina; próxima avaliação retorna `None` por `gap`; worker interpreta `None` como falso e rearma. Na recuperação, emite outro episódio sem uma condição falsa comprovada. Isso viola o rearme acordado ([SHADOW-LAB.md:14](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:14)).

   **Correção:** acrescentar à `Evaluation` um estado tipado, por exemplo `triggered | not_triggered | unavailable | ineligible`, deixando `reason` como diagnóstico. Apenas `not_triggered`, sobre dados exigidos completos e mercado elegível, serve para rearme. `geometry` também precisa de classificação explícita; não deve virar autorização implícita para rearmar.

6. **Precisão explícita deve envolver toda a aritmética; `frozen` precisa alcançar os dados internos.**

   **Cenário numérico:** soma dos TRs ou multiplicação do ATR arredonda no contexto ambiente antes da divisão controlada. O limiar muda apesar de `Context.divide`. Use `localcontext` com contexto fixado sobre toda a operação, inclusive agregação, retornos, níveis e mediana. A implementação surgida durante a leitura ainda soma e multiplica fora desse contexto ([indicators.py:70](/C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:70)).

   **Cenário de mutação:** depois de produzir a decisão, alguém altera o dicionário de custos e muda o snapshot antes da persistência. `frozen=True` não congela dicionários internos, conforme a [documentação do Pydantic](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability). Prefira modelos congelados tipados para custos e cópias imutáveis dos demais valores consumidos.

**NICE-TO-HAVE**

- Testes de igualdade exata nos limiares e valores imediatamente adjacentes, sob a precisão definida.
- `FeatureEvidence` com unidade, timeframe e início/fim da janela; `window=14` sozinho não identifica a janela.
- Ordenação determinística das evidências e precedência estável dos motivos.
- Para agregação indisponível: intervalo solicitado e primeiro minuto ausente no `detail`, sem preencher barras artificiais.

**O QUE EU FARIA DIFERENTE**

Respondendo aos nove pontos:

1. **`canonical.py`:** aceito formato no digest, JSON compacto, chaves ordenadas, UTC com `Z` e float rejeitado. Retornaria **bytes UTF-8**. Não tentaria interpretar strings numéricas dentro do canonicalizador: `"007"` pode ser um identificador. Parâmetros devem chegar completos e tipados antes do hash; chave ausente e chave com `None` não são automaticamente equivalentes.

2. **`Strategy` / `Evaluation`:** manteria a assinatura exigida pelo brief. `explain()` seria a única implementação da avaliação, e `evaluate()` retornaria `self.explain(ctx, params).decision`. O worker chama **uma vez** `explain()`. Assim não existem dois caminhos de cálculo nem custo duplicado. Acrescentaria o estado do must-fix 5.

3. **Contexto estrito / builder filtrante:** concordo. Builder remove não finais e posteriores, ordena e chama o construtor. Não deve deduplicar silenciosamente nem corrigir velas inválidas. Como o contexto proposto não contém timeframe da estratégia, inclua-o ou deixe claramente essa validação na entrada da avaliação.

   O corte temporal protege contra velas futuras; não prova sozinho que um dado histórico já estava disponível numa decisão passada. Disponibilidade, proveniência e coorte continuam sendo responsabilidades do worker, coerentemente com o envelope acordado ([SHADOW-LAB.md:12](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:12)).

4. **Agregação:** concordo com janela exata e sem redução. `warmup` quando falta o prefixo histórico necessário; `gap` para ausência dentro da cobertura ou no final exigido. Não use apenas contagem total para distinguir os dois.

   As quantidades incluem a barra atual: mediana de 96 anteriores exige **97 barras de 15 minutos**; mediana de 288 anteriores exige **289 barras de 5 minutos**. O volume terá solicitações distintas para sinal e ATR.

5. **Indicadores / âncora:** concordo com `seed_anchor = bars[period].open_time` na convenção em que `bars[0]` fornece apenas o fechamento anterior. Para período 14, é a 15ª barra da sequência e a 14ª que produz TR. Não usaria a primeira barra da janela como `seed_anchor`; chamaria esse outro marco de `seed_window_start`.

   A âncora indica **qual barra** recebeu a seed; a seed só fica disponível no fechamento dessa barra. Mediana zero indisponível, exclusão da atual e retornos em fração estão corretos. Resolveria explicitamente o gate M2 antes do congelamento.

6. **`Decision`:** concordo com os campos e com `decision_at`/`cohort` acrescentados pelo worker. Usaria `Literal` para LONG, `research_only`, formato e timeframes; limites para confidence e horizonte; rejeição explícita de floats na entrada dos campos numéricos.

   Geometria inválida conhecida retorna `Evaluation(..., reason="geometry")` antes de construir a decisão. Não capturaria qualquer `ValidationError` como geometria: isso esconderia erros de timestamp ou envelope.

7. **Escolhas explícitas:**
   
   **(a) Invalidações:** concordo com ambas, como hipóteses congeladas. Níveis fixos da barra de sinal, comparação estrita `<`, avaliação somente em fechamentos posteriores e completos do timeframe indicado.

   Ressalva: a invalidação do momentum **pode** ficar redundante em determinados sinais. Exemplo hipotético: referência 110, ATR 2, stop 107 e rompimento em 100. Fechar abaixo de 100 implica já ter atravessado 107. Eu manteria a regra; apenas não afirmaria independência do stop em todos os casos. A do volume, com barra não degenerada, fica acima da mínima usada como stop.

   **(b) Confidence:** concordo com `Decimal("0.5")` como parâmetro convencional. Gravaria `confidence_method="constant_uncalibrated_v1"` no envelope. O número não significa probabilidade de acerto de 50%; não criaria fórmula baseada em rvol.

8. **Parâmetros / fronteiras:** concordo com `target2_atr`, `target3_atr`, `return_min` e `base_confidence`. Falta tornar explícito o multiplicador do teto do volume, por exemplo `return_max_atr=2`.

   Inclusividade nos limites de ATR e retorno do volume é coerente; momentum permanece estritamente positivo. Mudança de operador depois da ativação exige versão nova, assim como mudança de parâmetro ([SHADOW-LAB.md:11](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:11)).

   Interpretaria “nenhum número hardcoded” como **nenhum parâmetro experimental escondido**. O divisor 2 da média, conversões de unidade e índices não precisam virar knobs.

9. **Schema / verificador no teste:** concordo **apenas como teste de um subconjunto explicitamente limitado**, não como prova geral de conformidade JSON Schema. Rejeite keywords desconhecidas e teste o próprio helper com casos inválidos.

   Fixe qual representação o schema descreve. `Decimal("1.5")` serializado como `"1.5"` é uma string JSON, que não satisfaz `type: number`; limites numéricos não validam strings como números ([JSON Schema — tipos numéricos](https://json-schema.org/understanding-json-schema/reference/numeric)). Um teste que aceita Decimal em memória pode passar enquanto o round-trip falha.

   Eu exigiria o contrato `parâmetros tipados → JSONB → parâmetros tipados → mesmo hash e decisão`. Se o objetivo for anunciar conformidade real com JSON Schema, prefiro uma dependência de teste a manter um validador próprio.

**CONCORDO COM**

Funções puras, Decimal/UTC, janela completa, motivo separado do sinal, referência distinta da entrada, alvos adicionais informativos, isolamento `research_only` e ausência de confidence inventada a partir dos indicadores.

**OBSIDIAN**

- **Strategies** — registrar `evaluate`/`explain`, estados da avaliação e responsabilidades do worker.
- **Features (Feature Engine)** — documentar origem, seed, gate, precisão e fechamento usado no ATR%.
- **Momentum Agent** — acrescentar invalidação pelo rompimento e confidence não calibrada.
- **Volume Agent** — acrescentar invalidação pelo meio da barra e seleção do último fechamento de 15 minutos.
- **Revisões Astra — S1: StrategyContext/Decision** — registrar esta revisão e a resolução dos must-fix, com links para SHADOW e M2.