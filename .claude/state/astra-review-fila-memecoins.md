**RESUMO**

A entrega precisa de correções. **M-A é reparametrizável hoje; M-G é calculável com os dados atuais, mas exige implementar a regra; M-E não recebe funding no caminho atual do worker.** A retirada da T-032 tem justificativa estrutural falsa. Também existe uma via para volume de 24 horas usando as próprias velas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Revisão estática com `Get-Content` e `rg`. Não executei testes, consultas à VPS nem os diagnósticos; portanto, não revalidei os números publicados.

**MUST-FIX**

1. **A restrição estrutural está ampla demais — perguntas 1 e 4.**

   O contexto também contém `exchange`, `symbol` e `source_bar_close`. Ele impede misturar velas de mercados diferentes, mas isso **não impede classificar o próprio mercado**. A estratégia recebe parâmetros arbitrários pelo contrato `Mapping[str, Any]`. Uma lista congelada de símbolos, consultada por `ctx.symbol`, permite implementar “só memes” ou “sem memes” sem ampliar `StrategyContext`. [base.py:112](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:112), [base.py:138](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:138), [base.py:293](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:293).

   **Corrija a justificativa da T-032.** Pode continuar adiada por prioridade, amostra insuficiente e classificação subjetiva; não por impossibilidade técnica. Ausência de diferença detectada também não estabelece equivalência.

   Existe outra via: `NormalizedCandle` contém `quote_volume`, e o repositório efetivamente transporta esse campo. O worker pede, por padrão, 1.560 minutos. Logo, é possível somar `quote_volume` das **1.440 velas finais e contíguas anteriores ao corte**, exigindo valores presentes. Não requer campo novo no contexto. [market.py:252](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:252), [repo.py:95](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:95), [repo.py:122](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:122), [config.py:44](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/config.py:44).

   Essa soma precisa de definição e cobertura próprias; não deve ser apresentada automaticamente como o ticker móvel da exchange. Minha formulação anterior de que **todo** filtro de volume de 24 horas exige mudança de contrato foi excessiva.

   **Cenário de falha:** descartar duas regras implementáveis ou abrir uma expansão desnecessária de interface. Spread, livro e observações contemporâneas de outros mercados continuam ausentes do contexto; uma classificação estática não fornece esses dados.

2. **M-E está disponível no tipo, mas não no worker — pergunta 2.**

   `build_market_context` chama `build_context` sem passar `funding` nem `open_interest`; ambos ficam `None`. O chamador entrega esse contexto diretamente a `strategy.explain`, sem enriquecimento intermediário. [context.py:75](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:75), [base.py:173](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:173), [decide.py:114](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:114).

   O `load_funding` existente atende à **apuração posterior do outcome**, não à decisão de entrada. [settle.py:60](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:60).

   **Cenário de falha:** implementar M-E supondo dado presente; com tratamento rigoroso, tudo vira indisponível; com ausência convertida em zero, o filtro nunca atua.

   Status correto: **calculável pelo contrato, bloqueada pela alimentação do contexto**. O objeto `NormalizedFunding` já prevê `funding_kind`, `next_funding_time`, `mark_price` e `index_price`; não é necessário inventar esses campos. [market.py:295](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:295).

3. **“Funding absoluto como custo simétrico” não descreve corretamente a hipótese.**

   O Lab admite apenas LONG, e sua contabilidade trata funding como transferência **assinada**: positivo é pagamento pelo long; negativo aumenta seu resultado. [base.py:214](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:214), [pricing.py:13](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:13), [pricing.py:79](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:79). Isso corresponde à [documentação da Binance](https://www.binance.com/en/support/faq/detail/360033525031).

   **Cenário de falha:** dois acompanhamentos atravessam funding de +10 e −10 bps. O filtro absoluto elimina ambos e atribui a exclusão a custo, embora um pagasse e o outro recebesse.

   Eu derrubaria **a justificativa de custo simétrico**. A regra pode sobreviver como “exclusão de funding extremo em módulo”, com outra hipótese econômica.

   Sobre estimativa em formação: **não torna a regra intrinsecamente inavaliável**. Com a observação realmente disponível na decisão, pode-se avaliar prospectivamente `abs(rate) > θ`. Entretanto, fase e cadência ausentes misturam estados distintos; não é possível presumir que isso seja apenas ruído aleatório. Também não se pode traduzir a taxa diretamente em custo esperado durante quatro horas. Nunca substituir a estimativa histórica pela taxa liquidada posteriormente.

4. **O efeito pareado do filtro precisa ser separado do efeito da estratégia independente.**

   A M-A promete diferença pareada, mas versões independentes têm slots próprios e transições de rearme. Excluir uma entrada pode liberar uma oportunidade posterior que a base não poderia aproveitar. [decide.py:129](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:129), [decide.py:152](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:152).

   **Cenário de falha:** a base entra às 12h e permanece ocupada; o filtro recusa essa entrada e entra depois. Parear somente sinais coincidentes omite parte do efeito.

   Para a `C-META`, use oportunidades fixadas pela base e avalie aceitação/recusa nessa população. Para versões autônomas, reporte também a mudança de população e rearme. A ressalva está na KB-0057, mas precisa acompanhar a promessa da [M-A no backlog:498](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:498>).

5. **Duas correções anteriores voltaram erradas na consolidação.**

   - “Metade da diferença é cadência” reaparece como fato no [backlog:449](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:449>), enquanto a [KB-0059:59](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento.md:59) reconhece que essa atribuição não foi medida. **Falha:** tratar D-045 como confirmação de uma decomposição causal já estabelecida.
   - T-033 ainda atribui aquecimento de 24h à Volume Anomaly. Ela pede 289 barras de 5m **e** 97 barras completas de 15m para ATR. Portanto, também exige pelo menos 24h15 de buckets de ATR, com possível espera adicional pelo alinhamento. [volume_anomaly_v1.py:122](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:122). **Falha:** esperar avaliação em T+24h e diagnosticar indisponibilidade normal como defeito.

**NICE-TO-HAVE**

**M-G é distinta, não uma distinção inventada.** As grandezas são:

| Regra | Grandeza |
|---|---|
| M-A | `ATRₜ / closeₜ` |
| M-G | `(highₜ − lowₜ) / ATRₜ` |
| `return_max_atr` | Retorno entre fechamentos de 5m comparado ao ATR% de 15m |

As fórmulas atuais estão em [indicators.py:104](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:104), [indicators.py:150](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:150) e [volume_anomaly_v1.py:150](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:150). Máxima e mínima estão disponíveis na agregação. [aggregate.py:40](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:40).

Uma barra pode ter pavios grandes e retorno pequeno. Também pode haver volatilidade persistentemente alta sem uma barra excepcional relativamente ao ATR.

A ressalva é que **o ATR atual inclui a barra atual**. Pela recorrência implementada, `ATRₜ = (13·ATR_anterior + TRₜ)/14`; como `high−low ≤ TR`, a razão da M-G não ultrapassa 14. Um `K ≥ 14` seria inoperante. Usar ATR anterior mede outra coisa e deve ser explicitado como outra definição. [indicators.py:62](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:62), [indicators.py:88](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:88).

**Duplicação — pergunta 3:** não encontrei duplicata exata entre T-001 e T-027.

- M-A é relacionada à T-007, mas altera o **teto**, enquanto T-007 altera o piso.
- M-E difere da T-016 direcional e da T-012 de observação da fase.
- M-G é relacionada à T-002, mas amplitude não é impulso; também não equivale à T-025, que compara ATRs anteriores.

Referências: [Registro:37](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:37>), [Registro:42](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:42>), [Registro:107](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:107>), [Registro:286](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:286>). São contrastes distintos, sem que isso os torne buscas estatisticamente independentes.

**O QUE EU FARIA DIFERENTE**

Para a pergunta 5, minha ordem seria:

1. **D-050 + D-048 primeiro:** reconciliar população, versões, estados e mercados desmonitorados, com `as_of` e `read_at`.
2. **D-042, D-044 e D-049:** podem avançar como diagnósticos descritivos. Em D-042, separar reconstrução com dados hoje disponíveis de recusa operacional comprovada naquela decisão.
3. **D-005 antes ou dentro de D-043:** medir cobertura e idade do spread anterior; ausência de snapshot não pode eliminar silenciosamente as oportunidades mais problemáticas.
4. **D-040 antes de inferência entre coortes:** concentração temporal precisa orientar os blocos de análise.
5. **Antes da M-E:** alimentar e observar funding sem decidir, seguindo D-010; usar D-016/D-045 para exposição e cadência.

D-044 roda hoje **como sensibilidade a custos assumidos**, inclusive usando os spreads publicados como cenários. Isso não equivale a reconstruir spreads executáveis em cada entrada e saída.

Mantenho **D-042 e D-043 antes da M-A**, dado o mecanismo de liquidez proposto. Acrescentaria, antes da M-G, distribuição e retenção incremental sobre os sinais da base.

Na pergunta 6, derrubaria por completo as afirmações de impossibilidade de coorte/volume e a interpretação de M-E como custo simétrico. **Não derrubaria M-A nem M-G.**

**CONCORDO COM**

- Preservar as IDs e registrar correções, sem apagar tentativas.
- Separar spread, profundidade, amplitude e gap do modelo.
- Manter a confirmação em janela futura reservada.
- Não promover “meme” a vantagem econômica com essa amostra.
- Manter o bloco de saídas à frente dessas novas variantes.

**OBSIDIAN**

- **Strategy Backlog:** corrigir capacidades do contexto, status da M-E, justificativa da T-032 e ordem dos diagnósticos.
- **Registro de Tentativas:** acrescentar as correções de T-029, T-031, T-032 e T-033 preservando o histórico.
- **Spread e profundidade — o custo de sair de uma meme:** registrar a alternativa de volume de cotação reconstruído pelas velas.
- **Funding em memes — a cadência antes do sentimento:** separar taxa extrema, custo assinado e disponibilidade na decisão.
- **A coorte de memes não se distingue do resto:** distinguir baixa prioridade de impossibilidade técnica e ausência de diferença de equivalência.
- **Strategies:** atualizar o contrato descrito e distinguir campos aceitos de dados efetivamente alimentados pelo worker.